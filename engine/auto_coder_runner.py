import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import HYPOTHESIS_DIR, LOG_DIR, ensure_runtime_dirs

def run_auto_coder():
    """
    Automated Local Code Generator
    Reads batch JSONs and calls backtest_coder.py in --local mode.
    """
    ensure_runtime_dirs()
    
    error_log = LOG_DIR / "coder_errors.log"
    batch_files = sorted(glob.glob(str(HYPOTHESIS_DIR / "local_batch_*.json")))
    
    if not batch_files:
        print(f"No local batch files found in {HYPOTHESIS_DIR}. Run local_hypothesis_generator.py first.")
        return

    output_dir = ROOT_DIR / "engine" / "generated_backtests"
    output_dir.mkdir(parents=True, exist_ok=True)

    total_count = 0
    success_count = 0
    fail_count = 0

    print(f"Starting auto-coder for {len(batch_files)} batches...")

    for batch_file in batch_files:
        print(f"Processing batch: {Path(batch_file).name}")
        try:
            with open(batch_file, "r", encoding="utf-8") as f:
                hypotheses = json.load(f)
        except Exception as e:
            with open(error_log, "a", encoding="utf-8") as f:
                f.write(f"[ERROR] Failed to read {batch_file}: {e}\n")
            continue

        for hypo in hypotheses:
            hypo_id = hypo.get("hypothesis_id")
            total_count += 1
            
            # Call backtest_coder in local mode
            # Command: python agents/backtest_coder.py --hypothesis-id <ID> --local --output engine/generated_backtests/batch_xxx.py
            cmd = [
                sys.executable,
                str(ROOT_DIR / "agents" / "backtest_coder.py"),
                "--hypothesis-id", hypo_id,
                "--local",
                "--output", str(output_dir / f"{hypo_id}.py"),
                "--input", str(batch_file)
            ]
            
            try:
                # Capture output to avoid flooding terminal
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                success_count += 1
            except subprocess.CalledProcessError as e:
                fail_count += 1
                with open(error_log, "a", encoding="utf-8") as f:
                    f.write(f"[ERROR] Failed {hypo_id}: {e}\n")
                    f.write(f"Stderr: {e.stderr}\n")
            except Exception as e:
                fail_count += 1
                with open(error_log, "a", encoding="utf-8") as f:
                    f.write(f"[CRITICAL] Unexpected error for {hypo_id}: {e}\n")

            if total_count % 100 == 0:
                print(f"Progress: {total_count} processed ({success_count} success, {fail_count} fail)")

    print(f"\nCompleted Strategy Factory Run!")
    print(f"Total: {total_count}")
    print(f"Success: {success_count}")
    print(f"Failures: {fail_count} (Check {error_log} for details)")

if __name__ == "__main__":
    run_auto_coder()
