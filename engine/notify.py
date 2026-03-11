from __future__ import annotations

import sys
from typing import Any
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SETTINGS


def send_signal(message: str) -> bool:
    if not SETTINGS.telegram_bot_token or not SETTINGS.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{SETTINGS.telegram_bot_token}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": SETTINGS.telegram_chat_id, "text": message},
        timeout=15,
    )
    response.raise_for_status()
    return True


def build_signal_message(signal: dict[str, Any]) -> str:
    title_map = {
        "long": "LONG",
        "exit": "EXIT",
        "short": "SHORT",
    }
    title = title_map.get(signal["direction"], signal["direction"].upper())
    stars = "*" * signal.get("stars", 1)
    lines = [f"[{title} {stars}] {signal['stock_id']}"]
    for item in signal["signals"]:
        lines.append(
            f"- {item['signal_id']} {item['id']} {item['desc']} (hold {item['horizon_days']}d)"
        )
    return "\n".join(lines)


def test_notify() -> None:
    send_signal("Strategy Mining v11 connectivity test passed.")


if __name__ == "__main__":
    test_notify()
