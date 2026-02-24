import re
import json
import hashlib
import os
from datetime import datetime
from typing import Dict, Optional
from app.models.deal import Deal
from app.core.logging import logger

CACHE_FILE = "cache.json"

class Processor:
    # Hard Filter Keywords (Immediate Drop)
    DROP_KEYWORDS = ["종료", "품절", "매진", "취소", "광고", "제휴", "체험단"]
    
    # Soft Score Keywords
    HIGH_DISCOUNT_KEYWORDS = ["역대", "대박", "오류", "무배", "무료배송"]
    POSITIVE_KEYWORDS = ["추천", "강추", "필구", "탑승"]
    NEGATIVE_KEYWORDS = ["업자", "바이럴", "망설", "비쌈"]
    
    _cache: Dict[str, dict] = {}
    _cache_loaded = False

    @staticmethod
    def _load_cache():
        if Processor._cache_loaded:
            return
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    Processor._cache = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
        Processor._cache_loaded = True

    @staticmethod
    def _save_cache():
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(Processor._cache, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    @staticmethod
    def _get_cache_key(deal: Deal) -> str:
        # Hash(title + link) - assume price is part of title or dynamic
        raw = f"{deal.title}{deal.link}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    @staticmethod
    def check_cache(deal: Deal) -> bool:
        """Checks cache for existing result. Updates deal if found. Returns True if hit."""
        Processor._load_cache()
        key = Processor._get_cache_key(deal)
        
        if key in Processor._cache:
            cached = Processor._cache[key]
            
            # Date Check: Expire if not crawled today
            crawled_at = cached.get("crawled_at")
            today = datetime.now().date().isoformat()
            
            if crawled_at != today:
                # Cache expired or from different day -> Treat as miss
                return False
                
            deal.is_hotdeal = cached.get("is_hotdeal")
            # why_hotdeal removed
            deal.category = cached.get("category")
            deal.savings = cached.get("savings", 0) # Restore savings if available
            
            if deal.is_hotdeal:
                deal.status = "HOT (Cached)"
            else:
                deal.status = "DROP (Cached)"
            return True
        return False

    @staticmethod
    def update_cache(deal: Deal):
        """Updates cache with deal analysis result."""
        Processor._load_cache()
        key = Processor._get_cache_key(deal)
        Processor._cache[key] = {
            "is_hotdeal": deal.is_hotdeal,
            "category": deal.category,
            "savings": deal.savings, # Cache savings for stats
            "crawled_at": datetime.now().date().isoformat()
        }
        Processor._save_cache()

    @staticmethod
    def _calculate_velocity(deal: Deal) -> float:
        """
        Calculate reaction velocity score.
        V = (C + 1) / (T + 10)^1.5
        T is minutes since posted.
        """
        now = datetime.now()
        # Handle naive/aware datetime
        if deal.posted_at.tzinfo is None:
             delta = now - deal.posted_at
        else:
             delta = now.astimezone() - deal.posted_at.astimezone()
             
        minutes_elapsed = max(0, delta.total_seconds() / 60)
        
        velocity = (deal.comment_count + 1) / ((minutes_elapsed + 10) ** 1.5)
        return velocity * 100 # Scale up for readability (e.g., 0.05 -> 5.0)

    @staticmethod
    async def process_deal(deal: Deal) -> Deal:
        """
        Apply Hard Filter -> Soft Filter (Scoring) -> Threshold Check
        Note: Changed to async to support Naver API call
        """
        # 0. Check Cache (Optimization)
        # Note: We usually cache FINAL analysis result. 
        # But if it was dropped by filter previously, maybe we don't cache that?
        # The user plan says: "Result: Classification only and cache for reuse".
        # So we cache Analysis results.
        # Filter drops are fast, so maybe not strictly needed to cache, but Analysis is expensive.
        
        # 1. Hard Filter
        if Processor._apply_hard_filter(deal):
            return deal # Status is DROP
            
        # 2. Soft Scoring (and Naver Price Check)
        await Processor._calculate_soft_score(deal)
        
        # Check if dropped during soft scoring (e.g. expensive)
        if deal.status == "DROP":
             return deal
        
        # 3. Threshold Check (e.g., Score >= 0 to pass to LLM)
        if deal.score < 0:
            deal.status = "DROP"
            deal.reason = f"Low Score: {deal.score}"
            logger.info(f"Dropped {deal.title} (Low Score: {deal.score})")
        else:
            deal.status = "READY"
            
        return deal

    @staticmethod
    def normalize_price_text(text: str) -> Optional[str]:
        """
        Normalize price text to pure integer string (KRW).
        - '1,000원' -> '1000'
        - '$10' -> '14500' (Rate: 1450)
        - '10달러' -> '14500'
        """
        if not text:
            return None
            
        text = text.strip()
        
        # 1. USD Conversion (Rate 1450)
        # Pattern: $10, 10.5달러, $ 10
        usd_pattern = re.search(r"(?:\$|달러)\s*(\d+(?:\.\d+)?)", text)
        if not usd_pattern:
             # Try suffix style '10달러' but allow spacing
             usd_pattern = re.search(r"(\d+(?:\.\d+)?)\s*(?:달러|\$)", text)
             
        if usd_pattern:
            try:
                val = float(usd_pattern.group(1))
                krw = int(val * 1450)
                return str(krw)
            except:
                pass
                
        # 2. KRW Cleaning
        # Extract number before '원' or just numbers if it looks like price
        # Pattern: 1,000원 or 1000
        # Remove non-digits except maybe dots if mixed (but usually KRW is int)
        clean = re.sub(r"[^\d]", "", text)
        if clean:
            return clean
            
        return None

    @staticmethod
    def clean_title_for_search(title: str) -> str:
        """Removes marketing terms in brackets/parentheses at the beginning for Naver search."""
        import re
        # Remove any prefix combinations of (), [], {}, <>
        clean = re.sub(r"^(\s*[\[\(<\{][^\]\)>\}]+[\]\)>\}])+\s*", "", title)
        return clean.strip() or title

    @staticmethod
    def extract_quantity(text: str) -> int:
        """Extracts total quantity from title like '12병', '30롤 2팩'."""
        import re
        pattern = r"(\d+)\s*(병|롤|팩|개|매|캔|정|포|구|박스|봉|입|페트|pet|번|묶음|포기)"
        matches = re.findall(pattern, text.lower())
        
        if not matches:
            return 1
            
        total_qty = 1
        for match in matches:
            qty = int(match[0])
            total_qty *= qty
            
        return min(total_qty, 10000)

    @staticmethod
    def _apply_hard_filter(deal: Deal) -> bool:
        """Returns True if deal should be DROPPED"""
        
        # 1. Keywords
        for kw in Processor.DROP_KEYWORDS:
            if kw in deal.title:
                deal.status = "DROP"
                deal.reason = f"Keyword: {kw}"
                logger.info(f"Dropped {deal.title} ({deal.reason})")
                return True
                
        # 1.5 Self-Referencing Link Check (Generic) - REMOVED (Causes early drop before detail crawl)
        # self_ref_map = {
        #     "Ppomppu": "ppomppu.co.kr",
        #     "FMKorea": "fmkorea.com",
        #     "Arca": "arca.live"
        # }
        
        # target_domain = self_ref_map.get(deal.source)
        # if target_domain and target_domain in deal.link:
        #     deal.status = "DROP"
        #     deal.reason = f"Self-Referencing Link ({target_domain})"
        #     logger.info(f"Dropped {deal.title} ({deal.reason})")
        #     return True
                
        # 2. Comment Count (< 3) WITH Time Decay Exception
        # Exception: Created < 30 mins ago AND Comments >= 1 -> Keep (PENDING/READY)
        now = datetime.now()
        if deal.posted_at.tzinfo is None:
             delta = now - deal.posted_at
        else:
             delta = now.astimezone() - deal.posted_at.astimezone()
        minutes_elapsed = delta.total_seconds() / 60
        
        if deal.comment_count < 3:
            if minutes_elapsed < 30 and deal.comment_count >= 1:
                logger.info(f"kept fresh deal {deal.title} (Time: {int(minutes_elapsed)}m, Comments: {deal.comment_count})")
                # Don't drop, proceed to scoring
            else:
                deal.status = "DROP"
                deal.reason = f"Low Comments: {deal.comment_count}"
                logger.info(f"Dropped {deal.title} ({deal.reason})")
                return True
            
        # 3. Price Pattern Check & Normalization
        # Try to extract price from Title if not already found by crawler
        if not deal.discount_price:
             price_match = re.search(r"(\d{1,3}(?:,\d{3})*)원", deal.title)
             if price_match:
                 deal.discount_price = price_match.group(1) # Send to normalizer later
             else:
                 usd_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:달러|\$)", deal.title) or re.search(r"(?:\$)\s*(\d+(?:\.\d+)?)", deal.title)
                 if usd_match:
                     deal.discount_price = usd_match.group(0) # Send whole match
        
        # Use new normalization logic
        normalized = Processor.normalize_price_text(deal.discount_price)
        
        if normalized:
             deal.discount_price = normalized
        else:
             # No price found even after parsing attempt
             # Check distinct price hint in title (e.g. just raw number?) No, risky.
             # Fallback: check if title has explicit price-like chars as fallback to avoid dropping
             has_price_in_title = re.search(r"\d+(원|%|달러|\$)", deal.title)
             if not has_price_in_title:
                 deal.status = "DROP"
                 deal.reason = "No Price Found"
                 logger.info(f"Dropped {deal.title} ({deal.reason})")
                 return True

        return False

    @staticmethod
    async def _calculate_soft_score(deal: Deal):
        score = 0.0
        
        # +2: Price explicit (Parsed or in title)
        if deal.discount_price:
            score += 2
            
        # +2: High Discount Keywords
        for kw in Processor.HIGH_DISCOUNT_KEYWORDS:
            if kw in deal.title:
                score += 2
                break # Count once
                
        # +1: Comments >= 10
        if deal.comment_count >= 10:
            score += 1
            
        # +1: Positive Keywords
        for kw in Processor.POSITIVE_KEYWORDS:
            if kw in deal.title:
                score += 1
                break
                
        # -3: Negative/Ad Keywords
        for kw in Processor.NEGATIVE_KEYWORDS:
            if kw in deal.title:
                score -= 3
        
        # Velocity Bonus
        velocity = Processor._calculate_velocity(deal)
        if velocity > 0.5: # Arbitrary threshold for "fast" reaction
             score += 1
        
        # Naver Price Comparison
        try:
            from app.services.naver import NaverSearchService
            
            # Extract numeric price from deal if possible
            deal_price = None
            if deal.discount_price:
                # Remove non-numeric chars
                price_str = re.sub(r"[^\d]", "", deal.discount_price)
                if price_str:
                    deal_price = int(price_str)
            
            if deal_price:
                # 1. Clean Title for Search
                search_query = Processor.clean_title_for_search(deal.title)
                
                naver_result = await NaverSearchService.search_lowest_price(search_query)
                if naver_result:
                    naver_price = naver_result["price"]
                    naver_title = naver_result["title"]
                    deal.naver_price = naver_price # Store for LLM context
                    
                    # 2. Extract Quantities
                    deal_qty = Processor.extract_quantity(deal.title)
                    naver_qty = Processor.extract_quantity(naver_title)
                    
                    # 3. Consider Shipping Fees
                    deal_shipping = 0 if any(kw in deal.title for kw in ("무배", "무료배송", "배송비 무료")) else 3000
                    naver_shipping = 3000
                    
                    total_deal_cost = deal_price + deal_shipping
                    total_naver_cost = naver_price + naver_shipping
                    
                    # 4. Calculate Unit Prices
                    deal_unit_price = total_deal_cost / deal_qty
                    naver_unit_price = total_naver_cost / naver_qty
                    
                    # 5. Strict Filter: Drop if expensive per unit
                    if deal_unit_price > naver_unit_price:
                         deal.status = "DROP"
                         deal.reason = f"Expensive than Naver Unit Price ({deal_unit_price:.1f} > {naver_unit_price:.1f})"
                         logger.info(f"Dropped {deal.title} ({deal.reason})")
                         return # Stop scoring
                    
                    # 6. Calculate Savings
                    deal.savings = int((naver_unit_price - deal_unit_price) * deal_qty)
                    
                    ratio = deal_unit_price / naver_unit_price
                    # Bonus 1: Ratio
                    if ratio < 0.85: # 15% cheaper
                        score += 3
                        logger.info(f"Naver Price Bonus for {deal.title}: {deal_unit_price:.1f} vs {naver_unit_price:.1f} ({ratio:.2f}) -> +3")
                    elif ratio < 0.90: # 10% cheaper
                        score += 2
                        logger.info(f"Naver Price Bonus for {deal.title}: {deal_unit_price:.1f} vs {naver_unit_price:.1f} ({ratio:.2f}) -> +2")
                    
                    # Bonus 2: Total Savings amount
                    if deal.savings > 30000:
                        score += 2
                        logger.info(f"Naver Huge Savings Bonus for {deal.title}: {deal.savings} KRW -> +2")
        except Exception as e:
            logger.warning(f"Naver check failed: {e}")
                
        deal.score = score
        logger.debug(f"Scored {deal.title}: {score}")
