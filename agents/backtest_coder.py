from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.llm_router import cloud_llm

LOCAL_STRATEGY_TEMPLATES = {
    "A": """
    def next(self):
        # A類：籌碼邏輯
        if self.data.foreign_net[-1] > self.threshold_a and self.data.trust_net[-1] < -self.threshold_a:
            if not self.position:
                self.buy()
        elif len(self.data) >= self.horizon_days:
            self.position.close()
""",
    "B": """
    def next(self):
        # B類：動量加速
        if self.data.close_return[-1] > self.bar_body_pct:
            if not self.position:
                self.buy()
        elif len(self.data) >= self.horizon_days:
            self.position.close()
""",
    "E": """
    def next(self):
        # E類：均值回歸 (RSI/Stochastic)
        if self.data.rsi_14[-1] < self.indicator_val:
            if not self.position:
                self.buy()
        elif self.data.rsi_14[-1] > 70 or len(self.data) >= self.horizon_days:
            self.position.close()
""",
    "J": """
    def next(self):
        # J類：情緒極值
        if self.data.margin_balance[-1] > self.data.margin_balance[-20:].max():
            if not self.position:
                self.buy()
        elif len(self.data) >= self.horizon_days:
            self.position.close()
"""
}

def generate_local_backtest_code(hypothesis: dict[str, Any]) -> str:
    """
    不使用 LLM，直接根據母題 ID 產生對應的本地程式碼模板
    """
    hypothesis_id = hypothesis.get("hypothesis_id", "unknown")
    template_id = hypothesis.get("id", "")
    family = template_id[:1]
    params = hypothesis.get("params", {})
    
    # 將參數定義為類別變數 (符合 backtesting.py 規範)
    param_lines = []
    for k, v in params.items():
        val = f"'{v}'" if isinstance(v, str) else v
        param_lines.append(f"    {k} = {val}")
    
    class_params = "\n".join(param_lines)
    
    # 獲取對應家族的 next() 實作，如果沒有則用預設
    next_impl = LOCAL_STRATEGY_TEMPLATES.get(family, """
    def next(self):
        # 預設邏輯：價格上漲進場
        if self.data.Close[-1] > self.data.Close[-2]:
            if not self.position:
                self.buy()
        elif len(self.data) >= self.horizon_days:
            self.position.close()
""")

    code = f"""
class Strategy_{hypothesis_id}(Strategy):
    # 參數定義
{class_params}

    def init(self):
        pass
        
    {next_impl.strip()}
"""
    return code

def generate_backtest_code(hypothesis: dict[str, Any], use_local: bool = False) -> str:
    """
    生成單一假設的回測程式碼，支援本地規則或 LLM
    """
    if use_local:
        return generate_local_backtest_code(hypothesis)
        
    try:
        template_id = hypothesis.get("id", "")
        params = hypothesis.get("params", {})
        desc = hypothesis.get("desc", "")
        hypothesis_id = hypothesis.get("hypothesis_id", "")

        # 構建 Agent 2 的 prompt
        prompt = f"""
你是一個專業的量化交易策略程式碼生成器。請根據以下假設結構，生成完整的 backtesting.py 回測程式碼。

**假設資訊：**
- 假設 ID: {hypothesis_id}
- 模板 ID: {template_id}
- 描述: {desc}
- 參數: {json.dumps(params, indent=2)}

**要求：**
1. 生成一個完整的 Strategy 類，繼承自 backtesting.Strategy
2. 在 init() 方法中設定所有參數，使用 hypothesis['params'] 字典
3. 在 next() 方法中實作訊號偵測邏輯
4. 嚴格遵守 T+1 進場鐵律：訊號出現在 T 日，進場點為 T+1 日開盤
5. 加入漲跌停過濾：檢查 T+1 開盤是否為漲停（>9.5%）或跌停（<-9.5%）
6. 使用 self.data.PrevClose 欄位進行漲跌停判斷
7. 所有參數使用佔位符名稱，如 threshold_a, consecutive_n 等
8. 程式碼必須能夠在 backtesting.py 框架中運行
9. 包含必要的 import 語句
10. 訊號方向根據模板 ID 自動判斷（參考 engine/backtest.py 的 infer_direction 函數）

**模板類型對應邏輯：**
- A 類（籌碼矛盾）: 使用 foreign_net, trust_net, dealer_net, margin_balance
- B 類（動量加速）: 使用價格和成交量變化率
- C 類（跨股聯動）: 檢查特定股票的行為
- D 類（基本面）: 使用 EPS 等財務指標（如果可用）
- E 類（均值回歸）: 使用 RSI, 布林帶等技術指標
- F 類（時間結構）: 使用月份、日期等時間條件
- G 類（量價背離）: 使用成交量與價格的背離
- H 類（反直覺）: 利空出盡、利多出盡等反向訊號
- I 類（跨市場）: 使用外部指數資料
- J 類（情緒極端）: 使用融資餘額、成交量極端值
- K 類（序列模式）: 使用 detect_sequence() 函數
- L 類（跨序列）: 使用複合條件
- M 類（群體行為）: 使用 detect_group_sequence() 函數

**輸出格式：**
只輸出完整的 Python 程式碼，不要包含任何解釋或 markdown 格式。
程式碼應該可以直接複製到 .py 檔案中運行。
"""

        return cloud_llm(prompt)
    except Exception as e:
        # 返回一個基本的錯誤處理版本
        hypothesis_id = hypothesis.get("hypothesis_id", "unknown")
        return f"""
# Error generating code for {hypothesis_id}: {str(e)}

class Strategy_{hypothesis_id}(Strategy):
    def init(self):
        pass
    
    def next(self):
        pass
"""


def generate_all_backtests(hypotheses_file: str | Path, output_file: str | Path, target_id: str | None = None, use_local: bool = False) -> None:
    """
    為所有或指定假設生成回測程式碼
    """
    hypotheses_file = Path(hypotheses_file)
    output_file = Path(output_file)

    if not hypotheses_file.exists():
        raise FileNotFoundError(f"Hypotheses file not found: {hypotheses_file}")

    # 讀取假設
    with open(hypotheses_file, 'r', encoding='utf-8') as f:
        hypotheses = json.load(f)

    # 如果有指定 ID，則過濾
    if target_id:
        hypotheses = [h for h in hypotheses if h.get("hypothesis_id") == target_id]
        if not hypotheses:
            print(f"No hypothesis found with ID: {target_id}")
            return

    # 生成程式碼
    generated_code = []
    generated_code.append("# Auto-generated backtest strategies")
    generated_code.append("# Generated by Agent 2 (backtest_coder.py)")
    generated_code.append("")
    generated_code.append("from backtesting import Strategy")
    generated_code.append("import pandas as pd")
    generated_code.append("import numpy as np")
    generated_code.append("")
    generated_code.append("# Import project modules")
    generated_code.append("import sys")
    generated_code.append("from pathlib import Path")
    generated_code.append("ROOT_DIR = Path(__file__).resolve().parents[1]")
    generated_code.append("if str(ROOT_DIR) not in sys.path:")
    generated_code.append("    sys.path.insert(0, str(ROOT_DIR))")
    generated_code.append("")
    generated_code.append("from engine.backtest import detect_sequence, detect_group_sequence")
    generated_code.append("")

    for hypothesis in hypotheses:
        hypothesis_id = hypothesis.get("hypothesis_id", "")
        print(f"Generating code for {hypothesis_id} {'(Local Mode)' if use_local else ''}...")
        code = generate_backtest_code(hypothesis, use_local=use_local)

        generated_code.append(f"# {hypothesis_id}")
        generated_code.append(code)
        generated_code.append("")

    # 寫入檔案
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(generated_code))

    print(f"Generated backtest code for {len(hypotheses)} hypotheses: {output_file}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate backtest code for hypotheses using Agent 2")
    parser.add_argument(
        "--input",
        default="results/hypotheses/batch_001.json",
        help="Input hypotheses JSON file"
    )
    parser.add_argument(
        "--output",
        default="engine/generated_backtests.py",
        help="Output generated backtest code file"
    )
    parser.add_argument(
        "--hypothesis-id",
        help="Specific hypothesis ID to generate code for (prevents mass token usage)"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local rule-based generation instead of cloud LLM (free tier friendly)"
    )

    args = parser.parse_args()
    generate_all_backtests(args.input, args.output, target_id=args.hypothesis_id, use_local=args.local)


def build_backtest_payload(hypothesis: dict[str, Any]) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "template_id": hypothesis.get("id"),
        "params": hypothesis.get("params", {}),
        "desc": hypothesis.get("desc", ""),
        "family": str(hypothesis.get("id", ""))[:1],
    }
