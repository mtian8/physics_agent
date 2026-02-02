from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def artifacts_root() -> Path:
    return repo_root() / "artifacts"


def runs_root() -> Path:
    return artifacts_root() / "runs"


def papers_root() -> Path:
    return artifacts_root() / "papers"


def run_dir(run_id: str) -> Path:
    return runs_root() / run_id


def run_outputs_dir(run_id: str) -> Path:
    return run_dir(run_id) / "agent_outputs"


def db_path() -> Path:
    return repo_root() / "db" / "metadata.sqlite"
