# trading

台股策略探勘與日常掃描系統。  
此專案的目標是把「資料抓取 -> 策略假設生成 -> 批次回測 -> 驗證篩選 -> 每日掃描通知」串成可重複執行的流程，並以台股交易成本與 T+1 進場規則做回測。

## 專案定位

這不是下單系統，而是研究與訊號篩選系統，主要用途是：

- 從 FinMind 抓取台股日線、籌碼、融資融券資料
- 批次生成多組策略假設
- 對假設進行跨股票回測
- 用統計與市場循環條件過濾策略
- 針對最新資料掃描觸發訊號
- 將通過投票的訊號送到 Telegram

## 系統流程

標準執行順序如下：

1. 設定 `.env`
2. 執行 `python engine/preflight.py`
3. 執行 `python data/fetcher.py --mode full`
4. 執行 `python agents/hypothesis_generator.py`
5. 執行 `python engine/run_backtests.py`
6. 執行 `python engine/validator.py`
7. 執行 `python engine/run_daily_scan.py`

日常更新通常只需要：

1. `python data/fetcher.py --mode daily`
2. `python engine/run_daily_scan.py`

## 主要模組

- `data/`
  負責股票池、資料抓取、原始資料整理與合併。
- `agents/`
  負責生成策略假設。目前 `hypothesis_generator.py` 會依模板與參數組合批次產生假設。
- `engine/`
  負責回測、驗證、每日掃描、訊號檢查、通知發送。
- `config/`
  負責環境設定、路徑管理、加密輸出與市場循環標記。
- `results/`
  儲存假設、回測結果、訊號庫等輸出。

## 環境需求

- Python 3.11
- 建議使用虛擬環境
- Windows / PowerShell 已驗證可直接執行
- 需要網路以存取 FinMind 與 Telegram API

## 安裝

### 1. 建立虛擬環境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安裝相依套件

```powershell
pip install -r requirements.txt
```

### 3. 建立環境變數檔

```powershell
Copy-Item .env.example .env
```

接著編輯 `.env`。

## 環境變數說明

`.env.example` 內目前包含：

```env
ANTHROPIC_API_KEY=your_claude_key_here
ENCRYPT_PASSWORD=replace_with_a_long_random_password
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
FINMIND_TOKEN=your_finmind_token
```

各欄位用途如下：

- `FINMIND_TOKEN`
  必填。`data/fetcher.py` 會用它登入 FinMind API 抓資料。
- `ENCRYPT_PASSWORD`
  必填。回測結果與訊號庫會以 Fernet 加密輸出為 `.enc` 檔。
- `TELEGRAM_BOT_TOKEN`
  若要發送通知則需填寫。`engine/preflight.py` 也會檢查此欄位。
- `TELEGRAM_CHAT_ID`
  若要發送通知則需填寫。`engine/preflight.py` 也會檢查此欄位。
- `ANTHROPIC_API_KEY`
  預留給 LLM 相關流程使用；目前這份基礎流程的主要入口腳本不直接依賴它。

## 快速開始

### 1. 預檢查

```powershell
python engine/preflight.py
```

此腳本會檢查：

- `ENCRYPT_PASSWORD`
- `FINMIND_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `data/parquet_db` 內是否已有 `kline` / `chip` / `margin` parquet 檔

如果資料尚未建立，下一步通常是先跑完整抓取。

### 2. 抓取歷史資料

```powershell
python data/fetcher.py --mode full
```

說明：

- 預設從 `2015-01-01` 開始抓取
- 資料來源包含：
  - 日線價格
  - 三大法人 / 籌碼資料
  - 融資融券資料
- 預設股票池來自 `data/universe.py`
- 目前股票池會去重後截取前 150 檔

指定單一或多檔股票：

```powershell
python data/fetcher.py --mode full --symbol 2330 --symbol 2317
```

日常增量更新：

```powershell
python data/fetcher.py --mode daily
```

`daily` 模式會從既有 parquet 的最新日期往前回補 7 天後再合併去重，避免漏資料。

### 3. 生成策略假設

```powershell
python agents/hypothesis_generator.py
```

預設輸出：

- `results/hypotheses/batch_001.json`

可調整每個模板的抽樣數量與亂數種子：

```powershell
python agents/hypothesis_generator.py --batch-size 200 --seed 42
```

目前策略模板涵蓋：

- 籌碼
- 動能
- 跨股票傳導
- 均值回歸
- 月底 / 季底 / 年初等日曆效應
- 價量結構
- 逆勢 / 情緒類因子

注意：

- `D` 類、`I` 類以及 `F02` 在目前回測實作中屬於未支援，生成器仍保留模板概念，但回測會將其視為 `supported = False`。

### 4. 批次回測

```powershell
python engine/run_backtests.py
```

預設輸入 / 輸出：

- 輸入：`results/hypotheses/batch_001.json`
- 輸出：`results/backtests/batch_001.enc`

常用參數：

```powershell
python engine/run_backtests.py --progress
python engine/run_backtests.py --workers 4 --chunksize 10
python engine/run_backtests.py --start-index 0 --count 300
```

回測特性：

- 以全股票池逐一套用假設
- 訊號出現後採 T+1 開盤進場
- 持有天數由 `horizon_days` 決定
- 遇到漲停 / 跌停開盤會跳過
- 已內建台股來回成本模型
- 放空交易另計借券成本

### 5. 大批量可續跑回測

若假設數量很多，建議使用 chunk 版本：

```powershell
python engine/run_backtests_chunked.py --chunk-size 100 --workers 4
```

常用範例：

```powershell
python engine/run_backtests_chunked.py --chunk-size 100 --workers 4 --no-inner-progress
python engine/run_backtests_chunked.py --start-index 300 --count 500
```

特性：

- 會把輸出拆成多個 chunk 檔案
- 已存在的 chunk 會自動略過
- 適合長時間跑批次時中斷後續跑

### 6. 驗證與建立訊號庫

```powershell
python engine/validator.py
```

預設輸入 / 輸出：

- 輸入：`results/backtests/batch_001.enc`
- 輸出：`results/signals/library.enc`

如果是 chunked 結果，可以用：

```powershell
python engine/validator.py --input-glob "results/backtests/chunks/*.enc"
```

目前驗證條件包含：

- `supported = True`
- `sample_count >= 200`
- `win_rate >= 0.55`
- `oos_win_rate >= 0.53`
- `sharpe >= 1.0`
- `adjusted_p_value < 0.05`
- 牛市 / 熊市 / 盤整三種市場循環各至少 30 筆樣本

另外還會做兩層處理：

- 同一 `hypothesis_id` 去重，優先保留樣本數與績效較佳者
- 根據交易報酬相關性過濾過度相似的訊號，建立較乾淨的 signal library

### 7. 每日掃描

```powershell
python engine/run_daily_scan.py
```

此步驟會：

- 載入 `results/signals/library.enc`
- 對最新市場資料逐檔計算是否觸發
- 將相同股票、相同方向的訊號做分組投票
- 只有來自至少 2 個不同 group 的訊號才會保留
- 依 group 數量給 1 到 3 顆星
- 若 Telegram 設定完整，會同步發送通知

指定股票測試：

```powershell
python engine/run_daily_scan.py --symbol 2330 --symbol 2317
```

## 訊號檢查

可用於確認特定假設近期是否有觸發：

```powershell
python engine/inspect_signal.py --hypothesis-id B05_0063
```

輸出最近 5 天觸發清單：

```powershell
python engine/inspect_signal.py --hypothesis-id B05_0063 --lookback-days 5 --output results/signals/B05_0063_recent_5d.csv
```

支援：

- `.csv`
- `.json`

用途：

- 檢查某個策略是否真的在最近市場條件下活躍
- 匯出近期觸發股票清單給人工複核
- 對 `B05` 類型額外查看 near miss 與條件拆解

## 目錄結構

```text
trading/
|-- agents/
|-- config/
|-- data/
|   |-- parquet_db/
|   `-- raw/
|-- engine/
|-- logs/
|-- results/
|   |-- hypotheses/
|   |-- backtests/
|   `-- signals/
|-- .env
|-- .env.example
|-- requirements.txt
`-- README.md
```

## 重要輸出檔案

- `results/hypotheses/*.json`
  策略假設原始清單，未加密。
- `results/backtests/*.enc`
  回測結果，加密輸出。
- `results/backtests/chunks/*.enc`
  分段回測結果，加密輸出。
- `results/signals/*.enc`
  驗證後的訊號庫或其他訊號輸出，加密輸出。
- `data/parquet_db/*.parquet`
  市場資料快取，不應提交到版本控制。

## 資料與策略限制

使用前應先理解以下限制：

- 目前資料頻率為日資料，不是分鐘資料或逐筆資料
- 進出場採用簡化規則，不含真實撮合、滑價模型與成交量約束
- `D` 類與 `I` 類模板目前未完成實作
- `F02` 模板目前明確標記為未支援
- 預設股票池不是全市場，而是 `data/universe.py` 內定義的 150 檔樣本池
- Telegram 未設定時，`run_daily_scan.py` 仍可印出訊號，但不會送出通知

## 安全規則

- 不要提交 `.env`
- 不要提交加密輸出、第三方加密函式庫或 parquet 資料檔
- 所有盤後訊號應以 T+1 進場理解，不可直接當作當日收盤成交
- 回測績效必須視為研究結果，不應直接當作實盤保證

## Docker

此專案附有簡單的 `Dockerfile`：

```powershell
docker build -t trading .
docker run --rm trading
```

注意：

- 容器預設執行 `python engine/run_daily_scan.py`
- 若要在容器內正常運作，仍需把 `.env`、資料目錄與結果目錄一併掛載或注入

## 常見問題

### `FINMIND_TOKEN is required.`

代表 `.env` 未正確設定 `FINMIND_TOKEN`，或目前 shell session 沒有讀到 `.env`。

### `ENCRYPT_PASSWORD is required for encrypted output.`

代表你在執行回測輸出或載入 `.enc` 檔時沒有設定 `ENCRYPT_PASSWORD`。

### `Signal library not found`

代表你尚未先執行 `engine/validator.py` 建立訊號庫。

### `Hypothesis file not found`

代表你尚未先執行 `agents/hypothesis_generator.py`，或輸入了錯誤的路徑。

### `No signals triggered.`

代表最新資料下沒有任何策略觸發，或雖有原始 trigger，但未通過至少 2 個不同 group 的投票門檻。

## 建議操作節奏

研究初次建庫：

1. `python engine/preflight.py`
2. `python data/fetcher.py --mode full`
3. `python agents/hypothesis_generator.py`
4. `python engine/run_backtests_chunked.py --chunk-size 100 --workers 4`
5. `python engine/validator.py --input-glob "results/backtests/chunks/*.enc"`
6. `python engine/run_daily_scan.py`

每日例行更新：

1. `python data/fetcher.py --mode daily`
2. `python engine/run_daily_scan.py`

## 目前相依套件

核心套件包括：

- `pandas`
- `numpy`
- `pyarrow`
- `FinMind`
- `scipy`
- `statsmodels`
- `cryptography`
- `tqdm`
- `python-dotenv`
- `requests`

完整版本請見 `requirements.txt`。
