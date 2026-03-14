"""
Extreme edge-case robustness.
Liquidity check via Daily Turnover (NTD).
"""
from __future__ import annotations


def filter_by_turnover(
    volume_shares: float,
    close_price: float,
    min_turnover_ntd: float,
) -> bool:
    """
    True = passes (sufficient turnover). False = filter out (illiquid).
    volume_shares: Daily Trading Volume (股)
    close_price: Daily Close Price (元)
    min_turnover_ntd: Minimum acceptable turnover in NTD (元)
    """
    turnover = float(volume_shares) * float(close_price)
    return turnover >= min_turnover_ntd
