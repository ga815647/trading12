# Known Statistical Limitations & Use Cases

While this system implements advanced statistical rigor, users should be aware of the following limitations inherent in algorithmic strategy mining.

## 1. Survival Bias in Strategy Discovery
Even with FDR correction, the "best" strategies we find are survivors of thousands of tests. While group-wise FDR helps, there is still a residual risk that the highest-ranked strategies perform well partly due to luck during the IS period.

## 2. Market Regime Shifts
Statistical validation assumes a certain level of stationary behavior in market patterns. A fundamental shift in market structure (e.g., changing from T+2 to T+0, new tax laws, or high-frequency trading dominance) can render historical validation obsolete regardless of OOS performance.

## 3. Execution Slippage
The backtest uses a realistic cost model (`engine/cost_model.py`), but real-world "impact cost" for large positions or illiquid stocks cannot be perfectly simulated. Actual performance may lag backtest results by 0.5% - 1.0% depending on size.

## 4. Signal Correlation
Triggers within the same cluster (e.g., different chip-based triggers) may still share unmodeled dependencies. While our `independent_votes` logic mitigates this, it does not eliminate it entirely.

---

## Recommended Use Cases
- **Primary Use**: Identifying candidate strategies for manual verification or small-scale paper trading.
- **Secondary Use**: Discovering market anomalies and "edge" in specific stock universes (e.g., ETF constituents).
- **Not Recommended**: Fully autonomous "black-box" trading without human oversight of the underlying triggers.
