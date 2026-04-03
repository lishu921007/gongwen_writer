from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / 'config'


@lru_cache(maxsize=32)
def load_json_config(name: str) -> Dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))
