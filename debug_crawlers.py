
import asyncio
from playwright.async_api import async_playwright
from app.crawlers.arca import ArcaCrawler
from app.crawlers.fmkorea import FMKoreaCrawler
from app.core.processor import Processor

async def debug_crawlers():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        print("=== Debugging ArcaCrawler ===")
        arca = ArcaCrawler()
        arca_deals = await arca.process(context)
        print(f"Arca Found: {len(arca_deals)}")
        for d in arca_deals[:3]:
            print(f"[{d.title}]")
            print(f"  Price: {d.discount_price}")
            print(f"  Comments ({d.comment_count}): {d.comments[:2]}")
            print(f"  Link: {d.link}")

        print("\n=== Debugging FMKoreaCrawler ===")
        fm = FMKoreaCrawler()
        fm_deals = await fm.process(context)
        print(f"FMKorea Found: {len(fm_deals)}")
        for d in fm_deals[:3]:
            print(f"[{d.title}]")
            print(f"  Price: {d.discount_price}")
            print(f"  Comments ({d.comment_count}): {d.comments[:2]}")
            print(f"  Link: {d.link}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_crawlers())
