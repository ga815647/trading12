import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.llm_router import cloud_llm
from config.config import SETTINGS

def test_llms():
    print("=== LLM Connectivity Test ===")
    
    # Test Anthropic (Claude)
    if SETTINGS.anthropic_api_key:
        print("\n[Testing Anthropic/Claude]...")
        try:
            # Use default or a widely available model
            res = cloud_llm("Hello, respond with 'Claude is working!'")
            print(f"Response: {res}")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("\n[Anthropic/Claude] Skipped: No API key found.")

    # Test Gemini
    if SETTINGS.gemini_api_key:
        print("\n[Testing Google/Gemini]...")
        try:
            # Use gemini-1.5-flash which is more likely to be available for free keys
            res = cloud_llm("Hello, respond with 'Gemini is working!'", model="gemini-1.5-flash")
            print(f"Response: {res}")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("\n[Google/Gemini] Skipped: No API key found.")

    # Test OpenAI (ChatGPT)
    if SETTINGS.openai_api_key:
        print("\n[Testing OpenAI/ChatGPT]...")
        try:
            res = cloud_llm("Hello, respond with 'ChatGPT is working!'")
            print(f"Response: {res}")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("\n[OpenAI/ChatGPT] Skipped: No API key found.")

if __name__ == "__main__":
    test_llms()
