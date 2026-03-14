from __future__ import annotations

import math
from statistics import mean
from typing import Any

import numpy as np
import pandas as pd

from config.config import (
    EDGE_DEFENSE_ENABLED,
    MIN_DAILY_TURNOVER_NTD,
    SHARES_PER_LOT,
    TRANSACTION_COST_PCT,
    OOS_YEARS,
)
from datetime import datetime, timedelta
from collections import defaultdict
from scipy import stats
from data.processor import merge_market_data
from data.universe import UNIVERSE
from engine.cost_model import DEFAULT_SHORT_BORROW_COST, apply_round_trip_cost
from engine.edge_defense import filter_by_turnover

# 提前啟用 pandas 新版降轉行為，讓潛在的 dtype 問題提早以 error 形式浮現
pd.set_option('future.no_silent_downcasting', True)


SEQUENCE_PATTERNS = {
    'trap_buy':          [-1, -1,  1, -1, -1],  
    'trap_sell':         [ 1,  1, -1,  1,  1],  
    'sell_5':            [-1, -1, -1, -1, -1],  
    'buy_5':             [ 1,  1,  1,  1,  1],  
    'sell_3':            [-1, -1, -1],          
    'buy_3':             [ 1,  1,  1],          
    'hesitate_sell':     [ 1,  1,  0, -1, -1],  
    'hesitate_buy':      [-1, -1,  0,  1,  1],  
    'sell_buy_sell':     [-1,  1, -1],          
    'buy_sell_buy':      [ 1, -1,  1],          
    'accelerate_sell':   [-1, -1, -1,  0, -1],  
    'accelerate_buy':    [ 1,  1,  1,  0,  1],  
}

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
    df["volume_lots"] = df["Volume"] / SHARES_PER_LOT
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
    df["stoch_d_3"] = df["stoch_14"].rolling(3).mean()
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


def detect_sequence(chip_series: pd.Series, pattern_name: str, threshold: float = 0.0) -> pd.Series:
    pattern = SEQUENCE_PATTERNS.get(pattern_name)
    if not pattern:
        return pd.Series(False, index=chip_series.index)
    n = len(pattern)
    pattern_arr = np.array(pattern)
    
    sig_arr = np.zeros(len(chip_series), dtype=int)
    sig_arr[chip_series > threshold] = 1
    sig_arr[chip_series < -threshold] = -1
    
    triggered = np.zeros(len(chip_series), dtype=bool)
    for i in range(n - 1, len(chip_series)):
        window = sig_arr[i - n + 1: i + 1]
        if np.array_equal(window, pattern_arr):
            triggered[i] = True
    return pd.Series(triggered, index=chip_series.index)


def calculate_tva_state(
    price_series: pd.Series,
    trend_period: int = 20,
    velocity_period: int = 5
) -> pd.Series:
    """
    計算 T/V/A 八狀態系統。
    
    T (趨勢): 價格相對趨勢線的位置
    V (速度): 價格變化的方向  
    A (加速度): 速度變化的方向
    
    回傳 1-8 的狀態代碼:
    1: T>0, V>0, A>0  (上升趨勢，加速向上)
    2: T>0, V>0, A<0  (上升趨勢，減速向上)
    3: T>0, V<0, A>0  (上升趨勢，加速向下)
    4: T>0, V<0, A<0  (上升趨勢，減速向下)
    5: T<0, V>0, A>0  (下降趨勢，加速向上)
    6: T<0, V>0, A<0  (下降趨勢，減速向上)
    7: T<0, V<0, A>0  (下降趨勢，加速向下)
    8: T<0, V<0, A<0  (下降趨勢，減速向下)
    """
    # T: 價格相對 MA(trend_period) 的位置
    ma_trend = price_series.rolling(trend_period).mean()
    T = (price_series - ma_trend) / ma_trend.replace(0, np.nan)
    
    # V: 價格變化方向 (當日-前日)
    V = price_series.diff(velocity_period)
    
    # A: 速度變化方向 (當日速度-前日速度)
    A = V.diff(velocity_period)
    
    # 計算狀態代碼
    states = pd.Series(0, index=price_series.index)
    
    # 狀態映射邏輯
    t_positive = T > 0
    v_positive = V > 0  
    a_positive = A > 0
    
    # 使用位元運算編碼狀態 (T*4 + V*2 + A*1 + 1)
    states[t_positive & v_positive & a_positive] = 1
    states[t_positive & v_positive & ~a_positive] = 2
    states[t_positive & ~v_positive & a_positive] = 3
    states[t_positive & ~v_positive & ~a_positive] = 4
    states[~t_positive & v_positive & a_positive] = 5
    states[~t_positive & v_positive & ~a_positive] = 6
    states[~t_positive & ~v_positive & a_positive] = 7
    states[~t_positive & ~v_positive & ~a_positive] = 8
    
    return states


def calculate_price_zone(
    price_series: pd.Series,
    window: int = 250
) -> pd.Series:
    """
    四/五區間價格框架 (Five-Zone Price Framework)
    回傳 0-4 的狀態代碼:
    0: 破壞價 (0.0 - 0.1) - breakdown zone
    1: 便宜區 (0.1 - 0.3) - cheap zone
    2: 合理區 (0.3 - 0.7) - fair zone
    3: 昂貴區 (0.7 - 0.9) - expensive zone
    4: 盤子價 (0.9 - 1.0) - bubble zone
    """
    rolling_min = price_series.rolling(window).min()
    rolling_max = price_series.rolling(window).max()
    
    # Calculate relative position (0 to 1)
    position = (price_series - rolling_min) / (rolling_max - rolling_min).replace(0, np.nan)
    
    zones = pd.Series(-1, index=price_series.index)
    zones[position <= 0.1] = 0
    zones[(position > 0.1) & (position <= 0.3)] = 1
    zones[(position > 0.3) & (position <= 0.7)] = 2
    zones[(position > 0.7) & (position <= 0.9)] = 3
    zones[position > 0.9] = 4
    
    return zones


def detect_group_sequence(
    leader_series: pd.Series,
    follower_series: pd.Series,
    leader_days: int = 3,
    follower_window: int = 5,
    divergence_threshold: float = 0.7,
) -> pd.Series:
    """
    偵測領先序列帶動跟隨序列的群體行為。
    使用 z-score 正規化後比較，避免單位不一致的問題（如張數 vs 比例）。
    divergence_threshold 代表標準差的倍數。
    """
    # Z-score 正規化（用 60 日滾動統計）
    def zscore(s: pd.Series, window: int = 60) -> pd.Series:
        mu = s.rolling(window, min_periods=10).mean()
        sigma = s.rolling(window, min_periods=10).std()
        return (s - mu) / sigma.replace(0, np.nan)

    leader_z = zscore(leader_series)
    follower_z = zscore(follower_series)

    leader_mean = leader_z.rolling(leader_days).mean()
    leader_direction = leader_mean.shift(follower_window)
    follower_avg = follower_z.rolling(follower_window).mean()

    valid_leader = leader_direction.abs() >= divergence_threshold
    triggered = valid_leader & (follower_avg.abs() > divergence_threshold)

    return triggered.fillna(False).astype(bool)


def build_signal_series(stock_id: str, frame: pd.DataFrame, hypothesis: dict[str, Any]) -> pd.Series:
    df = frame
    params = hypothesis.get("params", {})
    threshold_a = float(params.get("threshold_a", 200))
    consecutive_n = int(params.get("consecutive_n", 3))
    indicator_val = float(params.get("indicator_val", 30))
    bar_body_pct = float(params.get("bar_body_pct", 0.03))
    pattern_name = str(params.get("pattern_name", "buy_3"))
    chip_days = int(params.get("chip_days", 3))
    price_days = int(params.get("price_days", 1))
    divergence_threshold = float(params.get("divergence_threshold", 0.7))
    template_id = str(hypothesis.get("id", ""))

    if not is_supported_hypothesis(hypothesis):
        return pd.Series(False, index=df.index)

    # Multi-Layered Matrix (LM) Support
    matrix_filter_id = "NONE"
    if template_id.startswith("LM_"):
        # Format is LM_{TRIGGER}_{FILTER}_{INDEX}
        # Example: LM_A01_FLT_UP_TREND_0001
        parts = template_id.split("_")
        if len(parts) >= 4:
            # First part is LM, second is TRIGGER, last is INDEX
            # Everything between them is the FILTER
            template_id = parts[1]
            matrix_filter_id = "_".join(parts[2:-1])

    def get_signal_for_template(t_id: str) -> pd.Series:
        prefix = t_id[:1]
        if t_id == "A01":
            return (df["foreign_net"].rolling(consecutive_n).sum() > threshold_a) & (df["trust_net"].rolling(consecutive_n).sum() < 0)
        elif t_id == "A02":
            return (df["foreign_net"].rolling(consecutive_n).sum() > threshold_a) & (df["margin_balance"].diff(consecutive_n) > threshold_a)
        elif t_id == "A03":
            return df["inst_total_net"].rolling(consecutive_n).sum() > threshold_a
        elif t_id == "A04":
            return (df["foreign_net"].shift(1).rolling(consecutive_n).sum() > threshold_a) & (df["foreign_net"] < -threshold_a / max(consecutive_n, 1))
        elif t_id == "A05":
            return (df["trust_net"].rolling(consecutive_n).sum() > threshold_a) & (df["foreign_net"].rolling(consecutive_n).sum().abs() < threshold_a / 2)
        elif t_id == "B01":
            return df["inst_total_net"] > (df["inst_total_net"].rolling(consecutive_n).mean() + threshold_a)
        elif t_id == "B02":
            return df["n_return_5"] > (df["n_return_10"] + bar_body_pct)
        elif t_id == "B03":
            return df["volume_ma_5"] > df["volume_ma_20"] * (1 + bar_body_pct)
        elif t_id == "B04":
            return df["margin_balance"].diff() > (df["margin_balance"].diff().rolling(consecutive_n).mean() + threshold_a)
        elif t_id == "B05":
            return (df["Close"].pct_change(consecutive_n) < -bar_body_pct) & (df["Close"].pct_change(max(2, consecutive_n // 2)) > bar_body_pct / 2)
        elif t_id == "C01":
            return pd.Series(stock_id in SEMICONDUCTOR_PEERS and stock_id != "2330", index=df.index) & (df["foreign_net"].rolling(consecutive_n).sum() > threshold_a)
        elif t_id == "C02":
            return (df["Close"] > df["price_ma_20"]) & (df["n_return_10"] > bar_body_pct)
        elif t_id == "C03":
            return (df["Close"] < df["price_high_60"] * (1 - bar_body_pct)) & (df["Close"] > df["price_ma_20"])
        elif t_id == "C04":
            return pd.Series(stock_id in EXPORTER_PEERS, index=df.index) & (df["n_return_5"] > bar_body_pct)
        elif t_id == "C05":
            return (df["Close"] < df["price_ma_20"] * (1 - bar_body_pct)) & (df["inst_total_net"] > 0)
        elif t_id == "E01":
            return df["rsi_14"] < indicator_val
        elif t_id == "E02":
            return df["stoch_14"] < indicator_val
        elif t_id == "E03":
            return df["Close"].pct_change(consecutive_n) < -bar_body_pct
        elif t_id == "E04":
            return df["short_balance"] > df["short_balance"].rolling(60).quantile(0.8)
        elif t_id == "E05":
            return df["Close"] < df["price_low_20"] * (1 + bar_body_pct / 2)
        elif t_id == "F01":
            return (df["days_to_month_end"] <= consecutive_n) & (df["inst_total_net"].rolling(consecutive_n).sum() > 0)
        elif t_id == "F03":
            return (df["quarter_month"] == 1) & (df["day"] <= consecutive_n) & (df["foreign_net"] > 0)
        elif t_id == "F04":
            return (df["month"] == 12) & (df["days_to_month_end"] <= consecutive_n)
        elif t_id == "F05":
            return (df["month"] == 1) & (df["day"] <= max(consecutive_n * 3, 10))
        elif t_id == "G01":
            return (df["Close"] >= df["price_high_20"]) & (df["Volume"] < df["volume_ma_20"])
        elif t_id == "G02":
            return (df["Close"] <= df["price_low_20"]) & (df["Volume"] < df["volume_ma_20"] * 0.7)
        elif t_id == "G03":
            return (df["upper_shadow_pct"] > bar_body_pct) & (df["Volume"] > df["volume_ma_20"] * 1.5)
        elif t_id == "G04":
            return (df["Volume"] < df["volume_ma_20"] * 0.7) & (df["Close"] > df["price_high_20"].shift(1))
        elif t_id == "G05":
            return df["Volume"] < df["volume_ma_20"] * 0.5
        elif t_id == "H01":
            return (df["Close"].pct_change() > -bar_body_pct / 2) & (df["Low"] < df["price_low_20"] * (1 + bar_body_pct))
        elif t_id == "H02":
            return (df["n_return_10"] > bar_body_pct) & (df["body_pct"] < bar_body_pct / 2)
        elif t_id == "H03":
            return (df["n_return_5"] > -bar_body_pct / 2) & (df["Close"].pct_change(consecutive_n) > df["Close"].pct_change(consecutive_n * 2))
        elif t_id == "H04":
            return (df["margin_balance"].diff(consecutive_n) < -threshold_a) & (df["Close"] > df["price_ma_20"])
        elif t_id == "H05":
            return (df["foreign_net"].rolling(consecutive_n).sum() < -threshold_a) & (df["Volume"] > df["volume_ma_20"] * 1.3) & (df["Close"] > df["Open"])
        elif t_id == "J01":
            return df["margin_balance"] > df["margin_balance"].rolling(120).quantile(0.8)
        elif t_id == "J02":
            return df["Volume"] > df["Volume"].rolling(60).quantile(0.9)
        elif t_id == "J03":
            ratio = df["margin_balance"] / df["short_balance"].replace(0, np.nan)
            return ratio > max(indicator_val / 5, 2)
        elif t_id == "J04":
            return df["Close"].pct_change(consecutive_n) < -bar_body_pct
        elif t_id == "J05":
            return (df["High"] - df["Low"]) / df["Open"].replace(0, np.nan) > bar_body_pct * 2
        elif t_id == "J06":
            from config.sentiment_layers import get_sentiment_layer_filter
            sentiment_filter = get_sentiment_layer_filter(df["margin_balance"], df["Volume"], df["Close"], ["smart_money_entry"])
            return sentiment_filter & (df["inst_total_net"] > threshold_a)
        elif t_id == "J07":
            from config.sentiment_layers import get_sentiment_layer_filter
            sentiment_filter = get_sentiment_layer_filter(df["margin_balance"], df["Volume"], df["Close"], ["smart_money_exit"])
            return sentiment_filter & (df["inst_total_net"] < -threshold_a)
        elif t_id == "J08":
            from config.sentiment_layers import get_sentiment_layer_filter
            sentiment_filter = get_sentiment_layer_filter(df["margin_balance"], df["Volume"], df["Close"], ["crowd_chase"])
            return sentiment_filter & (df["margin_balance"].diff(3) > threshold_a)
        elif t_id == "J09":
            from config.sentiment_layers import get_sentiment_layer_filter
            sentiment_filter = get_sentiment_layer_filter(df["margin_balance"], df["Volume"], df["Close"], ["crowd_panic"])
            return sentiment_filter & (df["Close"].pct_change(consecutive_n) < -bar_body_pct)
        elif t_id == "J10":
            from config.sentiment_layers import SentimentLayerSystem
            system = SentimentLayerSystem()
            layer_series = system.create_sentiment_layer_series(df["margin_balance"], df["Volume"], df["Close"])
            neutral_to_extreme = (layer_series.shift(1).isin(["neutral", "insufficient_data"])) & (layer_series.isin(["crowd_chase", "crowd_panic", "smart_money_entry", "smart_money_exit"]))
            return neutral_to_extreme
        elif t_id == "K01":
            return detect_sequence(df["foreign_net"], pattern_name, threshold_a)
        elif t_id == "K02":
            return detect_sequence(df["trust_net"], pattern_name, threshold_a)
        elif t_id == "K03":
            return detect_sequence(df["inst_total_net"], pattern_name, threshold_a)
        elif t_id == "K04":
            return detect_sequence(df["foreign_net"], pattern_name, threshold_a) & (df["margin_balance"].diff(3) > threshold_a * 5)
        elif t_id == "K05":
            return detect_sequence(df["foreign_net"], pattern_name, threshold_a) & (df["stoch_14"] < indicator_val)
        elif t_id == "L01":
            inst_streak = (df["inst_total_net"] > 0).rolling(chip_days).sum() == chip_days
            price_streak = (df["close_return"] > 0).rolling(price_days).sum() == price_days
            kd_bull = df["stoch_14"] > df["stoch_d_3"]
            price_streak_shifted = price_streak.shift(1).fillna(False).astype(bool)
            return inst_streak & price_streak_shifted & kd_bull
        elif t_id == "M01":
            return detect_group_sequence(df["foreign_net"], df["trust_net"], 3, 5, divergence_threshold)
        elif t_id == "M02":
            return detect_group_sequence(df["foreign_net"], df["margin_balance"].diff(), 3, 5, divergence_threshold)
        elif t_id == "M03":
            return detect_group_sequence(df["foreign_net"] + df["trust_net"], df["margin_balance"].diff(), 3, 5, divergence_threshold)
        elif t_id == "FLT_UP_TREND":
            ma20 = df["Close"].rolling(20).mean()
            return (df["Close"] > ma20) & (ma20 > ma20.shift(1))
        elif t_id == "FLT_VOL_SHRINK":
            vol_ma5 = df["Volume"].rolling(5).mean()
            return df["Volume"].shift(1) < (vol_ma5.shift(1) * 0.8)
        elif t_id == "FLT_KD_OVERSOLD":
            return (df["stoch_14"] < 30) & (df["stoch_d_3"] < 30)
        elif t_id.startswith("TVA") or t_id.startswith("PZ_"):
            # These are parameter-based post-filters handled later in step 3/4
            return pd.Series(True, index=df.index)
        elif prefix == "E":
            return df["rsi_14"] < indicator_val
        else:
            return pd.Series(False, index=df.index)

    # 1. Trigger
    signal = get_signal_for_template(template_id)

    # 2. Matrix Filter
    if matrix_filter_id != "NONE":
        filter_signal = get_signal_for_template(matrix_filter_id)
        signal = signal & filter_signal

    # 3. Post-Filter (TVA)
    state_filter = params.get("state_filter")
    if state_filter is not None and isinstance(state_filter, (int, list)):
        current_states = calculate_tva_state(df["Close"])
        if isinstance(state_filter, int):
            signal = signal & (current_states == state_filter)
        else:
            signal = signal & (current_states.isin(state_filter))

    # 4. Post-Filter (Price Zone)
    price_zone = params.get("price_zone")
    if price_zone is not None and isinstance(price_zone, (int, list)):
        current_zones = calculate_price_zone(df["Close"])
        if isinstance(price_zone, int):
            signal = signal & (current_zones == price_zone)
        else:
            signal = signal & (current_zones.isin(price_zone))

    return signal.fillna(False).astype(bool)


def infer_direction(hypothesis: dict[str, Any]) -> str:
    template_id = str(hypothesis.get("id", ""))
    # 解析 LM_ 前綴取得真正的 trigger ID
    if template_id.startswith("LM_"):
        parts = template_id.split("_")
        template_id = parts[1] if len(parts) >= 2 else template_id
    if template_id in {"G03"}:
        return "exit"
    if template_id in {"J01", "J02", "J03", "L02"}:
        return "short"
    return "long"


def _trade_return(direction: str, entry_open: float, exit_close: float) -> float:
    if entry_open <= 0 or exit_close <= 0:
        raise ValueError("Trade prices must be positive.")
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
    
    # Convert to NumPy for 400x faster loop access compared to .iloc
    signal_arr = signal.to_numpy()
    open_arr = frame["Open"].to_numpy()
    close_arr = frame["Close"].to_numpy()
    prev_close_arr = frame["PrevClose"].to_numpy()
    dates = frame.index.strftime('%Y-%m-%d').to_list()
    
    if EDGE_DEFENSE_ENABLED:
        vol_arr = frame["Volume"].to_numpy()
    
    idx = 0
    max_idx = len(frame) - horizon_days - 1
    
    while idx < max_idx:
        if not signal_arr[idx]:
            idx += 1
            continue
            
        entry_idx = idx + 1
        exit_idx = entry_idx + horizon_days - 1
        
        entry_open = float(open_arr[entry_idx])
        prev_close = float(prev_close_arr[entry_idx])
        
        if entry_open <= 0 or prev_close <= 0:
            idx += 1
            continue
            
        if is_limit_up(entry_open, prev_close) or is_limit_down(entry_open, prev_close):
            idx += 1
            continue
            
        if EDGE_DEFENSE_ENABLED:
            vol = float(vol_arr[entry_idx])
            price = float(close_arr[entry_idx])
            if not filter_by_turnover(vol, price, MIN_DAILY_TURNOVER_NTD):
                idx += 1
                continue
                
        exit_close = float(close_arr[exit_idx])
        if exit_close <= 0:
            idx += 1
            continue
            
        raw_return = _trade_return(direction, entry_open, exit_close)
        net_return = apply_round_trip_cost(raw_return)
        
        trades.append(
            {
                "stock_id": stock_id,
                "direction": direction,
                "entry_date": dates[entry_idx],
                "exit_date": dates[exit_idx],
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

def _portfolio_sharpe(trades: list[dict]) -> float:
    """
    把同日在倉的交易合併成當日組合報酬，再計算年化 Sharpe。
    每筆交易在 entry_date 到 exit_date 之間每個交易日貢獻 net_return / holding_days。
    最後對每個日期的平均報酬計算 Sharpe。
    """
    if not trades:
        return 0.0
    
    # 若 trades 數量超過 10000 筆，抽樣最近 2000 筆以控制效能
    if len(trades) > 10000:
        trades = trades[-2000:]
    
    daily_returns = defaultdict(list)
    
    for trade in trades:
        try:
            entry = datetime.strptime(trade["entry_date"], "%Y-%m-%d")
            exit_  = datetime.strptime(trade["exit_date"],  "%Y-%m-%d")
            holding = max(trade["holding_days"], 1)
            daily_ret = trade["net_return"] / holding
            
            current = entry
            while current <= exit_:
                daily_returns[current].append(daily_ret)
                current += timedelta(days=1)
        except Exception:
            continue
    
    if not daily_returns:
        return 0.0
    
    sorted_dates = sorted(daily_returns.keys())
    port_returns = np.array([np.mean(daily_returns[d]) for d in sorted_dates])
    
    if len(port_returns) < 5 or np.std(port_returns, ddof=1) == 0:
        return 0.0
    
    return float(np.mean(port_returns) / np.std(port_returns, ddof=1) * np.sqrt(252))


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
                "portfolio_sharpe": 0.0,
                "p_value": 1.0,
            }
        )
        return summary

    cutoff = max(
        datetime.strptime(t["exit_date"], "%Y-%m-%d") for t in trades
    ) - timedelta(days=OOS_YEARS * 365)

    is_returns  = np.asarray(
        [t["net_return"] for t in trades
         if datetime.strptime(t["exit_date"], "%Y-%m-%d") < cutoff],
        dtype=float
    )
    oos_returns = np.asarray(
        [t["net_return"] for t in trades
         if datetime.strptime(t["exit_date"], "%Y-%m-%d") >= cutoff],
        dtype=float
    )
    returns = np.asarray(summary["trade_returns"], dtype=float)  # 全量，僅用於 p_value/avg
    avg_holding = mean(trade["holding_days"] for trade in trades)
    sharpe_scale = math.sqrt(252 / max(avg_holding, 1))
    
    # Calculate individual trade sharpe
    if len(returns) > 1 and np.std(returns, ddof=1) > 0:
        sharpe = float(np.mean(returns) / np.std(returns, ddof=1) * sharpe_scale)
        try:
            # Assuming scipy.stats is imported
            p_value = float(
                stats.ttest_1samp(returns, popmean=0.0, alternative="greater").pvalue
            )
        except Exception:
            z_score = float(np.mean(returns) / (np.std(returns, ddof=1) / math.sqrt(len(returns))))
            p_value = max(0.0, min(1.0, 0.5 * math.erfc(z_score / math.sqrt(2))))
    else:
        sharpe = 0.0
        p_value = 1.0

    # Calculate portfolio sharpe
    portfolio_sharpe = _portfolio_sharpe(trades)

    summary.update(
        {
            "win_rate":        float((is_returns > 0).mean()) if len(is_returns) else 0.0,
            "oos_win_rate":    float((oos_returns > 0).mean()) if len(oos_returns) else 0.0,
            "is_count":        int(len(is_returns)),
            "oos_count":       int(len(oos_returns)),
            "avg_return":      float(np.mean(returns)),
            "median_return":   float(np.median(returns)),
            "sharpe":          sharpe,            # 保留 per-trade sharpe 供參考
            "portfolio_sharpe": portfolio_sharpe, # 新增：組合層面 sharpe
            "p_value":         p_value,
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
    force: bool = False,
) -> dict[str, Any] | None:
    frame = market_cache.get(stock_id) if market_cache is not None else prepare_market_frame(stock_id)
    if frame is None or len(frame) < 60:
        return None
    signal = build_signal_series(stock_id, frame, hypothesis)

    # 只在訊號首次觸發時推播（從 False 變成 True）
    # 若今天觸發且昨天也觸發，視為持續訊號，不重複推播
    signal_today     = bool(signal.iloc[-1])
    signal_yesterday = bool(signal.iloc[-2]) if len(signal) >= 2 else False

    if not signal_today:
        return None
    if signal_yesterday and not force:
        # 訊號持續，非新訊號，跳過（force=True 時強制推播）
        return None

    latest = frame.iloc[-1]
    return {
        "stock_id":     stock_id,
        "direction":    infer_direction(hypothesis),
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "signal_id":    hypothesis.get("signal_id"),
        "id":           hypothesis.get("id"),
        "desc":         hypothesis.get("desc"),
        "group":        hypothesis.get("group", str(hypothesis.get("id", ""))[:1]),
        "horizon_days": int(hypothesis.get("params", {}).get("horizon_days", 10)),
        "close":        float(latest["Close"]),
        "open":         float(latest["Open"]),
        "win_rate":     float(hypothesis.get("win_rate", 0.0)),
        "sample_count": int(hypothesis.get("sample_count", 0)),
        "portfolio_sharpe": float(hypothesis.get("portfolio_sharpe", 0.0)),
    }
