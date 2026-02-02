from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def load_config(path: str | Path, *, resolve_env: bool = True) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping.")
    return resolve_env_values(data) if resolve_env else data


def snapshot_config(config: dict[str, Any]) -> str:
    return yaml.safe_dump(config, sort_keys=False).strip()


def save_config(path: str | Path, config: dict[str, Any]) -> None:
    config_path = Path(path)
    config_path.write_text(snapshot_config(config) + "\n")


def resolve_env_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: resolve_env_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_env_values(item) for item in value]
    if isinstance(value, str):
        match = ENV_PATTERN.match(value.strip())
        if match:
            env_key = match.group(1)
            env_value = os.getenv(env_key)
            if env_value is None:
                raise ValueError(f"Missing required env var: {env_key}")
            return env_value
    return value
