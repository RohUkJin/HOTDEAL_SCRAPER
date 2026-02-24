import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Hotdeal Analyzer"
    VERSION: str = "0.1.0"
    
    
    # Crawler Settings
    CRAWL_INTERVAL_MINUTES: int = 10
    USER_AGENT: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    
    # AI Settings
    GEMINI_API_KEY: str
    
    # Database Settings
    SUPABASE_URL: str
    SUPABASE_KEY: str = "your-supabase-key"
    SUPABASE_SECRET_KEY: Optional[str] = None
    
    # Naver Shopping API
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
