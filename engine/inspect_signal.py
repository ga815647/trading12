from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import HYPOTHESIS_DIR, SIGNAL_DIR, ensure_runtime_dirs
from config.encrypt import load_encrypted_json
from engine.backtest import build_signal_series, load_market_cache


def load_json_items(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_hypothesis(
    hypothesis_id: str,
    hypothesis_file: Path,
    signal_file: Path,
) -> dict[str, Any]:
    if signal_file.exists():
        for item in load_encrypted_json(signal_file):
            if str(item.get("hypothesis_id")) == hypothesis_id:
                return item
    if hypothesis_file.exists():
        for item in load_json_items(hypothesis_file):
            if str(item.get("hypothesis_id")) == hypothesis_id:
                return item
    raise SystemExit(f"Hypothesis not found: {hypothesis_id}")


def inspect_recent_triggers(
    hypothesis: dict[str, Any],
    lookback_days: int,
) -> tuple[str, list[dict[str, Any]]]:
    cache = load_market_cache()
    latest_date = "n/a"
    recent_hits: list[dict[str, Any]] = []
    for stock_id, frame in cache.items():
        signal = build_signal_series(stock_id, frame, hypothesis)
        latest_date = str(frame.index[-1].date())
        window = signal.iloc[-lookback_days:]
        hit_dates = [str(idx.date()) for idx, value in window.items() if bool(value)]
        if hit_dates:
            recent_hits.append(
                {
                    "stock_id": stock_id,
                    "hit_dates": hit_dates,
                    "hit_count": len(hit_dates),
                    "latest_hit_date": hit_dates[-1],
                }
            )
    return latest_date, recent_hits


def export_recent_hits(
    output_path: Path,
    hypothesis: dict[str, Any],
    latest_date: str,
    lookback_days: int,
    recent_hits: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    rows = [
        {
            "hypothesis_id": str(hypothesis.get("hypothesis_id")),
            "template_id": str(hypothesis.get("id")),
            "latest_market_date": latest_date,
            "lookback_days": lookback_days,
            "stock_id": item["stock_id"],
            "hit_count": item["hit_count"],
            "latest_hit_date": item["latest_hit_date"],
            "hit_dates": ",".join(item["hit_dates"]),
        }
        for item in recent_hits
    ]
    if suffix == ".json":
        payload = {
            "hypothesis_id": hypothesis.get("hypothesis_id"),
            "template_id": hypothesis.get("id"),
            "latest_market_date": latest_date,
            "lookback_days": lookback_days,
            "count": len(rows),
            "items": rows,
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return
    if suffix != ".csv":
        raise SystemExit(f"Unsupported output format: {output_path.suffix}")
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "hypothesis_id",
                "template_id",
                "latest_market_date",
                "lookback_days",
                "stock_id",
                "hit_count",
                "latest_hit_date",
                "hit_dates",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def inspect_b05_latest(hypothesis: dict[str, Any]) -> dict[str, Any]:
    params = hypothesis.get("params", {})
    bar_body_pct = float(params.get("bar_body_pct", 0.07))
    consecutive_n = int(params.get("consecutive_n", 5))
    short_window = max(2, consecutive_n // 2)
    cache = load_market_cache()

    rows: list[dict[str, Any]] = []
    latest_date = "n/a"
    for stock_id, frame in cache.items():
        latest_date = str(frame.index[-1].date())
        ret_long = float(frame["Close"].pct_change(consecutive_n).iloc[-1])
        ret_short = float(frame["Close"].pct_change(short_window).iloc[-1])
        cond1 = ret_long < -bar_body_pct
        cond2 = ret_short > bar_body_pct / 2
        miss1 = ret_long + bar_body_pct
        miss2 = ret_short - bar_body_pct / 2
        rows.append(
            {
                "stock_id": stock_id,
                "ret_long": ret_long,
                "ret_short": ret_short,
                "cond1": cond1,
                "cond2": cond2,
                "score": min(miss1, 0.0) + min(miss2, 0.0),
                "miss1": miss1,
                "miss2": miss2,
            }
        )

    rows.sort(key=lambda item: item["score"], reverse=True)
    return {
        "latest_date": latest_date,
        "total_symbols": len(rows),
        "both": sum(item["cond1"] and item["cond2"] for item in rows),
        "only_cond1": sum(item["cond1"] and not item["cond2"] for item in rows),
        "only_cond2": sum((not item["cond1"]) and item["cond2"] for item in rows),
        "neither": sum((not item["cond1"]) and (not item["cond2"]) for item in rows),
        "near_miss": rows[:10],
        "long_window": consecutive_n,
        "short_window": short_window,
        "bar_body_pct": bar_body_pct,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect latest trigger status for one hypothesis.")
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument(
        "--hypothesis-file",
        default=str(HYPOTHESIS_DIR / "batch_001.json"),
    )
    parser.add_argument(
        "--signal-file",
        default=str(SIGNAL_DIR / "library_real_relaxed.enc"),
    )
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    hypothesis = resolve_hypothesis(
        args.hypothesis_id,
        Path(args.hypothesis_file),
        Path(args.signal_file),
    )
    print(f"Hypothesis: {hypothesis.get('hypothesis_id')} ({hypothesis.get('id')})")
    print(f"Desc: {hypothesis.get('desc')}")
    print(f"Params: {hypothesis.get('params', {})}")

    latest_date, recent_hits = inspect_recent_triggers(hypothesis, args.lookback_days)
    triggered_today = sum(item["latest_hit_date"] == latest_date for item in recent_hits)
    print(f"Latest market date: {latest_date}")
    print(f"Triggered today: {triggered_today}")
    print(f"Triggered in last {args.lookback_days} day(s): {len(recent_hits)}")
    for item in recent_hits[:20]:
        print(f"  {item['stock_id']}: {', '.join(item['hit_dates'])}")
    if args.output:
        output_path = Path(args.output)
        export_recent_hits(output_path, hypothesis, latest_date, args.lookback_days, recent_hits)
        print(f"Exported recent hits: {output_path}")

    if str(hypothesis.get("id")) == "B05":
        details = inspect_b05_latest(hypothesis)
        print(
            "B05 latest condition split: "
            f"both={details['both']}, "
            f"only_cond1={details['only_cond1']}, "
            f"only_cond2={details['only_cond2']}, "
            f"neither={details['neither']}"
        )
        print(
            "B05 thresholds: "
            f"{details['long_window']}d_return < {-details['bar_body_pct']:.4f}, "
            f"{details['short_window']}d_return > {details['bar_body_pct'] / 2:.4f}"
        )
        print("Top near misses:")
        for item in details["near_miss"]:
            print(
                "  "
                f"{item['stock_id']} "
                f"ret{details['long_window']}={item['ret_long']:.4f} "
                f"ret{details['short_window']}={item['ret_short']:.4f} "
                f"cond1={item['cond1']} cond2={item['cond2']}"
            )


if __name__ == "__main__":
    main()
