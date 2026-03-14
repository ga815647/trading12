import sys
sys.path.insert(0, '.')
import pandas as pd
import numpy as np

print('🧪 價格區間框架測試')
print('=' * 50)

# 測試價格區間框架
print('價格區間框架測試:')
try:
    from config.price_zones import PriceZoneFramework

    # 建立測試資料
    dates = pd.date_range('2020-01-01', periods=500, freq='D')
    prices = pd.Series(np.cumsum(np.random.normal(0, 2, 500)) + 100, index=dates)

    # 測試價格區間框架
    framework = PriceZoneFramework()

    # 測試百分位數方法
    zones_pct = framework.calculate_zones_percentile(prices)
    print(f'  百分位數區間: ✓ ({len(zones_pct)} 個區間)')
    if zones_pct:
        print(f'    區間: {list(zones_pct.keys())}')

    # 測試相對範圍方法
    current_price = prices.iloc[-1]
    zones_range = framework.calculate_zones_relative(prices, current_price)
    print(f'  相對範圍區間: ✓ ({len(zones_range)} 個區間)')
    if zones_range:
        print(f'    區間: {list(zones_range.keys())}')

    # 測試區間判斷
    test_price = prices.iloc[-1]
    zone_pct = framework.get_price_zone(test_price, zones_pct)
    zone_range = framework.get_price_zone(test_price, zones_range)

    print(f'  區間判斷測試: ✓ (價格 {test_price:.1f} 在 \"{zone_pct}\" 區 / \"{zone_range}\" 區)')

    print('✓ 價格區間框架測試通過')

except Exception as e:
    print(f'✗ 價格區間框架測試失敗: {e}')
    import traceback
    traceback.print_exc()