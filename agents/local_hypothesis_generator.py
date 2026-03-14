import itertools
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import HYPOTHESIS_DIR, ensure_runtime_dirs

def generate_local_factory():
    """
    Zero-API Strategy Factory (Batch Mode)
    Generates thousands of hypotheses for Themes A, B, E, J using a parameter grid.
    """
    ensure_runtime_dirs()
    
    # Theme A: Institutional Following (Chips)
    # Params: threshold_a, consecutive_n, horizon_days
    theme_a_grid = {
        "id": ["A01", "A02", "A03", "A04", "A05"],
        "threshold_a": [100, 200, 400, 600, 800, 1000, 1500, 2000],
        "consecutive_n": [1, 2, 3, 5, 7, 10],
        "horizon_days": [10, 20, 30, 60]
    }
    
    # Theme B: Price Momentum
    # Params: bar_body_pct, consecutive_n, horizon_days
    theme_b_grid = {
        "id": ["B01", "B02", "B03", "B04", "B05"],
        "bar_body_pct": [0.01, 0.02, 0.03, 0.05, 0.07, 0.10],
        "consecutive_n": [1, 3, 5, 10, 20],
        "horizon_days": [3, 5, 10, 20]
    }
    
    # Theme E: Mean Reversion (Oversold)
    # Params: indicator_val, consecutive_n, horizon_days
    theme_e_grid = {
        "id": ["E01", "E02", "E03", "E04", "E05"],
        "indicator_val": [15, 20, 25, 30, 35, 40, 45, 50],
        "consecutive_n": [2, 3, 5, 10],
        "horizon_days": [5, 10, 15, 20]
    }
    
    # Theme J: Sentiment / Smart Money
    # Params: threshold_a, indicator_val, horizon_days
    theme_j_grid = {
        "id": ["J01", "J03", "J06", "J07", "J08", "J09", "J10"],
        "threshold_a": [100, 300, 500, 1000, 1500],
        "indicator_val": [20, 30, 40, 50],
        "horizon_days": [10, 20, 40, 60]
    }

    all_hypotheses = []
    
    # Process Grids
    grids = [
        ("A", theme_a_grid),
        ("B", theme_b_grid),
        ("E", theme_e_grid),
        ("J", theme_j_grid)
    ]
    
    for theme_name, grid in grids:
        keys = grid.keys()
        values = grid.values()
        for combination in itertools.product(*values):
            params = dict(zip(keys, combination))
            template_id = params.pop("id")
            
            hypo_id = f"LOCAL_{template_id}_{len(all_hypotheses):04d}"
            all_hypotheses.append({
                "hypothesis_id": hypo_id,
                "id": template_id,
                "desc": f"Local Factory Strategy: Theme {theme_name} Template {template_id}",
                "params": params
            })
    
    print(f"Generated {len(all_hypotheses)} hypotheses.")
    
    # Batch saving (500 per file)
    batch_size = 500
    for i in range(0, len(all_hypotheses), batch_size):
        batch_num = (i // batch_size) + 1
        batch_data = all_hypotheses[i : i + batch_size]
        filename = HYPOTHESIS_DIR / f"local_batch_{batch_num:03d}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch_data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(batch_data)} to {filename}")

if __name__ == "__main__":
    generate_local_factory()
