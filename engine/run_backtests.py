from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import BACKTEST_DIR, HYPOTHESIS_DIR, ensure_runtime_dirs
from config.encrypt import save_signal


_WORKER_MARKET_CACHE: dict | None = None


def run_single(hypothesis: dict, market_cache: dict | None = None) -> dict:
    from engine.backtest import run_hypothesis_backtest

    return run_hypothesis_backtest(hypothesis, market_cache=market_cache)


def _init_worker() -> None:
    from engine.backtest import load_market_cache

    global _WORKER_MARKET_CACHE
    _WORKER_MARKET_CACHE = load_market_cache()


def _run_single_worker(hypothesis: dict) -> dict:
    return run_single(hypothesis, market_cache=_WORKER_MARKET_CACHE)


def run_all(hypothesis_file: Path, workers: int = 1, chunksize: int = 10) -> list[dict]:
    from engine.backtest import load_market_cache

    hypotheses = json.loads(hypothesis_file.read_text(encoding="utf-8"))
    if workers <= 1:
        market_cache = load_market_cache()
        return [run_single(hypothesis, market_cache=market_cache) for hypothesis in hypotheses]

    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as executor:
        return list(executor.map(_run_single_worker, hypotheses, chunksize=chunksize))


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
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(4, os.cpu_count() or 1)),
    )
    parser.add_argument("--chunksize", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    hypothesis_path = Path(args.hypothesis_file)
    if not hypothesis_path.exists():
        raise SystemExit(f"Hypothesis file not found: {hypothesis_path}")
    results = run_all(hypothesis_path, workers=args.workers, chunksize=args.chunksize)
    output = save_signal(results, args.output)
    print(f"Completed {len(results)} backtests into {output} using {args.workers} worker(s)")


if __name__ == "__main__":
    main()
