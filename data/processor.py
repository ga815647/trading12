from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from config.config import PARQUET_DIR


COLUMN_MAP = {
    "date": "Date",
    "open": "Open",
    "max": "High",
    "min": "Low",
    "close": "Close",
    "Trading_Volume": "Volume",
    "trading_volume": "Volume",
    "volume": "Volume",
    "prev_close": "PrevClose",
}


CHIP_NAME_MAP = {
    "Foreign_Investor": "Foreign_Investor",
    "Foreign_Investor_self": "Foreign_Investor",
    "foreign": "Foreign_Investor",
    "foreign_investor": "Foreign_Investor",
    "Investment_Trust": "Investment_Trust",
    "investment_trust": "Investment_Trust",
    "Dealer": "Dealer",
    "dealer": "Dealer",
    "Dealer_self": "Dealer",
    "dealer_self": "Dealer",
}


MARGIN_ALIASES = {
    "MarginPurchaseTodayBalance": "MarginPurchaseBalance",
    "MarginPurchaseTodayBuyValue": "MarginPurchaseBuy",
    "MarginPurchaseTodaySellValue": "MarginPurchaseSell",
    "ShortSaleTodayBalance": "ShortSaleBalance",
    "ShortSaleTodaySellValue": "ShortSaleSell",
    "ShortSaleTodayBuyValue": "ShortSaleBuy",
}


def _parquet_path(stock_id: str, suffix: str) -> Path:
    return PARQUET_DIR / f"{stock_id}_{suffix}.parquet"


def _read_parquet(stock_id: str, suffix: str) -> pd.DataFrame:
    path = _parquet_path(stock_id, suffix)
    if not path.exists():
        raise FileNotFoundError(path)
    return pq.read_table(path).to_pandas()


def load_kline(stock_id: str) -> pd.DataFrame:
    df = _read_parquet(stock_id, "kline")
    df = df.rename(columns=COLUMN_MAP)
    if "Date" not in df.columns:
        raise KeyError(f"{stock_id} kline parquet is missing date column.")
    if "PrevClose" not in df.columns and "Close" in df.columns:
        df["PrevClose"] = df["Close"].shift(1)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    required = ["Open", "High", "Low", "Close", "Volume", "PrevClose"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"{stock_id} kline parquet is missing columns: {missing}")
    return df[required].dropna(subset=["Open", "High", "Low", "Close", "Volume"])


def _normalize_chip_long(df: pd.DataFrame) -> pd.DataFrame:
    if "date" not in df.columns:
        return df
    if {"name", "buy", "sell"}.issubset(df.columns):
        pivot_source = df.copy()
        pivot_source["name"] = (
            pivot_source["name"]
            .astype(str)
            .str.replace(" ", "_", regex=False)
            .map(lambda value: CHIP_NAME_MAP.get(value, value))
        )
        buy = pivot_source.pivot_table(
            index="date", columns="name", values="buy", aggfunc="sum"
        ).add_suffix("_Buy")
        sell = pivot_source.pivot_table(
            index="date", columns="name", values="sell", aggfunc="sum"
        ).add_suffix("_Sell")
        normalized = buy.join(sell, how="outer").fillna(0.0)
        for base in ["Foreign_Investor", "Investment_Trust", "Dealer"]:
            normalized[f"{base}_Net"] = (
                normalized.get(f"{base}_Buy", 0.0) - normalized.get(f"{base}_Sell", 0.0)
            )
        normalized.index = pd.to_datetime(normalized.index)
        return normalized.sort_index()
    return df


def load_chip(stock_id: str) -> pd.DataFrame:
    df = _read_parquet(stock_id, "chip")
    normalized = _normalize_chip_long(df)
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"])
        normalized = normalized.set_index("date")
    normalized.index = pd.to_datetime(normalized.index)
    return normalized.sort_index().fillna(0.0)


def load_margin(stock_id: str) -> pd.DataFrame:
    df = _read_parquet(stock_id, "margin")
    df = df.rename(columns=MARGIN_ALIASES)
    if "date" not in df.columns:
        raise KeyError(f"{stock_id} margin parquet is missing date column.")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.fillna(0.0)


def merge_market_data(stock_id: str) -> pd.DataFrame:
    kline = load_kline(stock_id)
    try:
        chip = load_chip(stock_id)
    except FileNotFoundError:
        chip = pd.DataFrame(index=kline.index)
    try:
        margin = load_margin(stock_id)
    except FileNotFoundError:
        margin = pd.DataFrame(index=kline.index)
    merged = kline.join(chip, how="left").join(margin, how="left")
    return merged.sort_index().fillna(0.0)
