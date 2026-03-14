from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import BACKTEST_DIR, HYPOTHESIS_DIR, ensure_runtime_dirs
from config.encrypt import save_signal
from tqdm import tqdm


_WORKER_MARKET_CACHE: dict | None = None


def run_single(hypothesis: dict, market_cache: dict | None = None) -> dict:
    from engine.backtest import run_hypothesis_backtest

    return run_hypothesis_backtest(hypothesis, market_cache=market_cache)


def _init_worker() -> None:
    from engine.backtest import load_market_cache

    global _WORKER_MARKET_CACHE
    _WORKER_MARKET_CACHE = load_market_cache()


def _run_single_worker(hypothesis: dict) -> dict:
    from datetime import datetime
    print(f"[{datetime.now()}] Worker executing: {hypothesis.get('hypothesis_id')}", flush=True)
    return run_single(hypothesis, market_cache=_WORKER_MARKET_CACHE)
def load_hypotheses(hypothesis_file: Path) -> list[dict]:
    return json.loads(hypothesis_file.read_text(encoding="utf-8"))


def select_hypotheses(
    hypotheses: list[dict],
    start_index: int = 0,
    count: int | None = None,
) -> list[dict]:
    start_index = max(0, start_index)
    if count is None:
        return hypotheses[start_index:]
    return hypotheses[start_index : start_index + max(0, count)]


def run_many(
    hypotheses: list[dict],
    workers: int = 1,
    chunksize: int = 10,
    show_progress: bool = False,
    progress_desc: str = "Backtests",
    is_shutdown: callable | None = None,
) -> list[dict]:
    from engine.backtest import load_market_cache

    if workers <= 1:
        market_cache = load_market_cache()
        results = []
        progress = None
        if show_progress:
            progress = tqdm(
                total=len(hypotheses),
                desc=progress_desc,
                dynamic_ncols=True,
                unit="hyp",
                file=sys.stdout,
            )
        
        for index, hypothesis in enumerate(hypotheses, start=1):
            if is_shutdown and is_shutdown():
                break
            print(f"[{index}/{len(hypotheses)}] Single Worker executing: {hypothesis.get('hypothesis_id')}", flush=True)
            result = run_single(hypothesis, market_cache=market_cache)
            results.append(result)
            if progress:
                progress.update(1)
                progress.set_postfix_str(f"done {index}/{len(hypotheses)}")
        
        if progress:
            progress.close()
        return results

    import multiprocessing

    # Multiprocessing
    results: list[dict | None] = [None] * len(hypotheses)
    ctx = multiprocessing.get_context("spawn")
    executor = ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_init_worker)
    
    progress = None
    if show_progress:
        progress = tqdm(
            total=len(hypotheses),
            desc=progress_desc,
            dynamic_ncols=True,
            unit="hyp",
            file=sys.stdout,
        )
        
    futures = {}
    for index, hypothesis in enumerate(hypotheses):
        if is_shutdown and is_shutdown():
            break
        futures[executor.submit(_run_single_worker, hypothesis)] = index
    
    completed = 0
    try:
        # Use a generator expression with a list cast to avoid iterating over a moving target
        # or being blocked by as_completed internal locks during shutdown
        for future in as_completed(futures):
            # Check shutdown BEFORE processing each result
            if is_shutdown and is_shutdown():
                break
            
            try:
                index = futures[future]
                results[index] = future.result()
                completed += 1
                if progress:
                    progress.update(1)
                    progress.set_postfix_str(f"done {completed}/{len(hypotheses)}")
            except (KeyboardInterrupt, BrokenProcessPool):
                break
            except Exception as e:
                # If a single task fails, we log and continue unless it's a shutdown
                if is_shutdown and is_shutdown():
                    break
                print(f"\nTask failed: {e}")
                
    except (KeyboardInterrupt, BrokenProcessPool):
        pass
    except Exception as e:
        executor.shutdown(wait=False, cancel_futures=True)
        raise e
    finally:
        if progress:
            progress.close()
        
        is_hard_shutdown = is_shutdown and is_shutdown()
        if is_hard_shutdown:
            # Force shutdown the executor to prevent hanging
            executor.shutdown(wait=False, cancel_futures=True)
            return [result for result in results if result is not None]
        
        executor.shutdown(wait=True)

    return [result for result in results if result is not None]


def run_all(
    hypothesis_file: Path,
    workers: int = 1,
    chunksize: int = 10,
    start_index: int = 0,
    count: int | None = None,
    show_progress: bool = False,
    progress_desc: str = "Backtests",
    is_shutdown: callable | None = None,
) -> list[dict]:
    hypotheses = load_hypotheses(hypothesis_file)
    selected = select_hypotheses(hypotheses, start_index=start_index, count=count)
    return run_many(
        selected,
        workers=workers,
        chunksize=chunksize,
        show_progress=show_progress,
        progress_desc=progress_desc,
        is_shutdown=is_shutdown,
    )


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
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--count", type=int)
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Show a live progress bar while backtests are running.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    hypothesis_path = Path(args.hypothesis_file)
    if not hypothesis_path.exists():
        raise SystemExit(f"Hypothesis file not found: {hypothesis_path}")
    results = run_all(
        hypothesis_path,
        workers=args.workers,
        chunksize=args.chunksize,
        start_index=args.start_index,
        count=args.count,
        show_progress=args.progress,
    )
    output = save_signal(results, args.output)
    print(
        f"Completed {len(results)} backtests into {output} using {args.workers} worker(s)"
    )


if __name__ == "__main__":
    main()
