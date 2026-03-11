# trading

Automated strategy mining system for Taiwan equities.

## Quick start

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env` and fill in the required secrets.
3. Run `python engine/preflight.py` to verify env and local data readiness.
4. Download market data with `python data/fetcher.py --mode full`.
5. Generate hypotheses with `python agents/hypothesis_generator.py`.
6. Run batch backtests with `python engine/run_backtests.py`.
7. Validate signals with `python engine/validator.py`.
8. Scan daily opportunities with `python engine/run_daily_scan.py`.

## Safety rules

- Do not commit `.env`, encrypted libraries, or parquet files.
- Use T+1 entry for all post-close signals.
- Keep backtests cost-aware with the built-in Taiwan stock cost model.
