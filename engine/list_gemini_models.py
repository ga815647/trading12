import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SETTINGS

def list_gemini_models():
    if not SETTINGS.gemini_api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    print(f"Checking models for Gemini key: {SETTINGS.gemini_api_key[:5]}...{SETTINGS.gemini_api_key[-5:]}")
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=SETTINGS.gemini_api_key)
        
        print("\nAvailable models:")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name} (Display: {m.display_name})")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    list_gemini_models()
