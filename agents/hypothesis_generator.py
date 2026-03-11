from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import HYPOTHESIS_DIR, ensure_runtime_dirs


HYPOTHESIS_TEMPLATES = [
    {"id": "A01", "desc": "Foreign net buy conflicts with trust selling."},
    {"id": "A02", "desc": "Foreign net buy while margin balance surges."},
    {"id": "A03", "desc": "All major institutions align on buying."},
    {"id": "A04", "desc": "Foreign buying streak flips to a sell wave."},
    {"id": "A05", "desc": "Trust buys while foreign flow stays neutral."},
    {"id": "B01", "desc": "Institutional buying accelerates above trend."},
    {"id": "B02", "desc": "Price momentum accelerates above prior slope."},
    {"id": "B03", "desc": "Volume expansion accelerates above trend."},
    {"id": "B04", "desc": "Margin expansion accelerates above trend."},
    {"id": "B05", "desc": "Negative momentum flips back to positive."},
    {"id": "C01", "desc": "Sector leader flow propagates to peers."},
    {"id": "C02", "desc": "Benchmark strength spills into constituents."},
    {"id": "C03", "desc": "Peer laggards follow a sector leader breakout."},
    {"id": "C04", "desc": "Upstream strength spills into downstream names."},
    {"id": "C05", "desc": "Weak relative ranking mean reverts in sector."},
    {"id": "D01", "desc": "EPS growth diverges from foreign selling."},
    {"id": "D02", "desc": "EPS contraction diverges from foreign buying."},
    {"id": "D03", "desc": "Margin expansion diverges from weak sponsorship."},
    {"id": "D04", "desc": "Valuation proxy and flow shift conflict."},
    {"id": "D05", "desc": "Fundamental surprise is not priced in."},
    {"id": "E01", "desc": "RSI oversold mean reversion."},
    {"id": "E02", "desc": "Stochastic oversold mean reversion."},
    {"id": "E03", "desc": "Large drawdown mean reversion."},
    {"id": "E04", "desc": "Short pressure reaches an extreme."},
    {"id": "E05", "desc": "Deep valuation proxy discount mean reverts."},
    {"id": "F01", "desc": "Month-end institutional window dressing."},
    {"id": "F02", "desc": "Dividend event timing edge."},
    {"id": "F03", "desc": "Quarter-end positioning ahead of filings."},
    {"id": "F04", "desc": "Year-end dressing in target groups."},
    {"id": "F05", "desc": "January effect in smaller names."},
    {"id": "G01", "desc": "New high with shrinking volume divergence."},
    {"id": "G02", "desc": "Breakdown with no follow-through volume."},
    {"id": "G03", "desc": "High-volume upper shadow reversal."},
    {"id": "G04", "desc": "Volume squeeze then breakout."},
    {"id": "G05", "desc": "Extreme dry-up in turnover."},
    {"id": "H01", "desc": "Bad news priced in but price holds."},
    {"id": "H02", "desc": "Good news exhaustion with no lift."},
    {"id": "H03", "desc": "Stock stays strong during market drop."},
    {"id": "H04", "desc": "Margin washout triggers reversal."},
    {"id": "H05", "desc": "Foreign selling streak ends with reversal volume."},
    {"id": "I01", "desc": "SOX move transmits to Taiwan peers."},
    {"id": "I02", "desc": "DXY shock transmits to exporters."},
    {"id": "I03", "desc": "VIX spike mean reverts into Taiwan."},
    {"id": "I04", "desc": "US yield shock transmits to financials."},
    {"id": "I05", "desc": "JPY move transmits to exporters."},
    {"id": "J01", "desc": "Margin frenzy signals overheating."},
    {"id": "J02", "desc": "Market turnover hits an extreme."},
    {"id": "J03", "desc": "Retail sentiment proxy becomes extreme."},
    {"id": "J04", "desc": "Market panic triggers mean reversion."},
    {"id": "J05", "desc": "Breadth imbalance reaches an extreme."},
]

PARAM_GRIDS = {
    "threshold_a": [100, 200, 300, 500, 800, 1000],
    "consecutive_n": [2, 3, 5, 8, 10],
    "indicator_val": [20, 25, 30, 35, 40],
    "bar_body_pct": [0.02, 0.03, 0.05, 0.07],
    "horizon_days": [10, 15, 20, 30, 45, 60],
}

PHASE1_SKIP = ["D", "F02", "I"]


def should_skip(template_id: str) -> bool:
    return template_id == "F02" or any(template_id.startswith(prefix) for prefix in ["D", "I"])


def generate_batch(
    template: dict[str, Any],
    batch_size: int = 200,
    random_seed: int | None = None,
) -> list[dict[str, Any]]:
    if should_skip(template["id"]):
        return []
    rng = random.Random(random_seed or template["id"])
    all_combos = list(itertools.product(*PARAM_GRIDS.values()))
    sampled = rng.sample(all_combos, min(batch_size, len(all_combos)))
    keys = list(PARAM_GRIDS.keys())
    return [
        {
            **template,
            "params": dict(zip(keys, combo)),
            "hypothesis_id": f"{template['id']}_{index:04d}",
        }
        for index, combo in enumerate(sampled, start=1)
    ]


def generate_all(batch_size: int = 200, random_seed: int = 42) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for index, template in enumerate(HYPOTHESIS_TEMPLATES):
        hypotheses.extend(generate_batch(template, batch_size, random_seed + index))
    return hypotheses


def save_batch(hypotheses: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(hypotheses, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate strategy hypotheses.")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        default=str(HYPOTHESIS_DIR / "batch_001.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    hypotheses = generate_all(batch_size=args.batch_size, random_seed=args.seed)
    output_path = save_batch(hypotheses, Path(args.output))
    print(f"Generated {len(hypotheses)} hypotheses into {output_path}")


if __name__ == "__main__":
    main()
