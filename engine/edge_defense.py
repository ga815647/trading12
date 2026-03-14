"""
Extreme edge-case robustness.
Volume: FinMind uses shares (股). 1 lot (張) = 1000 shares.
"""
from __future__ import annotations


def filter_by_liquidity(
    volume_shares: float,
    min_volume_lots: int,
    shares_per_lot: int = 1000,
) -> bool:
    """
    True = passes (sufficient liquidity). False = filter out (illiquid).
    volume_shares: FinMind Trading_Volume (股)
    min_volume_lots: minimum acceptable volume in lots (張)
    """
    min_shares = min_volume_lots * shares_per_lot
    return float(volume_shares) >= min_shares
