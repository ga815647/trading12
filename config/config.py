from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


ROOT_DIR = Path(__file__).resolve().parents[1]

# Time decay (validator)
TIME_DECAY_LAMBDA = 1.0
MIN_WEIGHTED_WIN_RATE = 0.54
MIN_RECENT_2Y_WIN_RATE = 0.52
MIN_RECENT_2Y_TRADES = 10

# Edge defense (liquidity). FinMind Volume = shares. 1 lot = 1000 shares.
SHARES_PER_LOT = 1000
MIN_DAILY_VOLUME_LOTS = 100
EDGE_DEFENSE_ENABLED = True
DATA_DIR = ROOT_DIR / "data"
PARQUET_DIR = DATA_DIR / "parquet_db"
RAW_DIR = DATA_DIR / "raw"
RESULTS_DIR = ROOT_DIR / "results"
HYPOTHESIS_DIR = RESULTS_DIR / "hypotheses"
BACKTEST_DIR = RESULTS_DIR / "backtests"
SIGNAL_DIR = RESULTS_DIR / "signals"
LOG_DIR = ROOT_DIR / "logs"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    encrypt_password: str = os.getenv("ENCRYPT_PASSWORD", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    finmind_token: str = os.getenv("FINMIND_TOKEN", "")


def ensure_runtime_dirs() -> None:
    for path in [
        DATA_DIR,
        PARQUET_DIR,
        RAW_DIR,
        RESULTS_DIR,
        HYPOTHESIS_DIR,
        BACKTEST_DIR,
        SIGNAL_DIR,
        LOG_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
