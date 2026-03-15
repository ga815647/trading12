from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SIGNAL_DIR, STOP_LOSS_PCT, TAKE_PROFIT_PCT, ensure_runtime_dirs
from config.encrypt import load_signals
from data.universe import UNIVERSE
from engine.notify import build_signal_message, send_signal
from engine.portfolio import vote_signals, get_current_holdings

logger = logging.getLogger(__name__)


def check_time_exits(
    detailed_holdings: list[dict],
    market_cache: dict[str, pd.DataFrame],
    stop_loss: float = STOP_LOSS_PCT,
    take_profit: float = TAKE_PROFIT_PCT,
) -> list[dict]:
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
        current_price = float(frame["Close"].iloc[-1])
        pnl = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0

        exit_reason = None
        if trading_days_passed >= horizon:
            exit_reason = f"時間到期（{trading_days_passed}/{horizon}日）"
        elif pnl <= stop_loss:
            exit_reason = f"止損觸發（{pnl:+.1%}）"
        elif pnl >= take_profit:
            exit_reason = f"止盈觸發（{pnl:+.1%}）"

        if exit_reason:
            exit_signals.append({
                "stock_id": symbol,
                "direction": "exit",
                "hypothesis_id": "AUTO_EXIT",
                "signal_id": "auto_exit",
                "id": "T_EXIT",
                "desc": exit_reason,
                "group": "time",
                "horizon_days": horizon,
                "close": current_price,
                "pnl_ext": pnl,
                "entry_price": entry_price,
            })
    return exit_signals


def run_daily_scan(signal_library: list[dict], symbols: list[str] | None = None, paper_mode: bool = False, force_notify: bool = False, long_only: bool = False) -> dict[str, list[dict]]:
    """
    運行三管線每日掃描
    paper_mode=True 時忽略 portfolio.json，對全市場推播所有訊號（實測用）
    """
    from engine.backtest import evaluate_latest_signal, load_market_cache, infer_direction
    from engine.portfolio import get_detailed_holdings

    detailed_holdings = get_detailed_holdings() if not paper_mode else []
    current_holding_symbols = [h["symbol"] for h in detailed_holdings]

    # 定義各管線的目標股票
    long_universe = set(symbols or UNIVERSE)
    # Paper Mode: 對全體 UNIVERSE 掃描賣出管線，而非只看持倉
    exit_universe = set(symbols or UNIVERSE) if paper_mode else set(current_holding_symbols)
    short_universe = set(UNIVERSE[:100])
    
    # long_only 模式：完全跳過 exit 和 short 管線
    if long_only:
        exit_universe = set()
        short_universe = set()
    
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
            trigger = evaluate_latest_signal(stock_id, hypothesis, market_cache=market_cache, force=force_notify)
            if trigger:
                # 增強 PnL 回報 (針對賣出管線)
                if direction == "exit":
                    pos = next((h for h in detailed_holdings if h["symbol"] == stock_id), None)
                    if pos:
                        entry_price = pos["entry_price"]
                        current_price = trigger["close"]
                        pnl = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0
                        trigger["entry_price"] = entry_price
                        trigger["pnl_ext"] = pnl
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
    parser.add_argument(
        "--paper-mode", action="store_true", default=False,
        help="Paper mode: scan full UNIVERSE for all pipelines, ignoring portfolio.json (testing use)."
    )
    parser.add_argument(
        "--force-notify", action="store_true", default=False,
        help="強制推播所有今日觸發的訊號，忽略首次觸發限制（測試用）"
    )
    parser.add_argument(
        "--long-only", action="store_true", default=False,
        help="只推做多訊號，忽略 exit 和 short 管線（測試階段使用）"
    )
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
    if args.paper_mode:
        print("[Paper Mode] 實測模式：忽略持倉，推播所有管線的全市場訊號。")
    voted_signals = run_daily_scan(signal_library, symbols=args.symbols, paper_mode=args.paper_mode, force_notify=args.force_notify, long_only=args.long_only)
    
    # 處理各管線的訊號
    total_sent = 0
    for pipeline, signals in voted_signals.items():
        if args.long_only and pipeline in ("exit", "short"):
            continue
        if not signals:
            print(f"No {pipeline} signals triggered.")
            continue
            
        pipeline_name = {
            "long": "做多",
            "exit": "賣出平倉", 
            "short": "放空"
        }.get(pipeline, pipeline)
        
        for signal in signals:
            message = build_signal_message(signal, pipeline=pipeline)
            sent = send_signal(message)
            
            # 自動記錄進場（非 paper_mode 才記錄）
            if pipeline == "long" and not args.paper_mode and sent:
                from engine.portfolio import update_holdings
                best_signal = signal.get("signals", [{}])[0]
                update_holdings(
                    symbol=signal["stock_id"],
                    action="add",
                    entry_date=datetime.now().strftime("%Y-%m-%d"),
                    entry_price=best_signal.get("close", 0.0),
                    horizon_days=best_signal.get("horizon_days", 10),
                    hypothesis_id=best_signal.get("hypothesis_id", "unknown"),
                    direction="long"
                )
                logger.info(f"[Portfolio] 記錄進場：{signal['stock_id']} @ {best_signal.get('close', 0.0)}")
            
            # 自動移除出場（非 paper_mode 才移除）
            if pipeline == "exit" and not args.paper_mode and sent:
                from engine.portfolio import update_holdings
                update_holdings(symbol=signal["stock_id"], action="remove")
                logger.info(f"[Portfolio] 移除持倉：{signal['stock_id']}")
            
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
