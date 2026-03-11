from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SIGNAL_DIR, ensure_runtime_dirs
from config.encrypt import load_encrypted_json, save_signal


def rolling_winrate_by_trades(trades: list[dict[str, Any]], window: int = 20) -> float | None:
    if len(trades) < window:
        return None
    recent = trades[-window:]
    wins = sum(1 for trade in recent if float(trade.get("pnl", 0.0)) > 0)
    return wins / window


def mark_signal_decay(signals: list[dict[str, Any]], window: int = 20) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for signal in signals:
        item = dict(signal)
        rolling = rolling_winrate_by_trades(item.get("trades", []), window=window)
        item["rolling_win_rate"] = rolling
        item["excluded"] = rolling is not None and rolling < 0.5
        updated.append(item)
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check signal decay using recent trades.")
    parser.add_argument("--input", default=str(SIGNAL_DIR / "library.enc"))
    parser.add_argument("--output", default=str(SIGNAL_DIR / "library.enc"))
    parser.add_argument("--window", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Signal library not found: {input_path}")
    signals = load_encrypted_json(input_path)
    updated = mark_signal_decay(signals, window=args.window)
    output = save_signal(updated, args.output)
    excluded = sum(1 for item in updated if item.get("excluded"))
    print(f"Decay check complete: {excluded} signals marked excluded in {output}")


if __name__ == "__main__":
    main()
