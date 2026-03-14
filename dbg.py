import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))
from dotenv import load_dotenv
load_dotenv(Path.home() / "strategy-mining" / ".env")

from config.encrypt import load_encrypted_json
from engine.validator import dedupe_backtests

data = load_encrypted_json('results/backtests/orchestrator_results.enc')
data = dedupe_backtests(data)

samples = []
for d in data:
    samples.append(d.get("sample_count", 0))

print(f"Total strategies: {len(samples)}")
print(f"Max trades: {max(samples)}")
print(f"Mean trades: {sum(samples)/len(samples)}")
print(f"Strategies with 0 trades: {samples.count(0)}")
print(f"Strategies with >= 200 trades: {sum(1 for s in samples if s >= 200)}")

print("\nSample top 5 strategies by sample_count:")
top_sampled = sorted(data, key=lambda x: x.get("sample_count", 0), reverse=True)[:5]
for s in top_sampled:
    print(f"ID: {s.get('id')} - Trades: {s.get('sample_count')} - WinRate: {s.get('win_rate')} - Sharpe: {s.get('sharpe')}")
