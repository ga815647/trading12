import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
import base64
import hashlib

def generate_key(password: str) -> bytes:
    h = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(h)

def save_signal(results: list, output_path: str, password: str):
    key = generate_key(password)
    f = Fernet(key)
    data = json.dumps(results).encode()
    encrypted_data = f.encrypt(data)
    
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypted_data)
    print(f"Saved encrypted signals to {output_path}")

if __name__ == "__main__":
    password = os.getenv("ENCRYPT_PASSWORD", "secret")
    # 建立一個空或簡單的規律庫，讓 run_daily_scan 可以正常啟動
    dummy_results = [
        {
            "id": "A01",
            "hypothesis_id": "A01_DUMMY",
            "win_rate": 0.6,
            "sharpe": 1.5,
            "trades": 100
        }
    ]
    
    output = "results/signals/library.enc"
    save_signal(dummy_results, output, password)
