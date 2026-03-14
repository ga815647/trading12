import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import HYPOTHESIS_DIR, LOG_DIR, ensure_runtime_dirs
from engine.backtest import prepare_market_frame, build_signal_series, infer_direction

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("xray")

def find_hypothesis(hypo_id: str) -> dict | None:
    """Search for the hypothesis in the hypothesis directory."""
    for hf in HYPOTHESIS_DIR.glob("*.json"):
        try:
            with open(hf, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    if item.get("hypothesis_id") == hypo_id:
                        return item
        except:
            continue
    return None

def run_xray(symbol: str, hypo_id: str, start_date: str = None, end_date: str = None):
    ensure_runtime_dirs()
    
    # 1. Load Hypothesis
    hypo = find_hypothesis(hypo_id)
    if not hypo:
        logger.error(f"❌ Cannot find hypothesis ID: {hypo_id}")
        return

    logger.info(f"🔍 [X-Ray] Loading Strategy: {hypo_id}")
    logger.info(f"📝 Desc: {hypo.get('desc')}")
    logger.info(f"⚙️ Params: {json.dumps(hypo.get('params'), indent=2)}")

    # 2. Load Market Data
    df = prepare_market_frame(symbol)
    if df is None:
        logger.error(f"❌ Cannot load market data for symbol: {symbol}")
        return
    
    if start_date:
        df = df[df.index >= start_date]
    if end_date:
        df = df[df.index <= end_date]
        
    if df.empty:
        logger.error("❌ DataFrame is empty after date filtering.")
        return

    # 3. Build Signal Components
    # We reconstruct the trigger and filter signals for inspection
    template_id = str(hypo.get("id", ""))
    trigger_id = template_id
    filter_id = "NONE"
    
    if template_id.startswith("LM_"):
        parts = template_id.split("_")
        if len(parts) >= 4:
            trigger_id = parts[1]
            filter_id = "_".join(parts[2:-1])

    # Re-use engine logic to get components
    from engine.backtest import is_supported_hypothesis, calculate_tva_state
    
    # Custom signal series for inspection
    # build_signal_series returns the full composite signal
    full_signal = build_signal_series(symbol, df, hypo)
    
    # We manually get trigger and filter signals for display
    # (By creating temporary hypothesis objects)
    trigger_hypo = {"id": trigger_id, "params": hypo.get("params", {}), "hypothesis_id": "TMP_T"}
    filter_hypo = {"id": filter_id, "params": hypo.get("params", {}), "hypothesis_id": "TMP_F"}
    
    trigger_sig = build_signal_series(symbol, df, trigger_hypo)
    filter_sig = build_signal_series(symbol, df, filter_hypo) if filter_id != "NONE" else pd.Series(True, index=df.index)
    
    # 4. Scan and Print
    direction = infer_direction(hypo)
    triggers_found = df[full_signal]
    
    logger.info(f"\n🚀 Found {len(triggers_found)} signals for {symbol} | Direction: {direction}")
    logger.info("-" * 80)
    
    xray_details = []
    
    display_count = 0
    for date, row in triggers_found.iterrows():
        # Get T+1 Open
        t_plus_1_idx = df.index.get_loc(date) + 1
        t_plus_1_info = "N/A (End of Data)"
        t_plus_1_date = "N/A"
        t_plus_1_open = 0.0
        
        if t_plus_1_idx < len(df):
            next_row = df.iloc[t_plus_1_idx]
            t_plus_1_date = str(next_row.name.date())
            t_plus_1_open = next_row["Open"]
            t_plus_1_info = f"{t_plus_1_open:.2f}"

        # Indicators for debug
        # We can add more based on common triggers as needed
        indicators = {
            "Close": row["Close"],
            "Foreign_Net": row.get("foreign_net", 0),
            "Trust_Net": row.get("trust_net", 0),
            "Vol": row["Volume"],
            "Vol_MA5": row.get("volume_ma_5", 0),
            "Price_MA20": row.get("price_ma_20", 0),
            "K": row.get("stoch_14", 0),
            "D": row.get("stoch_d_3", 0)
        }

        # Detailed logging for terminal
        if display_count < 15:
            logger.info(f"📅 [T] {date.date()} | Close: {row['Close']:.2f}")
            logger.info(f"   ∟ Trigger ({trigger_id}): {'✅' if trigger_sig.loc[date] else '❌'} | Filter ({filter_id}): {'✅' if filter_sig.loc[date] else '❌'}")
            logger.info(f"   ∟ Data: F_Net={indicators['Foreign_Net']:.0f}, T_Net={indicators['Trust_Net']:.0f}, Vol={indicators['Vol']:.0f}, MA20={indicators['Price_MA20']:.2f}")
            if "stoch_14" in row:
                logger.info(f"   ∟ Indicators: K={indicators['K']:.2f}, D={indicators['D']:.2f}, RSI={row.get('rsi_14', 0):.2f}")
            logger.info(f"   ∟ [T+1 Execution] {t_plus_1_date} | Expected Open: {t_plus_1_info}")
            logger.info("-" * 40)
            display_count += 1
        
        # Collect for CSV
        detail = {
            "date": str(date.date()),
            "close": row["Close"],
            "trigger_ok": trigger_sig.loc[date],
            "filter_ok": filter_sig.loc[date],
            "foreign_net": indicators["Foreign_Net"],
            "trust_net": indicators["Trust_Net"],
            "volume": indicators["Vol"],
            "k_val": indicators["K"],
            "d_val": indicators["D"],
            "exec_date": t_plus_1_date,
            "exec_open": t_plus_1_open
        }
        xray_details.append(detail)

    if len(triggers_found) > 15:
        logger.info(f"... (Truncated {len(triggers_found) - 15} more signals from display)")

    # 5. Export to CSV
    if xray_details:
        csv_path = LOG_DIR / f"xray_{symbol}_{hypo_id}.csv"
        pd.DataFrame(xray_details).to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info(f"\n💾 Full details exported to: {csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Glass-Box X-Ray Tester")
    parser.add_argument("--symbol", required=True, help="Stock symbol (e.g., 2330)")
    parser.add_argument("--hypothesis-id", required=True, help="Hypothesis ID to test")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    run_xray(args.symbol, args.hypothesis_id, args.start_date, args.end_date)
