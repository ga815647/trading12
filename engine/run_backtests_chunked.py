from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import BACKTEST_DIR, HYPOTHESIS_DIR, ensure_runtime_dirs
from config.encrypt import save_signal
from engine.run_backtests import load_hypotheses, run_many, select_hypotheses
from tqdm import tqdm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backtests in resumable chunks.")
    parser.add_argument(
        "--hypothesis-file",
        default=str(HYPOTHESIS_DIR / "batch_001.json"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(BACKTEST_DIR / "chunks"),
    )
    parser.add_argument("--chunk-size", type=int, default=250)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunksize", type=int, default=12)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--count", type=int)
    parser.add_argument(
        "--no-inner-progress",
        action="store_true",
        help="Disable per-hypothesis progress for each chunk.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    hypothesis_path = Path(args.hypothesis_file)
    if not hypothesis_path.exists():
        raise SystemExit(f"Hypothesis file not found: {hypothesis_path}")

    all_hypotheses = load_hypotheses(hypothesis_path)
    selected = select_hypotheses(all_hypotheses, args.start_index, args.count)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(selected)
    total_chunks = math.ceil(total / args.chunk_size) if total else 0
    existing_outputs = []
    for chunk_no in range(total_chunks):
        start = chunk_no * args.chunk_size
        end = min(total, start + args.chunk_size)
        global_start = args.start_index + start
        global_end = args.start_index + end - 1
        output_path = output_dir / f"chunk_{global_start:05d}_{global_end:05d}.enc"
        if output_path.exists():
            existing_outputs.append(output_path)

    progress = tqdm(
        total=total_chunks,
        initial=len(existing_outputs),
        dynamic_ncols=True,
        unit="chunk",
        desc="Chunked backtests",
        file=sys.stdout,
    )

    for chunk_no in range(total_chunks):
        start = chunk_no * args.chunk_size
        end = min(total, start + args.chunk_size)
        chunk_hypotheses = selected[start:end]
        global_start = args.start_index + start
        global_end = args.start_index + end - 1
        output_path = output_dir / f"chunk_{global_start:05d}_{global_end:05d}.enc"
        if output_path.exists():
            progress.set_postfix_str(f"skip {global_start}-{global_end}")
            progress.update(1)
            continue
        progress.set_postfix_str(f"run {global_start}-{global_end}")
        results = run_many(
            chunk_hypotheses,
            workers=args.workers,
            chunksize=args.chunksize,
            show_progress=not args.no_inner_progress,
            progress_desc=f"Hyp {global_start}-{global_end}",
        )
        save_signal(results, output_path)
        progress.update(1)
        progress.set_postfix_str(f"saved {global_start}-{global_end}")

    progress.close()
    print(
        f"Completed chunked backtests: {total_chunks} chunks, "
        f"{total} hypotheses, output_dir={output_dir}"
    )


if __name__ == "__main__":
    main()
