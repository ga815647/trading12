from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import (
    BACKTEST_DIR,
    MAX_ADJUSTED_P_VALUE,
    MIN_CYCLE_SAMPLES,
    MIN_OOS_WIN_RATE,
    MIN_RECENT_2Y_TRADES,
    MIN_RECENT_2Y_WIN_RATE,
    MIN_SAMPLE_COUNT,
    MIN_SHARPE,
    MIN_WEIGHTED_WIN_RATE,
    MIN_WIN_RATE,
    SIGNAL_DIR,
    TIME_DECAY_LAMBDA,
    ensure_runtime_dirs,
)
from collections import defaultdict
from config.encrypt import load_encrypted_json, save_signal
from config.market_cycle import label_date
from engine.portfolio import select_signal_library
from engine.time_decay import (
    _parse_date,
    compute_recent_stats,
    compute_weighted_win_rate,
)


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


def _group_key(item: dict) -> str:
    """
    從 hypothesis_id 萃取 trigger 家族。
    LM_A01_TVA1_0023 → "A01"
    LM_K03_NONE_0001 → "K03"
    A01_0001         → "A01"（舊格式相容）
    """
    h_id = str(item.get("hypothesis_id", item.get("id", "")))
    if h_id.startswith("LM_"):
        parts = h_id.split("_")
        return parts[1] if len(parts) >= 2 else "unknown"
    return h_id[:3]  # 例如 "A01"


def _cycle_pass(trade_dates: list[str], minimum: int = MIN_CYCLE_SAMPLES) -> tuple[bool, dict[str, int]]:
    counts = {"bull": 0, "bear": 0, "sideways": 0}
    for trade_date in trade_dates:
        counts[label_date(trade_date)] += 1
    return all(count >= minimum for count in counts.values()), counts


def dedupe_backtests(backtests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in backtests:
        key = str(item.get("hypothesis_id") or item.get("id") or "")
        if not key:
            continue
        current = deduped.get(key)
        if current is None:
            deduped[key] = item
            continue
        current_score = (
            float(current.get("sample_count", 0)),
            float(current.get("sharpe", 0.0)),
            -float(current.get("p_value", 1.0)),
        )
        next_score = (
            float(item.get("sample_count", 0)),
            float(item.get("sharpe", 0.0)),
            -float(item.get("p_value", 1.0)),
        )
        if next_score > current_score:
            deduped[key] = item
    return list(deduped.values())


def validate_backtests(
    backtests: list[dict[str, Any]],
    min_sample_count: int = MIN_SAMPLE_COUNT,
    min_win_rate: float = MIN_WIN_RATE,
    min_oos_win_rate: float = MIN_OOS_WIN_RATE,
    min_sharpe: float = MIN_SHARPE,
    max_adjusted_p_value: float = MAX_ADJUSTED_P_VALUE,
    min_weighted_win_rate: float | None = None,
    min_recent_2y_win_rate: float | None = None,
    min_recent_2y_trades: int | None = None,
    time_decay_lambda: float | None = None,
) -> list[dict[str, Any]]:
    _min_wr = min_weighted_win_rate if min_weighted_win_rate is not None else MIN_WEIGHTED_WIN_RATE
    _min_recent_wr = min_recent_2y_win_rate if min_recent_2y_win_rate is not None else MIN_RECENT_2Y_WIN_RATE
    _min_recent_n = min_recent_2y_trades if min_recent_2y_trades is not None else MIN_RECENT_2Y_TRADES
    _lambda = time_decay_lambda if time_decay_lambda is not None else TIME_DECAY_LAMBDA

    # FDR 校正改為按 Trigger 家族分組做
    groups = defaultdict(list)
    for idx, item in enumerate(backtests):
        groups[_group_key(item)].append((idx, item))

    adjusted = [1.0] * len(backtests)
    for group_key, group_items in groups.items():
        indices = [i for i, _ in group_items]
        p_vals  = [float(backtests[i].get("p_value", 1.0)) for i in indices]
        adj     = _adjust_p_values(p_vals)
        for i, adj_p in zip(indices, adj):
            adjusted[i] = adj_p

    validated: list[dict[str, Any]] = []
    for item, adjusted_p in zip(backtests, adjusted):
        trade_dates = item.get("trade_dates", [])
        trade_returns = item.get("trade_returns", [])
        
        # 每個策略用自己的最新交易日當 anchor (anchor=None)
        weighted_wr, _ = compute_weighted_win_rate(
            trade_dates, trade_returns, decay_lambda=_lambda, anchor=None
        )
        recent_wr, recent_count = compute_recent_stats(
            trade_dates, trade_returns, anchor=None
        )

        # Small Sample Size Defense: Bayesian Smoothing towards 0.5
        if recent_count < _min_recent_n and recent_wr is not None:
            wins = recent_wr * recent_count
            recent_wr = (wins + (_min_recent_n * 0.5)) / (recent_count + _min_recent_n)

        recent_pass = recent_count >= _min_recent_n and (
            recent_wr is not None and recent_wr >= _min_recent_wr
        )

        passed_cycle, cycle_counts = _cycle_pass(trade_dates)
        candidate = dict(item)
        candidate["adjusted_p_value"] = adjusted_p
        candidate["cycle_counts"] = cycle_counts
        candidate["weighted_win_rate"] = weighted_wr
        candidate["recent_2y_win_rate"] = recent_wr
        candidate["recent_2y_count"] = recent_count
        candidate["passes_validation"] = all(
            [
                candidate.get("supported", False),
                candidate.get("sample_count", 0) >= min_sample_count,
                candidate.get("win_rate", 0.0) >= min_win_rate,
                candidate.get("oos_win_rate", 0.0) >= min_oos_win_rate,
                candidate.get("sharpe", 0.0) >= min_sharpe,
                adjusted_p < max_adjusted_p_value,
                passed_cycle,
                weighted_wr >= _min_wr,
                recent_pass,
            ]
        )
        if candidate["passes_validation"]:
            validated.append(candidate)
    
    # Generate evolution hints
    hints = {
        "survivor_count": len(validated),
        "mutation_intensity": "normal" if len(validated) > 0 else "high",
        "top_themes": []
    }
    if validated:
        themes = {}
        for v in validated:
            tid = str(v.get("id", ""))[:1]
            themes[tid] = themes.get(tid, 0) + 1
        hints["top_themes"] = sorted(themes.keys(), key=lambda x: themes[x], reverse=True)
    
    # Save hints for Agent 1 (as a plain JSON for easy reading)
    import json
    hint_path = SIGNAL_DIR / "evolution_hints.json"
    with open(hint_path, "w", encoding="utf-8") as f:
        json.dump(hints, f, indent=2)

    return select_signal_library(validated)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate backtest results.")
    parser.add_argument("--input", default=str(BACKTEST_DIR / "batch_001.enc"))
    parser.add_argument("--input-glob")
    parser.add_argument("--output", default=str(SIGNAL_DIR / "library.enc"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    backtests: list[dict[str, Any]] = []
    if args.input_glob:
        matches = sorted(glob.glob(args.input_glob))
        if not matches:
            raise SystemExit(f"No backtest files matched: {args.input_glob}")
        for match in matches:
            backtests.extend(load_encrypted_json(Path(match)))
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            raise SystemExit(f"Backtest file not found: {input_path}")
        backtests = load_encrypted_json(input_path)
    raw_count = len(backtests)
    backtests = dedupe_backtests(backtests)
    validated = validate_backtests(backtests)
    output = save_signal(validated, args.output)
    print(
        f"Validated {len(validated)} signals into {output} "
        f"(raw={raw_count}, deduped={len(backtests)})"
    )


if __name__ == "__main__":
    main()
