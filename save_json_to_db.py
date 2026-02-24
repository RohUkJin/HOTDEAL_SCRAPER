import json
import logging
import asyncio
from typing import List
from app.models.deal import Deal
from app.core.database import db
from app.core.processor import Processor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("manual_save")

def save_from_json(filepath: str = "last_run_result.json"):
    logger.info(f"📂 Loading results from {filepath}...")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        logger.info(f"Found {len(data)} items. Saving to DB...")
        
        saved_count = 0
        for item in data:
            try:
                # Convert string back to Deal object
                deal = Deal(**item)
                
                # Check if it really is a hotdeal (redundant check if filtered source, but safe)
                if deal.is_hotdeal:
                    # Retroactive Check: Filter out self-referencing links
                    self_ref_map = {
                        "Ppomppu": "ppomppu.co.kr",
                        "FMKorea": "fmkorea.com",
                        "Arca": "arca.live"
                    }
                    target_domain = self_ref_map.get(deal.source)
                    if target_domain and target_domain in deal.link:
                        logger.info(f"Skipping self-referencing link ({target_domain}): {deal.title}")
                        continue

                    # Normalize Price
                    normalized_price = Processor.normalize_price_text(deal.discount_price)
                    if normalized_price:
                        deal.discount_price = normalized_price

                    db.save_deal(deal)
                    saved_count += 1
            except Exception as e:
                logger.error(f"Failed to process item {item.get('title', 'Unknown')}: {e}")
                
        logger.info(f"✅ Successfully saved {saved_count} hot deals to Supabase.")
        
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    save_from_json()
