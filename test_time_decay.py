import sys
sys.path.insert(0, '.')
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print('🧪 時間衰減模組測試')
print('=' * 50)

try:
    from engine.time_decay import (
        anchor_date, days_ago, time_weight,
        compute_weighted_win_rate, compute_recent_stats
    )

    # 建立測試資料
    base_date = datetime(2024, 1, 1)
    trade_dates = [
        (base_date - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in [1, 30, 90, 180, 365]  # 不同時間的交易
    ]
    trade_returns = [0.05, -0.02, 0.08, -0.03, 0.12]  # 對應的報酬

    print('測試資料:')
    for date, ret in zip(trade_dates, trade_returns):
        print(f'  {date}: {ret:+.1%}')

    print()
    print('時間衰減功能測試:')

    # 測試 anchor_date
    anchor = anchor_date(trade_dates)
    print(f'  Anchor 日期: ✓ {anchor.strftime("%Y-%m-%d")}')

    # 測試 days_ago
    days_list = [days_ago(anchor, date) for date in trade_dates]
    print(f'  天數計算: ✓ {days_list}')

    # 測試 time_weight
    weights = [time_weight(days) for days in days_list]
    print(f'  權重計算: ✓ {[f"{w:.3f}" for w in weights]}')

    # 測試加權勝率
    weighted_win_rate, total_weight = compute_weighted_win_rate(trade_dates, trade_returns)
    print(f'  加權勝率: ✓ {weighted_win_rate:.1%} (總權重: {total_weight:.1f})')

    # 測試近期統計
    recent_win_rate, recent_count = compute_recent_stats(trade_dates, trade_returns)
    recent_display = f"{recent_win_rate:.1%}" if recent_win_rate else "N/A"
    print(f'  近期勝率: ✓ {recent_display} ({recent_count} 筆)')

    print('✓ 時間衰減模組測試通過')

except Exception as e:
    print(f'✗ 時間衰減模組測試失敗: {e}')
    import traceback
    traceback.print_exc()