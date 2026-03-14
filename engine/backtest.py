from __future__ import annotations

import math
from statistics import mean
from typing import Any

import numpy as np
import pandas as pd

from config.config import (
    EDGE_DEFENSE_ENABLED,
    MIN_DAILY_VOLUME_LOTS,
    SHARES_PER_LOT,
)
from data.processor import merge_market_data
from data.universe import UNIVERSE
from engine.cost_model import DEFAULT_SHORT_BORROW_COST, apply_round_trip_cost
from engine.edge_defense import filter_by_liquidity


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
    
    triggered = pd.Series(False, index=chip_series.index)
    for i in range(n - 1, len(chip_series)):
        window = sig_arr[i - n + 1: i + 1]
        if np.array_equal(window, pattern_arr):
            triggered.iloc[i] = True
    return triggered


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


def detect_group_sequence(
    leader_series: pd.Series,
    follower_series: pd.Series,
    leader_days: int = 3,
    follower_window: int = 5,
    divergence_threshold: float = 0.7
) -> pd.Series:
    """
    偵測 M 類群體行為序列。
    
    檢查先動者持續某方向後，後動者是否在指定窗口內跟進。
    支援順序擴散（相同方向）和背離（相反方向）偵測。
    """
    triggered = pd.Series(False, index=leader_series.index)
    
    for i in range(leader_days + follower_window - 1, len(leader_series)):
        # 檢查先動者連續方向
        leader_window = leader_series.iloc[i - follower_window - leader_days + 1: i - follower_window + 1]
        leader_direction = leader_window.mean()  # 正值表示買超趨勢
        
        if abs(leader_direction) < divergence_threshold:
            continue
            
        # 檢查後動者在窗口內的行為
        follower_window_data = follower_series.iloc[i - follower_window + 1: i + 1]
        follower_avg = follower_window_data.mean()
        
        # 順序擴散：方向相同且後動者幅度達門檻
        if (leader_direction > 0 and follower_avg > divergence_threshold) or \
           (leader_direction < 0 and follower_avg < -divergence_threshold):
            triggered.iloc[i] = True
        # 背離：方向相反（危險訊號）
        elif (leader_direction > 0 and follower_avg < -divergence_threshold) or \
             (leader_direction < 0 and follower_avg > divergence_threshold):
            triggered.iloc[i] = True
    
    return triggered


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
    divergence_threshold = float(params.get("divergence_threshold", 0.7))  # M 類專用參數
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
    elif template_id == "J06":
        # 少數人買入區間：臨界點突破前
        from config.sentiment_layers import get_sentiment_layer_filter
        sentiment_filter = get_sentiment_layer_filter(
            df["margin_balance"], df["Volume"], df["Close"], ["smart_money_entry"]
        )
        signal = sentiment_filter & (df["inst_total_net"] > threshold_a)
    elif template_id == "J07":
        # 少數人賣出區間：臨界點突破前
        from config.sentiment_layers import get_sentiment_layer_filter
        sentiment_filter = get_sentiment_layer_filter(
            df["margin_balance"], df["Volume"], df["Close"], ["smart_money_exit"]
        )
        signal = sentiment_filter & (df["inst_total_net"] < -threshold_a)
    elif template_id == "J08":
        # 多數人追高區間：臨界點突破後
        from config.sentiment_layers import get_sentiment_layer_filter
        sentiment_filter = get_sentiment_layer_filter(
            df["margin_balance"], df["Volume"], df["Close"], ["crowd_chase"]
        )
        signal = sentiment_filter & (df["margin_balance"].diff(3) > threshold_a)
    elif template_id == "J09":
        # 多數人恐慌區間：臨界點突破後
        from config.sentiment_layers import get_sentiment_layer_filter
        sentiment_filter = get_sentiment_layer_filter(
            df["margin_balance"], df["Volume"], df["Close"], ["crowd_panic"]
        )
        signal = sentiment_filter & (df["Close"].pct_change(consecutive_n) < -bar_body_pct)
    elif template_id == "J10":
        # 情緒分層轉換訊號
        from config.sentiment_layers import SentimentLayerSystem
        system = SentimentLayerSystem()
        layer_series = system.create_sentiment_layer_series(df["margin_balance"], df["Volume"], df["Close"])
        # 偵測分層轉換（從中性到極端情緒）
        neutral_to_extreme = (
            (layer_series.shift(1).isin(["neutral", "insufficient_data"])) &
            (layer_series.isin(["crowd_chase", "crowd_panic", "smart_money_entry", "smart_money_exit"]))
        )
        signal = neutral_to_extreme
    elif template_id == "K01":
        signal = detect_sequence(df["foreign_net"], pattern_name, threshold_a)
    elif template_id == "K02":
        signal = detect_sequence(df["trust_net"], pattern_name, threshold_a)
    elif template_id == "K03":
        signal = detect_sequence(df["inst_total_net"], pattern_name, threshold_a)
    elif template_id == "K04":
        signal = detect_sequence(df["foreign_net"], pattern_name, threshold_a) & (df["margin_balance"].diff(3) > threshold_a * 5)
    elif template_id == "K05":
        signal = detect_sequence(df["foreign_net"], pattern_name, threshold_a) & (df["stoch_14"] < indicator_val)
    elif template_id == "L01":
        inst_buy = df["inst_total_net"] > 0
        inst_buy_streak = inst_buy.rolling(chip_days).sum() == chip_days
        limit_up = ((df["Close"] - df["PrevClose"]) / df["PrevClose"].replace(0, np.nan)) >= 0.095
        limit_up_streak = limit_up.rolling(price_days).sum() == price_days
        signal = inst_buy_streak.shift(price_days).fillna(False) & limit_up_streak & (df["stoch_14"] < 80)
    elif template_id == "L02":
        inst_sell = df["inst_total_net"] < 0
        inst_sell_streak = inst_sell.rolling(chip_days).sum() == chip_days
        limit_down = ((df["Close"] - df["PrevClose"]) / df["PrevClose"].replace(0, np.nan)) <= -0.095
        limit_down_streak = limit_down.rolling(price_days).sum() == price_days
        signal = inst_sell_streak.shift(price_days).fillna(False) & limit_down_streak & (df["stoch_14"] > 20)
    elif template_id == "L03":
        inst_buy = df["inst_total_net"] > 0
        inst_buy_streak = inst_buy.rolling(chip_days).sum() == chip_days
        limit_up = ((df["Close"] - df["PrevClose"]) / df["PrevClose"].replace(0, np.nan)) >= 0.095
        limit_up_streak = limit_up.rolling(price_days).sum() == price_days
        signal = inst_buy_streak.shift(price_days).fillna(False) & limit_up_streak & (df["inst_total_net"] < 0)
    elif template_id == "M01":
        # 外資買超 N 天後，投信在 D 天內跟進買超（機構共識形成）
        leader_days = int(params.get("leader_days", 3))
        follower_window = int(params.get("follower_window", 5))
        signal = detect_group_sequence(df["foreign_net"], df["trust_net"], leader_days, follower_window, divergence_threshold)
    elif template_id == "M02":
        # 外資賣超 N 天後，融資持續增加（背離危險訊號）
        leader_days = int(params.get("leader_days", 3))
        follower_window = int(params.get("follower_window", 5))
        signal = detect_group_sequence(df["foreign_net"], df["margin_balance"].diff(), leader_days, follower_window, divergence_threshold)
    elif template_id == "M03":
        # 機構同步買超後，融資急增（散戶追高確認）
        leader_days = int(params.get("leader_days", 3))
        follower_window = int(params.get("follower_window", 5))
        inst_combined = df["foreign_net"] + df["trust_net"]
        signal = detect_group_sequence(inst_combined, df["margin_balance"].diff(), leader_days, follower_window, divergence_threshold)
    elif template_id == "M04":
        # 外資獨立賣超但投信無動作（弱訊號）
        leader_days = int(params.get("leader_days", 3))
        follower_window = int(params.get("follower_window", 5))
        # 外資賣超但投信變化小於門檻
        trust_neutral = df["trust_net"].rolling(follower_window).std() < divergence_threshold
        foreign_sell = df["foreign_net"].rolling(leader_days).mean() < -divergence_threshold
        signal = foreign_sell & trust_neutral
    elif template_id == "M05":
        # 外資賣超同時融資達近期高點（極端背離）
        leader_days = int(params.get("leader_days", 3))
        foreign_sell = df["foreign_net"].rolling(leader_days).mean() < -divergence_threshold
        margin_high = df["margin_balance"] > df["margin_balance"].rolling(60).quantile(0.8)
        signal = foreign_sell & margin_high
    elif prefix == "E":
        signal = df["rsi_14"] < indicator_val
    else:
        signal = pd.Series(False, index=df.index)

    # 應用狀態分層過濾（T/V/A 八狀態系統）
    state_filter = params.get("state_filter")
    if state_filter is not None and isinstance(state_filter, int) and 1 <= state_filter <= 8:
        # 計算當前狀態
        current_states = calculate_tva_state(df["Close"])
        # 只保留指定狀態的訊號
        signal = signal & (current_states == state_filter)

    return signal.fillna(False).astype(bool)


def infer_direction(hypothesis: dict[str, Any]) -> str:
    template_id = str(hypothesis.get("id", ""))
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
        if entry_open <= 0 or prev_close <= 0:
            idx += 1
            continue
        if is_limit_up(entry_open, prev_close) or is_limit_down(entry_open, prev_close):
            idx += 1
            continue
        if EDGE_DEFENSE_ENABLED:
            vol_lots = float(frame["volume_lots"].iloc[entry_idx])
            if vol_lots < MIN_DAILY_VOLUME_LOTS:
                idx += 1
                continue
        exit_close = float(frame["Close"].iloc[exit_idx])
        if exit_close <= 0:
            idx += 1
            continue
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
