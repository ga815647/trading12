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
        # 對於 exit 管線，一個 group (例如 time) 觸發就應該推播
        if direction != "exit" and len(groups) < 2:
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


def get_current_holdings() -> list[str]:
    """
    獲取當前持有部位的代碼列表 (Backward compatibility)
    """
    holdings = get_detailed_holdings()
    return [h["symbol"] for h in holdings]


def get_detailed_holdings() -> list[dict[str, Any]]:
    """
    獲取當前持有部位的詳細資訊
    """
    from config.config import DATA_DIR
    portfolio_path = DATA_DIR / "portfolio.json"
    if not portfolio_path.exists():
        return []
    try:
        import json
        with open(portfolio_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("holdings", [])
    except Exception:
        return []


def update_holdings(symbol: str, action: str = "add", **kwargs) -> bool:
    """
    更新持有部位 (add/remove)
    
    add 時可選參數:
        entry_date: YYYY-MM-DD
        entry_price: float
        horizon_days: int
        hypothesis_id: str
        direction: str
    """
    from config.config import DATA_DIR
    portfolio_path = DATA_DIR / "portfolio.json"
    detailed_holdings = get_detailed_holdings()
    
    if action == "add":
        # 如果已存在，先移除舊的 (更新資訊)
        detailed_holdings = [h for h in detailed_holdings if h["symbol"] != symbol]
        new_position = {
            "symbol": symbol,
            "entry_date": kwargs.get("entry_date", ""),
            "entry_price": float(kwargs.get("entry_price", 0.0)),
            "horizon_days": int(kwargs.get("horizon_days", 10)),
            "hypothesis_id": kwargs.get("hypothesis_id", "manual"),
            "direction": kwargs.get("direction", "long")
        }
        detailed_holdings.append(new_position)
    elif action == "remove":
        detailed_holdings = [h for h in detailed_holdings if h["symbol"] != symbol]
    else:
        return False
        
    try:
        import json
        with open(portfolio_path, 'w', encoding='utf-8') as f:
            json.dump({"holdings": detailed_holdings}, f, indent=4)
        return True
    except Exception:
        return False
