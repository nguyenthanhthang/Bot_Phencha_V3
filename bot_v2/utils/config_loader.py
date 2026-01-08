from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


class ConfigError(RuntimeError):
    pass


def load_yaml(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p.resolve()}")

    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigError(f"Failed to parse YAML: {p.resolve()} -> {e}") from e

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"YAML root must be a dict: {p.resolve()}")

    return data


def get_nested(d: Dict[str, Any], keys: str, default: Any = None) -> Any:
    """
    keys format: "a.b.c"
    """
    cur: Any = d
    for k in keys.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

