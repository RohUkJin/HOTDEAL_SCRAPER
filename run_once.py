import asyncio
import logging
from playwright.async_api import async_playwright
from app.crawlers.community_1 import PpomppuCrawler
from app.crawlers.community_3 import ArcaCrawler
from app.crawlers.community_2 import FMKoreaCrawler
from app.core.processor import Processor
from app.core.analyzer import Analyzer
from app.core.database import db
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ai_hotdeal")

async def run_pipeline():
    logger.info("🚀 Starting optimized batch crawl...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a single context for all crawlers for efficiency, or separate if needed
        context = await browser.new_context(user_agent=settings.USER_AGENT)
        
        # 1. Crawl All Sources
        # 크롤러 구성: 어떤 사이트를 순회할지 여기서 정의
        crawlers = [
            PpomppuCrawler(),
            ArcaCrawler(),
            FMKoreaCrawler()
        ]
        
        all_deals = []
        
        # Track cached items for stats
        cached_hotdeal_count = 0
        cached_savings = 0

        
        # 크롤러 실행: 각 크롤러가 실제로 목록/상세를 수집하는 구간
        for crawler in crawlers:
            try:
                logger.info(f"🕷️ Crawling {crawler.source_name}...")
                # 크롤링 시작점: process 내부에서 crawl_list -> crawl_detail로 이어짐
                deals = await crawler.process(context) # 'process' calls internal crawl_list -> crawl_detail
                all_deals.extend(deals)
                logger.info(f"   Collected {len(deals)} items from {crawler.source_name}.")
            except Exception as e:
                logger.error(f"Error crawling {crawler.source_name}: {e}")

        logger.info(f"🔍 Applying Filters & Scoring on total {len(all_deals)} items...")
        
        ready_deals = []
        dropped_count = 0
        
        for deal in all_deals:
            # Check Cache first
            if Processor.check_cache(deal):
                 if deal.is_hotdeal:
                      print(f"   [{deal.status}] {deal.title} (Cached)")
                      cached_hotdeal_count += 1
                      if deal.savings:
                           cached_savings += deal.savings
                 continue

            processed_deal = await Processor.process_deal(deal)
            
            if processed_deal.status == "READY":
                print(f"   [READY] {deal.title} (Score: {deal.score})")
                ready_deals.append(processed_deal)
            else:
                 dropped_count += 1
                 
        logger.info(f"   -> {len(ready_deals)} items to analyze, {dropped_count} dropped/cached.")
        
        if not ready_deals:
            print("No items to analyze.")
            return

        print(f"🧠 Analyzing batch of {len(ready_deals)} items...")
        # LLM 분석기 생성: 이 지점부터 LLM 판단 로직이 준비됨
        analyzer = Analyzer()
        # LLM 개입 지점: ready_deals를 LLM이 실제로 분석/판단하는 호출
        results = analyzer.analyze_batch(ready_deals)
        
        print("\n" + "="*50)
        print(f"🎉 Final Result: {len(results)} Hot Deals Found")
        print("="*50)
        
        hotdeal_count = 0
        for deal in results:
            # Update cache with final result
            Processor.update_cache(deal)
            
            # Save to Database ONLY if HOT
            if deal.is_hotdeal:
                db.save_deal(deal)
                hotdeal_count += 1
            else:
                 pass
            
            # Print log regardless
            
            print(f"[{deal.category}] {deal.title} ({deal.discount_price})")
            print(f"   Link: {deal.link}")
            print("-" * 30)

        # Optional: Save to file for quick inspection
        import json
        with open("last_run_result.json", "w", encoding="utf-8") as f:
            json.dump([d.model_dump(mode='json') for d in results], f, ensure_ascii=False, indent=2)

        # 4. Save Crawl Statistics
        # Calculate total savings (sum of savings for all hot deals)
        new_savings = sum([deal.savings for deal in results if deal.savings and deal.is_hotdeal])
        total_savings = new_savings + cached_savings
        
        stats = {
            "community_count": len(crawlers),
            "total_items": len(all_deals),
            "filtered_items": dropped_count,  # dropped in processor loop
            "hotdeal_items": hotdeal_count + cached_hotdeal_count,   # final saved hotdeals + cached ones
            "total_savings": total_savings
        }
        logger.info(f"📊 Saving Pipeline Stats: {stats}")
        db.save_app_stats(stats)

        # 5. Data Retention Policy (Cleanup)
        logger.info("🧹 Cleaning up old deals (> 5 days)...")
        db.clean_old_deals(days=5)



if __name__ == "__main__":
    asyncio.run(run_pipeline())
