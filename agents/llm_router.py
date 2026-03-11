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


def cloud_llm(prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    if not SETTINGS.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured.")

    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package is not installed.") from exc

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SAFETY_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
