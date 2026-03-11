from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import BACKTEST_DIR, HYPOTHESIS_DIR, ensure_runtime_dirs
from config.encrypt import save_signal


def run_single(hypothesis: dict) -> dict:
    from engine.backtest import run_hypothesis_backtest

    return run_hypothesis_backtest(hypothesis)


def run_all(hypothesis_file: Path) -> list[dict]:
    hypotheses = json.loads(hypothesis_file.read_text(encoding="utf-8"))
    results: list[dict] = []
    for hypothesis in hypotheses:
        result = run_single(hypothesis)
        results.append(result)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch strategy backtests.")
    parser.add_argument(
        "--hypothesis-file",
        default=str(HYPOTHESIS_DIR / "batch_001.json"),
    )
    parser.add_argument(
        "--output",
        default=str(BACKTEST_DIR / "batch_001.enc"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    hypothesis_path = Path(args.hypothesis_file)
    if not hypothesis_path.exists():
        raise SystemExit(f"Hypothesis file not found: {hypothesis_path}")
    results = run_all(hypothesis_path)
    output = save_signal(results, args.output)
    print(f"Completed {len(results)} backtests into {output}")


if __name__ == "__main__":
    main()
