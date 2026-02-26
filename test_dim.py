from google import genai
from app.core.config import settings
def main():
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.embed_content(
        model='gemini-embedding-001',
        contents='test string'
    )
    print("gemini-embedding-001 length:", len(response.embeddings[0].values))
    
    try:
        response = client.models.embed_content(
            model='text-embedding-004',
            contents='test string'
        )
        print("text-embedding-004 length:", len(response.embeddings[0].values))
    except Exception as e:
        print("text-embedding-004 failed:", e)

main()
