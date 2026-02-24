from typing import List
from datetime import datetime, timedelta
import re
from playwright.async_api import Page
from app.crawlers.base import BaseCrawler
from app.models.deal import Deal
from app.core.logging import logger
from app.core.processor import Processor
import re
from urllib.parse import unquote

class ArcaCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="Arca", base_url="https://arca.live/b/hotdeal")

    async def crawl_list(self, page: Page) -> List[Deal]:
        all_deals = []
        page_num = 1
        max_pages = 20
        today = datetime.now().date()
        stop_crawling = False

        while page_num <= max_pages and not stop_crawling:
            logger.info(f"Crawling Arca page {page_num}...")
            url = f"{self.base_url}?p={page_num}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.error(f"Failed to load Arca page {page_num}: {e}")
                break

            # Arca uses 'vrow hybrid' for list items
            rows = await page.locator("div.vrow.hybrid:not(.notice)").all()
            if not rows:
                 break
                 
            logger.info(f"Detected {len(rows)} deal rows in Arca page {page_num}")
            
            page_deals = []
            for i, row in enumerate(rows):
                try:
                    # Title & Link (Internal)
                    title_el = row.locator(".title.hybrid-title")
                    if not await title_el.count():
                        continue
                    
                    # Title Text
                    text = await title_el.inner_text()
                    title = re.sub(r"\s*\[\d+\]\s*$", "", text).strip()
                    
                    link = await title_el.get_attribute("href")
                    
                    # ID
                    deal_id = link.split('/')[-1].split('?')[0] if link else f"arca_{i}"
    
                    # Price (Try multiple selectors)
                    price = None
                    # .deal-price OR .hybrid-title span OR hybrid-bottom
                    price_el = row.locator(".deal-price").or_(row.locator(".hybrid-bottom span")).first
                    if await price_el.count():
                        price = await price_el.inner_text()
                        price = price.strip()
                    
                    # Comment Count
                    comment_count = 0
                    comment_el = row.locator(".comment-count")
                    if await comment_el.count():
                        c_text = await comment_el.inner_text()
                        # format "[10]" or "10"
                        c_text = re.sub(r"[\[\]]", "", c_text)
                        if c_text.isdigit():
                            comment_count = int(c_text)
    
                    # Votes / Recommendations
                    votes = 0
                    vote_el = row.locator(".col-rate")
                    if await vote_el.count():
                        v_text = await vote_el.inner_text()
                        if v_text.isdigit():
                            votes = int(v_text)
                    
                    # Date
                    date_el = row.locator("time")
                    posted_at = None
                    if await date_el.count():
                        # Arca uses datetime attribute for precision
                        iso_time = await date_el.get_attribute("datetime")
                        if iso_time:
                            # format: 2024-01-21T06:00:00+09:00
                            try:
                                posted_at = datetime.fromisoformat(iso_time)
                            except:
                                pass
                    
                    if not posted_at:
                        posted_at = self._parse_date("0분 전") # Fallback
                        
                    if not posted_at:
                        posted_at = self._parse_date("0분 전") # Fallback
                        
                    # Stop Condition: If deal is older than 24 hours
                    cutoff_time = datetime.now() - timedelta(hours=24)
                    
                    if posted_at < cutoff_time:
                        stop_crawling = True
                        logger.info(f"Found deal from {posted_at}, older than 24h. Stopping pagination.")
                        break
    
                    deal = Deal(
                        id=deal_id,
                        source=self.source_name,
                        title=title,
                        link=link, # Internal link first
                        image_url=None,
                        posted_at=posted_at,
                        votes=votes,
                        comment_count=comment_count,
                        discount_price=price
                    )
                    
                    # Early Filter
                    if Processor._apply_hard_filter(deal):
                        continue
                        
                    page_deals.append(deal)
                    
                except Exception as e:
                    logger.error(f"Arca Row {i} Error: {e}")
            
            all_deals.extend(page_deals)
            if stop_crawling:
                break
            
            page_num += 1
            await page.wait_for_timeout(1000)
                
        return all_deals

    async def crawl_detail(self, page: Page, deal: Deal) -> Deal:
        try:
            # Handle relative links before navigation
            if deal.link.startswith("/"):
                deal.link = f"https://arca.live{deal.link}"
                
            await page.goto(deal.link, wait_until="domcontentloaded", timeout=60000)
            
            # 1. Extract Real Product Link
            # Selector: a.external
            link_el = page.locator("a.external").first
            if await link_el.count():
                raw_link = await link_el.get_attribute("href")
                
                # Handle 'unsafelink.com' redirect
                # Format: https://unsafelink.com/https://...
                if raw_link and "unsafelink.com" in raw_link:
                    # Remove the prefix
                    clean_link = raw_link.split("unsafelink.com/")[-1]
                    # Sometimes it leaves a leading slash or http doubling
                    if not clean_link.startswith("http"):
                         clean_link = "http" + clean_link # rough fix if needed but usually exact match
                    # Often it is just appending the url
                    deal.link = clean_link
                else:
                    deal.link = raw_link if raw_link else deal.link
            
            # 2. Extract Comment Contents
            # Selector: .comment-item .text
            comments_els = await page.locator(".comment-item .text").all()
            deal.comments = []
            for c_el in comments_els[:15]:
                text = await c_el.inner_text()
                if text.strip():
                     deal.comments.append(text.strip())

            # Image
            img_el = page.locator(".article-content img").first
            if await img_el.count():
                deal.image_url = await img_el.get_attribute("src")

        except Exception as e:
            logger.error(f"Error checking detail for {deal.title}: {e}")

        return deal

    def _parse_date(self, date_text: str) -> datetime:
        # Arca: YYYY-MM-DD HH:MM:SS or similar in <time> tag
        # But here we get inner_text mostly like "2024.01.21 15:30" or "1 mins ago"
        try:
           # If using <time> tag it's usually ISO
           # If text:
           date_text = date_text.strip()
           if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", date_text):
               return datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S")
           if re.match(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}", date_text):
               return datetime.strptime(date_text, "%Y.%m.%d %H:%M")
           return datetime.now()
        except:
           return datetime.now()
