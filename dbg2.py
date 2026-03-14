import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))
from dotenv import load_dotenv
load_dotenv(Path.home() / "strategy-mining" / ".env")

from config.encrypt import load_encrypted_json
from engine.validator import dedupe_backtests

data = load_encrypted_json('results/backtests/orchestrator_results.enc')
data = dedupe_backtests(data)

# Filter out ones with < 100 trades to remove noise
valid = [d for d in data if d.get("sample_count", 0) >= 100]

print("\n--- Top 5 by Win Rate ---")
top_wr = sorted(valid, key=lambda x: x.get("win_rate", 0.0), reverse=True)[:5]
for s in top_wr:
    print(f"ID: {s.get('id')} | Trades: {s.get('sample_count')} | WR: {s.get('win_rate'):.2%} | Sharpe: {s.get('sharpe'):.2f} | AvgRet: {s.get('avg_return'):.2%}")

print("\n--- Top 5 by Sharpe ---")
top_sharpe = sorted(valid, key=lambda x: x.get("sharpe", 0.0), reverse=True)[:5]
for s in top_sharpe:
    print(f"ID: {s.get('id')} | Trades: {s.get('sample_count')} | WR: {s.get('win_rate'):.2%} | Sharpe: {s.get('sharpe'):.2f} | AvgRet: {s.get('avg_return'):.2%}")
