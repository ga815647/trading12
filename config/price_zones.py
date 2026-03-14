"""
價格區間框架實作
支援四區間價格框架：破壞價、便宜區、合理區、昂貴區、盤子價
"""

from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np


class PriceZoneFramework:
    """
    四區間價格框架實作

    區間定義：
    - 破壞價：歷史低估區，多數人恐慌賣出
    - 便宜區：相對低估
    - 合理區：公允價值區間
    - 昂貴區：相對高估
    - 盤子價：歷史高估區，多數人瘋狂追高
    """

    def __init__(self, lookback_years: int = 3, method: str = "percentile"):
        """
        初始化價格區間框架

        Args:
            lookback_years: 歷史回顧期間（年）
            method: 區間定義方法 ("percentile" 或 "relative_range")
        """
        self.lookback_years = lookback_years
        self.method = method

    def calculate_zones_percentile(
        self,
        price_series: pd.Series,
        zone_thresholds: List[float] = [0.1, 0.3, 0.7, 0.9]
    ) -> Dict[str, float]:
        """
        基於歷史分位數計算價格區間

        Args:
            price_series: 價格序列
            zone_thresholds: 區間邊界分位數 [破壞價上限, 便宜區上限, 昂貴區下限, 盤子價下限]

        Returns:
            區間邊界字典
        """
        if len(price_series) < 252:  # 至少一年交易日
            return {}

        # 使用過去N年的資料計算分位數
        lookback_periods = self.lookback_years * 252
        recent_prices = price_series.tail(lookback_periods)

        zones = {}
        percentiles = np.percentile(recent_prices, [t * 100 for t in zone_thresholds])

        zones['破壞價上限'] = percentiles[0]  # 10% 分位數
        zones['便宜區上限'] = percentiles[1]  # 30% 分位數
        zones['昂貴區下限'] = percentiles[2]  # 70% 分位數
        zones['盤子價下限'] = percentiles[3]  # 90% 分位數

        return zones

    def calculate_zones_relative(
        self,
        price_series: pd.Series,
        current_price: float,
        lookback_years: int = 3
    ) -> Dict[str, float]:
        """
        基於相對歷史高低點計算價格區間

        Args:
            price_series: 價格序列
            current_price: 當前價格
            lookback_years: 回顧期間

        Returns:
            區間邊界字典
        """
        if len(price_series) < 252:
            return {}

        lookback_periods = lookback_years * 252
        recent_prices = price_series.tail(lookback_periods)

        high = recent_prices.max()
        low = recent_prices.min()
        median = recent_prices.median()

        # 相對區間定義
        zones = {}
        zones['破壞價上限'] = low * 1.1      # 歷史低點+10%
        zones['便宜區上限'] = median * 0.9   # 中位數-10%
        zones['昂貴區下限'] = median * 1.1   # 中位數+10%
        zones['盤子價下限'] = high * 0.9     # 歷史高點-10%

        return zones

    def get_price_zone(self, price: float, zones: Dict[str, float]) -> str:
        """
        判斷價格所屬區間

        Args:
            price: 當前價格
            zones: 區間邊界字典

        Returns:
            區間名稱
        """
        if not zones:
            return "未知"

        if price <= zones['破壞價上限']:
            return "破壞價"
        elif price <= zones['便宜區上限']:
            return "便宜區"
        elif price < zones['昂貴區下限']:
            return "合理區"
        elif price < zones['盤子價下限']:
            return "昂貴區"
        else:
            return "盤子價"

    def calculate_zone_series(
        self,
        price_series: pd.Series,
        method: str = "percentile",
        rolling: bool = True
    ) -> pd.Series:
        """
        計算整個價格序列的區間序列

        Args:
            price_series: 價格序列
            method: 計算方法
            rolling: 是否使用滾動計算

        Returns:
            區間名稱序列
        """
        if not rolling:
            raise RuntimeError(
                "Static (non-rolling) zone calculation uses full-series percentiles "
                "and introduces look-ahead bias. Always use rolling=True in backtests. "
                "If you need a static zone for display purposes only, call "
                "calculate_zones_percentile() directly and handle the bias yourself."
            )

        # 滾動區間計算
        zone_series = pd.Series(index=price_series.index, dtype=str)

        for i in range(len(price_series)):
            if i < 252:  # 不足一年資料
                zone_series.iloc[i] = "未知"
                continue

            # 使用過去資料計算區間
            historical_prices = price_series.iloc[:i+1]

            if method == "percentile":
                zones = self.calculate_zones_percentile(historical_prices)
            else:
                current_price = price_series.iloc[i]
                zones = self.calculate_zones_relative(historical_prices, current_price)

            zone_series.iloc[i] = self.get_price_zone(price_series.iloc[i], zones)

        return zone_series


    target_zones: List[str],
    lookback_years: int = 3,
    method: str = "percentile",
    rolling: bool = True
) -> pd.Series:
    """
    產生價格區間過濾器

    Args:
        price_series: 價格序列
        target_zones: 目標區間列表 ["破壞價", "便宜區", "合理區", "昂貴區", "盤子價"]
        lookback_years: 回顧期間
        method: 計算方法
        rolling: 是否使用滾動計算 (預設為 True 以避免未來資訊洩漏)

    Returns:
        布林序列，True表示價格在目標區間內
    """
    # 強制 rolling=True，防止未來洩漏
    if not rolling:  # 若呼叫方傳入 rolling=False
        raise RuntimeError("get_price_zone_filter() must use rolling=True to avoid look-ahead bias.")
        
    framework = PriceZoneFramework(lookback_years, method)
    zone_series = framework.calculate_zone_series(price_series, method, rolling=rolling)

    return zone_series.isin(target_zones)


# 預設參數格網（供 Grid Search 使用）
PRICE_ZONE_PARAM_GRIDS = {
    "zone_method": ["percentile", "relative_range"],
    "lookback_years": [1, 2, 3, 5],
    "zone_thresholds": [
        [0.1, 0.3, 0.7, 0.9],  # 標準分位數
        [0.2, 0.4, 0.6, 0.8],  # 較寬鬆的分位數
        [0.05, 0.25, 0.75, 0.95]  # 更極端的分位數
    ],
    "target_zones": [
        ["破壞價"],           # 只在破壞價區間
        ["破壞價", "便宜區"], # 在低估區間
        ["昂貴區", "盤子價"], # 在高估區間
        ["合理區"]           # 只在合理區間
    ]
}