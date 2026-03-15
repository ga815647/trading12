import itertools
import json
import random
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import HYPOTHESIS_DIR, ensure_runtime_dirs

def generate_local_factory(max_count: int = 3000):
    """
    Multi-Layered Matrix Strategy Factory
    Combines TRIGGERS and FILTERS with parameter grids.
    """
    ensure_runtime_dirs()
    
    # Core Triggers (The 'What')
    TRIGGERS = {
        # --- A 類：籌碼集中 (Chip Accumulation) ---
        "A01": {"threshold_a": [50, 100, 300, 800, 2000], "consecutive_n": [3, 5, 7]},
        "A03": {"threshold_a": [100, 300, 800, 2000], "consecutive_n": [1, 3, 5]},
        # --- B 類：動能 (Momentum) ---
        "B02": {"bar_body_pct": [0.02, 0.03, 0.05], "consecutive_n": [3, 5, 7]},
        "B03": {"bar_body_pct": [0.02, 0.04, 0.07], "consecutive_n": [3, 5, 10]},
        # --- J 類：情緒 (Sentiment) ---
        "J06": {"threshold_a": [300, 800, 2000], "indicator_val": [20, 30, 50]},
        # --- K 類：籌碼序列 (Chip Sequences) ---
        "K01": {"threshold_a": [100, 500, 2000], "pattern_name": ["buy_3", "buy_5", "accelerate_buy"]},
        "K02": {"threshold_a": [100, 500, 2000], "pattern_name": ["buy_3", "buy_5"]},
        "K03": {"threshold_a": [100, 500, 2000], "pattern_name": ["buy_3", "buy_5"]},
        # --- L 類：跨資料源複合序列 (Multi-Source Sequences) ---
        "L01": {"threshold_a": [100, 500], "consecutive_n": [3, 5],
                "chip_days": [3, 5], "price_days": [1, 3]},
        # --- M 類：群體行為序列與背離 (Group Behavior Sequences) ---
        "M01": {"divergence_threshold": [0.5, 0.7, 0.9]},  # 外資買 + 投信追
        "M02": {"divergence_threshold": [0.5, 0.7, 0.9]},  # 外資買 + 融資退
        "M03": {"divergence_threshold": [0.5, 0.7, 0.9]},  # 法人合買 + 融資退
        # --- Expanded Triggers ---
        "A02": {"threshold_a": [100, 300, 800, 2000], "consecutive_n": [2, 3, 5]},
        "A05": {"threshold_a": [100, 300, 800], "consecutive_n": [2, 3, 5]},
        "B05": {"bar_body_pct": [0.02, 0.03, 0.05, 0.07], "consecutive_n": [3, 5, 8]},
        "E01": {"indicator_val": [20, 25, 30, 35]},
        "E02": {"indicator_val": [20, 25, 30, 35]},
        "E03": {"bar_body_pct": [0.05, 0.08, 0.12], "consecutive_n": [5, 10, 15]},
        "G01": {"bar_body_pct": [0.02, 0.03, 0.05]},
        "G03": {"bar_body_pct": [0.03, 0.05, 0.07]},
        "G04": {"bar_body_pct": [0.02, 0.03, 0.05]},
        "H01": {"bar_body_pct": [0.02, 0.03, 0.05], "consecutive_n": [3, 5, 10]},
        "H04": {"threshold_a": [100, 300, 800], "consecutive_n": [3, 5, 10]},
        "H05": {"threshold_a": [100, 300, 800], "consecutive_n": [3, 5, 10]},
        "J01": {"indicator_val": [60, 70, 80]},
        "J04": {"bar_body_pct": [0.05, 0.08, 0.12], "consecutive_n": [3, 5, 10]},
        "K04": {"threshold_a": [100, 500, 2000], "pattern_name": ["buy_3", "buy_5"]},
        "K05": {"threshold_a": [100, 500, 2000], "indicator_val": [20, 30]},
        "M04": {"divergence_threshold": [0.5, 0.7, 0.9]},
        "M05": {"divergence_threshold": [0.5, 0.7, 0.9]},
    }

    SIMPLE_TRIGGERS = {
        # 單一籌碼條件（不要求連續天數，只看當日）
        "A03_SIMPLE": {
            "threshold_a": [200, 500, 1000, 2000, 3000],
            "consecutive_n": [1, 2, 3],
        },
        # RSI 超賣（單條件，觸發頻率高）
        "E01_SIMPLE": {
            "indicator_val": [25, 30, 35, 40],
        },
        # KD 超賣
        "E02_SIMPLE": {
            "indicator_val": [20, 25, 30],
        },
        # 外資買超（單日，門檻低）
        "FOREIGN_NET_SIMPLE": {
            "threshold_a": [100, 200, 500, 1000],
            "consecutive_n": [1, 2],
        },
        # 成交量放大
        "B03_SIMPLE": {
            "bar_body_pct": [0.3, 0.5, 0.8],  # volume_ma_5 > volume_ma_20 * (1+pct)
            "consecutive_n": [1, 2, 3],
        },
        # 近期跌深反彈
        "E03_SIMPLE": {
            "bar_body_pct": [0.05, 0.08, 0.10, 0.12],
            "consecutive_n": [5, 10, 15, 20],
        },
    }

    # Mapping for backtest.py compatibility
    TRIGGER_MAP = {
        "A03_SIMPLE": "A03",
        "E01_SIMPLE": "E01",
        "E02_SIMPLE": "E02",
        "FOREIGN_NET_SIMPLE": "A03",
        "B03_SIMPLE": "B03",
        "E03_SIMPLE": "E03",
    }

    # State Filters (The 'Where/When')
    FILTERS = {
        "NONE": {}, # No filter — baseline

        # --- 技術面過濾器 ---
        "E01": {"indicator_val": [20, 35]},       # RSI Oversold
        "E02": {"indicator_val": [25, 40]},       # Stoch Oversold
        "G01": {"bar_body_pct": [0.02, 0.05]},    # Vol break
        "FLT_UP_TREND": {},                       # 多頭排列
        "FLT_VOL_SHRINK": {},                     # 量縮洗盤
        "FLT_KD_OVERSOLD": {},                    # KD 落底

        # --- T/V/A 八狀態系統 (全部 8 個) ---
        "TVA1": {"state_filter": [1]},  # T+, V+, A+  全面多頭加速 → 追漲
        "TVA2": {"state_filter": [2]},  # T+, V+, A-  多頭但加速轉弱 → 獲利了結觀察
        "TVA3": {"state_filter": [3]},  # T+, V-, A+  多頭但速度轉負（回調中）
        "TVA4": {"state_filter": [4]},  # T+, V-, A-  多頭但全面轉弱 → 賣出前夕
        "TVA5": {"state_filter": [5]},  # T-, V+, A+  空頭中反彈加速 → 強反彈
        "TVA6": {"state_filter": [6]},  # T-, V+, A-  空頭中反彈趨緩
        "TVA7": {"state_filter": [7]},  # T-, V-, A+  空頭但加速度回升 → 底部前兆
        "TVA8": {"state_filter": [8]},  # T-, V-, A-  全面崩跌加速 → 危險區

        # --- 複合 TVA 過濾器 (進階組合) ---
        "TVA_BULL":     {"state_filter": [1, 2]},  # 確定多頭區間 (States 1+2)
        "TVA_REVERSAL": {"state_filter": [5, 7]},  # 反轉前夕 (底部確認)

        # --- 四/五區間價格框架 ---
        "PZ_BREAKDOWN": {"price_zone": [0]},  # 破壞價 ≤ 10th percentile
        "PZ_CHEAP":     {"price_zone": [1]},  # 便宜區 10-30th
        "PZ_FAIR":      {"price_zone": [2]},  # 合理區 30-70th
        "PZ_EXPENSIVE": {"price_zone": [3]},  # 昂貴區 70-90th
        "PZ_BUBBLE":    {"price_zone": [4]},  # 盤子價 > 90th percentile
    }

    common_params = {
        "horizon_days": [10, 20]
    }

    all_combinations = []
    
    for t_id, t_grid in TRIGGERS.items():
        for f_id, f_grid in FILTERS.items():
            # Combine grids
            combined_grid = {**t_grid, **f_grid, **common_params}
            keys = list(combined_grid.keys())
            values = list(combined_grid.values())
            
            for combination in itertools.product(*values):
                params = dict(zip(keys, combination))
                all_combinations.append({
                    "trigger_id": t_id,
                    "filter_id": f_id,
                    "params": params
                })

    # Combine SIMPLE_TRIGGERS with FILTERS
    for st_id, st_grid in SIMPLE_TRIGGERS.items():
        t_id_mapped = TRIGGER_MAP.get(st_id, st_id)
        for f_id, f_grid in FILTERS.items():
            combined_grid = {**st_grid, **f_grid, **common_params}
            keys = list(combined_grid.keys())
            values = list(combined_grid.values())
            
            for combination in itertools.product(*values):
                params = dict(zip(keys, combination))
                all_combinations.append({
                    "trigger_id": t_id_mapped,
                    "filter_id": f_id,
                    "params": params
                })

    # Shuffle to ensure diversity when capped
    random.seed(42)
    random.shuffle(all_combinations)
    
    selected_combinations = all_combinations[:max_count]
    all_hypotheses = []

    for i, combo in enumerate(selected_combinations):
        t_id = combo["trigger_id"]
        f_id = combo["filter_id"]
        params = combo["params"]
        
        # ID Format: LM_{TRIGGER}_{FILTER}_{INDEX}
        hypo_id = f"LM_{t_id}_{f_id}_{i:04d}"
        
        filter_desc = f"with filter {f_id}" if f_id != "NONE" else "without filter"
        desc = f"Matrix Strategy: Trigger {t_id} {filter_desc}"
        
        all_hypotheses.append({
            "hypothesis_id": hypo_id,
            "id": hypo_id, # Keeping duplicated for engine compatibility if needed
            "desc": desc,
            "params": params
        })

    print(f"Matrix combinations possible: {len(all_combinations)}")
    print(f"Generated {len(all_hypotheses)} hypotheses (capped at {max_count}).")
    
    # Cleanup old local batches to prevent confusion
    for old_file in HYPOTHESIS_DIR.glob("local_batch_*.json"):
        old_file.unlink()
    for old_file in HYPOTHESIS_DIR.glob("matrix_batch_*.json"):
        old_file.unlink()

    # Batch saving (500 per file)
    batch_size = 500
    for i in range(0, len(all_hypotheses), batch_size):
        batch_num = (i // batch_size) + 1
        batch_data = all_hypotheses[i : i + batch_size]
        filename = HYPOTHESIS_DIR / f"matrix_batch_{batch_num:03d}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch_data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(batch_data)} to {filename}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-count", type=int, default=3000)
    args = parser.parse_args()
    
    generate_local_factory(max_count=args.max_count)
