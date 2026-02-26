import json
from typing import List
from google import genai
from google.genai import types
from app.core.config import settings
from app.core.logging import logger
from app.models.deal import Deal
from app.models.enums import Category
from pydantic import BaseModel, Field

class BatchAnalysisResult(BaseModel):
    deal_id: str
    is_hotdeal: bool
    category: str
    reason: str # Curated summary
    sentiment: int # 0-100
    embed_text: str # For vector embedding

class BatchResponse(BaseModel):
    results: List[BatchAnalysisResult]

class Analyzer:
    def __init__(self):
        try:
            self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
            self.model_name = "gemini-3-flash-preview"
            self.fallback_model_name = "gemini-2.0-flash"
            self.embedding_model = "gemini-embedding-001"
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.client = None

    def analyze_batch(self, deals: List[Deal]) -> List[Deal]:
        """Analyzes a batch of deals using Google Gemini API."""
        if not deals or not self.client:
            return deals

        # Prepare Batch Prompt
        items_str = ""
        for deal in deals:
            comments_preview = " | ".join(deal.comments[:5]) # Pass top 5 comments
            items_str += f"""
            [ID: {deal.id}]
            Title: {deal.title}
            Price: {deal.discount_price}
            Naver Lowest Price: {deal.naver_price if deal.naver_price else 'N/A'}
            Savings: {deal.savings if deal.savings else 0} won
            Link: {deal.link}
            Score: {deal.score}
            Votes/CommentsCount: {deal.votes}/{deal.comment_count}
            Viewer Reactions (Comments): {comments_preview}
            ---"""

        prompt = f"""
        You are a data analyst for a company's procurement team. 
        Your goal is to identify "Daily Necessity Hot Deals" suitable for company bulk purchase.
        
        Analyze the following items based on Title, Price, and User Reactions (Comments).
        
        CRITERIA:
        1. HOT: 
           - Item is a DAILY NECESSITY (Food, Drink, Toiletries, Office, Others) OR useful general goods (Electronics, Small Appliances, Home Goods, Health Supplements).
           - **Important**: Clothes, Games, Luxury Items, and Coupons are still generally DROP, unless they are exceptionally cheap and widely applicable.
           - Price is cheap (verified by 'Savings' > 0 OR user comments like "cheap", "good price"). The 'Savings' value is already unit-price adjusted and considers shipping. Even if there are few or no comments, if the 'Savings' are clearly positive, consider it a HOT deal.
           - User sentiment is POSITIVE or NEUTRAL. Lack of comments does not disqualify a deal if the price is good.
        2. DROP: 
           - Highly specific niche items (e.g., specific game titles, high-end luxury fashion, obscure components).
           - Price is NOT competitive (Savings <= 0 AND users say "expensive").
           - User sentiment is predominantly NEGATIVE (e.g., "don't buy", "not a deal").
           - **VIRAL/AD WARNING**: If comments strongly complain about "바이럴", "광고", "업자", "비추", Sentiment Score MUST be < 30.
        3. MAYBE: Ambiguous cases.

        INPUT ITEMS:
        {items_str}

        OUTPUT INSTRUCTIONS:
        - ONLY include items in the "results" array that are classified as HOT or MAYBE. 
        - STRICT RULE: DO NOT include items that are classified as DROP in your response. Omit them entirely to save output space.
        
        Provide a JSON object with a "results" list.
        Schema:
        {{
            "results": [
                {{
                    "deal_id": "string (matches input ID)",
                    "is_hotdeal": boolean (true if HOT),
                    "category": "string (MUST BE ONE OF: Food, Drink, Toiletries, Office, Others)",
                    "reason": "string (3-line CURATED summary in Korean. Tone: Shopping Host. Use emojis sparingly (max 1 per line).)",
                    "sentiment": integer (0 to 100, based on User Reactions. <30 if viral suspected)",
                    "embed_text": "string (Vector search context. Format: [Category] Product Name / Key Features (e.g., 역대가, 무배) / Target Audience. MUST be NOUNS ONLY. NO polite words like '안녕하세요', '추천합니다'. NO particles like '은/는/이/가/의'. Space-separated.)"
                }}
            ]
        }}
        Important: The 'reason' MUST be written in Korean with an engaging tone but NOT excessive usage of emojis.
        """

        try:
            response = self._generate_with_fallback(prompt)
            
            result_json = json.loads(response.text)
            
            # Map results back to deals
            result_list = result_json.get("results", [])
            result_map = {str(r["deal_id"]): r for r in result_list} # ensure string keys
            
            for deal in deals:
                if str(deal.id) in result_map:
                    res = result_map[str(deal.id)]
                    deal.is_hotdeal = res.get("is_hotdeal", False)
                    
                    # Category mapping with fallback
                    raw_category = res.get("category", "OTHERS")
                    try:
                        # Try to match case-insensitive
                        deal.category = Category(raw_category)
                    except ValueError:
                         logger.warning(f"Invalid category '{raw_category}' for ID {deal.id}. Defaulting to OTHERS.")
                         deal.category = Category.OTHERS

                    deal.ai_summary = res.get("reason", "")
                    deal.sentiment_score = res.get("sentiment", 50)
                    deal.embed_text = res.get("embed_text", "")
                    
                    if deal.is_hotdeal:
                        deal.status = "HOT"
                    else:
                        deal.status = "DROP"
                else:
                    # Item is missing from LLM response, meaning it was classified as DROP
                    deal.is_hotdeal = False
                    deal.category = Category.DROP
                    deal.ai_summary = "AI 판단: 필터링 조건 미달 (DROP)"
                    deal.sentiment_score = 0
                    deal.embed_text = ""
                    deal.status = "DROP"
                    
            logger.info(f"Batch analysis complete for {len(deals)} items. LLM returned {len(result_list)} items.")

        except Exception as e:
            logger.error(f"Error in batch analysis (usually JSON decode error from text truncation): {e}")
            # Log the raw text so we can debug what went wrong.
            if 'response' in locals() and hasattr(response, 'text'):
                logger.error(f"Raw Response Text: {response.text[:500]} ... [truncated]")
                
            # Fallback for errors
            for deal in deals:
                if deal.status == "READY": 
                    deal.status = "ERROR"
            
        # Generate embeddings for successful hot deals
        try:
            self._generate_embeddings(deals)
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            
        return deals

    def _generate_with_fallback(self, prompt: str):
        """Attempts to generate content with primary model, fallback on 429."""
        try:
            logger.info(f"Generating content using {self.model_name}...")
            return self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
        except Exception as e:
            # Check for 429 or Resource Exhausted
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "Too Many Requests" in str(e)
            
            if is_rate_limit and self.fallback_model_name:
                logger.warning(f"Rate limit hit on {self.model_name}. Switching to fallback: {self.fallback_model_name}")
                try:
                    return self.client.models.generate_content(
                        model=self.fallback_model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                except Exception as fallback_e:
                    logger.error(f"Fallback model also failed: {fallback_e}")
                    raise fallback_e
            else:
                raise e

        except Exception as e:
            logger.error(f"Error in generation: {e}")
            raise e
            
        return None

    def _generate_embeddings(self, deals: List[Deal]):
        """Generates vector embeddings for hot deals."""
        hotdeals_to_embed = [d for d in deals if d.is_hotdeal and d.embed_text]
        if not hotdeals_to_embed or not self.client:
            return

        try:
            logger.info(f"Generating embeddings for {len(hotdeals_to_embed)} hot deals using {self.embedding_model}...")
            texts = [d.embed_text for d in hotdeals_to_embed]
            
            response = self.client.models.embed_content(
                model=self.embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=768
                )
            )
            
            # Map embeddings back to deals
            for i, deal in enumerate(hotdeals_to_embed):
                deal.embedding = response.embeddings[i].values
                
            logger.info("Successfully generated and assigned embeddings.")
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise e
