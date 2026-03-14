"""
Time-decay scoring for validator.
Anchor = max(trade_dates) from batch; NEVER use datetime.now().
"""
from __future__ import annotations

from datetime import datetime


RECENT_2Y_DAYS = 500
DEFAULT_LAMBDA = 1.0
T_MAX_DAYS = 3650


def _parse_date(d: str) -> datetime:
    if isinstance(d, datetime):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d")


def anchor_date(trade_dates: list[str]) -> datetime | None:
    """Day 0 = max(trade_dates). Never use system date."""
    if not trade_dates:
        return None
    return max(_parse_date(d) for d in trade_dates)


def days_ago(anchor: datetime, date_str: str) -> int:
    return (anchor - _parse_date(date_str)).days


def time_weight(days_ago_val: int, decay_lambda: float = DEFAULT_LAMBDA) -> float:
    """Exponential decay: w = exp(-lambda * days_ago / T_max)."""
    if days_ago_val < 0:
        days_ago_val = 0
    return float(
        __import__("math").exp(-decay_lambda * days_ago_val / T_MAX_DAYS)
    )


def compute_weighted_win_rate(
    trade_dates: list[str],
    trade_returns: list[float],
    decay_lambda: float = DEFAULT_LAMBDA,
) -> tuple[float, int]:
    """
    Weighted win rate. Anchor = max(trade_dates).
    Returns (weighted_win_rate, total_weighted_count).
    """
    if not trade_dates or not trade_returns or len(trade_dates) != len(trade_returns):
        return 0.0, 0

    anchor = anchor_date(trade_dates)
    if anchor is None:
        return 0.0, 0

    weighted_wins = 0.0
    total_weight = 0.0
    for dt_str, ret in zip(trade_dates, trade_returns):
        d = days_ago(anchor, dt_str)
        w = time_weight(d, decay_lambda)
        total_weight += w
        if float(ret) > 0:
            weighted_wins += w

    if total_weight <= 0:
        return 0.0, 0
    return weighted_wins / total_weight, int(round(total_weight))


def compute_recent_stats(
    trade_dates: list[str],
    trade_returns: list[float],
    recent_days: int = RECENT_2Y_DAYS,
) -> tuple[float | None, int]:
    """
    Recent N days stats. Anchor = max(trade_dates).
    Returns (recent_win_rate, recent_count). Win rate is None if recent_count < 1.
    """
    if not trade_dates or not trade_returns or len(trade_dates) != len(trade_returns):
        return None, 0

    anchor = anchor_date(trade_dates)
    if anchor is None:
        return None, 0

    recent_returns: list[float] = []
    for dt_str, ret in zip(trade_dates, trade_returns):
        d = days_ago(anchor, dt_str)
        if d <= recent_days:
            recent_returns.append(float(ret))

    n = len(recent_returns)
    if n == 0:
        return None, 0
    wins = sum(1 for r in recent_returns if r > 0)
    return wins / n, n
