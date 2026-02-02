from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import run_dir
from .state_doc import extract_section


def _truncate(text: str, max_lines: int = 200) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text.strip()
    return "\n".join(lines[:max_lines]).strip() + "\n... (truncated)"


def _paper_pool_summary(run_id: str) -> str:
    candidates = run_dir(run_id) / "paper_candidates.json"
    if not candidates.exists():
        return "_none_"
    try:
        data = json.loads(candidates.read_text())
    except json.JSONDecodeError:
        return "_invalid_json_"
    if isinstance(data, dict) and "papers" in data:
        papers = data.get("papers", [])
    else:
        papers = data if isinstance(data, list) else []
    lines = []
    for item in papers[:5]:
        if isinstance(item, dict):
            title = item.get("title") or "untitled"
            year = item.get("year") or "unknown year"
            lines.append(f"- {title} ({year})")
    return "\n".join(lines) if lines else "_none_"


def _read_top_lines(path: Path, max_lines: int = 10) -> str:
    if not path.exists():
        return "_none_"
    lines = [line.rstrip() for line in path.read_text().splitlines() if line.strip()]
    if not lines:
        return "_none_"
    return "\n".join(lines[:max_lines])


def build_context_pack(
    run_id: str, state_doc_text: str, stage: dict[str, Any]
) -> str:
    problem_spec = extract_section(state_doc_text, "Problem spec")
    best_answer = extract_section(state_doc_text, "Current best answer")
    verifier = extract_section(state_doc_text, "Verifier status")
    lines = [
        "# Context Pack",
        "## Goal + constraints",
        _truncate(problem_spec, 120),
        "## Current stage",
        f"Stage {stage.get('id')}: {stage.get('name')}",
    ]
    for task in stage.get("tasks", []):
        lines.append(f"- {task.get('id')} {task.get('title')} ({task.get('status')})")
    lines += [
        "",
        "## Current best answer",
        _truncate(best_answer, 120),
        "## Key equations",
        _read_top_lines(run_dir(run_id) / "equation_bank.md", 10),
        "## Key assumptions",
        _read_top_lines(run_dir(run_id) / "assumptions.md", 10),
        "## Verifier status",
        _truncate(verifier, 40),
        "## Paper pool summary",
        _paper_pool_summary(run_id),
    ]
    return "\n".join(lines).strip() + "\n"


def write_context_pack(run_id: str, content: str) -> Path:
    path = run_dir(run_id) / "context_pack.md"
    path.write_text(content)
    return path
