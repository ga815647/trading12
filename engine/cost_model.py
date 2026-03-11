from __future__ import annotations


BACKTEST_COMMISSION = 0.002925
ROUND_TRIP_COST = BACKTEST_COMMISSION * 2
DEFAULT_SHORT_BORROW_COST = 0.003


def apply_round_trip_cost(raw_return: float) -> float:
    return raw_return - ROUND_TRIP_COST


def minimum_gross_return() -> float:
    return ROUND_TRIP_COST
