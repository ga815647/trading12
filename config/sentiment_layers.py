"""
情緒臨界點與群體分層系統
擴展 J 類假設，實作市場情緒分層分析
"""

from typing import Dict, List, Tuple, Optional, Union
import pandas as pd
import numpy as np


class SentimentLayerSystem:
    """
    情緒臨界點與群體分層系統

    核心概念：
    - 正向臨界點：過度樂觀邊界（突破後多數人追高）
    - 負向臨界點：過度悲觀邊界（突破後多數人恐慌賣出）
    - 90% 多數人行為：臨界點突破後
    - 10% 少數人行為：臨界點突破前
    """

    def __init__(self, lookback_periods: int = 60):
        """
        初始化情緒分層系統

        Args:
            lookback_periods: 歷史回顧期間（交易日）
        """
        self.lookback_periods = lookback_periods

    def calculate_margin_sentiment_percentile(
        self,
        margin_balance: pd.Series,
        window: int = 60
    ) -> pd.Series:
        """
        計算融資餘額相對歷史分位數

        Args:
            margin_balance: 融資餘額序列
            window: 滾動視窗期間

        Returns:
            融資情緒分位數 (0-1)
        """
        return margin_balance.rolling(window).rank(pct=True)

    def calculate_volume_sentiment_ratio(
        self,
        volume: pd.Series,
        window: int = 20
    ) -> pd.Series:
        """
        計算成交量相對均量倍數

        Args:
            volume: 成交量序列
            window: 均量計算期間

        Returns:
            成交量倍數
        """
        volume_ma = volume.rolling(window).mean()
        return volume / volume_ma

    def calculate_consecutive_move_streak(
        self,
        price_series: pd.Series,
        threshold: float = 0.01
    ) -> Tuple[pd.Series, pd.Series]:
        """
        計算連續漲跌天數

        Args:
            price_series: 價格序列
            threshold: 漲跌幅門檻

        Returns:
            (連續上漲天數, 連續下跌天數)
        """
        returns = price_series.pct_change()

        # 連續上漲天數
        up_days = (returns > threshold).astype(int)
        consecutive_up = up_days.groupby((up_days != up_days.shift()).cumsum()).cumsum()
        consecutive_up = consecutive_up.where(up_days == 1, 0)

        # 連續下跌天數
        down_days = (returns < -threshold).astype(int)
        consecutive_down = down_days.groupby((down_days != down_days.shift()).cumsum()).cumsum()
        consecutive_down = consecutive_down.where(down_days == 1, 0)

        return consecutive_up, consecutive_down

    def detect_sentiment_thresholds(
        self,
        margin_percentile: pd.Series,
        volume_ratio: pd.Series,
        consecutive_up: pd.Series,
        consecutive_down: pd.Series,
        positive_threshold: float = 0.8,
        negative_threshold: float = 0.2
    ) -> Dict[str, pd.Series]:
        """
        偵測情緒臨界點突破

        Args:
            margin_percentile: 融資分位數
            volume_ratio: 成交量倍數
            consecutive_up: 連續上漲天數
            consecutive_down: 連續下跌天數
            positive_threshold: 正向臨界點
            negative_threshold: 負向臨界點

        Returns:
            情緒狀態字典
        """
        # 正向臨界點突破（過度樂觀）
        positive_breakout = (
            (margin_percentile > positive_threshold) &
            (volume_ratio > 1.5) &
            (consecutive_up >= 3)
        )

        # 負向臨界點突破（過度悲觀）
        negative_breakout = (
            (margin_percentile < negative_threshold) &
            (volume_ratio > 1.5) &
            (consecutive_down >= 3)
        )

        # 少數人行為區間（臨界點突破前）
        minority_zone_positive = (
            (margin_percentile > positive_threshold * 0.9) &
            (volume_ratio > 1.2) &
            (consecutive_up >= 2) &
            ~positive_breakout
        )

        minority_zone_negative = (
            (margin_percentile < negative_threshold * 1.1) &
            (volume_ratio > 1.2) &
            (consecutive_down >= 2) &
            ~negative_breakout
        )

        return {
            'positive_breakout': positive_breakout,      # 多數人追高區間
            'negative_breakout': negative_breakout,      # 多數人恐慌區間
            'minority_positive': minority_zone_positive, # 少數人提前買入區間
            'minority_negative': minority_zone_negative, # 少數人提前賣出區間
            'neutral_zone': ~(positive_breakout | negative_breakout |
                            minority_zone_positive | minority_zone_negative)
        }

    def create_sentiment_layer_series(
        self,
        margin_balance: pd.Series,
        volume: pd.Series,
        price_series: pd.Series
    ) -> pd.Series:
        """
        建立完整的情緒分層序列 (Vectorized Version)
        """
        # Vectorized calculations for the entire series at once
        margin_pct = self.calculate_margin_sentiment_percentile(margin_balance)
        vol_ratio = self.calculate_volume_sentiment_ratio(volume)
        consec_up, consec_down = self.calculate_consecutive_move_streak(price_series)

        sentiment_states = self.detect_sentiment_thresholds(
            margin_pct, vol_ratio, consec_up, consec_down
        )

        layer_series = pd.Series('neutral', index=margin_balance.index, dtype=str)
        
        layer_series[sentiment_states['positive_breakout']] = 'crowd_chase'
        layer_series[sentiment_states['negative_breakout']] = 'crowd_panic'
        layer_series[sentiment_states['minority_positive']] = 'smart_money_entry'
        layer_series[sentiment_states['minority_negative']] = 'smart_money_exit'
        
        # Ensure first 30 days are 'insufficient_data'
        layer_series.iloc[:30] = 'insufficient_data'

        return layer_series


def get_sentiment_layer_filter(
    margin_balance: pd.Series,
    volume: pd.Series,
    price_series: pd.Series,
    target_layers: List[str]
) -> pd.Series:
    """
    產生情緒分層過濾器

    Args:
        margin_balance: 融資餘額序列
        volume: 成交量序列
        price_series: 價格序列
        target_layers: 目標情緒分層列表

    Returns:
        布林序列，True表示處於目標情緒分層
    """
    system = SentimentLayerSystem()
    layer_series = system.create_sentiment_layer_series(
        margin_balance, volume, price_series
    )
    return layer_series.isin(target_layers)


# 擴展 J 類假設的參數格網
EXTENDED_J_PARAM_GRIDS = {
    "sentiment_layer": [
        "crowd_chase",      # 多數人追高區間
        "crowd_panic",      # 多數人恐慌區間
        "smart_money_entry", # 少數人買入區間
        "smart_money_exit",  # 少數人賣出區間
        "neutral"           # 中性區間
    ],
    "margin_percentile_threshold": [0.1, 0.2, 0.8, 0.9],
    "volume_ratio_threshold": [1.2, 1.5, 2.0, 2.5],
    "consecutive_days_threshold": [2, 3, 5, 7],
    "lookback_window": [20, 30, 60, 90],
}