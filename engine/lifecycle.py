import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SIGNAL_DIR

LIFECYCLE_FILE = SIGNAL_DIR / "strategy_lifecycle.json"

def get_strategy_hash(hypothesis: dict[str, Any]) -> str:
    """
    Generate a unique hash for a strategy based purely on its components,
    ignoring randomized generation IDs to prevent redundant re-testing.
    """
    h_id = str(hypothesis.get("id", hypothesis.get("hypothesis_id", "")))
    params = hypothesis.get("params", {})
    
    # Extract structural identity by stripping the randomized index (_0XXX)
    # Format is LM_{TRIGGER}_{FILTER}_{INDEX}
    parts = h_id.split('_')
    if len(parts) >= 4 and parts[0] == "LM":
        # e.g., LM_A01_E01_0369 -> LM_A01_E01
        structural_id = "_".join(parts[:-1])
    else:
        structural_id = h_id

    # Sort keys to ensure consistent hashing
    param_str = json.dumps(params, sort_keys=True)
    combined = f"{structural_id}|{param_str}"
    print(f"DEBUG Hash: {structural_id} + {param_str}")
    return hashlib.sha256(combined.encode()).hexdigest()

def load_lifecycle() -> dict[str, dict[str, Any]]:
    if not LIFECYCLE_FILE.exists():
        return {}
    try:
        with open(LIFECYCLE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_lifecycle(data: dict[str, dict[str, Any]]):
    LIFECYCLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LIFECYCLE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_lifecycle(results: list[dict[str, Any]], current_bars: int):
    """
    Update the lifecycle status of tested strategies.
    States: active, soft_fail, hard_fail
    """
    registry = load_lifecycle()
    
    for res in results:
        h_id = res.get("id", "")
        params = res.get("params", {})
        h_hash = get_strategy_hash(res)  # Pass the entire dict to hash correctly
        
        sample_count = res.get("sample_count", 0)
        passes = res.get("passes_validation", False)
        
        if sample_count < 30:
            status = "hard_fail"
        elif passes:
            status = "active"
        else:
            status = "soft_fail"
            
        registry[h_hash] = {
            "id": h_id,
            "params": params,
            "status": status,
            "last_tested_bars": current_bars,
            "last_sample_count": sample_count,
            "hypothesis_id": res.get("hypothesis_id")
        }
        
    save_lifecycle(registry)

def filter_and_thaw(hypotheses: list[dict[str, Any]], current_bars: int) -> list[dict[str, Any]]:
    """
    Filters out already tested strategies and thaws soft_fail ones that are stale.
    """
    registry = load_lifecycle()
    filtered = []
    
    for hypo in hypotheses:
        h_hash = get_strategy_hash(hypo)
        record = registry.get(h_hash)
        
        if not record:
            # Never tested before
            filtered.append(hypo)
            continue
            
        status = record.get("status")
        
        if status == "hard_fail":
            # Permanently ignore
            continue
            
        if status == "active":
            # Already active in library, no need to re-backtest unless explicitly forced
            continue
            
        if status == "soft_fail":
            # Check for Thaw (復活)
            last_bars = record.get("last_tested_bars", 0)
            if current_bars - last_bars >= 250:
                print(f"[Thaw] Reviving strategy {hypo.get('hypothesis_id')} (Hash: {h_hash[:8]}) after {current_bars - last_bars} bars.")
                filtered.append(hypo)
            else:
                # Still in probation
                continue
                
    return filtered

def get_current_market_bars() -> int:
    """
    Estimate current market bars based on a major stock (e.g., 2330).
    """
    from config.config import PARQUET_DIR
    import pyarrow.parquet as pq
    
    path = PARQUET_DIR / "2330_kline.parquet"
    if not path.exists():
        # Fallback if 2330 is missing, pick the first available
        paths = list(PARQUET_DIR.glob("*_kline.parquet"))
        if not paths:
            return 0
        path = paths[0]
        
    try:
        table = pq.read_table(path, columns=["date"])
        return len(table)
    except Exception:
        return 0

if __name__ == "__main__":
    # Smoke test
    bars = get_current_market_bars()
    print(f"Current market bars: {bars}")
    reg = load_lifecycle()
    print(f"Lifecycle registry size: {len(reg)}")
