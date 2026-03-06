import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.absolute()))

from app.core.config import settings

try:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Say hello",
        config=types.GenerateContentConfig(
            response_mime_type="text/plain"
        )
    )
    print(f"Success: {response.text}")
except Exception as e:
    print(f"Error: {e}")
