from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SIGNAL_DIR, ensure_runtime_dirs
from config.encrypt import load_signals
from data.universe import UNIVERSE
from engine.notify import build_signal_message, send_signal
from engine.portfolio import vote_signals


def run_daily_scan(signal_library: list[dict], symbols: list[str] | None = None) -> list[dict]:
    from engine.backtest import evaluate_latest_signal, load_market_cache

    triggered: list[dict] = []
    target_symbols = set(symbols or UNIVERSE)
    market_cache = load_market_cache(sorted(target_symbols))
    for hypothesis in signal_library:
        if hypothesis.get("excluded"):
            continue
        for stock_id in target_symbols:
            trigger = evaluate_latest_signal(stock_id, hypothesis, market_cache=market_cache)
            if trigger:
                triggered.append(trigger)
    return vote_signals(triggered)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan latest market data for active signals.")
    parser.add_argument("--input", default=str(SIGNAL_DIR / "library.enc"))
    parser.add_argument("--symbol", action="append", dest="symbols")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(
            f"Signal library not found: {input_path}. Run engine/validator.py first."
        )
    signal_library = load_signals(input_path)
    voted = run_daily_scan(signal_library, symbols=args.symbols)
    if not voted:
        print("No signals triggered.")
        return
    for signal in voted:
        message = build_signal_message(signal)
        sent = send_signal(message)
        print(message)
        if sent:
            print("Sent to Telegram.")


if __name__ == "__main__":
    main()
