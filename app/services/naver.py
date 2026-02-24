import httpx
from typing import Optional
from app.core.config import settings
from app.core.logging import logger

class NaverSearchService:
    BASE_URL = "https://openapi.naver.com/v1/search/shop.json"

    @staticmethod
    async def search_lowest_price(query: str) -> Optional[int]:
        """
        Search for the lowest price (lprice) of a product on Naver Shopping.
        Returns the integer price or None if failed/not found.
        """
        if not settings.NAVER_CLIENT_ID or not settings.NAVER_CLIENT_SECRET:
            logger.warning("Naver API credentials not set. Skipping price comparison.")
            return None

        headers = {
            "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET
        }
        
        params = {
            "query": query,
            "display": 1,
            "sort": "sim" # Sort by similarity to get relevant item
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(NaverSearchService.BASE_URL, headers=headers, params=params, timeout=5.0)
                
                if response.status_code != 200:
                    logger.error(f"Naver API Error {response.status_code}: {response.text}")
                    return None
                
                data = response.json()
                items = data.get("items", [])
                
                if not items:
                    return None
                
                # Get the first item's lowest price
                lprice = items[0].get("lprice")
                return int(lprice) if lprice else None
                
        except Exception as e:
            logger.error(f"Error searching Naver for '{query}': {e}")
            return None
