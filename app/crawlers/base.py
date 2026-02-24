import abc
import asyncio
from typing import List, Optional
from playwright.async_api import Page, BrowserContext
from app.models.deal import Deal
from app.core.logging import logger

class BaseCrawler(abc.ABC):
    def __init__(self, source_name: str, base_url: str):
        self.source_name = source_name
        self.base_url = base_url
        self.seen_ids = set()
    
    @abc.abstractmethod
    async def crawl_list(self, page: Page) -> List[Deal]:
        """Crawl the list of deals from the main page."""
        pass
    
    @abc.abstractmethod
    async def crawl_detail(self, page: Page, deal: Deal) -> Deal:
        """Crawl detailed information for a specific deal."""
        pass
        
    async def process(self, context: BrowserContext):
        page = await context.new_page()
        try:
            logger.info(f"Starting crawl for {self.source_name} at {self.base_url}")
            # Use domcontentloaded to handle slow ad loading
            await page.goto(self.base_url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for list to load
            await page.wait_for_timeout(2000) 
            
            deals = await self.crawl_list(page)
            logger.info(f"Found {len(deals)} items in {self.source_name}")
            
            full_deals = []
            seen_ids = set()
            
            for deal in deals:
                try:
                    if deal.id in seen_ids:
                        continue
                    seen_ids.add(deal.id)
                    
                    # Optimization: Early Filter
                    # We use Processor logic to check if deal should be dropped immediately
                    # This avoids expensive detail page crawling
                    from app.core.processor import Processor
                    if Processor._apply_hard_filter(deal):
                        # If dropped, we still append it but skip detail crawl
                        # Or verify if we want to return dropped items? 
                        # run_once.py expects all items to tally dropped count.
                        full_deals.append(deal)
                        continue

                    # Logic to skip if already exists would go here
                    detailed_deal = await self.crawl_detail(page, deal)
                    full_deals.append(detailed_deal)
                    # Politeness delay
                    await page.wait_for_timeout(1000)
                except Exception as e:
                    logger.error(f"Error processing detail for {deal.link}: {e}")
            
            return full_deals
            
        except Exception as e:
            logger.error(f"Error crawling {self.source_name}: {e}")
            return []
        finally:
            await page.close()
