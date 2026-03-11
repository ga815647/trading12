from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import BACKTEST_DIR, SIGNAL_DIR, ensure_runtime_dirs
from config.encrypt import load_encrypted_json, save_signal
from config.market_cycle import label_date
from engine.portfolio import select_signal_library


def _adjust_p_values(values: list[float]) -> list[float]:
    try:
        from statsmodels.stats.multitest import multipletests

        return list(multipletests(values, method="fdr_bh")[1])
    except Exception:
        indexed = sorted(enumerate(values), key=lambda item: item[1])
        adjusted = [1.0] * len(values)
        total = len(values)
        running = 1.0
        for rank, (original_idx, p_value) in enumerate(reversed(indexed), start=1):
            adjusted_p = min(running, p_value * total / (total - rank + 1))
            adjusted[original_idx] = adjusted_p
            running = adjusted_p
        return adjusted


def _cycle_pass(trade_dates: list[str], minimum: int = 30) -> tuple[bool, dict[str, int]]:
    counts = {"bull": 0, "bear": 0, "sideways": 0}
    for trade_date in trade_dates:
        counts[label_date(trade_date)] += 1
    return all(count >= minimum for count in counts.values()), counts


def validate_backtests(
    backtests: list[dict[str, Any]],
    min_sample_count: int = 200,
    min_win_rate: float = 0.55,
    min_oos_win_rate: float = 0.53,
    min_sharpe: float = 1.0,
    max_adjusted_p_value: float = 0.05,
) -> list[dict[str, Any]]:
    p_values = [float(item.get("p_value", 1.0)) for item in backtests]
    adjusted = _adjust_p_values(p_values) if p_values else []
    validated: list[dict[str, Any]] = []

    for item, adjusted_p in zip(backtests, adjusted):
        passed_cycle, cycle_counts = _cycle_pass(item.get("trade_dates", []))
        candidate = dict(item)
        candidate["adjusted_p_value"] = adjusted_p
        candidate["cycle_counts"] = cycle_counts
        candidate["passes_validation"] = all(
            [
                candidate.get("supported", False),
                candidate.get("sample_count", 0) >= min_sample_count,
                candidate.get("win_rate", 0.0) >= min_win_rate,
                candidate.get("oos_win_rate", 0.0) >= min_oos_win_rate,
                candidate.get("sharpe", 0.0) >= min_sharpe,
                adjusted_p < max_adjusted_p_value,
                passed_cycle,
            ]
        )
        if candidate["passes_validation"]:
            validated.append(candidate)
    return select_signal_library(validated)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate backtest results.")
    parser.add_argument("--input", default=str(BACKTEST_DIR / "batch_001.enc"))
    parser.add_argument("--output", default=str(SIGNAL_DIR / "library.enc"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Backtest file not found: {input_path}")
    backtests = load_encrypted_json(input_path)
    validated = validate_backtests(backtests)
    output = save_signal(validated, args.output)
    print(f"Validated {len(validated)} signals into {output}")


if __name__ == "__main__":
    main()
