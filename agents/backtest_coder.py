from __future__ import annotations

from typing import Any


def build_backtest_payload(hypothesis: dict[str, Any]) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "template_id": hypothesis.get("id"),
        "params": hypothesis.get("params", {}),
        "desc": hypothesis.get("desc", ""),
        "family": str(hypothesis.get("id", ""))[:1],
    }
