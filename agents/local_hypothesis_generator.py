import itertools
import json
import random
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import HYPOTHESIS_DIR, ensure_runtime_dirs

def generate_local_factory(max_count: int = 1000):
    """
    Multi-Layered Matrix Strategy Factory
    Combines TRIGGERS and FILTERS with parameter grids.
    """
    ensure_runtime_dirs()
    
    # Core Triggers (The 'What')
    TRIGGERS = {
        "A01": {"threshold_a": [100, 400, 1000], "consecutive_n": [3, 5]},
        "A03": {"threshold_a": [200, 600, 1500], "consecutive_n": [1, 3]},
        "B02": {"bar_body_pct": [0.03, 0.05], "consecutive_n": [5]},
        "B03": {"bar_body_pct": [0.02, 0.07], "consecutive_n": [3, 10]},
        "J06": {"threshold_a": [500, 1500], "indicator_val": [30, 50]},
        "K01": {"threshold_a": [100, 500, 2000], "pattern_name": ["buy_3", "buy_5"]}
    }

    # State Filters (The 'Where/When')
    FILTERS = {
        "NONE": {}, # No filter
        "E01": {"indicator_val": [20, 40]},      # RSI Oversold
        "E02": {"indicator_val": [25, 45]},      # Stoch Oversold
        "G01": {"bar_body_pct": [0.02, 0.05]},   # Vol break
        "FLT_UP_TREND": {},                      # 多頭排列 (Close > 20MA & 20MA Up)
        "FLT_VOL_SHRINK": {},                    # 量縮洗盤 (Prev Vol < 0.8 * 5MA Vol)
        "FLT_KD_OVERSOLD": {},                   # KD 落底 (K < 30 & D < 30)
        "TVA1": {"state_filter": [1]},           # Up-Trend, Accelerating
        "TVA5": {"state_filter": [5]}            # Down-Trend, Accelerating Up
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

    # Shuffle to ensure diversity when capped
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
    parser.add_argument("--max-count", type=int, default=1000)
    args = parser.parse_args()
    
    generate_local_factory(max_count=args.max_count)
