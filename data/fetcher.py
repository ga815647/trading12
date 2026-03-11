from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import PARQUET_DIR, SETTINGS, ensure_runtime_dirs
from data.universe import UNIVERSE


START_DATE = "2015-01-01"
MAX_RETRY = 3
SLEEP_BETWEEN_STOCKS = 3.0


def build_loader():
    if not SETTINGS.finmind_token:
        raise ValueError("FINMIND_TOKEN is required.")
    try:
        from FinMind.data import DataLoader
    except ImportError as exc:
        raise RuntimeError("FinMind package is not installed.") from exc
    loader = DataLoader()
    loader.login_by_token(api_token=SETTINGS.finmind_token)
    return loader


def fetch_with_retry(func: Callable[..., pd.DataFrame], **kwargs) -> pd.DataFrame | None:
    for attempt in range(1, MAX_RETRY + 1):
        try:
            result = func(**kwargs)
            if result is not None and len(result) > 0:
                return result
        except Exception as exc:
            print(f"[retry {attempt}/{MAX_RETRY}] {kwargs.get('stock_id', '')} {exc}")
        time.sleep(10 * attempt)
    return None


def _merge_existing(path: Path, fresh: pd.DataFrame) -> pd.DataFrame:
    if not path.exists():
        return fresh
    existing = pq.read_table(path).to_pandas()
    combined = pd.concat([existing, fresh], ignore_index=True)
    subset = ["date"]
    if "name" in combined.columns:
        subset.append("name")
    return combined.drop_duplicates(subset=subset, keep="last").sort_values(subset)


def _write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df.reset_index(drop=True))
    pq.write_table(table, path)


def _last_start_date(stock_id: str, suffix: str) -> str:
    path = PARQUET_DIR / f"{stock_id}_{suffix}.parquet"
    if not path.exists():
        return START_DATE
    frame = pq.read_table(path, columns=["date"]).to_pandas()
    if frame.empty:
        return START_DATE
    latest = pd.to_datetime(frame["date"]).max().date()
    return str(latest - timedelta(days=7))


def fetch_and_save(loader, stock_id: str, mode: str = "full") -> None:
    start_date = START_DATE if mode == "full" else _last_start_date(stock_id, "kline")
    print(f"Fetching {stock_id} from {start_date}")

    kline = fetch_with_retry(
        loader.taiwan_stock_daily,
        stock_id=stock_id,
        start_date=start_date,
    )
    chip = fetch_with_retry(
        loader.taiwan_stock_institutional_investors,
        stock_id=stock_id,
        start_date=start_date,
    )
    margin = fetch_with_retry(
        loader.taiwan_stock_margin_purchase_short_sale,
        stock_id=stock_id,
        start_date=start_date,
    )

    if kline is not None:
        kline = kline.sort_values("date").reset_index(drop=True)
        kline["prev_close"] = kline["close"].shift(1)
        kline_path = PARQUET_DIR / f"{stock_id}_kline.parquet"
        _write_table(_merge_existing(kline_path, kline), kline_path)

    if chip is not None:
        chip_path = PARQUET_DIR / f"{stock_id}_chip.parquet"
        _write_table(_merge_existing(chip_path, chip), chip_path)

    if margin is not None:
        margin_path = PARQUET_DIR / f"{stock_id}_margin.parquet"
        _write_table(_merge_existing(margin_path, margin), margin_path)

    print(f"[ok] {stock_id}")
    time.sleep(SLEEP_BETWEEN_STOCKS)


def run_batch(mode: str, symbols: list[str]) -> list[str]:
    ensure_runtime_dirs()
    loader = build_loader()
    failed: list[str] = []
    for stock_id in symbols:
        try:
            fetch_and_save(loader, stock_id, mode=mode)
        except Exception as exc:
            print(f"[fail] {stock_id}: {exc}")
            failed.append(stock_id)
    return failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Taiwan stock data from FinMind.")
    parser.add_argument("--mode", choices=["full", "daily"], default="full")
    parser.add_argument("--symbol", action="append", dest="symbols")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = args.symbols or UNIVERSE
    failed = run_batch(mode=args.mode, symbols=symbols)
    if failed:
        print("Failed symbols:", ",".join(failed))
    else:
        print(f"Completed {len(symbols)} symbols on {date.today().isoformat()}")


if __name__ == "__main__":
    main()
