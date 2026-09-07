from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_raw(target: Path, data: bytes, meta: dict) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    checksum = sha256_bytes(data)
    sidecar = target.with_suffix(target.suffix + ".meta.json")
    payload = {"sha256": checksum, **meta}
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return checksum
