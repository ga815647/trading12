from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import PARQUET_DIR, ensure_runtime_dirs
from data.universe import UNIVERSE


DEFAULT_SYMBOLS = UNIVERSE[:30]


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(frame.reset_index(drop=True)), path)


def build_symbol_frames(stock_id: str, dates: pd.DatetimeIndex, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n = len(dates)

    base_price = 40 + (seed % 17) * 4
    trend = np.linspace(0, 18, n)
    seasonal = np.sin(np.arange(n) / 9.0) * 2.8
    fast = np.sin(np.arange(n) / 3.2) * 0.9
    noise = rng.normal(0, 0.35, n)

    buy_pulse = (np.arange(n) % 21 < 3).astype(float)
    breakout_pulse = (np.arange(n) % 34 == 0).astype(float)
    fear_pulse = (np.arange(n) % 55 > 46).astype(float)

    forward_boost = np.convolve(buy_pulse, np.array([0.0, 0.8, 0.6, 0.45, 0.3]), mode="same")
    breakdown_drag = np.convolve(fear_pulse, np.array([0.0, -0.55, -0.35, -0.2]), mode="same")
    close = base_price + trend + seasonal + fast + forward_boost + breakdown_drag + noise
    close = np.maximum(close, 10)

    open_price = close * (1 + rng.normal(0, 0.004, n))
    high = np.maximum(open_price, close) * (1 + np.abs(rng.normal(0.012, 0.004, n)))
    low = np.minimum(open_price, close) * (1 - np.abs(rng.normal(0.012, 0.004, n)))

    volume = (
        1_800_000
        + buy_pulse * 1_500_000
        + breakout_pulse * 2_200_000
        + fear_pulse * 800_000
        + (np.sin(np.arange(n) / 5.0) + 1.5) * 300_000
        + rng.normal(0, 120_000, n)
    )
    volume = np.maximum(volume, 150_000).astype(int)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    foreign_buy = 200 + buy_pulse * 780 + breakout_pulse * 260 + rng.normal(0, 30, n)
    foreign_sell = 160 + fear_pulse * 520 + rng.normal(0, 25, n)
    trust_buy = 95 + buy_pulse * 180 + rng.normal(0, 18, n)
    trust_sell = 90 + breakout_pulse * 75 + rng.normal(0, 18, n)
    dealer_buy = 55 + breakout_pulse * 60 + rng.normal(0, 10, n)
    dealer_sell = 52 + fear_pulse * 55 + rng.normal(0, 10, n)

    margin_balance = 3_000 + np.cumsum(20 + buy_pulse * 95 - fear_pulse * 65 + rng.normal(0, 12, n))
    short_balance = 420 + np.cumsum(2 + fear_pulse * 26 - buy_pulse * 8 + rng.normal(0, 3, n))

    kline = pd.DataFrame(
        {
            "date": dates,
            "open": open_price.round(2),
            "max": high.round(2),
            "min": low.round(2),
            "close": close.round(2),
            "Trading_Volume": volume,
            "prev_close": prev_close.round(2),
        }
    )

    chip = pd.DataFrame(
        {
            "date": dates,
            "Foreign_Investor_Buy": np.maximum(foreign_buy, 0).round(0),
            "Foreign_Investor_Sell": np.maximum(foreign_sell, 0).round(0),
            "Investment_Trust_Buy": np.maximum(trust_buy, 0).round(0),
            "Investment_Trust_Sell": np.maximum(trust_sell, 0).round(0),
            "Dealer_Buy": np.maximum(dealer_buy, 0).round(0),
            "Dealer_Sell": np.maximum(dealer_sell, 0).round(0),
        }
    )
    chip["Foreign_Investor_Net"] = chip["Foreign_Investor_Buy"] - chip["Foreign_Investor_Sell"]
    chip["Investment_Trust_Net"] = chip["Investment_Trust_Buy"] - chip["Investment_Trust_Sell"]
    chip["Dealer_Net"] = chip["Dealer_Buy"] - chip["Dealer_Sell"]

    margin = pd.DataFrame(
        {
            "date": dates,
            "MarginPurchaseBalance": np.maximum(margin_balance, 100).round(0),
            "MarginPurchaseBuy": np.maximum(80 + buy_pulse * 65 + rng.normal(0, 8, n), 0).round(0),
            "MarginPurchaseSell": np.maximum(75 + fear_pulse * 40 + rng.normal(0, 8, n), 0).round(0),
            "ShortSaleBalance": np.maximum(short_balance, 50).round(0),
            "ShortSaleSell": np.maximum(35 + fear_pulse * 16 + rng.normal(0, 5, n), 0).round(0),
            "ShortSaleBuy": np.maximum(32 + buy_pulse * 10 + rng.normal(0, 5, n), 0).round(0),
        }
    )

    return kline, chip, margin


def generate_mock_dataset(symbols: list[str], years: int = 6, seed: int = 42) -> None:
    ensure_runtime_dirs()
    periods = 252 * years
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=periods)

    for offset, stock_id in enumerate(symbols):
        kline, chip, margin = build_symbol_frames(stock_id, dates, seed + offset)
        _write_parquet(kline, PARQUET_DIR / f"{stock_id}_kline.parquet")
        _write_parquet(chip, PARQUET_DIR / f"{stock_id}_chip.parquet")
        _write_parquet(margin, PARQUET_DIR / f"{stock_id}_margin.parquet")

    print(f"Generated mock parquet data for {len(symbols)} symbols in {PARQUET_DIR}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate mock parquet data for local testing.")
    parser.add_argument("--symbols", type=int, default=len(DEFAULT_SYMBOLS), help="Number of universe symbols to generate.")
    parser.add_argument("--years", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = UNIVERSE[: max(1, min(args.symbols, len(UNIVERSE)))]
    generate_mock_dataset(symbols, years=args.years, seed=args.seed)


if __name__ == "__main__":
    main()
