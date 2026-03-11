# Strategy Mining Project Rules - v11

## Forbidden

- Do not read or modify `results/`, `signals/`, `.env`, `.enc`, or `data/parquet_db/`.
- Do not hardcode real strategy parameters or secrets.
- Do not expose backtest statistics outside encrypted outputs.

## Trading rules

- All post-close signals must enter at T+1 open.
- Skip entries if T+1 opens at limit up or limit down.
- Always include Taiwan stock trading cost assumptions.

## Allowed work

- Edit source under `agents/`, `config/`, `data/`, and `engine/`.
- Update Docker and repository configuration files.
