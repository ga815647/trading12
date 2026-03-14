from __future__ import annotations

from bisect import bisect_right


MARKET_CYCLES = {
    "2015-06-01": "bear",
    "2016-01-04": "bull",
    "2016-06-01": "sideways",
    "2017-01-02": "bull",
    "2018-10-01": "bear",
    "2019-01-02": "bull",
    "2019-06-01": "sideways",
    "2020-01-20": "bear",
    "2020-04-01": "bull",
    "2021-01-04": "bull",
    "2022-01-03": "bear",
    "2023-01-02": "bull",
    "2023-07-01": "sideways",
    "2024-01-01": "bull",
    "2024-07-01": "sideways",  # 2024 下半年高檔震盪整理
    "2024-10-01": "bull",      # Q4 AI 題材反彈
    "2025-01-01": "sideways",  # 2025 年初觀望
    "2025-04-01": "bear",      # 關稅戰衝擊急跌
    "2025-07-01": "bull",      # 下半年反彈回升
    "2026-01-01": "sideways",  # 2026 年初震盪
}

_CYCLE_DATES = sorted(MARKET_CYCLES)


def label_date(date_str: str) -> str:
    idx = bisect_right(_CYCLE_DATES, date_str) - 1
    if idx < 0:
        return "sideways"
    return MARKET_CYCLES[_CYCLE_DATES[idx]]
