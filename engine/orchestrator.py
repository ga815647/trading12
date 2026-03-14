import argparse
import json
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import BACKTEST_DIR, HYPOTHESIS_DIR, LOG_DIR, PARQUET_DIR, SIGNAL_DIR, ensure_runtime_dirs
from engine.lifecycle import filter_and_thaw, get_current_market_bars, update_lifecycle
from engine.notify import send_signal

import pyarrow.parquet as pq

# Global shutdown flag
SHUTDOWN_REQUESTED = False
MAIN_PID = os.getpid()

def shutdown_handler(signum, frame):
    global SHUTDOWN_REQUESTED
    # Only the main process should handle this to avoid log spam and redundant cleanup
    if os.getpid() != MAIN_PID:
        return
        
    if not SHUTDOWN_REQUESTED:
        SHUTDOWN_REQUESTED = True
        logger.info("\n[System] 🛑 收到中斷指令，正在安全停止所有平行任務並清理程序...")
    else:
        # Nuclear option: if user presses Ctrl+C again, kill EVERYTHING immediately
        print("\n[System] ⚠️ 再次收到中斷指令，強制執行核彈級終止！", flush=True)
        if sys.platform != "win32":
            try:
                os.killpg(0, signal.SIGKILL)
            except:
                pass
        os._exit(1)

def check_shutdown():
    if SHUTDOWN_REQUESTED:
        print("\n[System] 🔚 程序已執行安全終止流程 (Nuclear Cleanup)。", flush=True)
        if sys.platform != "win32":
            # Kill the entire process group to ensure no orphans remain
            try:
                os.killpg(0, signal.SIGKILL)
            except:
                pass
        os._exit(0)

# Register signal handler
signal.signal(signal.SIGINT, shutdown_handler)

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

def get_theoretical_latest_trading_day() -> str:
    """
    Returns the YYYY-MM-DD string of the latest expected trading day.
    """
    now = datetime.now()
    wd = now.weekday()  # Mon=0...Sun=6
    
    # If Sat=5, latest is Fri (now-1)
    # If Sun=6, latest is Fri (now-2)
    # If Mon-Fri and before 15:30, latest is T-1
    if wd == 5:
        latest = now - timedelta(days=1)
    elif wd == 6:
        latest = now - timedelta(days=2)
    else:
        # Weekday: check if market results should be out (15:30)
        if now.hour < 15 or (now.hour == 15 and now.minute < 30):
            # Prior trading day
            if wd == 0:  # Mon morning -> Fri
                latest = now - timedelta(days=3)
            else:
                latest = now - timedelta(days=1)
        else:
            latest = now
    
    return latest.strftime("%Y-%m-%d")

def run_step(name: str, cmd: list[str], cwd: Path = ROOT_DIR):
    if SHUTDOWN_REQUESTED:
        logger.info(f"Skipping step {name} due to shutdown request.")
        return

    logger.info(f">>> Starting Step: {name}")
    logger.info(f"Command: {' '.join(cmd)}")
    
    # Process group management for Linux/WSL to ensure clean cleanup
    popen_kwargs = {"cwd": cwd}
    if sys.platform != "win32":
        popen_kwargs["preexec_fn"] = os.setsid

    try:
        process = subprocess.Popen(cmd, **popen_kwargs)
        
        while process.poll() is None:
            if SHUTDOWN_REQUESTED:
                logger.info(f"[System] 🛑 Terminating {name} process group...")
                if sys.platform != "win32":
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=2)
                return
            # Small sleep to prevent CPU hogging while waiting
            import time
            time.sleep(0.5)

        if process.returncode != 0:
            logger.error(f"Step {name} failed with exit code {process.returncode}")
            raise subprocess.CalledProcessError(process.returncode, cmd)
            
        logger.info(f"Step {name} completed successfully.")
        return ""
    except Exception as e:
        if not SHUTDOWN_REQUESTED:
            logger.error(f"Error in step {name}: {e}")
        raise

def main():
    if sys.platform != "win32":
        try:
            os.setpgrp()
        except:
            pass
    parser = argparse.ArgumentParser(description="Master Pipeline Orchestrator")
    parser.add_argument("--mode", choices=["local", "llm"], default="local")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip data fetching")
    parser.add_argument("--force", action="store_true", help="Force run all steps regardless of date guard")
    parser.add_argument("--gen-hypotheses", type=str, choices=["True", "False"], default="True", help="Whether to run strategy generation")
    parser.add_argument("--gen-count", type=int, default=1000, help="Max strategies to generate")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) - 2))
    args = parser.parse_args()

    # Convert gen-hypotheses to bool
    args.gen_hypotheses = args.gen_hypotheses == "True"

    start_time = datetime.now()
    logger.info(f"===== Orchestrator Pulse Start: {start_time.isoformat()} =====")
    if args.force:
        logger.info("🚀 [Force Mode] Activated. Guards will be ignored.")

    try:
        # Pre-Fetch Guard
        date_before = get_latest_market_date()
        theoretical_latest = get_theoretical_latest_trading_day()
        
        logger.info(f"Market Date (Local): {date_before}")
        logger.info(f"Theoretical Latest: {theoretical_latest}")

        skip_fetch_reason = None
        if args.skip_fetch:
            skip_fetch_reason = "Manual skip"
        elif date_before == theoretical_latest and not args.force:
            skip_fetch_reason = f"Data already up-to-date ({date_before})"

        # 1. Data Prep
        if not skip_fetch_reason:
            run_step("Data Fetch", [sys.executable, "data/fetcher.py", "--mode", "daily"])
        else:
            logger.info(f"[Guard] [Pre-Fetch Guard] Skipping fetch: {skip_fetch_reason}")

        # Post-Fetch Final Guard
        date_after = get_latest_market_date()
        logger.info(f"Market Date After Fetch/Check: {date_after}")

        has_new_data = True
        if not args.force and date_before == date_after and date_after is not None:
            logger.info("[Guard] [State Guard] No data change detected. Skipping fetch but continuing mining.")
            has_new_data = False

        # 2. Generation & Lifecycle Filtering
        logger.info(">>> Segment: Generation & Lifecycle Filter")
        if args.gen_hypotheses:
            # Cleanup HYPOTHESIS_DIR before generation to prevent loading thousands of stale files
            for old_json in HYPOTHESIS_DIR.glob("*.json"):
                try:
                    old_json.unlink()
                except:
                    pass

            if args.mode == "local":
                from agents.local_hypothesis_generator import generate_local_factory
                logger.info(f"Running Local Matrix Generation (max_count={args.gen_count})")
                generate_local_factory(max_count=args.gen_count)
            else:
                # Placeholder for Agent 1 LLM generation if automated later
                logger.info("LLM generation segment skipped (manual/adhoc trigger expected)")
        else:
            logger.info("🛡️ [Orchestrator] Strategy generation skipped by command.")
            print("\n🛡️ [Orchestrator] 依指令跳過策略產生階段，測試既有或凍結名單。")

        # Load only relevant hypotheses (prevent loading thousands of historical files)
        # If we just generated them, they are in matrix_batch_*.json or orchestrator_batch.json
        hypo_files = list(HYPOTHESIS_DIR.glob("matrix_batch_*.json")) + \
                     list(HYPOTHESIS_DIR.glob("orchestrator_batch.json"))
        
        # Fallback if no specific batches found but we want to test whatever is there
        if not hypo_files:
            hypo_files = list(HYPOTHESIS_DIR.glob("*.json"))

        all_hypotheses = []
        for hf in hypo_files:
            try:
                with open(hf, "r", encoding="utf-8") as f:
                    batch = json.load(f)
                    if isinstance(batch, list):
                        all_hypotheses.extend(batch)
            except Exception as e:
                logger.warning(f"Failed to load {hf}: {e}")

        current_bars = get_current_market_bars()
        to_test = filter_and_thaw(all_hypotheses, current_bars)
        logger.info(f"Filtered {len(all_hypotheses)} down to {len(to_test)} for testing.")

        new_active_count = 0
        if not to_test:
            logger.info("No new or thawed strategies to test. Proceeding to scan.")
        else:
            # Save the filtered batches for run_backtests.py
            to_test_path = HYPOTHESIS_DIR / "orchestrator_batch.json"
            with open(to_test_path, "w", encoding="utf-8") as f:
                json.dump(to_test, f, indent=2)

            # 3. Backtest
            from engine.run_backtests import run_all
            from config.encrypt import save_signal

            def is_shutdown():
                return SHUTDOWN_REQUESTED

            logger.info(">>> Starting Step: Backtest (Parallel)")
            backtest_results = run_all(
                to_test_path,
                workers=args.workers,
                show_progress=True,
                is_shutdown=is_shutdown
            )
            
            if SHUTDOWN_REQUESTED:
                logger.warning("Backtesting interrupted. Saving partial results if any.")
            
            output_path = BACKTEST_DIR / "orchestrator_results.enc"
            save_signal(backtest_results, output_path)
            logger.info(f"Step Backtest completed. {len(backtest_results)} results saved.")

            if SHUTDOWN_REQUESTED:
                check_shutdown()

            # 4. Validate
            run_step("Validate", [
                sys.executable, "engine/validator.py",
                "--input", str(output_path),
                "--output", str(SIGNAL_DIR / "library.enc")
            ])

            if SHUTDOWN_REQUESTED:
                check_shutdown()

            # 5. Update Lifecycle
            from config.encrypt import load_encrypted_json
            # Use backtest_results which we already have in memory
            # Validated ID merging logic
            validated = load_encrypted_json(SIGNAL_DIR / "library.enc")
            valid_ids = {v.get("hypothesis_id") for v in validated if v.get("passes_validation")}
            
            for res in backtest_results:
                res["passes_validation"] = res.get("hypothesis_id") in valid_ids
            
            update_lifecycle(backtest_results, current_bars)
            
            new_active_count = len([vid for vid in valid_ids if vid in {t.get("hypothesis_id") for t in to_test}])
            logger.info(f"Lifecycle registry updated. New active strategies found: {new_active_count}")

            if SHUTDOWN_REQUESTED:
                check_shutdown()

        # 6. Smart Scan Guard
        if SHUTDOWN_REQUESTED: check_shutdown()
        if not has_new_data and new_active_count == 0:
            logger.info("[Guard] [Smart Scan Guard] No new data and no new strategies found. Skipping scan.")
            print("\n🛡️ 今日無新資料且未發現新策略，跳過掃描與推播以防洗版。")
            return

        # 7. Daily Scan
        if SHUTDOWN_REQUESTED: check_shutdown()
        scan_output = run_step("Daily Scan", [sys.executable, "engine/run_daily_scan.py"])
        
        # 8. Reporting
        if SHUTDOWN_REQUESTED: check_shutdown()
        end_time = datetime.now()
        duration = end_time - start_time
        summary_msg = (
            f"✅ **Orchestrator Run Complete**\n"
            f"• 耗時：{str(duration).split('.')[0]}\n"
            f"• 測試策略數：{len(to_test)}\n"
            f"• 新增有效策略：{new_active_count}\n"
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
