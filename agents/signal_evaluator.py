from __future__ import annotations

from typing import Any

from engine.validator import validate_backtests


def evaluate_backtests(backtests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return validate_backtests(backtests)
