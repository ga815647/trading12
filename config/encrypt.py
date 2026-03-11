from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _key() -> bytes:
    raw = os.getenv("ENCRYPT_PASSWORD", "").encode("utf-8")
    if not raw:
        raise ValueError("ENCRYPT_PASSWORD is required for encrypted output.")
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())


def save_encrypted_json(data: Any, path: str | Path) -> Path:
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("cryptography package is not installed.") from exc
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    target.write_bytes(Fernet(_key()).encrypt(payload))
    return target


def load_encrypted_json(path: str | Path) -> Any:
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("cryptography package is not installed.") from exc
    payload = Path(path).read_bytes()
    return json.loads(Fernet(_key()).decrypt(payload))


def save_signal(data: Any, path: str | Path = "results/signals/library.enc") -> Path:
    return save_encrypted_json(data, path)


def load_signals(path: str | Path = "results/signals/library.enc") -> Any:
    return load_encrypted_json(path)
