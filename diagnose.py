import os
import glob
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import numpy as np

# Set ROOT_DIR to the directory of this script
ROOT_DIR = Path(__file__).resolve().parent

# Ensure project root is in sys.path if needed
import sys
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from config.encrypt import load_signals, load_encrypted_json
    from config.market_cycle import label_date
    from config.config import (
        MIN_SAMPLE_COUNT,
        MIN_WIN_RATE,
        MIN_OOS_WIN_RATE,
        MIN_SHARPE,
        MAX_ADJUSTED_P_VALUE,
        MIN_WEIGHTED_WIN_RATE,
        MIN_RECENT_2Y_WIN_RATE,
        MIN_RECENT_2Y_TRADES,
        SIGNAL_DIR,
        BACKTEST_DIR
    )
except ImportError as e:
    print(f"[FATAL] 導入失敗，請確認在專案根目錄執行: {e}")
    sys.exit(1)

def diagnose_signals():
    print("\n=== 1. 訊號庫診斷 ===")
    lib_path = SIGNAL_DIR / "library.enc"
    if not lib_path.exists():
        print(f"[WARN] {lib_path.name} 不存在，尚未跑過 validator")
        return
    
    try:
        signals = load_signals(lib_path)
        print(f"[OK] 訊號庫：{len(signals)} 個策略")
        if len(signals) == 0:
            print("[WARN] 訊號庫是空的，以下是可能原因：")
            print("  1. market_cycle 標籤過期 → cycle_pass 失敗")
            print("  2. 回測樣本不足 → sample_count < MIN_SAMPLE_COUNT")
            print("  3. FDR 校正過嚴 → adjusted_p_value 全超標")
            print("  4. OOS 期間沒有足夠交易 → oos_count 太少")
    except Exception as e:
        print(f"[ERROR] 讀取訊號庫失敗: {e}")

def diagnose_backtests():
    print("\n=== 2. 回測結果分解診斷 ===")
    try:
        files = glob.glob(str(BACKTEST_DIR / "*.enc"))
        if not files:
            print(f"[SKIP] {BACKTEST_DIR} 下無 .enc 檔案")
            return
        
        latest_file = max(files, key=os.path.getmtime)
        print(f"最近回測檔案: {os.path.basename(latest_file)}")
        
        backtests = load_encrypted_json(Path(latest_file))
        if not backtests:
            print("[WARN] 回測檔案為空")
            return

        # Deduplicate like validator does
        deduped = {}
        for item in backtests:
            key = str(item.get("hypothesis_id") or item.get("id") or "")
            if not key: continue
            deduped[key] = item
        
        items = list(deduped.values())
        total = len(items)
        print(f"[回測結果診斷] 共 {total} 筆（去重後）")
        
        stats_fail = defaultdict(int)
        cycle_metrics = {"bull": [], "bear": [], "sideways": []}
        all_trade_dates = []
        
        for item in items:
            passed_all = True
            
            # supported
            if not item.get("supported", False):
                stats_fail["supported=False"] += 1
                passed_all = False
            
            # sample_count
            if item.get("sample_count", 0) < MIN_SAMPLE_COUNT:
                stats_fail[f"sample_count < {MIN_SAMPLE_COUNT}"] += 1
                passed_all = False
                
            # win_rate
            if item.get("win_rate", 0.0) < MIN_WIN_RATE:
                stats_fail[f"win_rate < {MIN_WIN_RATE}"] += 1
                passed_all = False
                
            # oos_win_rate
            if item.get("oos_win_rate", 0.0) < MIN_OOS_WIN_RATE:
                stats_fail[f"oos_win_rate < {MIN_OOS_WIN_RATE}"] += 1
                passed_all = False
                
            # oos_count (Targeting the requested "oos_count < 10")
            if item.get("oos_count", 0) < 10:
                stats_fail["oos_count < 10"] += 1
                passed_all = False

            # portfolio_sharpe
            if item.get("portfolio_sharpe", 0.0) < MIN_SHARPE:
                stats_fail[f"portfolio_sharpe < {MIN_SHARPE}"] += 1
                passed_all = False
                
            # p_value (raw)
            if item.get("p_value", 1.0) >= 0.05:
                stats_fail["p_value >= 0.05 (raw)"] += 1
                passed_all = False

            # cycle_pass
            trade_dates = item.get("trade_dates", [])
            all_trade_dates.extend(trade_dates)
            counts = {"bull": 0, "bear": 0, "sideways": 0}
            for d in trade_dates:
                counts[label_date(d)] += 1
            
            for k in cycle_metrics:
                cycle_metrics[k].append(counts[k])
                
            if not all(c >= 30 for c in counts.values()): # validator uses min 30 default normally, or from config
                stats_fail["cycle_pass 失敗"] += 1
                passed_all = False

            # weighted_wr
            if item.get("weighted_win_rate", 0.0) < MIN_WEIGHTED_WIN_RATE:
                stats_fail[f"weighted_wr < {MIN_WEIGHTED_WIN_RATE}"] += 1
                passed_all = False
                
            # recent_pass
            recent_pass = item.get("recent_2y_count", 0) >= MIN_RECENT_2Y_TRADES and \
                          (item.get("recent_2y_win_rate") is not None and item.get("recent_2y_win_rate") >= MIN_RECENT_2Y_WIN_RATE)
            if not recent_pass:
                stats_fail["recent_pass 失敗"] += 1
                passed_all = False
            
            if passed_all:
                stats_fail["全部通過"] += 1

        print("條件失敗統計：")
        for k in sorted(stats_fail.keys(), key=lambda x: "全部通過" in x):
            if k == "全部通過": continue
            print(f"  {k:<25}: {stats_fail[k]} 筆")
        print(f"  {'全部通過':<25}: {stats_fail['全部通過']} 筆")
        
        # Cycle medians
        medians = {k: int(np.median(v)) if v else 0 for k, v in cycle_metrics.items()}
        print(f"  cycle 分佈（中位數）: bull={medians['bull']}, bear={medians['bear']}, sideways={medians['sideways']}")
        
        # 3. Coverage diagnosis
        print("\n=== 3. 市場循環覆蓋診斷 ===")
        if all_trade_dates:
            dist = defaultdict(int)
            for d in all_trade_dates:
                dist[label_date(d)] += 1
            
            total_trades = len(all_trade_dates)
            print("[市場循環覆蓋]")
            for c in ["bull", "bear", "sideways"]:
                count = dist[c]
                pct = (count / total_trades * 100) if total_trades else 0
                print(f"  {c:<8}: {count:>6} 筆交易 ({pct:>4.1f}%)")
                if c in ["bear", "sideways"] and pct < 15:
                    print(f"  [WARN] {c} 交易比例過低 ({pct:.1f}%)，可能是 market_cycle 標籤未更新")
            
            print(f"  最新交易日: {max(all_trade_dates)}")
            print(f"  最舊交易日: {min(all_trade_dates)}")
        
        # 4. Rapid suggestions
        print("\n=== 4. 快速建議 ===")
        print("[建議]")
        if stats_fail["全部通過"] == 0:
            # Find the biggest bottleneck
            bottleneck = max(stats_fail.items(), key=lambda x: x[1] if x[0] != "全部通過" else -1)[0]
            print(f"  最主要瓶頸：{bottleneck}")
            print("  建議動作：")
            if "cycle_pass" in bottleneck:
                print("    - 確認 market_cycle.py 已更新至今天")
                print("    - 增加回測股票池或拉長回測起始日期")
            elif "sample_count" in bottleneck:
                print("    - 需要先跑更多回測 (增加股票或參數集)")
            elif "FDR" in bottleneck or "p_value" in bottleneck:
                print("    - 策略邏輯可能失效，或訊號強度不足")
            
            print(f"  → 修正後執行：python engine/orchestrator.py --skip-fetch")
        else:
            print("  系統狀態良好，訊號庫已有產出。")
            if stats_fail["cycle_pass 失敗"] > total * 0.5:
                print("  [提示] 雖然有通過，但過半策略因 cycle_pass 失敗，建議拉長回測時間。")

    except Exception as e:
        print(f"[ERROR] 診斷過程發生錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose_signals()
    diagnose_backtests()
    
    print("\n[操作流程指引]")
    print("1. 先執行 python diagnose.py 確認目前系統狀態")
    print("2. 如果訊號庫是空的，根據診斷結果的主要瓶頸決定下一步")
    print("3. 如果是 cycle_pass 失敗 → market_cycle.py 已更新，直接重跑 validator：")
    print("   python engine/validator.py --input results/backtests/orchestrator_results.enc")
    print("4. 如果是 sample_count 不足 → 需要先跑更多回測：")
    print("   python engine/orchestrator.py --skip-fetch")
    print("5. 如果兩個都 OK → 訊號庫有東西了，直接跑每日掃描：")
    print("   python engine/run_daily_scan.py --paper-mode")
    print("6. 再次執行 python diagnose.py 確認訊號庫數量")
