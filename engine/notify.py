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
    for item in signal.get("signals", []):
        if item.get("group") == "time":
            continue
        signal_type = "A-籌碼" if str(item['id']).startswith(('A', 'K', 'L')) else "技術指標"
        desc = item['desc']
        horizon_days = item['horizon_days']
        lines.append(f"[{signal_type}] {desc}")
        lines.append(f"• 建議持有：{horizon_days} 個交易日")
        
        # 輔助資訊（如果有 PnL 資訊也顯示，例如賣出管線的技術出場）
        if pipeline == "exit" and "pnl_ext" in item:
            pnl_str = f"{item['pnl_ext']:+.1%}"
            lines.append(f"• 估計損益：{pnl_str}")

    return "\n".join(lines)


def test_notify() -> None:
    send_signal("Strategy Mining v11 connectivity test passed.")


if __name__ == "__main__":
    test_notify()
