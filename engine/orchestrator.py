import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import BACKTEST_DIR, HYPOTHESIS_DIR, LOG_DIR, PARQUET_DIR, SIGNAL_DIR, ensure_runtime_dirs
from engine.lifecycle import filter_and_thaw, get_current_market_bars, update_lifecycle
from engine.notify import send_signal

import pyarrow.parquet as pq

# Configure logging
ensure_runtime_dirs()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "orchestrator.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("orchestrator")

def get_latest_market_date() -> str | None:
    """
    Efficiently gets the latest date from 2330_kline.parquet using metadata/tail reading.
    """
    path = PARQUET_DIR / "2330_kline.parquet"
    if not path.exists():
        return None
    try:
        pf = pq.ParquetFile(path)
        # Read only the last row group to find the last date
        last_rg = pf.read_row_group(pf.num_row_groups - 1, columns=["date"])
        if len(last_rg) > 0:
            return str(last_rg["date"][-1])
    except Exception as e:
        logger.warning(f"Error reading market date: {e}")
    return None

def run_step(name: str, cmd: list[str], cwd: Path = ROOT_DIR):
    logger.info(f">>> Starting Step: {name}")
    logger.info(f"Command: {' '.join(cmd)}")
    try:
        # Don't use capture_output=True, allow it to stream to the main terminal
        result = subprocess.run(cmd, cwd=cwd, check=True)
        logger.info(f"Step {name} completed successfully.")
        return ""
    except subprocess.CalledProcessError as e:
        logger.error(f"Step {name} failed with exit code {e.returncode}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Master Pipeline Orchestrator")
    parser.add_argument("--mode", choices=["local", "llm"], default="local")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip data fetching")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    start_time = datetime.now()
    logger.info(f"===== Orchestrator Pulse Start: {start_time.isoformat()} =====")

    try:
        # Check date before fetch
        date_before = get_latest_market_date()
        logger.info(f"Market Date Before Fetch: {date_before}")

        # 1. Data Prep
        if not args.skip_fetch:
            run_step("Data Fetch", [sys.executable, "data/fetcher.py", "--mode", "daily"])

        # Check date after fetch
        date_after = get_latest_market_date()
        logger.info(f"Market Date After Fetch: {date_after}")

        if not args.skip_fetch and date_before == date_after and date_after is not None:
            logger.info("🛡️ [State Guard] No new market data detected. Aborting scan to prevent alert fatigue.")
            print("\n🛡️ 今日無新交易資料，安全守衛攔截。跳過後續掃描與推播。")
            return

        # 2. Generation & Lifecycle Filtering
        logger.info(">>> Segment: Generation & Lifecycle Filter")
        if args.mode == "local":
            run_step("Local Generation", [sys.executable, "agents/local_hypothesis_generator.py"])
        else:
            # Placeholder for Agent 1 LLM generation if automated later
            logger.info("LLM generation segment skipped (manual/adhoc trigger expected)")

        # Load all hypotheses from HYPOTHESIS_DIR
        hypo_files = list(HYPOTHESIS_DIR.glob("*.json"))
        all_hypotheses = []
        for hf in hypo_files:
            try:
                with open(hf, "r", encoding="utf-8") as f:
                    all_hypotheses.extend(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load {hf}: {e}")

        current_bars = get_current_market_bars()
        to_test = filter_and_thaw(all_hypotheses, current_bars)
        logger.info(f"Filtered {len(all_hypotheses)} down to {len(to_test)} for testing.")

        if not to_test:
            logger.info("No new or thawed strategies to test. Proceeding to scan.")
        else:
            # Save the filtered batches for run_backtests.py
            to_test_path = HYPOTHESIS_DIR / "orchestrator_batch.json"
            with open(to_test_path, "w", encoding="utf-8") as f:
                json.dump(to_test, f, indent=2)

            # 3. Backtest
            run_step("Backtest", [
                sys.executable, "engine/run_backtests.py",
                "--hypothesis-file", str(to_test_path),
                "--output", str(BACKTEST_DIR / "orchestrator_results.enc"),
                "--workers", str(args.workers),
                "--progress"
            ])

            # 4. Validate
            run_step("Validate", [
                sys.executable, "engine/validator.py",
                "--input", str(BACKTEST_DIR / "orchestrator_results.enc"),
                "--output", str(SIGNAL_DIR / "library.enc")
            ])

            # 5. Update Lifecycle
            from config.encrypt import load_encrypted_json
            backtest_results = load_encrypted_json(BACKTEST_DIR / "orchestrator_results.enc")
            # We need the 'passes_validation' flag from validator output if we want accuracy, 
            # but validator.py saves its OWN output. 
            # Let's merge the validation status back.
            validated = load_encrypted_json(SIGNAL_DIR / "library.enc")
            valid_ids = {v.get("hypothesis_id") for v in validated if v.get("passes_validation")}
            
            for res in backtest_results:
                res["passes_validation"] = res.get("hypothesis_id") in valid_ids
            
            update_lifecycle(backtest_results, current_bars)
            logger.info("Lifecycle registry updated.")

        # 6. Daily Scan
        scan_output = run_step("Daily Scan", [sys.executable, "engine/run_daily_scan.py"])
        
        # 7. Reporting
        end_time = datetime.now()
        duration = end_time - start_time
        summary_msg = (
            f"✅ **Orchestrator Run Complete**\n"
            f"• 耗時：{str(duration).split('.')[0]}\n"
            f"• 測試策略數：{len(to_test)}\n"
            f"• 目前 K 線長度：{current_bars}\n"
            f"• 掃描狀態：完成\n"
            f"更多細節請查看 logs/orchestrator.log"
        )
        send_signal(summary_msg)
        logger.info("Final summary sent to Telegram.")

    except Exception as e:
        logger.error(f"Orchestrator CRITICAL FAILURE: {e}")
        send_signal(f"❌ **Orchestrator CRITICAL FAILURE**\nError: {str(e)}")
        sys.exit(1)

    logger.info(f"===== Orchestrator Pulse End: {datetime.now().isoformat()} =====")

if __name__ == "__main__":
    main()
