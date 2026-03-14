from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SIGNAL_DIR, ensure_runtime_dirs
from config.encrypt import load_signals
from data.universe import UNIVERSE
from engine.notify import build_signal_message, send_signal
from engine.portfolio import vote_signals, get_current_holdings


def check_time_exits(detailed_holdings: list[dict], market_cache: dict[str, pd.DataFrame]) -> list[dict]:
    """
    檢查持有部位是否已達持有天數 (依據實際 K 線數量)
    """
    exit_signals = []
    for pos in detailed_holdings:
        symbol = pos["symbol"]
        entry_date = pos["entry_date"]
        horizon = pos["horizon_days"]
        entry_price = pos["entry_price"]
        
        frame = market_cache.get(symbol)
        if frame is None or len(frame) == 0:
            continue
            
        # 找到進場日或之後的第一個交易日
        entry_dt = pd.to_datetime(entry_date)
        post_entry_df = frame[frame.index >= entry_dt]
        
        if post_entry_df.empty:
            continue
            
        # 實際經過的 K 線數量 (不含進場當日)
        trading_days_passed = len(post_entry_df) - 1
        
        if trading_days_passed >= horizon:
            current_price = float(frame["Close"].iloc[-1])
            pnl = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0
            
            exit_signals.append({
                "stock_id": symbol,
                "direction": "exit",
                "hypothesis_id": "TIME_EXIT",
                "signal_id": "time_exit",
                "id": "T_EXIT",
                "desc": f"Time Horizon Reached ({trading_days_passed}/{horizon} days)",
                "group": "time",
                "horizon_days": horizon,
                "close": current_price,
                "pnl_ext": pnl, # Added PnL extension
                "entry_price": entry_price
            })
    return exit_signals


def run_daily_scan(signal_library: list[dict], symbols: list[str] | None = None) -> dict[str, list[dict]]:
    """
    運行三管線每日掃描
    """
    from engine.backtest import evaluate_latest_signal, load_market_cache, infer_direction
    from engine.portfolio import get_detailed_holdings

    detailed_holdings = get_detailed_holdings()
    current_holding_symbols = [h["symbol"] for h in detailed_holdings]

    # 定義各管線的目標股票
    long_universe = set(symbols or UNIVERSE)
    exit_universe = set(current_holding_symbols)
    short_universe = set(UNIVERSE[:100])
    
    # 載入市場資料快取
    all_symbols = long_universe | exit_universe | short_universe
    market_cache = load_market_cache(sorted(all_symbols))
    
    triggered = {
        "long": [],
        "exit": [],
        "short": []
    }
    
    # 1. 檢查時間到期出場
    triggered["exit"].extend(check_time_exits(detailed_holdings, market_cache))
    
    # 2. 檢查技術訊號觸發
    for hypothesis in signal_library:
        if hypothesis.get("excluded"):
            continue
            
        direction = infer_direction(hypothesis)
        target_universe = {
            "long": long_universe,
            "exit": exit_universe, 
            "short": short_universe
        }.get(direction, set())
        
        if not target_universe:
            continue
            
        for stock_id in target_universe:
            trigger = evaluate_latest_signal(stock_id, hypothesis, market_cache=market_cache)
            if trigger:
                triggered[direction].append(trigger)
    
    # 對各管線進行訊號投票
    voted = {}
    for pipeline in ["long", "exit", "short"]:
        voted[pipeline] = vote_signals(triggered[pipeline])
    
    return voted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan latest market data for active signals.")
    parser.add_argument("--input", default=str(SIGNAL_DIR / "library.enc"))
    parser.add_argument("--symbol", action="append", dest="symbols")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(
            f"Signal library not found: {input_path}. Run engine/validator.py first."
        )
    signal_library = load_signals(input_path)
    voted_signals = run_daily_scan(signal_library, symbols=args.symbols)
    
    # 處理各管線的訊號
    total_sent = 0
    for pipeline, signals in voted_signals.items():
        if not signals:
            print(f"No {pipeline} signals triggered.")
            continue
            
        pipeline_name = {
            "long": "做多",
            "exit": "賣出平倉", 
            "short": "放空"
        }.get(pipeline, pipeline)
        
        print(f"\n=== {pipeline_name}管線 ===")
        for signal in signals:
            message = build_signal_message(signal, pipeline=pipeline)
            sent = send_signal(message)
            try:
                print(message)
            except UnicodeEncodeError:
                print(message.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
            if sent:
                print("Sent to Telegram.")
                total_sent += 1
    
    if total_sent == 0:
        print("No signals sent to Telegram.")


if __name__ == "__main__":
    main()
