from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import PARQUET_DIR, SETTINGS, ensure_runtime_dirs


def _status(ok: bool, label: str, detail: str = "") -> str:
    prefix = "[OK]" if ok else "[MISSING]"
    suffix = f" - {detail}" if detail else ""
    return f"{prefix} {label}{suffix}"


def parquet_summary() -> tuple[int, int, int]:
    if not PARQUET_DIR.exists():
        return 0, 0, 0
    files = list(PARQUET_DIR.glob("*.parquet"))
    kline = sum(1 for path in files if path.name.endswith("_kline.parquet"))
    chip = sum(1 for path in files if path.name.endswith("_chip.parquet"))
    margin = sum(1 for path in files if path.name.endswith("_margin.parquet"))
    return kline, chip, margin


def run_preflight() -> int:
    ensure_runtime_dirs()
    checks = [
        (bool(SETTINGS.encrypt_password), "ENCRYPT_PASSWORD"),
        (bool(SETTINGS.finmind_token), "FINMIND_TOKEN"),
        (bool(SETTINGS.telegram_bot_token), "TELEGRAM_BOT_TOKEN"),
        (bool(SETTINGS.telegram_chat_id), "TELEGRAM_CHAT_ID"),
    ]

    for ok, label in checks:
        print(_status(ok, label))

    kline, chip, margin = parquet_summary()
    print(_status(kline > 0, "Parquet kline", f"{kline} files"))
    print(_status(chip > 0, "Parquet chip", f"{chip} files"))
    print(_status(margin > 0, "Parquet margin", f"{margin} files"))

    fully_ready = all(ok for ok, _ in checks) and min(kline, chip, margin) > 0
    if fully_ready:
        print("\nSystem is ready for daily fetch, validation, and scanning.")
        return 0

    print("\nNext actions:")
    if not SETTINGS.finmind_token:
        print("- Fill FINMIND_TOKEN in .env")
    if not SETTINGS.telegram_bot_token or not SETTINGS.telegram_chat_id:
        print("- Fill TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
    if not SETTINGS.encrypt_password:
        print("- Replace ENCRYPT_PASSWORD with your own long random password")
    if min(kline, chip, margin) == 0:
        print(r"- Run .\.venv\Scripts\python data/fetcher.py --mode full")
    return 1


if __name__ == "__main__":
    raise SystemExit(run_preflight())
