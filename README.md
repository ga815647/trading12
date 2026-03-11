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

## Live progress

- Single batch progress: `python engine/run_backtests.py --progress`
- Resumable chunked progress: `python engine/run_backtests_chunked.py --chunk-size 100 --workers 4`
- Disable per-hypothesis inner bars: add `--no-inner-progress`

## Signal inspection

- Inspect one hypothesis on the latest market data: `python engine/inspect_signal.py --hypothesis-id B05_0063`
- Export recent trigger list: `python engine/inspect_signal.py --hypothesis-id B05_0063 --lookback-days 5 --output results/signals/B05_0063_recent_5d.csv`

## Safety rules

- Do not commit `.env`, encrypted libraries, or parquet files.
- Use T+1 entry for all post-close signals.
- Keep backtests cost-aware with the built-in Taiwan stock cost model.
