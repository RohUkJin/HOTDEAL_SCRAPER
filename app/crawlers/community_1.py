from typing import List, Optional
from datetime import datetime, timedelta
import re
from playwright.async_api import Page
from bs4 import BeautifulSoup
from app.crawlers.base import BaseCrawler
from app.models.deal import Deal
from app.core.logging import logger

class PpomppuCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="Ppomppu", base_url="https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu")

    async def crawl_list(self, page: Page) -> List[Deal]:
        all_deals = []
        page_num = 1
        max_pages = 20  # Safety limit
        today = datetime.now().date()
        stop_crawling = False

        while page_num <= max_pages and not stop_crawling:
            logger.info(f"Crawling Ppomppu page {page_num}...")
            # Navigate to specific page
            url = f"{self.base_url}&page={page_num}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.error(f"Failed to load Ppomppu page {page_num}: {e}")
                break

            # Use more specific selector for rows
            rows = await page.locator("tr.baseList:not(.bbs_notice)").all()
            if not rows:
                logger.info("No more rows found.")
                break
            
            logger.info(f"Detected {len(rows)} deal rows on page {page_num}")
            
            page_deals = []
            for i, row in enumerate(rows):
                try:
                    # Title & Link
                    title_el = row.locator(".baseList-title")
                    if not await title_el.count():
                        continue
                    
                    title = await title_el.inner_text()
                    link_el = row.locator("a.baseList-title")
                    link = await link_el.get_attribute("href")
                    
                    if not link:
                        continue
    
                    # Normalize link
                    if not link.startswith("http"):
                        if link.startswith("/"):
                            link = f"https://www.ppomppu.co.kr{link}"
                        else:
                            link = f"https://www.ppomppu.co.kr/zboard/{link}"
                    
                    deal_id_match = re.search(r"no=(\d+)", link)
                    deal_id = deal_id_match.group(1) if deal_id_match else link
    
                    if deal_id in self.seen_ids:
                        continue
                    # Just add to seen here to avoid duplicates across pages if any
                    self.seen_ids.add(deal_id)
    
                    # Date
                    date_el = row.locator("td:nth-child(4)")
                    date_text = await date_el.get_attribute("title")
                    if not date_text:
                         date_text = await date_el.inner_text()
                    posted_at = self._parse_date(date_text.strip())
                    
                    # Stop Condition: If deal is older than 24 hours
                    # This ensures we catch everything since the last run (if daily) or cover gaps
                    cutoff_time = datetime.now() - timedelta(hours=24)
                    
                    if posted_at < cutoff_time:
                        stop_crawling = True
                        logger.info(f"Found deal from {posted_at}, older than 24h. Stopping pagination.")
                        break

                    # Votes
                    vote_el = row.locator("td:nth-child(5)")
                    vote_text = await vote_el.inner_text()
                    votes = self._parse_votes(vote_text)
                    
                    # Comment Count (Optimization: Get from list)
                    comment_el = row.locator("span.baseList-c")
                    comment_count = 0
                    if await comment_el.count():
                        c_text = await comment_el.inner_text()
                        if c_text.isdigit():
                            comment_count = int(c_text)
    
                    deal = Deal(
                        id=deal_id,
                        source=self.source_name,
                        title=title.strip(),
                        link=link,
                        posted_at=posted_at,
                        votes=votes,
                        comment_count=comment_count 
                    )
                    page_deals.append(deal)
                    
                except Exception as e:
                    logger.error(f"Row {i} Error: {e}")
                    continue
            
            all_deals.extend(page_deals)
            if stop_crawling:
                break
                
            page_num += 1
            await page.wait_for_timeout(1000) # Politeness delay
                
        return all_deals

    async def crawl_detail(self, page: Page, deal: Deal) -> Deal:
        try:
            await page.goto(deal.link, wait_until="domcontentloaded", timeout=60000)
            
            # 1. Extract Actual Product Link
            product_link_el = page.locator(".topTitle-link.partner a").first
            if not await product_link_el.count():
                 product_link_el = page.locator("div.wordfix a").first
            
            raw_link = None
            if await product_link_el.count():
                raw_link = await product_link_el.get_attribute("href")
                # Also try link text if it looks like a URL
                link_text = await product_link_el.inner_text()
                if link_text.startswith("http") and not raw_link:
                     deal.link = link_text.strip()

            # Decode Ppomppu Redirect (s.ppomppu.co.kr)
            if raw_link and "s.ppomppu.co.kr" in raw_link:
                try:
                    from urllib.parse import urlparse, parse_qs
                    import base64
                    
                    parsed = urlparse(raw_link)
                    qs = parse_qs(parsed.query)
                    if 'target' in qs:
                        target_b64 = qs['target'][0]
                        # Padding check
                        missing_padding = len(target_b64) % 4
                        if missing_padding:
                            target_b64 += '='* (4 - missing_padding)
                        
                        decoded_bytes = base64.b64decode(target_b64)
                        deal.link = decoded_bytes.decode('utf-8')
                    else:
                         deal.link = raw_link 
                except Exception as e:
                    logger.warning(f"Failed to decode Ppomppu link: {e}")
                    deal.link = raw_link
            elif raw_link:
                 deal.link = raw_link

            # 2. Extract Comment Contents
            comments_els = await page.locator(".over_hide.link-point.mid-text-area").all()
            deal.comments = []
            for i, c_el in enumerate(comments_els[:15]):
                text = await c_el.inner_text()
                if text.strip():
                    deal.comments.append(text.strip())
            
            # 3. Image
            # Try to find content area first
            content_el = page.locator(".board-contents").or_(page.locator(".view_content")).first
            if await content_el.count():
                img_el = await page.query_selector(".board-contents img") # Corrected from detail_page to page
            if img_el:
                pass # Image extracted but unused
                
        except Exception as e:
            logger.error(f"Error crawling detail for {deal.link}: {e}")
            
        return deal

    def _parse_date(self, date_text: str) -> datetime:
        # Ppomppu date format: usually YY.MM.DD HH:MM:SS in title attribute
        # Or often just HH:mm for today, YY.MM.DD for past
        try:
             # Basic handling
             if re.match(r"\d{2}:\d{2}:\d{2}", date_text): # HH:MM:SS
                 now = datetime.now()
                 time_part = datetime.strptime(date_text, "%H:%M:%S").time()
                 return datetime.combine(now.date(), time_part)
             elif re.match(r"\d{2}\.\d{2}\.\d{2}", date_text): # YY.MM.DD
                 return datetime.strptime(date_text, "%y.%m.%d")
             else:
                 return datetime.now() # Fallback
        except:
            return datetime.now()

    def _parse_votes(self, vote_text: str) -> int:
        # Format: "54 - 0"
        try:
            parts = vote_text.split("-")
            if len(parts) >= 1:
                return int(parts[0].strip())
            return 0
        except:
            return 0
