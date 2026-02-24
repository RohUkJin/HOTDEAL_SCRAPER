from typing import List
from datetime import datetime, timedelta
from playwright.async_api import Page
from bs4 import BeautifulSoup
from app.crawlers.base import BaseCrawler
from app.models.deal import Deal
from app.core.logging import logger
from app.core.processor import Processor
import re
from urllib.parse import unquote, parse_qs, urlparse

class FMKoreaCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="FMKorea", base_url="https://www.fmkorea.com/hotdeal")

    async def crawl_list(self, page: Page) -> List[Deal]:
        all_deals = []
        page_num = 1
        max_pages = 20
        today = datetime.now().date()
        stop_crawling = False

        while page_num <= max_pages and not stop_crawling:
            logger.info(f"Crawling FMKorea page {page_num}...")
            url = f"{self.base_url}?page={page_num}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.error(f"Failed to load FMKorea page {page_num}: {e}")
                break

            # FMKorea Hotdeal usually uses table layout .bd_lst tr
            # Exclude notices
            rows = await page.locator("tr:not(.notice):not(.ub-content)").all() 
            # Note: .ub-content might be ad row, just safely checking tr inside .bd_lst is better potentially
            # Let's try consistent selector
            if len(rows) < 5:
                 # Fallback to .li if mobile view or different layout
                 rows = await page.locator("li.li:not(.notice)").all()
            
            logger.info(f"Detected {len(rows)} deal rows in FMKorea page {page_num}")
    
            page_deals = []
            for i, row in enumerate(rows):
                try:
                    # Title & Link
                    # Title usually in .title a or h3.title a
                    title_el = row.locator(".title a").last # often distinct 'category' link then 'title' link
                    # Or specifically select the one with text
                    if not await title_el.count():
                         title_el = row.locator("h3.title a")
                    
                    if not await title_el.count():
                        continue
    
                    text = await title_el.inner_text()
                    # Remove comment count in title if present [12]
                    title = re.sub(r"\s*\[\d+\]\s*$", "", text).strip()
                    
                    link = await title_el.get_attribute("href") # Relative usually /12345
                    
                    # ID
                    deal_id = f"fmkorea_{link.split('/')[-1]}" if link else f"fmk_{i}"
                    
                    # Date
                    # usually .regdate
                    date_el = row.locator(".regdate").first
                    posted_at = None
                    if await date_el.count():
                        date_text = await date_el.inner_text()
                        posted_at = self._parse_date(date_text)
                    else:
                        posted_at = self._parse_date("0분 전")

                    # Stop Condition: If deal is older than 24 hours
                    cutoff_time = datetime.now() - timedelta(hours=24)

                    if posted_at < cutoff_time:
                        stop_crawling = True
                        logger.info(f"Found deal from {posted_at}, older than 24h. Stopping pagination.")
                        break

                    # Price
                    # .hotdeal_info contains spans or strong tags
                    price = None
                    # Usually: 쇼핑몰 / 가격 / 배송
                    # Selector: .hotdeal_info span:nth-child(2) or similar
                    info_el = row.locator(".hotdeal_info")
                    if await info_el.count():
                        # get text "쇼핑몰 / 10,000원 / 무배"
                        info_text = await info_el.inner_text()
                        parts = info_text.split('/')
                        if len(parts) >= 2:
                            price = parts[1].strip()
                    
                    # Comment Count
                    comment_count = 0
                    comment_el = row.locator(".comment_count") # usually inside title anchor or after
                    if await comment_el.count():
                        c_text = await comment_el.inner_text()
                        c_text = re.sub(r"[\[\]]", "", c_text)
                        if c_text.isdigit():
                            comment_count = int(c_text)
                    
                    # Votes
                    votes = 0
                    # .pc_voted_count .count OR .m_voted_count
                    vote_el = row.locator(".pc_voted_count .count").first
                    if not await vote_el.count():
                         vote_el = row.locator(".m_voted_count").first
                    
                    if await vote_el.count():
                        v_text = await vote_el.inner_text()
                        if v_text.strip().isdigit():
                            votes = int(v_text.strip())
    
                    deal = Deal(
                        id=deal_id,
                        source=self.source_name,
                        title=title,
                        link=link,
                        image_url=None,
                        posted_at=posted_at,
                        votes=votes,
                        comment_count=comment_count,
                        discount_price=price
                    )
                    
                    if Processor._apply_hard_filter(deal):
                        continue
                        
                    page_deals.append(deal)
    
                except Exception as e:
                    logger.error(f"FMKorea Row {i} Error: {e}")

            all_deals.extend(page_deals)
            if stop_crawling:
                break
                
            page_num += 1
            await page.wait_for_timeout(1000)
            
        return all_deals

    async def crawl_detail(self, page: Page, deal: Deal) -> Deal:
        # ... (existing crawl_detail) ...
        try:
            # Handle relative links before navigation
            if deal.link.startswith("/"):
                deal.link = f"https://www.fmkorea.com{deal.link}"
                
            await page.goto(deal.link, wait_until="domcontentloaded", timeout=60000)
            
            # 1. Extract Real Product Link
            # Selector: tr inside .xu checking for '링크' label or just .hotdeal_url
            link_el = page.locator("a.hotdeal_url").first
            
            if await link_el.count():
                raw_link = await link_el.get_attribute("href")
                
                # https://link.fmkorea.org/link.php?url=...
                if raw_link and "link.fmkorea.org" in raw_link:
                     try:
                         # It is usually parse_qs
                         from urllib.parse import urlparse, parse_qs, unquote
                         parsed = urlparse(raw_link)
                         qs = parse_qs(parsed.query)
                         if 'url' in qs:
                             target = qs['url'][0]
                             deal.link = unquote(target)
                         else:
                             deal.link = raw_link
                     except:
                         deal.link = raw_link
                else:
                     deal.link = raw_link if raw_link else deal.link
            
            # 2. Extract Comment Contents
            comments_els = await page.locator(".comment-content .xe_content").all()
            deal.comments = []
            for c_el in comments_els[:15]:
                text = await c_el.inner_text()
                if text.strip():
                    deal.comments.append(text.strip())
            
            # Image
            content_el = page.locator(".xe_content").first
            if await content_el.count():
                img_el = content_el.locator("img").first
                if await img_el.count():
                     deal.image_url = await img_el.get_attribute("src")

        except Exception as e:
            logger.error(f"Error checking detail for {deal.title}: {e}")

        return deal

    def _parse_date(self, date_text: str) -> datetime:
        # FMKorea: YYYY.MM.DD or HH:MM
        try:
            date_text = date_text.strip()
            if re.match(r"\d{2}:\d{2}", date_text):
                now = datetime.now()
                time_part = datetime.strptime(date_text, "%H:%M").time()
                return datetime.combine(now.date(), time_part)
            elif re.match(r"\d{4}\.\d{2}\.\d{2}", date_text):
                return datetime.strptime(date_text, "%Y.%m.%d")
            else:
                return datetime.now()
        except:
             return datetime.now()
