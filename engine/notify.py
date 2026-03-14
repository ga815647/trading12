from __future__ import annotations

import sys
from typing import Any
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import SETTINGS


def send_signal(message: str) -> bool:
    if not SETTINGS.telegram_bot_token or not SETTINGS.telegram_chat_ids:
        print(f"Skipping notification: Token={bool(SETTINGS.telegram_bot_token)}, IDs={len(SETTINGS.telegram_chat_ids)}")
        return False
        
    url = f"https://api.telegram.org/bot{SETTINGS.telegram_bot_token}/sendMessage"
    success = False
    
    for chat_id in SETTINGS.telegram_chat_ids:
        payload = {"chat_id": chat_id, "text": message}
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code != 200:
                print(f"Telegram Error for ID {chat_id}: {response.status_code} - {response.text}")
            else:
                success = True
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to send Telegram signal to {chat_id}: {e}")
            
    return success


def build_signal_message(signal: dict[str, Any], pipeline: str = "long") -> str:
    """
    根據管線類型構建不同格式的推播訊息
    """
    # 根據管線確定標題和 emoji
    if pipeline == "long":
        emoji = "📈"
        title = "做多訊號"
    elif pipeline == "exit":
        emoji = "🔔"
        title = "賣出訊號"
    elif pipeline == "short":
        emoji = "📉"
        title = "放空訊號"
    else:
        emoji = "⚠️"
        title = signal.get("direction", "long").upper()
    
    # 星星評級
    stars = "⭐" * signal.get("stars", 1)
    
    # 股票資訊
    stock_id = signal['stock_id']
    
    # 訊號詳情
    lines = [f"【{title} {stars}】{stock_id}"]
    
    # 檢查是否有時間到期訊號 (group 為 time)
    time_signal = next((s for s in signal.get("signals", []) if s.get("group") == "time"), None)
    
    if time_signal:
        desc = time_signal.get("desc", "")
        pnl = time_signal.get("pnl_ext", 0.0)
        entry_price = time_signal.get("entry_price", 0.0)
        pnl_str = f"{pnl:+.1%}"
        lines.append(f"[⏰] {desc}")
        lines.append(f"• 進場價格：{entry_price:.2f}")
        lines.append(f"• 目前估計損益：{pnl_str}")
        
    # 處理其他技術/籌碼訊號
    GROUP_DISPLAY = {
        "chip":          "籌碼",
        "chip_sequence": "籌碼序列",
        "composite":     "複合序列",
        "momentum":      "動能",
        "mean_reversion":"均值回歸",
        "price_volume":  "量價",
        "contrarian":    "逆勢",
        "sentiment":     "情緒",
        "calendar":      "時間",
        "group_behavior":"群體行為",
        "cross_stock":   "跨股",
        "cross_market":  "跨市場",
    }

    # 在訊號標題後先加現價（只加一次，不在迴圈裡重複）
    current_close = signal.get("signals", [{}])[0].get("close", 0.0) if signal.get("signals") else 0.0
    if current_close > 0:
        stop_loss_price = current_close * 0.92
        lines.append(f"• 現價：{current_close:.2f}　參考停損：{stop_loss_price:.2f}（-8%）")

    for item in signal.get("signals", []):
        if item.get("group") == "time":
            continue
        group = item.get("group", "")
        signal_type = GROUP_DISPLAY.get(group, "技術指標")
        horizon_days = item.get("horizon_days", 10)
        win_rate = item.get("win_rate", 0.0)
        sample_count = item.get("sample_count", 0)
        sharpe = item.get("portfolio_sharpe", 0.0)

        # 把 desc 的 "Matrix Strategy: Trigger X with filter Y" 轉成可讀格式
        raw_desc = item.get("desc", "")
        if "Trigger" in raw_desc and "filter" in raw_desc:
            # 例：Matrix Strategy: Trigger E03 with filter PZ_CHEAP
            # → 顯示：E03 × PZ_CHEAP
            try:
                trigger_part = raw_desc.split("Trigger ")[1].split(" with")[0]
                filter_part  = raw_desc.split("filter ")[1] if "filter " in raw_desc else "NONE"
                display_desc = f"{trigger_part} × {filter_part}" if filter_part != "NONE" else trigger_part
            except Exception:
                display_desc = raw_desc
        else:
            display_desc = raw_desc

        lines.append(f"[{signal_type}] {display_desc}")
        lines.append(f"• 持有：{horizon_days}日　勝率：{win_rate:.1%}（{sample_count}筆）　Sharpe：{sharpe:.2f}")

        if pipeline == "exit" and "pnl_ext" in item:
            pnl_str = f"{item['pnl_ext']:+.1%}"
            lines.append(f"• 估計損益：{pnl_str}")

    return "\n".join(lines)


def test_notify() -> None:
    send_signal("Strategy Mining v11 connectivity test passed.")


if __name__ == "__main__":
    test_notify()
