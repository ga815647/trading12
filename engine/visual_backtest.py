from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
from backtesting import Backtest
import importlib.util

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.processor import merge_market_data
from engine.backtest import _enrich

def run_visual_backtest(stock_id: str, hypothesis_id: str, cash: int = 1000000):
    # 1. 載入市場資料
    print(f"Loading data for {stock_id}...")
    df = merge_market_data(stock_id)
    if df.empty:
        print(f"No data found for {stock_id}")
        return
    
    # 2. 資料擴展 (Enrichment) - 提供 strategies 所需的 foreign_net 等欄位
    df = _enrich(df)

    # 2. 動態載入 Agent 2 生成的策略類
    strategy_path = ROOT_DIR / "engine" / "generated_backtests.py"
    if not strategy_path.exists():
        print(f"Strategy file not found: {strategy_path}")
        return

    # 使用 importlib 動態載入模組
    spec = importlib.util.spec_from_file_location("generated_strategies", strategy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 尋找對應的 Strategy 類 (假設名稱規範為 Strategy_{hypothesis_id})
    # 注意：Agent 2 生成的類名可能直接包含在 code 裡，我們搜尋 module 成員
    strategy_cls = None
    for name, obj in vars(module).items():
        if hypothesis_id in name and isinstance(obj, type):
            strategy_cls = obj
            break
    
    if not strategy_cls:
        print(f"Strategy for {hypothesis_id} not found in {strategy_path}")
        return

    # 3. 執行 Backtest
    print(f"Running backtest for {stock_id} with strategy {hypothesis_id}...")
    # backtesting 庫要求欄位名稱首字母大寫
    bt = Backtest(df, strategy_cls, cash=cash, commission=.002925)
    stats = bt.run()
    
    # 4. 輸出結果
    print("\n=== Backtest Statistics ===")
    print(stats)
    
    # 5. 儲存圖表
    output_plot = ROOT_DIR / f"results/backtests/{stock_id}_{hypothesis_id}.html"
    output_plot.parent.mkdir(parents=True, exist_ok=True)
    bt.plot(filename=str(output_plot), open_browser=False)
    print(f"\nPlot saved to: {output_plot}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run a visual backtest for a specific stock and hypothesis.")
    parser.add_argument("--stock", default="2330", help="Stock ID (e.g., 2330)")
    parser.add_argument("--hypothesis", required=True, help="Hypothesis ID (e.g., A01_0001)")
    
    args = parser.parse_args()
    run_visual_backtest(args.stock, args.hypothesis)
