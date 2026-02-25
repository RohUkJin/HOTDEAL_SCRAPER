from supabase import create_client, Client
from app.core.config import settings
from app.models.deal import Deal
from app.core.logging import logger
from datetime import datetime, timedelta

class Database:
    def __init__(self):
        try:
            self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.client = None

    def save_deal(self, deal: Deal):
        """Saves a single deal to Supabase hotdeals table."""
        if not self.client:
             return

        try:
            # Only save if is_hotdeal is True
            if not deal.is_hotdeal:
                logger.info(f"Skipping non-hotdeal: {deal.title}")
                return

            # Prepare payload matching DB schema
            payload = {
                "id": deal.id,
                "source": deal.source,
                "title": deal.title,
                "link": deal.link,
                "original_price": deal.original_price,
                "discount_price": deal.discount_price,
                "posted_at": deal.posted_at.isoformat() if deal.posted_at else None,
                "votes": deal.votes,
                "comment_count": deal.comment_count,
                "image_url": deal.image_url,
                "is_hotdeal": deal.is_hotdeal,
                "category": str(deal.category) if deal.category else None,
                "embed_text": deal.embed_text,
                "naver_price": deal.naver_price,
                "savings": deal.savings,
                "score": deal.score,
                "status": deal.status,
                "comments": deal.comments,
                "why_hotdeal": deal.reason,
                "ai_summary": deal.ai_summary,
                "sentiment_score": deal.sentiment_score
            }
            
            # Upsert based on ID
            response = self.client.table("hotdeals").upsert(payload).execute()
            logger.info(f"Saved hotdeal to DB: {deal.title}")
        except Exception as e:
            logger.error(f"Error saving deal to DB: {e}")

    def clean_old_deals(self, days=7):
        """Deletes deals older than 'days'."""
        if not self.client:
            return

        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            response = self.client.table("hotdeals").delete().lt("posted_at", cutoff_date).execute()
            logger.info(f"Cleaned old deals older than {days} days.")
        except Exception as e:
             logger.error(f"Error cleaning old deals: {e}")

    def save_app_stats(self, stats: dict):
        """Saves pipeline execution statistics."""
        if not self.client:
            return

        try:
            # Stats schema: community_count, total_items, filtered_items, hotdeal_items
            response = self.client.table("crawl_stats").insert(stats).execute()
            logger.info(f"Saved crawl stats: {stats}")
        except Exception as e:
            logger.error(f"Error saving crawl stats: {e}")

db = Database()

