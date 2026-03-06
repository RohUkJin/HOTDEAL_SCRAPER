import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.absolute()))

from app.core.config import settings

try:
    from google import genai
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    models = list(client.models.list())
    for model in models:
        print(model.name)
except Exception as e:
    print(f"Error: {e}")
