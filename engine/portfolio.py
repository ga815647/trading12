from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

import numpy as np


GROUP_MAP = {
    "A": "chip",
    "B": "momentum",
    "C": "cross_stock",
    "D": "fundamental",
    "E": "mean_reversion",
    "F": "calendar",
    "G": "price_volume",
    "H": "contrarian",
    "I": "cross_market",
    "J": "sentiment",
}


def classify_group(hypothesis_id: str) -> str:
    return GROUP_MAP.get(str(hypothesis_id)[:1], "other")


def build_signal_id(item: dict[str, Any]) -> str:
    base = f"{item.get('hypothesis_id')}|{item.get('id')}|{item.get('params')}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def correlation_too_high(
    candidate_returns: list[float],
    existing_returns: list[float],
    threshold: float = 0.6,
) -> bool:
    size = min(len(candidate_returns), len(existing_returns))
    if size < 5:
        return False
    left = np.asarray(candidate_returns[-size:], dtype=float)
    right = np.asarray(existing_returns[-size:], dtype=float)
    if np.std(left) == 0 or np.std(right) == 0:
        return False
    corr = float(np.corrcoef(left, right)[0, 1])
    return corr > threshold


def select_signal_library(
    validated_signals: list[dict[str, Any]],
    correlation_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for signal in sorted(
        validated_signals,
        key=lambda item: (
            item.get("adjusted_p_value", 1.0),
            -item.get("sharpe", 0.0),
            -item.get("sample_count", 0),
        ),
    ):
        returns = signal.get("trade_returns", [])
        redundant = any(
            correlation_too_high(returns, chosen.get("trade_returns", []), correlation_threshold)
            for chosen in selected
        )
        if redundant:
            continue
        signal = dict(signal)
        signal["group"] = classify_group(signal.get("id", ""))
        signal["signal_id"] = build_signal_id(signal)
        selected.append(signal)
    return selected


def vote_signals(triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for trigger in triggers:
        buckets[(trigger["stock_id"], trigger["direction"])].append(trigger)

    voted: list[dict[str, Any]] = []
    for (stock_id, direction), items in buckets.items():
        groups = sorted({item["group"] for item in items})
        if len(groups) < 2:
            continue
        voted.append(
            {
                "stock_id": stock_id,
                "direction": direction,
                "groups": groups,
                "stars": min(3, len(groups)),
                "signals": sorted(items, key=lambda item: item.get("horizon_days", 0), reverse=True),
            }
        )
    return voted
