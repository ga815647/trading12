from __future__ import annotations
from config.config import TRANSACTION_COST_PCT

DEFAULT_SHORT_BORROW_COST = 0.003

def apply_round_trip_cost(raw_return: float) -> float:
    """
    Deducts the total friction (Fee + Tax) from the raw return.
    """
    return raw_return - TRANSACTION_COST_PCT

def minimum_gross_return() -> float:
    return TRANSACTION_COST_PCT
