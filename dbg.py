import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))
from dotenv import load_dotenv
load_dotenv(Path.home() / "strategy-mining" / ".env")

from config.config import (
    MIN_SAMPLE_COUNT,
    MIN_WIN_RATE,
    MIN_OOS_WIN_RATE,
    MIN_SHARPE,
    MAX_ADJUSTED_P_VALUE,
)
from config.encrypt import load_encrypted_json
from engine.validator import dedupe_backtests, _cycle_pass

data = load_encrypted_json('results/backtests/orchestrator_results.enc')
data = dedupe_backtests(data)

failure_counts = {
    'supported': 0, 'sample_count': 0, 'win_rate': 0, 
    'oos_win_rate': 0, 'sharpe': 0, 'p_value_raw': 0,  
    'cycle': 0
}

for item in data:
    if not item.get('supported', False): failure_counts['supported'] += 1
    if item.get('sample_count', 0) < MIN_SAMPLE_COUNT: failure_counts['sample_count'] += 1
    if item.get('win_rate', 0.0) < MIN_WIN_RATE: failure_counts['win_rate'] += 1
    if item.get('oos_win_rate', 0.0) < MIN_OOS_WIN_RATE: failure_counts['oos_win_rate'] += 1
    if item.get('sharpe', 0.0) < MIN_SHARPE: failure_counts['sharpe'] += 1
    if float(item.get('p_value', 1.0)) >= MAX_ADJUSTED_P_VALUE: failure_counts['p_value_raw'] += 1
    
    trade_dates = item.get('trade_dates', [])
    passed_cycle, _ = _cycle_pass(trade_dates)
    if not passed_cycle: failure_counts['cycle'] += 1

print('Failure counts out of', len(data), 'deduped hypotheses:')
print(json.dumps(failure_counts, indent=2))
