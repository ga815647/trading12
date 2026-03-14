# Taiwan Stock Strategy Validation Logic

This document outlines the statistical rigor and validation criteria used in the mining system.

## 1. Out-of-Sample (OOS) Testing
We employ a **Time-Based OOS** approach to prevent look-ahead bias and ensure the strategy generalizes to future data.
- **IS (In-Sample)**: Trades exiting before `anchor - OOS_YEARS` (default 2 years).
- **OOS (Out-of-Sample)**: Trades exiting within the last `OOS_YEARS`.
- **Criteria**: OOS Win Rate must be >= `0.53`.

## 2. Risk-Adjusted Returns (Sharpe Ratio)
We transition from per-trade Sharpe to **Portfolio-Level Sharpe** to account for inter-trade correlations.
- **Method**: Aggregate overlapping daily returns into a single portfolio series.
- **Threshold**: `MIN_SHARPE = 0.5`. This is generally lower than trade-level Sharpe because it accounts for volatility clusters during market downturns.

## 3. Multiple Hypothesis Testing (FDR Correction)
To control for "data mining bias" (finding patterns by chance), we apply False Discovery Rate (FDR) correction using the Benjamini-Hochberg (BH) procedure.
- **Family-Based FDR**: Correction is performed within each "Trigger Family" (e.g., A01) rather than globally. This balances the risk of Type I errors (false positives) while avoiding over-penalization of diverse signal types.
- **Threshold**: Adjusted P-Value < `0.05`.

## 4. Signal Independence & Ensemble Voting
The system uses a "Star" rating based on independent evidence.
- **Clusters**: Triggers are grouped into clusters (e.g., Chip, Technical, Sentiment). 
- **Voting**: High-confidence (3-star) signals require at least 3 independent source clusters to agree.

## 5. Time Decay & Recent Performance
We use a **Per-Strategy Anchor** for exponential weight calculation.
- This ensures that a strategy that was historically powerful but is currently in a quiet period (waiting for specific market conditions) is not unfairly discarded, provided its active periods show statistical significance.
