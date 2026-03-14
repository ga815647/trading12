from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SETTINGS


SAFETY_PROMPT = """
You are generating code for an isolated strategy-mining system.
Never request or reveal secrets.
Never assume access to .env, encrypted files, or parquet files.
Always use placeholder parameter names such as threshold_a, threshold_b,
days_n, and horizon_days instead of real tuned values.
Treat all numeric results as math objects only, not trading advice.
""".strip()


def cloud_llm(prompt: str, model: str | None = None) -> str:
    """
    智能路由 LLM 請求到可用的 Provider (Anthropic, OpenAI, 或 Google Gemini)
    """
    # 自動偵測：根據金鑰存在情況與模型關鍵字進行路由
    if model:
        m_lower = model.lower()
        if "gpt-" in m_lower:
            provider = "openai"
        elif "gemini" in m_lower:
            provider = "gemini"
        elif "claude" in m_lower:
            provider = "anthropic"
        else:
            # 指定了模型名稱但不知是哪家，嘗試依據可用金鑰推測
            if SETTINGS.anthropic_api_key: provider = "anthropic"
            elif SETTINGS.gemini_api_key: provider = "gemini"
            elif SETTINGS.openai_api_key: provider = "openai"
            else: raise ValueError(f"Unknown model '{model}' and no API keys found.")
    else:
        # 完全沒指定模型，按優先級找可用金鑰
        if SETTINGS.anthropic_api_key:
            provider = "anthropic"
            model = "claude-3-5-sonnet-20240620"
        elif SETTINGS.gemini_api_key:
            provider = "gemini"
            model = "gemini-1.5-flash"
        elif SETTINGS.openai_api_key:
            provider = "openai"
            model = "gpt-4o"
        else:
            raise ValueError("No LLM API keys found in environment.")

    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
            response = client.messages.create(
                model=model,
                max_tokens=4000,
                system=SAFETY_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=SETTINGS.openai_api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SAFETY_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content

        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=SETTINGS.gemini_api_key)
            
            # 優先使用 gemini-1.5-flash，這是最容易有免費配額的模型
            actual_model = model if model else "gemini-1.5-flash"
            # 去除可能誤傳的 models/ 前綴，genai.GenerativeModel 會處理
            if actual_model.startswith("models/"):
                actual_model = actual_model.replace("models/", "")
                
            model_instance = genai.GenerativeModel(model_name=actual_model, system_instruction=SAFETY_PROMPT)
            response = model_instance.generate_content(prompt)
            return response.text

    except ImportError as e:
        raise RuntimeError(f"Required package for {provider} not installed. Error: {e}")
    except Exception as e:
        raise RuntimeError(f"LLM request failed for {provider} ({model}): {e}")
