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
    # 根據提供者判斷
    if model and model.startswith("gpt-"):
        provider = "openai"
    elif model and (model.startswith("gemini-") or "gemini" in model.lower()):
        provider = "gemini"
    elif model and (model.startswith("claude-") or "claude" in model.lower()):
        provider = "anthropic"
    else:
        # 自動偵測：優先順序 Anthropic > Gemini > OpenAI
        if SETTINGS.anthropic_api_key:
            provider = "anthropic"
            model = model or "claude-3-5-sonnet-20240620"
        elif SETTINGS.gemini_api_key:
            provider = "gemini"
            model = model or "gemini-1.5-pro"
        elif SETTINGS.openai_api_key:
            provider = "openai"
            model = model or "gpt-4o"
        else:
            raise ValueError("No LLM API keys (Anthropic, Gemini, or OpenAI) found in environment.")

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
            model_instance = genai.GenerativeModel(model_name=model, system_instruction=SAFETY_PROMPT)
            response = model_instance.generate_content(prompt)
            return response.text

    except ImportError as e:
        raise RuntimeError(f"Required package for {provider} not installed. Error: {e}")
    except Exception as e:
        raise RuntimeError(f"LLM request failed for {provider} ({model}): {e}")
