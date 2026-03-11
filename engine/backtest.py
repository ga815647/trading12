from __future__ import annotations

import math
from statistics import mean
from typing import Any

import numpy as np
import pandas as pd

from data.processor import merge_market_data
from data.universe import UNIVERSE
from engine.cost_model import DEFAULT_SHORT_BORROW_COST, apply_round_trip_cost


SEMICONDUCTOR_PEERS = {
    "2330",
    "2303",
    "2308",
    "2327",
    "2344",
    "2379",
    "2454",
    "3034",
    "3443",
    "3711",
    "4966",
}

EXPORTER_PEERS = {"2317", "2357", "2382", "2395", "3037", "4938"}

UNSUPPORTED_TEMPLATE_IDS = {"F02"}
UNSUPPORTED_PREFIXES = {"D", "I"}


def is_limit_up(open_price: float, prev_close: float) -> bool:
    return prev_close > 0 and (open_price - prev_close) / prev_close >= 0.095


def is_limit_down(open_price: float, prev_close: float) -> bool:
    return prev_close > 0 and (open_price - prev_close) / prev_close <= -0.095


def is_supported_hypothesis(hypothesis: dict[str, Any]) -> bool:
    template_id = str(hypothesis.get("id", ""))
    return template_id not in UNSUPPORTED_TEMPLATE_IDS and template_id[:1] not in UNSUPPORTED_PREFIXES


def _get_col(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame.columns:
        return frame[name].astype(float)
    return pd.Series(0.0, index=frame.index)


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    lowest = low.rolling(window).min()
    highest = high.rolling(window).max()
    return (close - lowest) / (highest - lowest).replace(0, np.nan) * 100


def _enrich(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["foreign_net"] = _get_col(df, "Foreign_Investor_Net")
    df["trust_net"] = _get_col(df, "Investment_Trust_Net")
    df["dealer_net"] = _get_col(df, "Dealer_Net")
    df["inst_total_net"] = df["foreign_net"] + df["trust_net"] + df["dealer_net"]
    df["margin_balance"] = _get_col(df, "MarginPurchaseBalance")
    df["short_balance"] = _get_col(df, "ShortSaleBalance")
    df["close_return"] = df["Close"].pct_change()
    df["n_return_5"] = df["Close"].pct_change(5)
    df["n_return_10"] = df["Close"].pct_change(10)
    df["volume_ma_5"] = df["Volume"].rolling(5).mean()
    df["volume_ma_20"] = df["Volume"].rolling(20).mean()
    df["price_ma_20"] = df["Close"].rolling(20).mean()
    df["price_high_20"] = df["Close"].rolling(20).max()
    df["price_low_20"] = df["Close"].rolling(20).min()
    df["price_high_60"] = df["Close"].rolling(60).max()
    df["body_pct"] = (df["Close"] - df["Open"]).abs() / df["Open"].replace(0, np.nan)
    df["upper_shadow_pct"] = (df["High"] - df[["Open", "Close"]].max(axis=1)) / df["Open"].replace(0, np.nan)
    df["rsi_14"] = _rsi(df["Close"], 14)
    df["stoch_14"] = _stochastic(df["High"], df["Low"], df["Close"], 14)
    df["month"] = df.index.month
    df["day"] = df.index.day
    df["days_to_month_end"] = df.index.to_series().dt.days_in_month - df.index.day
    df["quarter_month"] = df.index.month.isin([3, 6, 9, 12]).astype(int)
    return df.replace([np.inf, -np.inf], np.nan)


def prepare_market_frame(stock_id: str) -> pd.DataFrame | None:
    try:
        frame = merge_market_data(stock_id)
    except FileNotFoundError:
        return None
    if len(frame) < 90:
        return None
    return _enrich(frame)


def load_market_cache(universe: list[str] | None = None) -> dict[str, pd.DataFrame]:
    cache: dict[str, pd.DataFrame] = {}
    for stock_id in universe or UNIVERSE:
        prepared = prepare_market_frame(stock_id)
        if prepared is not None:
            cache[stock_id] = prepared
    return cache


def build_signal_series(stock_id: str, frame: pd.DataFrame, hypothesis: dict[str, Any]) -> pd.Series:
    df = frame
    params = hypothesis.get("params", {})
    threshold_a = float(params.get("threshold_a", 200))
    consecutive_n = int(params.get("consecutive_n", 3))
    indicator_val = float(params.get("indicator_val", 30))
    bar_body_pct = float(params.get("bar_body_pct", 0.03))
    template_id = str(hypothesis.get("id", ""))

    if not is_supported_hypothesis(hypothesis):
        return pd.Series(False, index=df.index)

    prefix = template_id[:1]
    if template_id == "A01":
        signal = (
            df["foreign_net"].rolling(consecutive_n).sum() > threshold_a
        ) & (df["trust_net"].rolling(consecutive_n).sum() < 0)
    elif template_id == "A02":
        signal = (
            df["foreign_net"].rolling(consecutive_n).sum() > threshold_a
        ) & (df["margin_balance"].diff(consecutive_n) > threshold_a)
    elif template_id == "A03":
        signal = df["inst_total_net"].rolling(consecutive_n).sum() > threshold_a
    elif template_id == "A04":
        signal = (
            df["foreign_net"].shift(1).rolling(consecutive_n).sum() > threshold_a
        ) & (df["foreign_net"] < -threshold_a / max(consecutive_n, 1))
    elif template_id == "A05":
        signal = (
            df["trust_net"].rolling(consecutive_n).sum() > threshold_a
        ) & (df["foreign_net"].rolling(consecutive_n).sum().abs() < threshold_a / 2)
    elif template_id == "B01":
        signal = df["inst_total_net"] > (
            df["inst_total_net"].rolling(consecutive_n).mean() + threshold_a
        )
    elif template_id == "B02":
        signal = df["n_return_5"] > (df["n_return_10"] + bar_body_pct)
    elif template_id == "B03":
        signal = df["volume_ma_5"] > df["volume_ma_20"] * (1 + bar_body_pct)
    elif template_id == "B04":
        signal = df["margin_balance"].diff() > (
            df["margin_balance"].diff().rolling(consecutive_n).mean() + threshold_a
        )
    elif template_id == "B05":
        signal = (df["Close"].pct_change(consecutive_n) < -bar_body_pct) & (
            df["Close"].pct_change(max(2, consecutive_n // 2)) > bar_body_pct / 2
        )
    elif template_id == "C01":
        signal = pd.Series(stock_id in SEMICONDUCTOR_PEERS and stock_id != "2330", index=df.index) & (
            df["foreign_net"].rolling(consecutive_n).sum() > threshold_a
        )
    elif template_id == "C02":
        signal = (df["Close"] > df["price_ma_20"]) & (df["n_return_10"] > bar_body_pct)
    elif template_id == "C03":
        signal = (df["Close"] < df["price_high_60"] * (1 - bar_body_pct)) & (
            df["Close"] > df["price_ma_20"]
        )
    elif template_id == "C04":
        signal = pd.Series(stock_id in EXPORTER_PEERS, index=df.index) & (
            df["n_return_5"] > bar_body_pct
        )
    elif template_id == "C05":
        signal = (df["Close"] < df["price_ma_20"] * (1 - bar_body_pct)) & (
            df["inst_total_net"] > 0
        )
    elif template_id == "E01":
        signal = df["rsi_14"] < indicator_val
    elif template_id == "E02":
        signal = df["stoch_14"] < indicator_val
    elif template_id == "E03":
        signal = df["Close"].pct_change(consecutive_n) < -bar_body_pct
    elif template_id == "E04":
        signal = df["short_balance"] > df["short_balance"].rolling(60).quantile(0.8)
    elif template_id == "E05":
        signal = df["Close"] < df["price_low_20"] * (1 + bar_body_pct / 2)
    elif template_id == "F01":
        signal = (df["days_to_month_end"] <= consecutive_n) & (
            df["inst_total_net"].rolling(consecutive_n).sum() > 0
        )
    elif template_id == "F03":
        signal = (df["quarter_month"] == 1) & (df["day"] <= consecutive_n) & (df["foreign_net"] > 0)
    elif template_id == "F04":
        signal = (df["month"] == 12) & (df["days_to_month_end"] <= consecutive_n)
    elif template_id == "F05":
        signal = (df["month"] == 1) & (df["day"] <= max(consecutive_n * 3, 10))
    elif template_id == "G01":
        signal = (df["Close"] >= df["price_high_20"]) & (df["Volume"] < df["volume_ma_20"])
    elif template_id == "G02":
        signal = (df["Close"] <= df["price_low_20"]) & (df["Volume"] < df["volume_ma_20"] * 0.7)
    elif template_id == "G03":
        signal = (df["upper_shadow_pct"] > bar_body_pct) & (df["Volume"] > df["volume_ma_20"] * 1.5)
    elif template_id == "G04":
        signal = (df["Volume"] < df["volume_ma_20"] * 0.7) & (df["Close"] > df["price_high_20"].shift(1))
    elif template_id == "G05":
        signal = df["Volume"] < df["volume_ma_20"] * 0.5
    elif template_id == "H01":
        signal = (df["Close"].pct_change() > -bar_body_pct / 2) & (df["Low"] < df["price_low_20"] * (1 + bar_body_pct))
    elif template_id == "H02":
        signal = (df["n_return_10"] > bar_body_pct) & (df["body_pct"] < bar_body_pct / 2)
    elif template_id == "H03":
        signal = (df["n_return_5"] > -bar_body_pct / 2) & (
            df["Close"].pct_change(consecutive_n) > df["Close"].pct_change(consecutive_n * 2)
        )
    elif template_id == "H04":
        signal = (df["margin_balance"].diff(consecutive_n) < -threshold_a) & (
            df["Close"] > df["price_ma_20"]
        )
    elif template_id == "H05":
        signal = (df["foreign_net"].rolling(consecutive_n).sum() < -threshold_a) & (
            df["Volume"] > df["volume_ma_20"] * 1.3
        ) & (df["Close"] > df["Open"])
    elif template_id == "J01":
        signal = df["margin_balance"] > df["margin_balance"].rolling(120).quantile(0.8)
    elif template_id == "J02":
        signal = df["Volume"] > df["Volume"].rolling(60).quantile(0.9)
    elif template_id == "J03":
        ratio = df["margin_balance"] / df["short_balance"].replace(0, np.nan)
        signal = ratio > max(indicator_val / 5, 2)
    elif template_id == "J04":
        signal = df["Close"].pct_change(consecutive_n) < -bar_body_pct
    elif template_id == "J05":
        signal = (df["High"] - df["Low"]) / df["Open"].replace(0, np.nan) > bar_body_pct * 2
    elif prefix == "E":
        signal = df["rsi_14"] < indicator_val
    else:
        signal = pd.Series(False, index=df.index)
    return signal.fillna(False).astype(bool)


def infer_direction(hypothesis: dict[str, Any]) -> str:
    template_id = str(hypothesis.get("id", ""))
    if template_id in {"G03"}:
        return "exit"
    if template_id in {"J01", "J02", "J03"}:
        return "short"
    return "long"


def _trade_return(direction: str, entry_open: float, exit_close: float) -> float:
    if direction == "short":
        raw = (entry_open - exit_close) / entry_open
        return raw - DEFAULT_SHORT_BORROW_COST
    return (exit_close - entry_open) / entry_open


def backtest_stock(
    stock_id: str,
    frame: pd.DataFrame,
    hypothesis: dict[str, Any],
) -> list[dict[str, Any]]:
    direction = infer_direction(hypothesis)
    horizon_days = int(hypothesis.get("params", {}).get("horizon_days", 10))
    signal = build_signal_series(stock_id, frame, hypothesis)
    trades: list[dict[str, Any]] = []
    idx = 0
    while idx < len(frame) - horizon_days - 1:
        if not bool(signal.iloc[idx]):
            idx += 1
            continue
        entry_idx = idx + 1
        exit_idx = entry_idx + horizon_days - 1
        if exit_idx >= len(frame):
            break
        entry_open = float(frame["Open"].iloc[entry_idx])
        prev_close = float(frame["PrevClose"].iloc[entry_idx])
        if is_limit_up(entry_open, prev_close) or is_limit_down(entry_open, prev_close):
            idx += 1
            continue
        exit_close = float(frame["Close"].iloc[exit_idx])
        raw_return = _trade_return(direction, entry_open, exit_close)
        net_return = apply_round_trip_cost(raw_return)
        trades.append(
            {
                "stock_id": stock_id,
                "direction": direction,
                "entry_date": str(frame.index[entry_idx].date()),
                "exit_date": str(frame.index[exit_idx].date()),
                "entry_price": entry_open,
                "exit_price": exit_close,
                "holding_days": horizon_days,
                "gross_return": raw_return,
                "net_return": net_return,
                "pnl": net_return,
            }
        )
        idx = exit_idx + 1
    return trades


def summarize_hypothesis(hypothesis: dict[str, Any], trades: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "id": hypothesis.get("id"),
        "desc": hypothesis.get("desc"),
        "params": hypothesis.get("params", {}),
        "direction": infer_direction(hypothesis),
        "supported": is_supported_hypothesis(hypothesis),
        "sample_count": len(trades),
        "trade_dates": [trade["exit_date"] for trade in trades],
        "trade_returns": [trade["net_return"] for trade in trades],
        "recent_trade_pnls": [trade["pnl"] for trade in trades[-100:]],
    }
    if not trades:
        summary.update(
            {
                "win_rate": 0.0,
                "oos_win_rate": 0.0,
                "avg_return": 0.0,
                "median_return": 0.0,
                "sharpe": 0.0,
                "p_value": 1.0,
            }
        )
        return summary

    returns = np.asarray(summary["trade_returns"], dtype=float)
    split_idx = max(1, int(len(returns) * 0.7))
    oos_slice = returns[split_idx:]
    avg_holding = mean(trade["holding_days"] for trade in trades)
    sharpe_scale = math.sqrt(252 / max(avg_holding, 1))
    if len(returns) > 1 and np.std(returns, ddof=1) > 0:
        sharpe = float(np.mean(returns) / np.std(returns, ddof=1) * sharpe_scale)
        try:
            from scipy import stats

            p_value = float(
                stats.ttest_1samp(returns, popmean=0.0, alternative="greater").pvalue
            )
        except Exception:
            z_score = float(np.mean(returns) / (np.std(returns, ddof=1) / math.sqrt(len(returns))))
            p_value = max(0.0, min(1.0, 0.5 * math.erfc(z_score / math.sqrt(2))))
    else:
        sharpe = 0.0
        p_value = 1.0
    summary.update(
        {
            "win_rate": float((returns > 0).mean()),
            "oos_win_rate": float((oos_slice > 0).mean()) if len(oos_slice) else 0.0,
            "avg_return": float(np.mean(returns)),
            "median_return": float(np.median(returns)),
            "sharpe": sharpe,
            "p_value": p_value,
        }
    )
    return summary


def run_hypothesis_backtest(
    hypothesis: dict[str, Any],
    universe: list[str] | None = None,
    market_cache: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    all_trades: list[dict[str, Any]] = []
    frames = market_cache if market_cache is not None else load_market_cache(universe)
    for stock_id, frame in frames.items():
        stock_trades = backtest_stock(stock_id, frame, hypothesis)
        all_trades.extend(stock_trades)
    return summarize_hypothesis(hypothesis, all_trades)


def evaluate_latest_signal(
    stock_id: str,
    hypothesis: dict[str, Any],
    market_cache: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any] | None:
    frame = market_cache.get(stock_id) if market_cache is not None else prepare_market_frame(stock_id)
    if frame is None or len(frame) < 60:
        return None
    signal = build_signal_series(stock_id, frame, hypothesis)
    if not bool(signal.iloc[-1]):
        return None
    latest = frame.iloc[-1]
    return {
        "stock_id": stock_id,
        "direction": infer_direction(hypothesis),
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "signal_id": hypothesis.get("signal_id"),
        "id": hypothesis.get("id"),
        "desc": hypothesis.get("desc"),
        "group": hypothesis.get("group", str(hypothesis.get("id", ""))[:1]),
        "horizon_days": int(hypothesis.get("params", {}).get("horizon_days", 10)),
        "close": float(latest["Close"]),
        "open": float(latest["Open"]),
    }
