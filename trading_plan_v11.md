# 台股自動化策略挖掘系統
### Automated Strategy Mining System
**完整計畫書 v11.0 ｜ Windows 11 + WSL2 + Docker**

> ⚠️ 本文件為機密文件，禁止公開或分享任何與交易規律相關之內容

---

## 目錄

0. 系統概述與目標
1. 環境建置
2. 帳號與 API 清單
3. 系統隔離與安全設計
4. 網路攻擊防護
5. Agent 防洩密安全架構
6. AI 編碼助手工作流程
7. 系統架構（核心）
8. 建置時程
9. 待辦清單
- 附錄 A：常用指令與緊急處理
- 附錄 B：v10 → v11 變更摘要

---

## 0｜系統概述與目標

### 0.1 核心理念

本系統透過自動化產生大量假設、對歷史數據進行統計驗證，挖掘具有統計顯著性的
**中期交易規律（持有 10–60 個交易日）**，再將多個有效規律疊加成綜合訊號，
以 **Telegram Bot 推播**通知人工執行買賣。

**程式負責找規律與發訊號，人負責判斷與下單。程式永遠不持有下單權限。**

> 護城河不是任何一個規律本身，而是持續挖掘與驗證規律的能力。規律會失效，機器不會停。

> ⚠️ **定位說明**：本系統定位為「量化輔助的中期主動投資」，非自動交易、非高頻交易。
> 最短持有天數設為 **10 個交易日（約 2 週）**，低於此門檻的策略不納入規律庫，
> 以符合散戶手動操作的實際節奏與交易成本結構。

### 0.2 整體流程

```
AI 編碼助手（Cursor / Windsurf）
  → 假設產生（Agent 1，雲端 Claude API，依 50 個母題模板 Grid Search）
  → 程式碼骨架（Agent 2，雲端 Claude API）
  → 回測執行（WSL2 本機，backtesting.py，含交易成本 + 漲跌停過濾）
  → 統計篩選（Agent 3，純 Python，FDR 校正 + 市場週期驗證）
  → 加密存檔
  → 訊號疊加（群組投票制）
  → Telegram Bot 推播（漲 / 跌方向 + 觸發規律 + 持有天數）
  → 人工下單（永豐證券 App）
```

### 0.3 為什麼選台股

- 市場效率低，真正做量化的機構極少，散戶比例高達六七成
- 三大法人每日籌碼、融資融券完全公開，美股沒有對應資料
- 台股有明確的漲跌停制度（±10%），限制單日極端損失，適合中期持有策略

> **Phase 3 Roadmap（長期）：** 中文法說會 NLP 分析是潛在護城河，但需要額外的語料庫
> 與情緒模型建置，不在當前計畫範圍內，列為未來擴展項目。

---

## 1｜環境建置（Windows 11 逐步說明）

> 遇到錯誤時，把完整錯誤訊息複製，直接貼給 AI 編碼助手處理即可。
> **第一次接觸 Vibe Coding 的人，請先完成 1.0 節（Cursor 設定），再繼續往下。**

### 1.0 安裝並設定 AI 編碼助手 Cursor（一次性，約 10 分鐘）

Cursor 是整個開發流程的核心工具，所有程式碼由它代勞。

1. 前往 [cursor.com](https://cursor.com) 下載並安裝
2. 開啟 Cursor → 登入 GitHub 帳號
3. **重要：`.cursorignore` 需與 `.gitignore` 保持同步，防止 AI 讀取機密檔案**

> ⚠️ **執行時機：** `.gitignore` 在 §1.7 才建立，**請完成 §1.7 後再執行下列指令**，現在先跳過：
> ```bash
> cp .gitignore .cursorignore   # ← 完成 §1.7 後才執行
> ```

4. Cursor Settings → Features → 確認「Include .gitignore files」為關閉狀態
5. **絕對不要**讓 Cursor 的 AI 讀取 `.env`、`results/`、`data/parquet_db/` 任何內容

**Cursor 基本操作：**

| 動作 | 快捷鍵 / 方式 |
|------|------------|
| 開啟 AI 對話（Agent 模式） | `Ctrl + I` |
| 請 AI 直接改程式碼 | 在對話框輸入指令，AI 會直接編輯檔案 |
| 取消 AI 的修改 | `Ctrl + Z` 或對話框點「Reject」 |
| 查看 AI 的修改差異 | 對話框點「Review」 |

### 1.1 為什麼用 WSL2 + Docker

| 工具 | 理由 |
|------|------|
| 原生 Windows Python | 路徑問題多、套件相容性差，AI 容易出錯 |
| WSL2（必裝） | 在 Windows 裡跑真正的 Ubuntu Linux，所有 Linux 指令完全相容 |
| Docker（建議） | 把整個專案打包成隔離容器，換電腦不怕，敏感資料不外洩 |

### 1.2 安裝 WSL2（約 10 分鐘，一次性）

```powershell
# 以系統管理員執行 PowerShell
wsl --install
# 重開機後設定 Ubuntu 帳號密碼，確認：
wsl --version
```

### 1.3 安裝 Docker Desktop（約 15 分鐘，一次性）

1. 前往 docker.com/products/docker-desktop 下載
2. 安裝時勾選「Use WSL 2 instead of Hyper-V」
3. 啟動後 Settings → Resources → WSL Integration → 確認 Ubuntu 已開啟
4. 在 Ubuntu 確認：`docker --version`

### 1.4 在 WSL2 設定 Python 環境

```bash
python3 --version
# 若低於 3.10，升級：
sudo apt update && sudo apt install python3.11 python3.11-venv python3-pip -y
```

> ⚠️ **不安裝 Ollama。** Agent 3 為純 Python 統計腳本，不需要本地 LLM。

### 1.5 建立專案目錄結構

```bash
mkdir -p ~/strategy-mining/{engine,data,agents,config,results/hypotheses,results/backtests,results/signals,logs}
mkdir -p ~/strategy-mining/data/{raw,parquet_db}
cd ~/strategy-mining
touch .gitignore .cursorignore .env requirements.txt README.md SKILL.md
touch engine/{backtest,validator,portfolio,notify,check_decay,cost_model,run_backtests}.py
touch data/{fetcher,processor,universe}.py
touch agents/{hypothesis_generator,backtest_coder,signal_evaluator,llm_router}.py
touch config/{config,encrypt,market_cycle}.py
```

**目錄結構說明：**

```
~/strategy-mining/
├── data/
│   ├── raw/              # FinMind 原始下載暫存（不進 repo）
│   ├── parquet_db/       # 轉檔後的高效能資料庫（不進 repo）
│   ├── universe.py       # Phase 1 標的池定義（150 檔）
│   ├── fetcher.py        # 資料抓取腳本（含認證與 rate limit）
│   └── processor.py      # 資料清洗腳本
├── engine/
│   ├── backtest.py       # 回測引擎（含成本模型、漲跌停過濾）
│   ├── run_backtests.py  # 批次執行回測的主程式（v11 補定義）
│   ├── cost_model.py     # 交易成本模型（v11 新增）
│   ├── validator.py      # FDR 校正 + 市場週期驗證
│   ├── portfolio.py      # 訊號疊加器
│   ├── notify.py         # Telegram Bot 推播（v11 改）
│   └── check_decay.py    # 策略失效偵測（20 筆滾動版）
├── agents/               # Agent 1、2 Prompt 邏輯
├── config/
│   ├── config.py         # 全域設定
│   ├── encrypt.py        # 規律庫加密
│   └── market_cycle.py   # 市場週期標籤（v11 新增）
├── results/              # 加密回測結果（不進 repo）
└── logs/                 # 執行記錄（不進 repo）
```

### 1.6 建立 Python 虛擬環境並安裝套件

```bash
cd ~/strategy-mining && python3 -m venv .venv && source .venv/bin/activate

pip install pandas numpy scipy statsmodels
pip install backtesting anthropic
pip install cryptography python-dotenv
pip install pandas-ta FinMind pyarrow
pip install python-telegram-bot requests

pip freeze > requirements.txt
```

**套件清單說明：**

| 套件 | 用途 |
|------|------|
| `pandas` `numpy` `scipy` `statsmodels` | 資料處理與統計核心 |
| `backtesting` | Phase 1 回測引擎 |
| `anthropic` | Agent 1、2 呼叫 Claude API |
| `FinMind` | 台股 EOD 資料源（需帳號 token） |
| `pyarrow` | Parquet 高效能讀寫 |
| `python-telegram-bot` | 推播通知（取代已停用的 LINE Notify） |
| `pandas-ta` | 技術指標（KD、MACD 等） |
| `cryptography` `python-dotenv` | 規律庫加密與環境變數 |
| `requests` | FinMind rate limit 重試用 |

### 1.7 填入 .gitignore 與 .cursorignore

> ⚠️ **v11 修正：`*.json` 改為 `results/**/*.json`，避免把 universe.py 等設定檔誤排除。**

```
# 機密結果（不進 repo）
results/
logs/
*.enc

# 環境與金鑰
.env
params*
secrets*

# 本地 Data Lake（不進 repo，可能高達 GB 級）
data/raw/
data/parquet_db/
*.parquet

# 回測 JSON 結果（只排除 results 目錄下的，不影響其他 JSON）
results/**/*.json

# Python 環境
__pycache__/
.venv/
*.pyc
.DS_Store
```

```bash
# ⚠️ .gitignore 建好後，立刻執行這一行（這是 §1.0 第 3 點留下的待辦）
cp .gitignore .cursorignore
```

### 1.8 填入 .env 環境變數

```bash
nano ~/strategy-mining/.env
```

```env
# Claude API（Agent 1、2）
ANTHROPIC_API_KEY=your_claude_key_here

# 規律庫加密密碼
ENCRYPT_PASSWORD=your_very_long_random_password_here

# Telegram Bot 推播（取代 LINE Notify）
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# FinMind 資料認證（免費帳號即可）
FINMIND_TOKEN=your_finmind_token_here
```

> ⚠️ **絕對不放任何券商 API 金鑰。程式不下單，就不持有任何能動用資金的憑證。**

### 1.9 設定 Git 與 GitHub Private Repo

```bash
git config --global user.name "你的名字"
git config --global user.email "你的email"

cd ~/strategy-mining
git init && git add .gitignore .cursorignore requirements.txt README.md SKILL.md
git commit -m "init: project structure v11"
git remote add origin https://github.com/你的帳號/strategy-mining.git
git push -u origin main
```

### 1.10 Docker 容器隔離設定

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY engine/ ./engine/
COPY data/*.py ./data/
COPY agents/ ./agents/
COPY config/config.py ./config/
# results/ signals/ .env data/parquet_db/ 都不進容器
CMD ["python", "-m", "engine.backtest"]
```

```bash
cp .gitignore .dockerignore
```

---

## 2｜帳號與 API 清單

| 順序 | 服務 | 用途 | 月費（NT$） | 備注 |
|------|------|------|------------|------|
| 1 最先 | 永豐證券帳戶 | 台股下單（**僅供人工 App，不申請 Shioaji API**） | 無 | 審核 3-5 工作天 |
| 2 | FinMind 帳號 | 盤後抓取台股日 K、三大法人，建置 Data Lake | **免費** | finmindtrade.com |
| 3 | Anthropic Claude API | Agent 1、2（設定每月上限 **15 USD**） | 150–500 | 即時開通 |
| 4 | Telegram Bot | 訊號推播（取代已停用的 LINE Notify） | **免費** | 3 步驟完成 |
| 5 | GitHub 帳號 | Private repo 版控 | 免費 | 即時 |

**月費估算：**

| 方案 | 費用 |
|------|------|
| 最低（輕度測試） | Anthropic NT$150 + 其他全免費 ≈ **NT$150/月** |
| 建議（正式運作） | Anthropic NT$500 + 其他全免費 ≈ **NT$500/月** |
| 一次性 | 外接硬碟 NT$1,500–3,000（規律庫離線備份） |

**申請 Telegram Bot（3 步驟，約 3 分鐘）：**

1. Telegram 搜尋 `@BotFather` → 輸入 `/newbot` → 依指示命名
2. 取得 `BOT_TOKEN`，填入 `.env`
3. 對你建立的 Bot 傳任意一則訊息，然後開啟：
   `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
4. 在 JSON 中找到 `"chat":{"id":...}` 的數字 = `CHAT_ID`，填入 `.env`

---

## 3｜系統隔離與安全設計

### 3.1 什麼進 repo，什麼不進

| 類別 | 內容 |
|------|------|
| ✅ 可以進 repo | 引擎程式碼、Prompt 模板、套件清單、Dockerfile、SKILL.md、universe.py |
| ❌ 絕對不進 repo | 回測結果、有效規律清單、真實交易參數、API 金鑰（.env）、Data Lake（*.parquet） |
| 🔒 加密後本機備份 | 規律庫 JSON、勝率統計結果、signal_id 對應表 |
| 🤫 永遠不告訴任何人 | 哪些規律有效、系統是否在賺錢、真實下單參數 |

### 3.2 規律庫加密程式碼

```python
# config/encrypt.py
from cryptography.fernet import Fernet
import json, os, base64, hashlib
from dotenv import load_dotenv
load_dotenv()

def _key():
    raw = os.getenv('ENCRYPT_PASSWORD', '').encode()
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())

def save_signal(data, path='results/signals/library.enc'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(Fernet(_key()).encrypt(json.dumps(data).encode()))

def load_signals(path='results/signals/library.enc'):
    return json.loads(Fernet(_key()).decrypt(open(path, 'rb').read()))
```

---

## 4｜網路攻擊防護與隔離架構

### 4.1 攻擊面分析

| 資產 | 危險程度 | 防護重點 |
|------|---------|---------|
| 程式碼 | 低 | Private repo 即可 |
| API 金鑰 | 中（撤銷重申即可） | .env 不進 repo |
| 有效規律庫 | 極高 | 加密 + 離線備份 + 網路隔離 |
| 下單帳號憑證 | **已物理隔離，無任何券商連線** | 無風險 |

### 4.2 核心隔離原則

| 區域 | 說明 |
|------|------|
| 開發區（可聯網） | AI 編碼助手、Agent 1、2、Git push、套件安裝。不放任何規律庫。 |
| 運算區（白名單） | 回測引擎。只允許連到 Anthropic API 與 FinMind API。 |
| 規律庫（離線存放） | 加密後只存在本機目錄和外接硬碟，不掛載到任何聯網容器。 |
| Data Lake（本機唯讀） | `data/parquet_db/` 只在本機存取，不掛載到聯網容器，不進 repo。 |

### 4.3 Docker 網路白名單設定

```bash
docker network create --internal secure-net
docker network create --driver bridge restricted-net

# 回測容器：掛載本機 Data Lake（唯讀）+ 注入環境變數 + 網路白名單
# ⚠️ v11 修正：不加 -v 掛載的話，容器內找不到 parquet_db，立刻 FileNotFoundError
docker run \
  --env-file ~/.env \
  -v ~/strategy-mining/data/parquet_db:/app/data/parquet_db:ro \
  --network restricted-net \
  strategy-mining
# :ro = 唯讀掛載，容器只能讀取 Data Lake，無法寫入，符合安全設計原則
```

> ⚠️ **Docker 網路隔離的實際限制：** `--driver bridge` 的 `restricted-net` 並**不會**自動限制容器只能連 Anthropic 與 FinMind。它只是一個普通的自訂 bridge 網路，容器仍可連任何網際網路位址。真正的出口白名單需要 iptables 規則或 egress proxy，超出本計畫（Vibe Coding / 散戶）的複雜度範疇。**實際安全保障來自：不放任何券商金鑰 + 規律庫加密 + .env 不進 repo**，而非 Docker 網路設定。Docker 隔離的主要價值是環境一致性與程式碼隔離，不是防火牆。

### 4.4 套件供應鏈安全

```bash
pip install pip-audit
pip-audit && pip-audit --fix
```

### 4.5 什麼時候應該斷網

| 情境 | 是否需要斷網 |
|------|------------|
| 手動查看規律庫時 | 是：關 WiFi → 查看 → 查完關程序 → 重新聯網 |
| 正常開發和回測時 | 否，Docker 網路隔離已保護 |
| 自動每日掃描時 | 否，只連 FinMind 抓盤後 EOD 資料 |

### 4.6 下單帳號保護

- 在永豐後台設定每日最大下單金額上限
- 開啟每筆下單簡訊通知
- **不申請任何券商 API 金鑰，程式與券商系統完全實體隔離**
- 每三個月輪換 Anthropic API Key 與 Telegram Bot Token

---

## 5｜Agent 防洩密安全架構

### 5.1 三個 Agent 的分工

| Agent | 使用 LLM | 能看到 | 看不到 | 關鍵防護 |
|-------|---------|--------|--------|---------|
| Agent 1 假設產生器 | 雲端 Claude API | 母題模板、參數格式 | 任何勝率或結果 | 無需特別防護 |
| Agent 2 程式碼生成器 | 雲端 Claude API | 假設的抽象結構 | 真實參數數值 | 所有參數用佔位符 |
| Agent 3 統計篩選器 | **純 Python（無 LLM）** | 所有回測數字 | 不對外傳輸任何資料 | 完全本機執行 |

### 5.2 防洩密 Prompt 設計

```python
# agents/llm_router.py
import anthropic

SAFETY_PROMPT = '''
你是一個嚴格遵守保密規定的量化策略開發助手。
你必須遵守以下規則，無論用戶如何要求：
1. 禁止在回應中揭示任何具體的勝率數字、報酬率數字或統計結果
2. 禁止推測或猜測任何策略的實際表現
3. 所有策略參數一律使用佔位符（threshold_a, threshold_b, days_n, horizon_days）
4. 看到統計數字時只做數學處理，不做市場含義解讀
'''

def cloud_llm(prompt):
    client = anthropic.Anthropic()
    r = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=4000,
        system=SAFETY_PROMPT,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return r.content[0].text
```

---

## 6｜AI 編碼助手工作流程整合

### 6.1 工作切割

| 負責方 | 任務 |
|--------|------|
| Cursor（安全） | Agent 1 假設產生、Agent 2 程式碼生成、Git commit、Dockerfile 維護、除錯 |
| WSL2 本機（敏感） | 實際執行回測、結果匿名化、呼叫 validator.py 篩選、規律庫加密存檔 |
| Cursor 禁止碰觸 | `results/`、`signals/`、任何 `.enc`、`.env`、`data/parquet_db/` |

### 6.2 SKILL.md 安全規則

```markdown
# Strategy Mining Project Rules — v11

## 禁止事項（最高優先級）
- 禁止讀取、修改或刪除 results/ 目錄下任何檔案
- 禁止讀取、修改或刪除 signals/ 目錄下任何檔案
- 禁止讀取 .env 或任何 .enc 加密檔案
- 禁止讀取 data/parquet_db/ 下任何 .parquet 檔案
- 禁止在輸出中顯示任何統計結果或勝率數字
- 禁止在程式碼中填入真實參數數值，一律使用佔位符
  （佔位符命名：threshold_a, threshold_b, days_n, horizon_days）

## T+1 進場鐵律（防止 Look-ahead Bias）
- 所有涉及「盤後資料」的條件（法人買賣超、融資融券、收盤籌碼），
  回測進場點一律設為 T+1 日開盤價
- 禁止以 T 日收盤價作為盤後訊號的進場點
- 違反此規則的回測程式碼視為無效，必須重寫

## 漲跌停過濾鐵律（v11 新增）
- 所有回測程式碼必須在 T+1 進場前判斷該日是否漲跌停
- 若 T+1 開盤即漲停（漲幅 ≥ 9.5%）或跌停（跌幅 ≤ -9.5%），跳過該筆交易
- 此過濾邏輯寫在 engine/backtest.py 的 next() 方法中

## 交易成本鐵律（v11 新增）
- 所有回測必須設定 commission=0.002925（單邊 0.2925%）
- 來回總成本約 0.585%，不含成本的回測結果一律作廢
- 禁止使用 commission=0 的回測結果作為策略入庫依據

## 允許事項
- 修改 engine/、data/、agents/、config/config.py
- 執行 git add、git commit、git push
- 建立和修改 Dockerfile
```

### 6.3 典型工作流程

**步驟 1** — Cursor：Agent 1 產生假設

```
對 Cursor 輸入：
「執行 agents/hypothesis_generator.py，依 HYPOTHESIS_TEMPLATES 中的
50 個母題模板，使用 Grid Search 產生 10,000 個假設
（50 個母題 × 200 個參數組合），輸出到 results/hypotheses/batch_001.json。
最短持有天數 horizon_days 不得低於 10。」
```

**步驟 2** — Cursor：Agent 2 生成回測程式碼

```
對 Cursor 輸入：
「讀取 batch_001.json，用 agents/backtest_coder.py 為每個假設生成
帶佔位符的回測函式，存到 engine/generated_backtests.py。
進場點遵守 T+1 鐵律，加入漲跌停過濾，commission=0.002925，
使用 backtesting.py 框架，資料從 data/parquet_db/ 讀取。」
```

**步驟 3** — WSL2 本機：執行回測

```bash
cd ~/strategy-mining && source .venv/bin/activate
python engine/run_backtests.py
```

**步驟 4** — WSL2 本機：FDR 篩選 + 市場週期驗證

```bash
python engine/validator.py
# 有效 signal_id 加密存入 results/signals/library.enc
```

**步驟 5** — 回到 Cursor 繼續開發。有效規律已加密，Cursor 完全沒看到。

---

## 7｜系統架構（核心）

### 7.1 三層策略架構

| 層級 | 名稱 | 包含策略 | 用途 |
|------|------|---------|------|
| Layer 0 | 教科書基準層 | KD、MA 交叉、RSI、MACD 單獨測試 | 確認台股當前是否仍可行，作為 Layer 2 組合零件庫 |
| Layer 1 | 挖掘層 | A-J 十大類假設，Grid Search 10,000 個變體 | 禁用純教科書策略，允許「教科書 × 籌碼 × 技術形態」組合 |
| Layer 2 | 組合層 | 從 Layer 0 + Layer 1 通過篩選的策略，自動產生多條件疊加組合 | 篩選後仍滿足門檻的才存入規律庫 |

> ⚠️ **Phase 1 Universe 限制：** 所有回測只在「台灣 50 + 中型 100（共 150 檔）」執行。
> backtesting.py 是單資產框架，全市場 1,700 檔 × 10,000 假設 = 17,000,000 次迴圈，系統崩潰。
> 擴展至全市場是 Phase 2（vectorbt）的任務。

### 7.2 假設母題 10 大類 × 50 個母題模板

> ⚠️ **v11 新增：母題模板必須在 `agents/hypothesis_generator.py` 中明確定義。**
> 以下為 50 個母題的完整骨架，每類 5 個，Agent 1 依此 Grid Search 產生假設。

> ⚠️ **Phase 1 可用母題限制（重要）：**
> fetcher.py 抓取三種資料：日 K 線、三大法人買賣超、**融資融券**（v11 補入）。
> 以下母題仍需要額外資料，**Phase 1 回測時必須跳過**：
>
> | 無法用於 Phase 1 的母題 | 缺少的資料 | 取得方式 |
> |----------------------|-----------|---------|
> | D01–D05（財報類） | EPS、毛利率、本益比 | FinMind `taiwan_stock_financial_statement` / FinLab（Phase 2） |
> | F02（除息類） | 除息日期 | FinMind `taiwan_stock_dividend` |
> | I01–I05（跨市場類） | 費城半導體、VIX、DXY | Yahoo Finance `yfinance` 套件（Phase 2） |
>
> **Phase 1 實際可用母題：A、B、C、E、F01/F03/F04/F05、G、H、J，共約 35 個。**
> 融資融券已加入 fetcher.py，A02（融資追高）、B04（融資加速）、E04（融券軋空）、H04（融資斷頭）皆可正常回測。
> 在 `agents/hypothesis_generator.py` 中設定 `PHASE1_SKIP = ['D', 'F02', 'I']`。

```python
# agents/hypothesis_generator.py — HYPOTHESIS_TEMPLATES
HYPOTHESIS_TEMPLATES = [
    # ── A. 籌碼矛盾類（5 個）──
    {"id": "A01", "desc": "外資買超 N 日，同期投信賣超，後 D 日報酬"},
    {"id": "A02", "desc": "外資買超 N 日，同期融資大增（散戶追高），後 D 日報酬"},
    {"id": "A03", "desc": "三大法人同步買超 N 日，後 D 日報酬"},
    {"id": "A04", "desc": "外資連買 N 日後突然轉賣，後 D 日報酬"},
    {"id": "A05", "desc": "投信買超 N 日且外資無動作，後 D 日報酬"},

    # ── B. 速度與加速度類（5 個）──
    {"id": "B01", "desc": "法人買超張數加速（第 N 日 > 前 N 日均值 × ratio），後 D 日報酬"},
    {"id": "B02", "desc": "股價漲速（N 日斜率）超過過去 M 日均值 × ratio，後 D 日報酬"},
    {"id": "B03", "desc": "成交量加速放大（N 日均量 > 前 N 日均量 × ratio），後 D 日報酬"},
    {"id": "B04", "desc": "融資增幅加速（N 日融資增加量 > 前 N 日均值 × ratio），後 D 日報酬"},
    {"id": "B05", "desc": "股價動能轉正（前 N 日負報酬後，最近 M 日轉為正報酬），後 D 日報酬"},

    # ── C. 跨股聯動類（5 個）──
    {"id": "C01", "desc": "龍頭股（2330）外資買超 N 日，同族群二線廠後 D 日報酬"},
    {"id": "C02", "desc": "類股 ETF（0050 成分）多數上漲 N 日，個股後 D 日報酬"},
    {"id": "C03", "desc": "相同產業龍頭法說後 N 日，二線廠的報酬"},
    {"id": "C04", "desc": "上游原物料股上漲 N 日後，下游加工廠後 D 日報酬"},
    {"id": "C05", "desc": "同產業個股 N 日相對強弱排名倒數後的均值回歸報酬"},

    # ── D. 財報與籌碼背離類（5 個）──
    {"id": "D01", "desc": "EPS YoY 成長 > threshold%，但外資近 N 日賣超，後 D 日報酬"},
    {"id": "D02", "desc": "EPS YoY 衰退 > threshold%，但外資近 N 日買超，後 D 日報酬"},
    {"id": "D03", "desc": "毛利率 QoQ 上升 > threshold%，同期法人未追，後 D 日報酬"},
    {"id": "D04", "desc": "本益比低於過去 M 季中位數 threshold 倍，法人近 N 日轉買，後 D 日報酬"},
    {"id": "D05", "desc": "財報公佈後 N 日內，股價未反應 EPS 超預期，後 D 日報酬"},

    # ── E. 極端值均值回歸類（5 個）──
    {"id": "E01", "desc": "RSI 跌破 threshold（超賣），後 D 日報酬"},
    {"id": "E02", "desc": "KD 同時低於 threshold（超賣），後 D 日報酬"},
    {"id": "E03", "desc": "N 日跌幅超過 threshold%，後 D 日均值回歸報酬"},
    {"id": "E04", "desc": "融券比率達 M 日內歷史高點 threshold 分位，後 D 日軋空報酬"},
    {"id": "E05", "desc": "本益比跌破過去 M 季最低值，後 D 日均值回歸報酬"},

    # ── F. 時間結構類（5 個）──
    {"id": "F01", "desc": "月底前 N 個交易日，法人作帳效應，後 D 日報酬"},
    {"id": "F02", "desc": "除息日前 N 個交易日進場，除息後 D 日填息報酬"},
    {"id": "F03", "desc": "季報公佈前 N 個交易日，法人提前布局，後 D 日報酬"},
    {"id": "F04", "desc": "年底前 N 個交易日（作帳行情），特定族群後 D 日報酬"},
    {"id": "F05", "desc": "元月效應：1 月前 N 個交易日，中小型股後 D 日報酬"},

    # ── G. 量價背離類（5 個）──
    {"id": "G01", "desc": "股價創 N 日新高，但成交量萎縮（量價背離），後 D 日報酬"},
    {"id": "G02", "desc": "股價跌破支撐，但成交量極低（無量下跌），後 D 日報酬"},
    {"id": "G03", "desc": "爆量長上影線（收盤接近低點），後 D 日報酬"},
    {"id": "G04", "desc": "縮量整理 N 日後放量突破，後 D 日報酬"},
    {"id": "G05", "desc": "成交量連續 N 日低於 M 日均量 threshold 倍（極度縮量），後 D 日報酬"},

    # ── H. 反直覺類（5 個）──
    {"id": "H01", "desc": "利空消息公佈後 N 日股價不跌，後 D 日報酬"},
    {"id": "H02", "desc": "利多消息公佈後 N 日股價不漲（利多出盡），後 D 日報酬"},
    {"id": "H03", "desc": "大盤重跌 N%，個股僅跌不到 threshold%（相對強勢），後 D 日報酬"},
    {"id": "H04", "desc": "融資斷頭後 N 日，股價反向表現"},
    {"id": "H05", "desc": "外資連賣 N 日後放量買回，後 D 日報酬"},

    # ── I. 跨市場傳導類（5 個）──
    {"id": "I01", "desc": "費城半導體指數大漲 N% 後，台灣半導體族群後 D 日報酬"},
    {"id": "I02", "desc": "美元指數（DXY）急升 N% 後，台股出口族群後 D 日報酬"},
    {"id": "I03", "desc": "VIX 恐慌指數急升 threshold 後回落，台股後 D 日報酬"},
    {"id": "I04", "desc": "美國 10 年債利率急升 N bps 後，台股金融族群後 D 日報酬"},
    {"id": "I05", "desc": "日圓急貶 N% 後，台股出口競爭族群後 D 日報酬"},

    # ── J. 市場情緒極端類（5 個）──
    {"id": "J01", "desc": "大盤融資餘額創 N 日新高（市場過熱），個股後 D 日報酬"},
    {"id": "J02", "desc": "大盤單日成交量創 N 日新高，後 D 日報酬"},
    {"id": "J03", "desc": "散戶情緒指標（融資/融券比）超過 threshold，後 D 日報酬"},
    {"id": "J04", "desc": "大盤連跌 N 日（恐慌），個股後 D 日均值回歸報酬"},
    {"id": "J05", "desc": "漲停股數 / 跌停股數比率超過 threshold，後 D 日報酬"},
]
```

### 7.3 統計篩選門檻（含 FDR 校正 + 市場週期驗證）

| 條件 | 門檻 | 說明 |
|------|------|------|
| 樣本數 | ≥ 200 次 | 10 年歷史跨越牛熊市 |
| 勝率 | ≥ 55% | 統計顯著優於隨機 |
| p 值 | **FDR adjusted p < 0.05** | Benjamini-Hochberg 校正，非原始 p 值 |
| 樣本外勝率 | ≥ 53% | 後 30% 數據仍有效 |
| 夏普比率 | ≥ 1.0 | 報酬品質（**已含交易成本 0.585%**） |
| 市場週期覆蓋 | **各週期交易樣本數 ≥ 30 次** | 自動可計算，見 7.4 節 |

> ⚠️ **多重比較問題（必須處理）**
>
> ```python
> from statsmodels.stats.multitest import multipletests
> reject, p_adj, _, _ = multipletests(all_p_values, method='fdr_bh')
> # 篩選條件：reject == True（即 adjusted p < 0.05）
> ```

### 7.4 市場週期標籤系統（v11 新增）

> 解決 v10 矛盾：「牛熊各 ≥ 20%」無法自動計算。v11 改用預標記的週期表，
> validator.py 可直接查表，門檻也改為各週期 ≥ 30 筆交易樣本。

```python
# config/market_cycle.py
# 台股市場週期標籤（以加權指數定義，每年初更新一次）

MARKET_CYCLES = {
    # 格式：'YYYY-MM-DD': 'bull' / 'bear' / 'sideways'
    '2015-06-01': 'bear',     # 2015 年中崩跌
    '2016-01-04': 'bull',     # 2016 年初升段
    '2016-06-01': 'sideways', # 2016 年中盤整
    '2017-01-02': 'bull',     # 2017 全年多頭
    '2018-10-01': 'bear',     # 2018 Q4 崩跌
    '2019-01-02': 'bull',     # 2019 反彈
    '2019-06-01': 'sideways', # 2019 年中盤整
    '2020-01-20': 'bear',     # 2020 COVID 崩盤
    '2020-04-01': 'bull',     # 2020 V 型反彈
    '2021-01-04': 'bull',     # 2021 全年大多頭
    '2022-01-03': 'bear',     # 2022 升息崩跌
    '2023-01-02': 'bull',     # 2023 AI 行情
    '2023-07-01': 'sideways', # 2023 下半年盤整
    '2024-01-01': 'bull',     # 2024 AI 延續
}

def label_date(date_str: str) -> str:
    sorted_dates = sorted(MARKET_CYCLES.keys())
    label = 'sideways'
    for d in sorted_dates:
        if date_str >= d:
            label = MARKET_CYCLES[d]
    return label

# 在 validator.py 中使用：
# counts = {'bull': 0, 'bear': 0, 'sideways': 0}
# for d in trade_dates:
#     counts[label_date(str(d))] += 1
# pass_cycle = all(v >= 30 for v in counts.values())
```

### 7.5 交易成本模型（v11 新增）

> ⚠️ **不含交易成本的回測 = 假數據。** 台股來回一趟固定損耗 0.585%。

```python
# engine/cost_model.py
# 台股交易成本（2025 年適用）
BACKTEST_COMMISSION = 0.002925  # 單邊 0.2925%（backtesting.py commission 參數）
# 來回 0.585% = 買進手續費 0.1425% + 賣出手續費 0.1425% + 證交稅 0.3%
# 另加滑價 ~0.1%（T+1 開盤偏移），已含在 commission 估計內

# 使用方式：
# bt = Backtest(data, MyStrategy, commission=BACKTEST_COMMISSION)
```

**最低期望毛報酬（才能回本）：**

| 持有天數 | 需要毛報酬 | 年化換算 |
|---------|-----------|---------|
| 10 天 | ≥ 0.59% | ≥ 15% |
| 20 天 | ≥ 0.59% | ≥ 7.5% |
| 60 天 | ≥ 0.59% | ≥ 3.6% |

### 7.6 T+1 漲跌停過濾機制（v11 新增）

> T+1 開盤鎖漲停時買不到，是回測與現實最大落差之一。必須過濾。
> **統一使用 processor.py 載入的 `PrevClose` 欄位**，不用 `Close[-2]` 自己推算，
> 避免兩條路並存造成 Cursor 生成程式碼時的不一致。

```python
# engine/backtest.py — next() 方法中的過濾邏輯
# 前提：data 已包含 PrevClose 欄位（由 processor.load_kline 載入）

def is_limit_up(open_price: float, prev_close: float) -> bool:
    """T+1 開盤即漲停（買不到）"""
    return prev_close > 0 and (open_price - prev_close) / prev_close >= 0.095

def is_limit_down(open_price: float, prev_close: float) -> bool:
    """T+1 開盤即跌停（賣不掉）"""
    return prev_close > 0 and (open_price - prev_close) / prev_close <= -0.095

# 在 Strategy.next() 進場前加入：
# open_t1   = self.data.Open[-1]
# prev_cl   = self.data.PrevClose[-1]   # ← 來自 parquet，不用 Close[-2]
# if is_limit_up(open_t1, prev_cl):
#     return  # 跳過本次進場
```

### 7.7 Data Lake：FinMind 資料抓取（含認證與 Rate Limit）

> ⚠️ **v11 修正：加入 token 認證、重試邏輯、sleep 節流。**
> 免費帳號無認證容易被 429 封鎖。150 檔完整下載預估需 8–12 小時。

```python
# data/fetcher.py
from FinMind.data import DataLoader
import pandas as pd, pyarrow as pa, pyarrow.parquet as pq
import os, time
from dotenv import load_dotenv
load_dotenv()

dl = DataLoader()
dl.login_by_token(api_token=os.getenv('FINMIND_TOKEN'))

START_DATE = '2015-01-01'
SLEEP_BETWEEN_STOCKS = 3   # 秒（免費帳號建議 2–5 秒）
MAX_RETRY = 3

def fetch_with_retry(func, *args, **kwargs):
    for attempt in range(MAX_RETRY):
        try:
            result = func(*args, **kwargs)
            if result is not None and len(result) > 0:
                return result
        except Exception as e:
            print(f'  [RETRY {attempt+1}/{MAX_RETRY}] {e}')
            time.sleep(10 * (attempt + 1))
    return None

def fetch_and_save(stock_id: str):
    print(f'Fetching {stock_id}...')
    kline = fetch_with_retry(dl.taiwan_stock_daily,
                             stock_id=stock_id, start_date=START_DATE)
    chip  = fetch_with_retry(dl.taiwan_stock_institutional_investors,
                             stock_id=stock_id, start_date=START_DATE)
    margin = fetch_with_retry(dl.taiwan_stock_margin_purchase_short_sale,
                              stock_id=stock_id, start_date=START_DATE)
    os.makedirs('data/parquet_db', exist_ok=True)
    if kline is not None:
        kline = kline.sort_values('date').reset_index(drop=True)
        kline['prev_close'] = kline['close'].shift(1)  # 漲跌停判斷用
        pq.write_table(pa.Table.from_pandas(kline),
                       f'data/parquet_db/{stock_id}_kline.parquet')
    if chip is not None:
        pq.write_table(pa.Table.from_pandas(chip),
                       f'data/parquet_db/{stock_id}_chip.parquet')
    if margin is not None:
        pq.write_table(pa.Table.from_pandas(margin),
                       f'data/parquet_db/{stock_id}_margin.parquet')
    print(f'  [OK] {stock_id}')
    time.sleep(SLEEP_BETWEEN_STOCKS)

if __name__ == '__main__':
    from data.universe import UNIVERSE
    failed = []
    for sid in UNIVERSE:
        try:
            fetch_and_save(sid)
        except Exception as e:
            print(f'  [FAIL] {sid}: {e}')
            failed.append(sid)
    if failed:
        print(f'\n失敗清單（可重跑）：{failed}')
```

### 7.7b 資料清洗：processor.py（必須定義，否則回測直接 KeyError）

> ⚠️ **FinMind 回傳小寫欄位（`open`, `close`），backtesting.py 要求大寫（`Open`, `Close`）。**
> `processor.py` 空白的話，回測引擎第一行就 `KeyError: 'Open'`。以下為必須實作的最小骨架。

```python
# data/processor.py
import pandas as pd
import pyarrow.parquet as pq

COLUMN_MAP = {
    'date':           'Date',
    'open':           'Open',
    'max':            'High',       # ⚠️ FinMind 用 'max'，不是 'high'
    'min':            'Low',        # ⚠️ FinMind 用 'min'，不是 'low'
    'close':          'Close',
    'Trading_Volume': 'Volume',     # ⚠️ FinMind 用 'Trading_Volume'，不是 'volume'
    'prev_close':     'PrevClose',
}

def load_kline(stock_id: str) -> pd.DataFrame:
    """讀取日 K，轉換為 backtesting.py 相容格式（大寫欄位，Date 為 index）"""
    df = pq.read_table(f'data/parquet_db/{stock_id}_kline.parquet').to_pandas()
    df = df.rename(columns=COLUMN_MAP)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date').sort_index()
    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    return df[required + ['PrevClose']].dropna(subset=required)

def load_chip(stock_id: str) -> pd.DataFrame:
    """讀取三大法人買賣超，回傳以 date 為 index 的 DataFrame"""
    df = pq.read_table(f'data/parquet_db/{stock_id}_chip.parquet').to_pandas()
    df['date'] = pd.to_datetime(df['date'])
    return df.set_index('date').sort_index()
```

> **使用方式（在 backtest.py 中）：**
> ```python
> from data.processor import load_kline, load_chip
> kline  = load_kline('2330')
> chip   = load_chip('2330')
> merged = kline.join(chip[['Foreign_Investor_Buy', 'Foreign_Investor_Sell']], how='left')
> ```

### 7.7c run_backtests.py 骨架（批次執行入口）

> ⚠️ **§6.3 呼叫 `python engine/run_backtests.py` 但全文未定義。** 以下為最小骨架。

```python
# engine/run_backtests.py
"""批次執行所有假設的回測，結果加密存入 results/backtests/"""
import json, os
from config.encrypt import save_signal

HYPOTHESIS_FILE = 'results/hypotheses/batch_001.json'

def run_all():
    with open(HYPOTHESIS_FILE, encoding='utf-8') as f:
        hypotheses = json.load(f)

    results = []
    for hyp in hypotheses:
        # Cursor 會依據 hypothesis 結構生成具體回測邏輯
        # 每個 hyp 包含：hypothesis_id, id（母題）, params, desc
        result = run_single(hyp)
        if result:
            results.append(result)

    os.makedirs('results/backtests', exist_ok=True)
    save_signal(results, path='results/backtests/batch_001.enc')
    print(f'完成回測：{len(results)} 筆結果已加密存檔')

def run_single(hyp: dict) -> dict | None:
    """單一假設的回測邏輯，由 Agent 2 生成具體實作"""
    raise NotImplementedError('由 Agent 2 依 hypothesis 生成此函式')

if __name__ == '__main__':
    run_all()
```

### 7.8 Phase 1 標的池（data/universe.py）

```python
# data/universe.py
# Phase 1 Universe：台灣 50 + 中型 100 代表性成分股（共 150 檔）
# 更新依據：每季 FTSE Russell 公告，每年初手動核對一次

UNIVERSE = [
    # ── 台灣 50（前 50 大市值）──
    '2330','2317','2454','2382','2308','2881','2882','2303','2412','3711',
    '2002','1301','1303','1326','2886','2891','2885','5880','2884','2892',
    '2880','2883','2887','6505','2474','3045','4904','2357','2353','2395',
    '3008','2379','2408','3034','2344','2301','2327','4938','6669','2376',
    '2377','2356','2324','2385','2392','2049','1402','2207','2103','2105',
    # ── 中型 100 代表性成分（補足至 150 檔）──
    '6415','3231','2409','3481','2368','2360','3702','2347','2337','3017',
    '6770','6446','2492','3037','2059','2227','1605','2915','9910','1504',
    '2014','1314','1102','1101','1216','2912','2801','5876','2823','5871',
    '6239','3526','2449','6271','4966','6274','8046','1476','1477','9945',
    '2634','2610','2618','2609','2615','2603','5347','6488','3533','6176',
    '9914','9917','1590','3443','2723','2727','4919','3714','5269','6278',
    '3706','2023','2201','2371','3006','5904','2836','2845','9933','3324',
    '6756','4927','3296','2548','6116','5243','4743','1536','3130','6196',
    '2838','2633','2231','3085','3149','2634','1455','6523','3019','4938',
]

UNIVERSE = list(dict.fromkeys(UNIVERSE))[:150]  # 去重，保持 150 檔
```

### 7.9 回測引擎兩階段策略

| 階段 | 框架 | 升級時機 |
|------|------|---------|
| Phase 1（現在） | `backtesting.py` | 語法直覺，先跑通整個流程 |
| Phase 2（升級） | `vectorbt` | 單次全量回測 > 6 小時，或假設池 > 5,000 個 |

### 7.10 假設產生：Grid Search 設計

```python
# agents/hypothesis_generator.py — Grid Search 核心
import itertools, random, json, os  # ← os 補上，makedirs 用到

PARAM_GRIDS = {
    'threshold_a':    [100, 200, 300, 500, 800, 1000],
    'consecutive_n':  [2, 3, 5, 8, 10],
    'indicator_val':  [20, 25, 30, 35, 40],
    'bar_body_pct':   [0.02, 0.03, 0.05, 0.07],
    'horizon_days':   [10, 15, 20, 30, 45, 60],  # 最低 10 天
}

PHASE1_SKIP = ['D', 'F02', 'I']  # 財報、除息、跨市場資料未抓，Phase 1 跳過

def generate_batch(template: dict, batch_size: int = 200) -> list:
    # 跳過 Phase 1 無法回測的母題
    if any(template['id'].startswith(skip) for skip in PHASE1_SKIP):
        return []
    all_combos = list(itertools.product(*PARAM_GRIDS.values()))
    sampled = random.sample(all_combos, min(batch_size, len(all_combos)))
    keys = list(PARAM_GRIDS.keys())
    return [
        {**template,
         'params': dict(zip(keys, combo)),
         'hypothesis_id': f"{template['id']}_{i:04d}"}
        for i, combo in enumerate(sampled)
    ]

if __name__ == '__main__':
    all_hypotheses = []
    for template in HYPOTHESIS_TEMPLATES:
        all_hypotheses.extend(generate_batch(template, batch_size=200))
    os.makedirs('results/hypotheses', exist_ok=True)
    with open('results/hypotheses/batch_001.json', 'w', encoding='utf-8') as f:
        json.dump(all_hypotheses, f, ensure_ascii=False, indent=2)
    print(f'生成假設數量：{len(all_hypotheses)}')
```

### 7.11 策略失效偵測（修正版）

> ⚠️ **v11 修正：v10 的 90 天滾動窗口對 holding_days=60 只有 1–2 筆樣本。**
> 改為「最近 20 筆完成交易」滾動勝率，對任何持有期都有意義。

```python
# engine/check_decay.py
def rolling_winrate_by_trades(trades: list, window: int = 20) -> float:
    """以最近 N 筆完成交易計算滾動勝率（不依賴時間窗口）"""
    if len(trades) < window:
        return None  # 樣本不足，本週不判斷
    recent = trades[-window:]
    wins = sum(1 for t in recent if t['pnl'] > 0)
    return wins / window
# 失效門檻：最近 20 筆勝率 < 50% → 標記 excluded
```

### 7.12 訊號疊加設計（engine/portfolio.py）

| 環節 | 機制 | 說明 |
|------|------|------|
| 入庫時 | 相關性檢查 | 新規律與現有規律庫相關係數 > 0.6 → 不加入庫 |
| 入庫時 | 分群標記 | 籌碼類（A）、技術形態類（B）、時間結構類（C）、跨市場類（D） |
| 推播時 | 群組投票制 | 至少 2 個不同群組同時觸發才發推播；群組數越多，強度越高（⭐→⭐⭐→⭐⭐⭐） |

### 7.13 三管線雙向挖掘架構

| 管線 | 方向 | 輸出訊號 | 限制 |
|------|------|---------|------|
| 管線 A：做多 | 偵測進場時機 | 📈 買入推播 | Phase 1：Universe 150 檔 |
| 管線 B：賣出平倉 | 偵測動態出場時機 | 🔔 賣出推播 | 已持有部位者適用 |
| 管線 C：放空 | 偵測崩跌前兆 | 📉 放空推播 | 僅限市值前 100 大標的 |

**放空管線額外規則：**
- 跌的規律與漲的規律分開挖掘，不能直接將做多規律反轉使用
- 收到放空訊號當天須確認標的無漲停風險再執行
- 回測需加入融券費率成本（約 0.1–0.6%/年）

### 7.14 Telegram Bot 推播（engine/notify.py）

```python
# engine/notify.py
import os, requests
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID')

def send_signal(message: str):
    # 純文字模式：不使用 parse_mode HTML，避免 > < 符號觸發 HTTP 400
    # 推播格式（【訊號】、[群組]、⭐）純文字即可完整呈現，不需 HTML 排版
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    requests.post(url, json={
        'chat_id': CHAT_ID, 'text': message
    })

def test_notify():
    send_signal('✅ Strategy Mining v11 系統連線測試成功')

if __name__ == '__main__':
    test_notify()
```

**推播格式範例：**

```
【做多訊號 ⭐⭐】2330 台積電
[A-籌碼] 法人連3日買超 > 500張
[C-時間] 月底前5日 × 外資加碼
建議持有：20–30 個交易日
回測平均報酬：+4.2%（含手續費）  止損參考：-7%

【賣出訊號 ⭐⭐⭐】2330 台積電
[A-籌碼] 法人連2日大量出貨 > 1,000張
[B-技術] 爆大量長上影線收黑
建議：提前出場，不等原訂持有天數到期

【放空訊號 ⭐⭐】2317 鴻海
[A-籌碼] 外資連5日賣超
[B-技術] 週線跌破季線後反彈至月線壓力
⚠ 確認今日無漲停再執行，融券費率已計入回測
建議持有：10–20 個交易日
```

---

## 8｜建置時程

> ⚠️ **v11 時程調整：第 1 週只求「環境可動 + Telegram 推播成功」。**
> Data Lake 下載耗時 8–12 小時，獨立移至第 2 週，不與環境建置混在一起。

| 週次 | 工作內容 | 完成標準 |
|------|---------|---------|
| **第 1 週** | 安裝 WSL2、Docker、Cursor；申請所有帳號；建立目錄結構與 .env | `python engine/notify.py` → 手機 Telegram 收到測試訊息 ✅ |
| **第 2 週** | 完成 Universe 定義；執行 fetcher.py 下載 150 檔 × 10 年資料；Parquet 轉檔 | `data/parquet_db/` 中 ≥ 420 個 Parquet 檔（每檔 3 個：kline + chip + margin） |
| **第 3 週** | 建立回測引擎（backtesting.py + cost_model + 漲跌停過濾）；驗證 T+1 鐵律 | 單一策略回測正確執行，費用與漲跌停過濾有效 |
| **第 4 週** | 完成 Agent 1（Grid Search，依 50 個母題模板產生 10,000 個假設） | JSON 格式正確，含 hypothesis_id、母題 id、params，horizon_days ≥ 10 |
| **第 5 週** | 完成 Agent 2；整合參數盲化；跑第一次大規模回測 | 回測可自動執行，結果加密存檔 |
| **第 6 週** | 完成 validator.py（FDR + 市場週期驗證）；完成訊號疊加器 | 找到 ≥ 5 個有效 signal_id；推播格式正確 |
| **第 7 週** | 建立三管線架構；完成 check_decay.py；開始 60 天紙上驗收 | 手機收到三種格式推播；開始紙上記錄方向勝率 |
| **第 8 週+** | 持續迭代，紙上驗收 60 天勝率達標後開始人工跟單 | 初期每筆部位不超過總資金 5% |

---

## 8b｜每日使用流程（系統上線後）

> 這是計畫書最重要但最容易被忽略的一節——系統建好之後，你每天實際要做什麼。

### 盤後例行作業（每個交易日收盤後，約 15–30 分鐘）

```
盤後 15:00 後
  ↓
Step 1｜更新 Data Lake（約 5 分鐘）
  執行：python data/fetcher.py --mode daily
  （只抓今日新增的一筆 EOD 資料，不是重跑全部 10 年）

Step 2｜執行每日訊號掃描（約 10–20 分鐘，視 Universe 大小）
  執行：python engine/run_daily_scan.py
  系統對 150 檔逐一檢查今日是否觸發規律庫中的任一 signal_id

Step 3｜Telegram 推播（自動）
  若有訊號觸發，手機收到推播

Step 4｜人工判斷（約 5 分鐘）
  看推播內容，結合自己對市場的判斷，決定要不要跟單
  開啟永豐 App → 隔日委託（T+1 開盤價掛市價單）

Step 5｜每週五：執行失效偵測
  執行：python engine/check_decay.py
  檢查是否有規律需要標記 excluded
```

**每日時間投入估計：**

| 情境 | 時間 |
|------|------|
| 無訊號觸發 | 5 分鐘（只跑掃描腳本，自動完成） |
| 有 1–3 個訊號 | 15 分鐘（看推播 + 下委託單） |
| 有大量訊號（市場活躍期） | 30 分鐘（多看幾個，不用全跟） |

> ⚠️ **`run_daily_scan.py` 是 `run_backtests.py` 的日常版本**（掃描當日，不是跑歷史回測）。
> 這個腳本由 Cursor 在第 6–7 週依照引擎邏輯生成，在系統建置待辦（§9.3）中追蹤。

---

## 9｜待辦清單

### 9.1 第一週 Pre-flight Checklist

#### 【安全掃描】
- [ ] 用 Windows Defender 完整掃描，確認電腦乾淨

#### 【帳號申請（依序）】
- [ ] 申請**永豐證券帳戶**（審核最久，先送出，**不申請 Shioaji API**）
- [ ] 申請 **FinMind 帳號**，取得免費 Token（finmindtrade.com）
- [ ] 申請 **Anthropic Claude API Key**（綁定信用卡，設定每月上限 **15 USD**）
- [ ] 建立 **Telegram Bot**（依 §2 節 3 步驟），取得 BOT_TOKEN 與 CHAT_ID

#### 【AI 編碼助手】
- [ ] 安裝 **Cursor**（cursor.com），登入 GitHub 帳號（§1.0）
- [ ] 確認 `.cursorignore` 設定正確，AI 無法讀取 `.env`、`results/`、`data/parquet_db/`

#### 【環境建置】
- [ ] 安裝 WSL2（§1.2）
- [ ] 安裝 Docker Desktop（§1.3）
- [ ] 建立專案目錄結構（§1.5）
- [ ] 建立 Python 虛擬環境，安裝套件（§1.6）
- [ ] 填入 `.gitignore` 與 `.cursorignore`（§1.7，注意 `results/**/*.json` 修正）
- [ ] 填入 `.env`（5 個 key：ANTHROPIC、ENCRYPT_PASSWORD、TELEGRAM × 2、FINMIND）
- [ ] 建立 GitHub Private Repo，完成第一次 push（§1.9）
- [ ] 建立 `SKILL.md`（含 T+1、漲跌停、交易成本三條鐵律）
- [ ] 設定 Docker 網路隔離（§4.3）
- [ ] 購買外接硬碟（規律庫離線備份）

#### 【第一週完成驗收】
- [ ] 執行 `python engine/notify.py` → 手機 Telegram 收到「v11 系統連線測試成功」✅

---

### 9.2 第二週 Data Lake Checklist

- [ ] 確認 `data/universe.py` UNIVERSE 清單正確（150 檔，無重複）
- [ ] 確認 `.env` 中 `FINMIND_TOKEN` 已填入
- [ ] 睡前執行 `python data/fetcher.py`（預估 8–12 小時）
- [ ] 確認 `data/parquet_db/` 中檔案數 ≥ 420 個（每檔 3 個：kline + chip + margin）
- [ ] 抽查 3 檔：讀取 Parquet 確認欄位正確（kline 含 `PrevClose`；margin 含融資融券欄位）
- [ ] 重跑 fetcher.py 輸出的失敗清單

---

### 9.3 系統建置待辦

- [ ] 交易成本模型（`engine/cost_model.py`）
- [ ] 市場週期標籤系統（`config/market_cycle.py`）
- [ ] 回測引擎核心（`engine/backtest.py`，含 cost_model + 漲跌停過濾）
- [ ] 統計篩選器（`engine/validator.py`，FDR + 市場週期驗證）
- [ ] 假設產生器（`agents/hypothesis_generator.py`，50 個母題 + Grid Search）
- [ ] LLM 路由器（`agents/llm_router.py`，僅 cloud_llm）
- [ ] Agent 1、2 Prompt
- [ ] 結果匿名化與 signal_id 對應表加密模組
- [ ] 規律庫加密讀寫模組（`config/encrypt.py`）
- [ ] 訊號疊加器（`engine/portfolio.py`，群組投票制）
- [ ] Telegram 推播模組（`engine/notify.py`）
- [ ] 失效偵測腳本（`engine/check_decay.py`，20 筆滾動版本）
- [ ] 三管線架構：做多 / 賣出平倉 / 放空（分開挖掘）
- [ ] 每日掃描腳本（`engine/run_daily_scan.py`，日常版的 run_backtests，掃描當日觸發）

### 9.4 重要備忘

> **假設庫備份（容易被忽略）：** `results/hypotheses/` 被 `results/` 整個排除在 git 外。換電腦或硬碟損壞時，10,000 個假設 JSON 全部消失，需重新花費 API 費用產生。**每次產生新一批假設後，立刻將 `results/hypotheses/` 也備份到外接硬碟。**

> **倖存者偏差警告（Phase 1 已知限制）：** `data/universe.py` 使用的是「今天」的台灣 50 + 中型 100 成分股，回測過去 10 年時隱含倖存者偏差——過去 10 年間下市、衰退或跌出指數的股票已被排除，會導致回測勝率虛高。Phase 1 目標是跑通框架，先接受此偏差。**Phase 2 升級 vectorbt 時，必須改為全市場 1,700 檔或導入歷史成分股變動資料，否則勝率數字不可信，不能作為投入真實資金的依據。**

> **Phase 2 升級觸發點：** 單次全量回測 > 6 小時 → 升級 vectorbt，同步擴展 Universe 至全市場。

> **FinLab 升級時機：** 需要法說會情緒指標、冷門財報數據時付費加入，與 Parquet Data Lake 合併。

> **Phase 3 Roadmap（長期）：** 中文法說會 NLP 分析（語料庫 + 情緒模型），當前不在範圍。

> **紙上驗收門檻：** 三管線各自 60 天、各 ≥ 20 筆推播紀錄，勝率達標後才開始人工跟單。

> **安全習慣：** 每三個月輪換 Anthropic Key 與 Telegram Bot Token。每週規律庫備份外接硬碟後拔除。查看規律庫前先關 WiFi。

---

## 附錄 A｜常用指令與緊急處理

### A.1 常用指令

| 操作 | 指令 |
|------|------|
| 開啟 Ubuntu 終端機 | Windows 鍵 → 搜尋「Ubuntu」→ 開啟 |
| 進入專案目錄 | `cd ~/strategy-mining` |
| 啟動虛擬環境 | `source .venv/bin/activate` |
| 執行資料抓取 | `python data/fetcher.py`（建議睡前跑） |
| 測試 Telegram 推播 | `python engine/notify.py` |
| Git 存檔推送 | `git add . && git commit -m "說明" && git push` |
| 掃描套件安全漏洞 | `pip-audit` |
| 查看 Parquet 內容 | `python -c "import pandas as pd; print(pd.read_parquet('data/parquet_db/2330_kline.parquet').head())"` |

### A.2 緊急應對

| 情況 | 處理方式 |
|------|---------|
| 懷疑 API 金鑰外洩 | 用手機立刻到各服務後台撤銷，更新 .env，重新申請 |
| 不小心 commit 了 .env | `git rm --cached .env`，重新申請所有金鑰 |
| 不小心 commit 了 .parquet | `git rm --cached "data/parquet_db/*.parquet"`，確認 .gitignore 已更新 |
| FinMind 下載中斷 | 查看終端機失敗清單，只重跑失敗的代碼 |
| 規律庫加密檔遺失 | 從外接硬碟離線備份還原 |
| 防毒軟體出現可疑警告 | 記錄目標網址，若非已知服務域名則立刻斷網處理 |

---

## 附錄 B｜v10 → v11 變更摘要

| 項目 | v10 | v11 | 原因 |
|------|-----|-----|------|
| 推播通知 | LINE Notify | **Telegram Bot API** | LINE Notify 已於 2025/3/31 永久停用（致命錯誤修正） |
| `.gitignore` 的 `*.json` | 全域排除 | `results/**/*.json` | 避免把設定檔誤排除（致命錯誤修正） |
| AI 編碼助手設定 | 未說明 | **§1.0 Cursor 完整安裝與設定** | Vibe Coding 的第一步缺失 |
| 法說會 NLP | 列為台股優勢 | 移入 Phase 3 Roadmap | 當前無實作路徑，避免誤導 |
| 失效偵測窗口 | 90 天滾動 | **最近 20 筆完成交易** | 90 天對 holding_days=60 只有 1–2 筆樣本 |
| 假設母題模板 | 提及但未定義 | **50 個母題完整列出** | Agent 1 需要明確模板才能產生假設 |
| FinMind 認證 | `DataLoader()` 無 token | **加入 token 認證 + rate limit + 重試** | 免費帳號無認證容易被 429 封鎖 |
| 交易成本 | 未提及 | **全面加入（0.585% 來回）** | 不含成本的回測勝率無意義 |
| T+1 漲跌停過濾 | 未提及 | **加入漲跌停判斷邏輯** | 漲停買不到是現實面最大落差 |
| 最短持有天數 | 5 天 | **10 天** | 5 天無法覆蓋手續費，不符散戶中期定位 |
| 市場週期驗證 | 「各 ≥ 20%」無法自動計算 | **market_cycle.py 標籤系統 + 各 ≥ 30 筆** | 改為可自動計算的標準 |
| 第 1 週時程 | 環境 + Data Lake 全塞進去 | **第 1 週只求環境，Data Lake 移至第 2 週** | 資料下載 8–12 小時不能混在環境建置裡 |
