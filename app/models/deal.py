from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
from datetime import datetime
from app.models.enums import Category

class Deal(BaseModel):
    id: str = Field(..., description="Unique identifier for the deal (usually from the source site)")
    source: str = Field(..., description="Source community name (e.g., Ppomppu, Clien)")
    title: str
    link: str
    discount_price: Optional[str] = None
    posted_at: datetime
    votes: int = 0
    comment_count: int = 0
    naver_price: Optional[int] = None
    savings: Optional[int] = None # Naver Price - Discount Price
    comments: List[str] = Field(default_factory=list) # Comment contents
    is_hotdeal: Optional[bool] = None
    category: Optional[Category] = None
    embed_text: Optional[str] = None
    embedding: Optional[List[float]] = None
    
    # Analysis Fields
    score: float = 0.0 
    status: str = Field("READY", description="READY, HOT, MAYBE, DROP")
    reason: Optional[str] = None # For Hard Filter drop reason
    ai_summary: Optional[str] = None # One-line summary of AI reasoning
    sentiment_score: Optional[int] = None # 0-100 score
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }
