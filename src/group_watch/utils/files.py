"""Small shared filesystem primitives used by business services."""
import json
import os
from pathlib import Path
import uuid


def atomic_write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + '.' + uuid.uuid4().hex + '.part')
    try:
        part.write_bytes(raw)
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))
