# 動態自適應引擎 (Adaptive Engine) 升級企劃書

**版本**：v1.0  
**日期**：2025-03-14  
**定位**：從「靜態單次掃描器」升級為「具備演化能力的持續挖掘引擎」

> ⚠️ 本企劃書為架構設計文件，**未經討論確認前，請勿修改任何現有程式碼**。

---

## 一、升級背景與目標

### 1.1 現況與缺口

| 現況 | 缺口 |
|------|------|
| 單次 Grid Search → 產生假設 → 回測 → 篩選 → 結束 | 無迭代優化，一次掃描後即停止 |
| 全歷史等權重統計（樣本數、勝率、p 值、夏普） | 無法區分「歷史穩健」與「當前有效」 |
| 固定防護：commission、T+1 漲跌停 | 缺乏流動性、減資、暫停交易等極端市況防禦 |
| Antigravity（雲端）僅負責假設生成 | 雲端 LLM 絕不能接觸真實結果 |

### 1.2 升級目標

1. **時間衰減與滾動前向**：近期表現權重 > 遠期，自動區分歷史穩健度 vs. 當前有效性  
2. **盲化迭代演化**：多代演化、突變/重組，但**雲端 LLM 永遠看不到報酬率、勝率、解密結果**  
3. **極端邊界防禦**：流動性枯竭、減資、暫停交易等「紙上富貴」陷阱防禦

---

## 二、數學評估邏輯

### 2.1 時間衰減評分 (Time-Decay Scoring)

**概念**：過去 10 年 55% 勝率的含金量 < 近 2 年 55%，評分時應對近期交易給予更高權重。

**數學模型**：

令 \( t \) 為交易日期（距今天數），\( r_t \) 為該筆報酬，\( w(t) \) 為時間權重函數。

- **指數衰減**（推薦）：
  \[
  w(t) = \exp\left(-\lambda \cdot \frac{t}{T_{\text{max}}}\right), \quad \lambda \in [0.5, 2.0]
  \]
  其中 \( T_{\text{max}} \) 為資料最長天數（約 3,650 天 / 10 年）。  
  \( \lambda = 1 \) 時，1 年前權重約為今天的 \( e^{-0.1} \approx 0.9 \)。

- **分段權重**（實作較簡單）：
  - 近 2 年（約 500 日）：權重 1.0  
  - 2–5 年：權重 0.7  
  - 5–10 年：權重 0.4  

**加權統計量**（在 validator 中計算）：

| 指標 | 公式 |
|------|------|
| 加權勝率 | \( \bar{p}_w = \frac{\sum w(t_i) \cdot \mathbb{1}[r_i > 0]}{\sum w(t_i)} \) |
| 加權夏普 | 以 \( w(t) \) 加權的報酬序列，再算 Sharpe |
| 近期純勝率 | 近 500 日樣本的原始勝率（無加權，作為門檻） |

**門檻調整建議**：

- 新增：`min_weighted_win_rate >= 0.54`（加權勝率門檻）  
- 新增：`min_recent_2y_win_rate >= 0.52`（近 2 年純勝率）  
- 保留既有：`min_win_rate >= 0.55`（全樣本）、`min_oos_win_rate >= 0.53`

### 2.2 滾動前向 (Walk-Forward) 概念

**用途**：驗證策略在「未見未來」的表現，降低過擬合。

**設計**（擴展現有 OOS 邏輯）：

- 將資料切成多個區段，例如每 2 年為一段  
- 對每段計算：訓練期（前 80%）統計量、測試期（後 20%）勝率  
- 通過門檻條件：至少 \( K \) 個區段（如 \( K \geq 2 \)）的測試期勝率 ≥ 0.52  

**實作建議**：Phase 2 擴充，Phase 1 可先以「加權統計 + 近 2 年勝率」為主。

### 2.3 盲化適應度 (Blind Fitness)

**目標**：本機完成適應度評估，雲端 LLM 只收到「抽象繁衍指令」，**永遠看不到數值結果**。

**抽象描述符 (Abstract Descriptors)**（本機產生、可安全傳給雲端）：

| 描述符類型 | 內容 | 範例 |
|------------|------|------|
| 存活母題 ID | 通過篩選的 template 前綴 | `["A", "K", "L"]` |
| 參數傾向 | 參數「偏高/偏低」的相對描述 | `horizon_days:偏高` |
| 組合傾向 | 存活策略常出現的特徵 | `籌碼類+技術指標` |
| 突變指令 | 建議的搜尋方向 | `expand_pattern_near:trap_buy` |

**禁止傳遞**（絕對禁止出現在給 LLM 的 prompt 中）：

- 勝率、報酬率、夏普、p 值  
- 具體參數數值  
- 樣本數  
- 任何解密的結果內容  

---

## 三、資料流向與盲化迭代機制

### 3.1 整體架構

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Antigravity（雲端，可聯網）                        │
│  Agent 1 假設產生器                                                        │
│    輸入：母題模板 + 演化指令 (EvolutionHints)                               │
│    輸出：hypotheses batch JSON（僅含抽象結構 + 佔位符）                      │
│    可見：演化指令（抽象）                                                   │
│    不可見：任何報酬、勝率、真實參數                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ Git push
┌─────────────────────────────────────────────────────────────────────────┐
│                         WSL2 本機（敏感區）                                │
│  engine/run_backtests.py → results/backtests/*.enc                        │
│  engine/validator.py     → 含時間衰減 + 盲化適應度                          │
│  engine/evolution_hints.py（新增）→ 產生 EvolutionHints JSON               │
│  engine/edge_defense.py（新增）→ 極端邊界過濾                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    本機產生 evolution_hints.json（抽象，可進 repo）
                                    │
                                    ▼ Git push（可選，或手動複製到 Antigravity）
┌─────────────────────────────────────────────────────────────────────────┐
│                         Antigravity                                       │
│  Agent 1 讀取 evolution_hints.json，產生下一批假設                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 盲化迭代的詳細流程

**世代 0（初始化）**：  
- Agent 1 依現有母題 + Grid Search 產生 `batch_000.json`  
- 無演化指令

**世代 1（首次演化）**：

1. **本機**：`run_backtests.py` → 回測 → `validator.py`（含時間衰減）  
2. **本機**：`evolution_hints.py` 讀取加密回測結果，進行適應度評估（內部可見所有數字）  
3. **本機**：輸出 `evolution_hints.json`，內容**僅含抽象描述**：

```json
{
  "generation": 1,
  "surviving_templates": ["A", "K", "L", "E"],
  "param_tendencies": {
    "horizon_days": "prefer_longer",
    "pattern_name": "expand_near:trap_buy,hesitate_buy",
    "chip_days": "prefer_mid"
  },
  "feature_combos": ["chip_sequence", "oversold_confirmation"],
  "mutation_hints": [
    "add_variants_near_trap_buy",
    "combine_A_with_E"
  ],
  "suppress_templates": []
}
```

4. **Antigravity**：Agent 1 讀取 `evolution_hints.json`，依提示產生 `batch_001.json`  
5. 重複 1–4，形成世代 2、3、…  

**安全檢查**：  
- `evolution_hints.json` 由本機腳本產生，內容經嚴格過濾，**絕不包含數值結果**  
- 可納入 SKILL.md：禁止 Agent 1 在產生假設時寫入或推測任何數字

### 3.3 本機 evolution_hints 產生邏輯（偽代碼）

```python
# engine/evolution_hints.py（概念）
def produce_evolution_hints(validated_signals: list[dict]) -> dict:
    # validated_signals 來自 validator，含完整統計（僅本機可見）
    # 輸出必須是純抽象，可安全給雲端 LLM

    templates = set()
    param_tendencies = {}
    for s in validated_signals:
        templates.add(s["id"][:1])  # A, K, L...
        # 統計 horizon_days 分布 → 轉成 "prefer_longer" / "prefer_shorter"
        # 統計 pattern_name 分布 → 轉成 "expand_near:x,y"
        # 不做：輸出任何 win_rate, sharpe, p_value

    return {
        "surviving_templates": sorted(templates),
        "param_tendencies": param_tendencies,
        "mutation_hints": _derive_mutation_hints(validated_signals),
        "suppress_templates": _derive_suppress(validated_signals),  # 全滅的類
    }
```

---

## 四、極端邊界防禦 (Edge-Case Robustness)

### 4.1 防禦項目清單

| 陷阱類型 | 說明 | 防禦策略 |
|----------|------|----------|
| 流動性枯竭 | 成交量極低，實單難以成交 | 最低日均量門檻、最低週轉率 |
| 漲跌停無法進場 | 已實作 T+1 過濾 | 維持現有邏輯 |
| 減資暫停 | 減資當日/前後暫停交易 | 排除減資前後 N 日 |
| 下市/停止交易 | 股票長期停牌 | 排除交易日前後停牌標的 |
| 紙上富貴 | 回測可成交，實單因流動性無法成交 | 流動性加權報酬、滑價懲罰 |

### 4.2 數學與邏輯概念

**流動性過濾**：

- 進場當日（T+1）：  
  - 成交量 \( V_{T+1} \geq V_{\min} \)（例如 100 張或 20 日均量 × 0.3）  
  - 或 週轉率 \( \geq \tau_{\min} \)（例如 0.1%）  
- 若未達門檻，該筆交易視為「無法成交」，不計入報酬（或計為跳過）

**減資 / 暫停交易**：

- 需資料源：減資預告日、減資基準日、暫停交易日  
- FinMind：`taiwan_stock_dividend`、`taiwan_stock_info`（或類似）  
- 規則：進場日在「減資基準日前後 N 日」或「暫停交易區間」內 → 跳過該訊號

**滑價懲罰（選配）**：

- 對低流動性標的：  
  - 報酬扣減 \( -\beta \cdot (V_{\min} / V_{\text{actual}}) \)  
  - 或直接跳過流動性最低的 X% 交易  

### 4.3 實作位置

- `engine/edge_defense.py`：  
  - `filter_by_liquidity(trade_row, params) -> bool`  
  - `filter_by_corporate_events(trade_row, stock_id, date) -> bool`  
- `engine/backtest.py`：在 `next()` 或訊號觸發處呼叫上述過濾  
- `data/processor.py` 或新模組：取得減資、暫停交易日期

---

## 五、模組修改 / 新增清單

### 5.1 新增模組

| 模組 | 路徑 | 職責 |
|------|------|------|
|  evolution_hints | `engine/evolution_hints.py` | 從驗證結果產生抽象演化指令，供 Agent 1 使用 |
|  edge_defense | `engine/edge_defense.py` | 流動性、減資、暫停交易等極端邊界過濾 |
|  time_decay | `engine/time_decay.py` | 時間權重函數、加權勝率/夏普計算（可併入 validator） |

### 5.2 修改模組

| 模組 | 修改內容 |
|------|----------|
| `engine/validator.py` | 納入時間衰減評分、加權勝率/夏普、近期勝率門檻；呼叫 `evolution_hints` 產生 hints |
| `engine/backtest.py` | 整合 `edge_defense` 過濾；輸出每筆交易的日期供加權計算 |
| `engine/run_backtests.py` | 支援「世代」參數，輸出檔名可含 generation ID |
| `agents/hypothesis_generator.py` | 讀取 `evolution_hints.json`，依演化指令調整 Grid Search 範圍與母題取樣 |
| `config/config.py` | 新增時間衰減參數、流動性門檻、edge defense 開關 |
| `config/market_cycle.py` | 若 Walk-Forward 需要，可擴充分段定義 |
| `data/processor.py` 或新模組 | 取得減資、暫停交易日期（若 FinMind 有提供） |

### 5.3 新增 config 參數（建議）

```python
# config/config.py 擴充
TIME_DECAY_LAMBDA = 1.0           # 指數衰減係數
MIN_WEIGHTED_WIN_RATE = 0.54      # 加權勝率門檻
MIN_RECENT_2Y_WIN_RATE = 0.52     # 近 2 年勝率門檻
EDGE_DEFENSE_ENABLED = True       # 極端邊界防禦開關
MIN_DAILY_VOLUME = 100            # 最低進場日成交量（張）
MIN_TURNOVER_RATE = 0.001         # 最低週轉率
EVOLUTION_HINTS_PATH = "results/evolution_hints.json"  # 演化指令輸出
```

---

## 六、實作階段建議

| 階段 | 內容 | 優先級 |
|------|------|--------|
| Phase 1a | 時間衰減評分 + 門檻整合進 validator | 高 |
| Phase 1b | 極端邊界防禦（流動性過濾） | 高 |
| Phase 1c | evolution_hints 產生 + Agent 1 讀取演化指令 | 高 |
| Phase 2a | 減資 / 暫停交易過濾（依資料源可用性） | 中 |
| Phase 2b | Walk-Forward 分段驗證 | 中 |
| Phase 3 | 滑價懲罰、更細緻的突變策略 | 低 |

---

## 七、安全檢查表（防洩密）

在每次變更後確認：

- [ ] `evolution_hints.json` 僅含抽象描述，無勝率、報酬、p 值、夏普
- [ ] Agent 1 的 prompt 與輸出中，不會出現真實統計數值
- [ ] `results/`、`signals/`、`.enc` 仍不進 repo（或僅進 evolution_hints 的抽象版本）
- [ ] SKILL.md 明確禁止在程式碼或注釋中寫入任何統計結果
- [ ] 回測與 validator 仍在 WSL2 本機執行，雲端 LLM 不直接接觸

---

## 八、附錄：演化指令欄位定義（草案）

供 Agent 1 解讀用的 `evolution_hints.json` 欄位：

| 欄位 | 類型 | 含義 |
|------|------|------|
| `generation` | int | 當前世代編號 |
| `surviving_templates` | list[str] | 通過篩選的母題前綴（如 A, K, L） |
| `suppress_templates` | list[str] | 本世代全滅的母題前綴，可減少抽樣 |
| `param_tendencies` | dict | 參數傾向：`prefer_longer` / `prefer_shorter` / `prefer_mid` / `expand_near:x,y` |
| `feature_combos` | list[str] | 存活策略常見特徵組合（如 chip_sequence, oversold_confirmation） |
| `mutation_hints` | list[str] | 建議突變方向（如 add_variants_near_trap_buy） |
| `mutation_intensity` | str | 存活數=0 時為 `"high"`（大範圍隨機探索）；否則 `"normal"` |

---

## 九、與現有工作流程的整合步驟

### 9.1 升級後的 Antigravity ↔ WSL2 協作流程

**世代 0（首次，無演化）**：
1. Antigravity：Agent 1 產生 `batch_000.json`（與現有流程相同）
2. Antigravity：Agent 2 生成回測程式碼
3. WSL2：`git pull` → `run_backtests.py` → `validator.py` → 加密存檔
4. WSL2：**新增** `python -m engine.evolution_hints --input results/signals/library.enc --output results/evolution_hints.json`

**世代 1+（有演化）**：
1. Antigravity：Agent 1 **讀取** `results/evolution_hints.json`，產生 `batch_001.json`（抽樣偏向存活母題與參數傾向）
2. 其餘步驟同世代 0
3. 本機產生新的 `evolution_hints.json` 覆蓋，供下一世代使用

### 9.2 evolution_hints.json 是否進 Repo？

| 選項 | 優點 | 缺點 |
|------|------|------|
| **進 repo** | Antigravity 可直接讀取 | 需確保絕無洩密，欄位需白名單驗證 |
| **不進 repo** | 絕對隔離 | 需手動複製到 Antigravity 工作區或透過非敏感通道傳遞 |

**建議**：進 repo，但寫入 `.gitignore` 的例外（或獨立目錄 `config/evolution_hints.json`）。若放在 `config/` 下且內容僅含抽象欄位，可視為「策略搜尋配置」而非機密結果。

### 9.3 hypothesis_generator.py 擴充邏輯（概念）

```python
# 讀取 evolution_hints（若存在）
def load_evolution_hints(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None

def generate_batch_with_hints(template: dict, hints: dict | None, batch_size: int) -> list:
    if hints is None:
        return generate_batch(template, batch_size)  # 原有邏輯

    # 若此 template 前綴在 suppress_templates，跳過或大幅縮減抽樣
    prefix = template["id"][:1]
    if prefix in hints.get("suppress_templates", []):
        return generate_batch(template, batch_size // 4)  # 減少

    # 若在 surviving_templates，提高抽樣權重
    grids = _apply_param_tendencies(PARAM_GRIDS, hints.get("param_tendencies", {}))
    all_combos = list(itertools.product(*grids.values()))
    # 依 mutation_hints 微調組合（例如 expand pattern_name 範圍）
    ...
    return sampled_hypotheses
```

---

## 十、Agent 1 Prompt 擴充範例（供 Antigravity 使用）

當 `evolution_hints.json` 存在時，在 Agent 1 的 system 或 user prompt 中加入：

```
【演化指令 - 僅供調整假設抽樣方向，禁止推測任何統計結果】

本批次為第 {generation} 代假設產生。
存活母題前綴（可提高抽樣比例）：{surviving_templates}
建議減少抽樣的母題前綴：{suppress_templates}
參數傾向：{param_tendencies}
突變建議：{mutation_hints}

請依上述傾向調整 Grid Search 的抽樣權重與參數範圍，但：
- 不得在假設或程式中填入任何具體統計數值
- 不得推測勝率、報酬率、p 值或夏普
- 所有數值參數仍使用佔位符
```

---

## 十一、param_tendencies 推導規格（詳細）

| 參數 | 推導邏輯 | 輸出值 |
|------|----------|--------|
| `horizon_days` | 存活策略的 horizon_days 中位數 | 若 > 30 → `prefer_longer`；若 < 20 → `prefer_shorter`；否則 `prefer_mid` |
| `pattern_name` | 存活 K/L 類的 pattern_name 頻次 | 取 Top 2–3 → `expand_near:trap_buy,hesitate_buy` |
| `chip_days` | 存活 L 類的 chip_days 分布 | 同上邏輯 |
| `threshold_a` | 存活策略的 threshold 中位數 | `prefer_higher` / `prefer_lower` / `prefer_mid` |

**關鍵**：輸出僅為「傾向描述」，不輸出具體數值（如 `horizon_days: 45` 禁止；`prefer_longer` 允許）。

---

## 十二、Critical Pitfalls 避坑點（必納入實作）

### 12.1 基準日陷阱 (Anchor Date Trap)

**危險**：若以 `datetime.now()` 作為 Day 0 計算 days_ago，歷史區段 Walk-Forward（如 2015-2020）會因距離系統日期過遠而權重失真。

**解法**：Day 0 必須鎖定為**該批交易紀錄中日期最晚的一天**，即 `anchor_date = max(entry_date)` 或 `max(trade_dates)`。**禁止使用 `datetime.now()`**。

### 12.2 近期勝率小樣本失真 (Small Sample Size)

**危險**：近 2 年若只觸發 2 次且全勝，勝率 100% 無統計意義。

**解法**：新增 `MIN_RECENT_2Y_TRADES`（建議 10）。未達門檻者，近期勝率視為**未通過**（標記為 insufficient，不採用該門檻或視為失效）。

### 12.3 資料單位陷阱 (Data Unit Trap)

**危險**：FinMind `Trading_Volume` 單位為**股 (shares)**，非張。若門檻設 100 張卻以股比較，會誤濾掉所有標的。

**解法**：明確處理單位。常數 `SHARES_PER_LOT = 1000`，門檻以 `MIN_DAILY_VOLUME_LOTS`（張）定義，判斷時 `volume_shares >= MIN_DAILY_VOLUME_LOTS * SHARES_PER_LOT`。

### 12.4 全軍覆沒死鎖 (Evolutionary Deadlock)

**危險**：某世代篩選過嚴導致 0 個策略存活，下一代無法依 hints 抽樣。

**解法**：`evolution_hints` 新增 `mutation_intensity`。當存活數 = 0 時設為 `"high"`，指示假設產生器進行**大範圍隨機探索**；有存活時為 `"normal"`。

---

## 十三、風險與緩解

| 風險 | 緩解 |
|------|------|
| evolution_hints 誤含數值 | 本機腳本輸出前做欄位白名單檢查，拒絕任何數字欄位 |
| 過度聚焦存活母題導致多樣性喪失 | 保留至少 20% 抽樣給非存活母題，探索新方向 |
| 時間衰減過強導致樣本不足 | 近 2 年樣本數 < 50 時，該策略標記為「近期證據不足」，可選：放寬或跳過 |
| 流動性過濾過嚴 | 門檻可設為 config，Phase 1 先保守（如 100 張），再依實測調整 |
| 減資資料缺失 | FinMind 若無完整欄位，Phase 2a 可改為「已知事件手動清單」或暫緩 |

---

## 十四、驗收標準（各 Phase）

**Phase 1a 完成**（含避坑點 12.1、12.2）：  
- [ ] validator 可計算 `weighted_win_rate`、`recent_2y_win_rate`  
- [ ] 通過驗證的訊號需同時滿足既有門檻 + 新門檻  
- [ ] 回測結果 JSON 含 `trade_dates`，供加權計算使用  

**Phase 1b 完成**（含避坑點 12.3）：  
- [ ] backtest 在進場前呼叫 `filter_by_liquidity`  
- [ ] 未達流動性門檻的交易不計入報酬與樣本數  
- [ ] config 可開關 `EDGE_DEFENSE_ENABLED`
- [ ] 流動性門檻明確使用 `SHARES_PER_LOT` 換算（1 張 = 1000 股）  

**Phase 1c 完成**（含避坑點 12.4）：  
- [ ] `evolution_hints.py` 可從加密驗證結果產生合規的 JSON  
- [ ] `evolution_hints.json` 通過欄位白名單檢查，無數值洩密  
- [ ] `hypothesis_generator` 可讀取 hints 並調整抽樣  
- [ ] Agent 1 prompt 可接收並使用演化指令  

---

**文件結束**。待討論確認後，再進行具體程式碼實作。
