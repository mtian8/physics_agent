from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .task_graph import graph_to_yaml

SECTION_TITLES = [
    "Header",
    "Problem spec",
    "Current best answer",
    "Task Graph (machine-readable)",
    "Task Board (human-readable)",
    "Results ledger",
    "Evidence / citations ledger",
    "Verifier status",
    "History log",
]
SECTION_BOUNDARY_PATTERN = "|".join(re.escape(title) for title in SECTION_TITLES)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _choose_fence(text: str, char: str = "`", min_len: int = 3) -> str:
    length = max(3, min_len)
    while (char * length) in text:
        length += 1
    return char * length


def render_task_board(graph: dict[str, Any]) -> str:
    lines: list[str] = []
    for stage in graph.get("stages", []):
        lines.append(f"### Stage {stage.get('id')}: {stage.get('name')}")
        for task in stage.get("tasks", []):
            status = task.get("status", "todo")
            box = "x" if status in {"done", "skipped"} else " "
            lines.append(
                f"- [{box}] {task.get('id')} {task.get('title')} ({status})"
            )
        lines.append("")
    return "\n".join(lines).strip()


def _render_task_result_block(
    task_id: str,
    title: str,
    status: str,
    summary: str,
    artifacts: list[str] | None,
    evidence: list[str] | None,
    issues: list[str] | None,
) -> str:
    artifacts = artifacts or []
    evidence = evidence or []
    issues = issues or []
    lines = [
        f"### {task_id} {title}",
        f"- status: {status}",
        f"- summary: {summary}",
        "- artifacts:",
    ]
    if artifacts:
        lines.extend([f"  - {name}" for name in artifacts])
    else:
        lines.append("  - _none_")
    lines.append("- evidence:")
    if evidence:
        lines.extend([f"  - {item}" for item in evidence])
    else:
        lines.append("  - _none_")
    if issues:
        lines.append("- issues:")
        lines.extend([f"  - {item}" for item in issues])
    return "\n".join(lines)


def render_results_ledger(graph: dict[str, Any]) -> str:
    blocks: list[str] = []
    for stage in graph.get("stages", []):
        for task in stage.get("tasks", []):
            blocks.append(
                _render_task_result_block(
                    task.get("id"),
                    task.get("title"),
                    task.get("status", "todo"),
                    "_pending_",
                    [],
                    [],
                    [],
                )
            )
    return "\n\n".join(blocks).strip()


def _render_evidence_block(task_id: str, entries: list[str]) -> str:
    lines = [f"### {task_id}", "- evidence:"]
    if entries:
        lines.extend([f"  - {entry}" for entry in entries])
    else:
        lines.append("  - _none_")
    return "\n".join(lines)


def render_evidence_ledger(graph: dict[str, Any]) -> str:
    blocks: list[str] = []
    for stage in graph.get("stages", []):
        for task in stage.get("tasks", []):
            blocks.append(_render_evidence_block(task.get("id"), []))
    return "\n\n".join(blocks).strip()


def render_state_doc(
    run_id: str,
    question: str,
    problem_spec_text: str,
    config_snapshot: str,
    task_graph: dict[str, Any],
) -> str:
    created = _now_iso()
    task_graph_yaml = graph_to_yaml(task_graph)
    question_text = question.rstrip("\n") or "_TBD_"
    question_lines = question_text.splitlines()
    question_fence = _choose_fence(question_text, "`")
    header_lines = [
        f"- run_id: {run_id}",
        f"- created_at: {created}",
        f"- last_updated: {created}",
        "- question:",
        f"  {question_fence}md",
        *[f"  {line}" for line in question_lines],
        f"  {question_fence}",
        "- config_snapshot:",
        "```yaml",
        config_snapshot,
        "```",
    ]
    sections = [
        f"## {SECTION_TITLES[0]}\n" + "\n".join(header_lines),
        f"## {SECTION_TITLES[1]}\n{problem_spec_text.strip()}",
        f"## {SECTION_TITLES[2]}\n_TBD_",
        f"## {SECTION_TITLES[3]}\n```yaml\n{task_graph_yaml}\n```",
        f"## {SECTION_TITLES[4]}\n{render_task_board(task_graph)}",
        f"## {SECTION_TITLES[5]}\n{render_results_ledger(task_graph)}",
        f"## {SECTION_TITLES[6]}\n{render_evidence_ledger(task_graph)}",
        f"## {SECTION_TITLES[7]}\n- stage_verifier: not_run\n- final_verifier: not_run",
        f"## {SECTION_TITLES[8]}\n- {created}: init run",
    ]
    return "# Research State Doc\n\n" + "\n\n".join(sections) + "\n"


def load_state_doc(path: str | Path) -> str:
    return Path(path).read_text()


def write_state_doc(path: str | Path, content: str) -> None:
    Path(path).write_text(content)


def extract_section(text: str, title: str) -> str:
    pattern = rf"^## {re.escape(title)}\n(.*?)(?=^## (?:{SECTION_BOUNDARY_PATTERN})\n|\Z)"
    match = re.search(pattern, text, re.S | re.M)
    if not match:
        raise ValueError(f"Section not found: {title}")
    return match.group(1).strip()


def replace_section(text: str, title: str, new_body: str) -> str:
    pattern = rf"(^## {re.escape(title)}\n)(.*?)(?=^## (?:{SECTION_BOUNDARY_PATTERN})\n|\Z)"
    match = re.search(pattern, text, re.S | re.M)
    if not match:
        raise ValueError(f"Section not found: {title}")
    start = match.group(1)
    return text[: match.start(1)] + start + new_body.strip() + "\n\n" + text[match.end(2) :]


def update_current_best_answer(text: str, answer: str) -> str:
    return replace_section(text, "Current best answer", answer.strip())


def extract_header_field(text: str, field: str) -> str | None:
    header = extract_section(text, "Header")
    lines = header.splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith(f"- {field}:"):
            continue
        value = line.split(":", 1)[1].strip()
        if value:
            return value
        if idx + 1 >= len(lines):
            return ""
        fence_line = lines[idx + 1].strip()
        fence_match = re.match(r"^(`{3,})", fence_line)
        if not fence_match:
            return ""
        fence = fence_match.group(1)
        captured: list[str] = []
        for subline in lines[idx + 2 :]:
            if subline.strip() == fence:
                break
            captured.append(subline[2:] if subline.startswith("  ") else subline)
        return "\n".join(captured).strip()
    return None


def extract_task_graph_yaml(text: str) -> str:
    section = extract_section(text, "Task Graph (machine-readable)")
    match = re.search(r"```yaml\n(.*?)\n```", section, re.S)
    if not match:
        raise ValueError("Task graph YAML block not found.")
    return match.group(1).strip()


def extract_latest_human_review_awaitable(text: str) -> str | None:
    history = extract_section(text, "History log")
    last: str | None = None
    for line in history.splitlines():
        match = re.search(r"awaiting human review: (\S+)", line)
        if match:
            last = match.group(1)
    return last


def update_task_graph(text: str, task_graph: dict[str, Any]) -> str:
    task_graph_yaml = graph_to_yaml(task_graph)
    new_body = f"```yaml\n{task_graph_yaml}\n```"
    return replace_section(text, "Task Graph (machine-readable)", new_body)


def update_task_board(text: str, task_graph: dict[str, Any]) -> str:
    board = render_task_board(task_graph)
    return replace_section(text, "Task Board (human-readable)", board)


def _replace_subsection(body: str, header: str, new_block: str) -> str:
    pattern = rf"^### {re.escape(header)}.*?(?=^### |\Z)"
    match = re.search(pattern, body, re.S | re.M)
    if match:
        return body[: match.start()] + new_block + "\n\n" + body[match.end() :]
    return body.rstrip() + "\n\n" + new_block + "\n"


def update_results_ledger(
    text: str,
    task_id: str,
    title: str,
    status: str,
    summary: str,
    artifacts: list[str],
    evidence: list[str],
    issues: list[str] | None = None,
) -> str:
    ledger = extract_section(text, "Results ledger")
    block = _render_task_result_block(
        task_id, title, status, summary, artifacts, evidence, issues
    )
    updated = _replace_subsection(ledger, task_id, block)
    return replace_section(text, "Results ledger", updated.strip())


def update_evidence_ledger(
    text: str, task_id: str, entries: list[str]
) -> str:
    ledger = extract_section(text, "Evidence / citations ledger")
    block = _render_evidence_block(task_id, entries)
    updated = _replace_subsection(ledger, task_id, block)
    return replace_section(text, "Evidence / citations ledger", updated.strip())


def update_verifier_status(
    text: str,
    stage_id: int | None,
    verdict: str,
    issues: list[str],
    final_verdict: str | None = None,
) -> str:
    lines = []
    if stage_id is not None:
        lines.append(f"- stage_verifier: {verdict} (stage {stage_id})")
    else:
        lines.append("- stage_verifier: not_run")
    if final_verdict:
        lines.append(f"- final_verifier: {final_verdict}")
    else:
        lines.append("- final_verifier: not_run")
    if issues:
        lines.append("")
        lines.append("### Issues")
        lines.extend([f"- {issue}" for issue in issues])
    return replace_section(text, "Verifier status", "\n".join(lines))


def update_final_verifier(text: str, final_verdict: str) -> str:
    verifier = extract_section(text, "Verifier status")
    lines = verifier.splitlines()
    updated = []
    found = False
    for line in lines:
        if line.startswith("- final_verifier:"):
            updated.append(f"- final_verifier: {final_verdict}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(f"- final_verifier: {final_verdict}")
    return replace_section(text, "Verifier status", "\n".join(updated).strip())


def render_final_output(question: str, summary: str, final_report: str) -> str:
    return (
        "# Final Output\n\n"
        "## Question\n"
        f"{question.strip()}\n\n"
        "## Summary\n"
        f"{summary.strip()}\n\n"
        "## Final Result\n"
        f"{final_report.strip()}\n"
    )


def append_history(text: str, entry: str) -> str:
    history = extract_section(text, "History log")
    updated = history.rstrip() + f"\n- {_now_iso()}: {entry}"
    return replace_section(text, "History log", updated.strip())


def touch_last_updated(text: str) -> str:
    header = extract_section(text, "Header")
    lines = header.splitlines()
    updated_lines = []
    for line in lines:
        if line.startswith("- last_updated:"):
            updated_lines.append(f"- last_updated: {_now_iso()}")
        else:
            updated_lines.append(line)
    return replace_section(text, "Header", "\n".join(updated_lines).strip())
