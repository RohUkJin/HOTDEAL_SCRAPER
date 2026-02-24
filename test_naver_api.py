import asyncio
from app.services.naver import NaverSearchService

async def main():
    # We will temporarily modify NaverSearchService to print the full item
    # But for now let's just use httpx to fetch and print
    import httpx
    from app.core.config import settings
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET
    }
    params = {"query": "삼다수 1L 12병", "display": 1, "sort": "sim"}
    async with httpx.AsyncClient() as client:
        res = await client.get(NaverSearchService.BASE_URL, headers=headers, params=params)
        print(res.json())

asyncio.run(main())
