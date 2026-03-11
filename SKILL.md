# Strategy Mining Project Rules — v12
# Antigravity Agent 必須在每次任務開始前讀取並嚴格遵守本文件。

## 禁止事項（最高優先級，任何情況下不得違反）
- 禁止讀取、修改或刪除 results/ 目錄下任何檔案
- 禁止讀取、修改或刪除 signals/ 目錄下任何檔案
- 禁止讀取 .env 或任何 .enc 加密檔案
- 禁止讀取 data/parquet_db/ 下任何 .parquet 檔案
- 禁止在任何輸出、Artifact 或程式碼注釋中顯示任何統計結果或勝率數字
- 禁止在程式碼中填入真實參數數值，一律使用佔位符
  （佔位符命名：threshold_a, threshold_b, days_n, horizon_days, pattern_name）

## T+1 進場鐵律（防止 Look-ahead Bias）
- 所有涉及「盤後資料」的條件（法人買賣超、融資融券、收盤籌碼），
  回測進場點一律設為 T+1 日開盤價
- 禁止以 T 日收盤價作為盤後訊號的進場點
- 違反此規則的回測程式碼視為無效，必須重寫

## 漲跌停過濾鐵律（v11+）
- 所有回測程式碼必須在 T+1 進場前判斷該日是否漲跌停
- 若 T+1 開盤即漲停（漲幅 ≥ 9.5%）或跌停（跌幅 ≤ -9.5%），跳過該筆交易
- 此過濾邏輯寫在 engine/backtest.py 的 next() 方法中

## 交易成本鐵律（v11+）
- 所有回測必須設定 commission=0.002925（單邊 0.2925%）
- 來回總成本約 0.585%，不含成本的回測結果一律作廢
- 禁止使用 commission=0 的回測結果作為策略入庫依據

## 序列型假設規則（v12 新增）
- K 類（序列型籌碼）假設中，pattern 參數只使用 SEQUENCE_PATTERNS 字典中定義的鍵名
- L 類（跨資料源複合序列）假設中，chip_days / price_days 使用 CROSS_SEQUENCE_PARAM_GRIDS 定義的數值範圍
- 不得在程式碼中硬寫具體序列向量或硬寫天數數值，
  一律透過 pattern_name、chip_days、price_days 佔位符在本機填入

## 允許事項
- 修改 engine/、data/、agents/、config/config.py
- 執行 git add、git commit、git push
- 建立和修改 Dockerfile、requirements.txt
- 讀取和修改 SKILL.md 本身（需與開發者確認後執行）
- 每次完成程式碼修改後，應主動執行 git add、git commit、git push，確保 WSL2 本機可透過 git pull 同步
