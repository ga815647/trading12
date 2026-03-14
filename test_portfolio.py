import sys
sys.path.insert(0, '.')

print('🧪 訊號疊加器測試')
print('=' * 50)

try:
    from engine.portfolio import classify_group, build_signal_id, vote_signals
    import hashlib

    # 測試群組分類
    print('群組分類測試:')
    test_ids = ['A01', 'B05', 'C03', 'D02', 'E01', 'F04', 'G02', 'H03', 'I01', 'J06', 'K02', 'L01', 'M03']
    for hypothesis_id in test_ids:
        group = classify_group(hypothesis_id)
        print(f'  {hypothesis_id} → {group}')

    print()

    # 測試訊號ID生成
    print('訊號ID生成測試:')
    test_signal = {
        'hypothesis_id': 'J06_0001',
        'id': 'J06',
        'params': {'sentiment_layer': 'crowd_panic', 'margin_percentile_threshold': 0.2}
    }

    signal_id = build_signal_id(test_signal)
    print(f'  訊號ID: ✓ {signal_id}')
    print(f'  ID長度: {len(signal_id)} 字元')

    print()

    # 測試訊號投票
    print('訊號投票測試:')
    mock_triggers = [
        {
            'stock_id': '2330',
            'direction': 'long',
            'group': 'sentiment',
            'signal_id': 'J06_0001'
        },
        {
            'stock_id': '2330',
            'direction': 'long',
            'group': 'chip',
            'signal_id': 'A01_0001'
        },
        {
            'stock_id': '2330',
            'direction': 'long',
            'group': 'momentum',
            'signal_id': 'B02_0001'
        },
        {
            'stock_id': '2454',
            'direction': 'short',
            'group': 'sentiment',
            'signal_id': 'J08_0001'
        }
    ]

    voted = vote_signals(mock_triggers)
    print(f'  投票結果: ✓ {len(voted)} 個整合訊號')

    for signal in voted:
        groups_str = ', '.join(signal['groups'])
        print(f'    {signal["stock_id"]} {signal["direction"]}: {groups_str} (星級: {signal["stars"]})')

    print('✓ 訊號疊加器測試通過')

except Exception as e:
    print(f'✗ 訊號疊加器測試失敗: {e}')
    import traceback
    traceback.print_exc()