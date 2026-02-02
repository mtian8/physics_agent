from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import TaskResult
from .paths import run_dir, run_outputs_dir
from .state_doc import (
    append_history,
    extract_header_field,
    extract_section,
    extract_task_graph_yaml,
    load_state_doc,
    render_final_output,
    touch_last_updated,
    update_current_best_answer,
    update_evidence_ledger,
    update_results_ledger,
    update_task_board,
    update_task_graph,
    write_state_doc,
)
from .task_graph import find_task, set_task_status, validate_task_graph, yaml_to_graph


def _task_result_from_output(run_id: str, task_id: str) -> TaskResult | None:
    output_path = run_outputs_dir(run_id) / f"{task_id}.json"
    if not output_path.exists():
        return None
    return TaskResult.model_validate_json(output_path.read_text())


def _write_task_artifacts(run_id: str, output: TaskResult, artifacts: list[str]) -> None:
    run_path = run_dir(run_id)
    for name in artifacts:
        if name in output.artifacts:
            (run_path / name).write_text(output.artifacts[name])


def _evidence_lines(output: TaskResult) -> list[str]:
    lines: list[str] = []
    for item in output.evidence:
        note = item.note or ""
        location = item.location or ""
        lines.append(f"{item.source_id} | {location} | {note}".strip(" |"))
    return lines


def refresh_final_output(run_id: str) -> None:
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    state_doc = load_state_doc(state_doc_path)
    question = extract_header_field(state_doc, "question") or "_unknown_"
    summary = extract_section(state_doc, "Current best answer")
    final_report_path = run_dir(run_id) / "final_report.md"
    final_report = final_report_path.read_text() if final_report_path.exists() else summary
    output_text = render_final_output(question, summary, final_report)
    (run_dir(run_id) / "final_output.md").write_text(output_text)


def record_human_review_awaitable(run_id: str, awaitable_id: str) -> None:
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    state_doc = load_state_doc(state_doc_path)
    state_doc = append_history(state_doc, f"awaiting human review: {awaitable_id}")
    state_doc = touch_last_updated(state_doc)
    write_state_doc(state_doc_path, state_doc)


def list_review_queue(run_id: str) -> list[dict[str, Any]]:
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    state_doc = load_state_doc(state_doc_path)
    graph = yaml_to_graph(extract_task_graph_yaml(state_doc))
    validate_task_graph(graph)
    items: list[dict[str, Any]] = []
    for stage in graph.get("stages", []):
        for task in stage.get("tasks", []):
            if task.get("status") == "blocked" and task.get("blocked_reason") == "awaiting_human_review":
                items.append(
                    {
                        "task_id": task.get("id"),
                        "title": task.get("title"),
                        "agent": task.get("agent"),
                        "blocked_reason": task.get("blocked_reason"),
                    }
                )
    return items


def _existing_task_issues(state_doc: str, task_id: str) -> list[str]:
    ledger = extract_section(state_doc, "Results ledger")
    block_match = re.search(
        rf"^### {re.escape(task_id)}\\b.*?(?=^### |\\Z)",
        ledger,
        re.S | re.M,
    )
    if not block_match:
        return []
    block = block_match.group(0)
    issues_match = re.search(r"^- issues:\n((?:  - .*\n?)*)", block, re.M)
    if not issues_match:
        return []
    issues: list[str] = []
    for line in issues_match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            issues.append(stripped[2:].strip())
    return issues


def approve_task(run_id: str, task_id: str) -> None:
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    state_doc = load_state_doc(state_doc_path)
    graph = yaml_to_graph(extract_task_graph_yaml(state_doc))
    validate_task_graph(graph)
    task = find_task(graph, task_id)
    if task is None:
        raise ValueError(f"Unknown task id: {task_id}")
    issues = _existing_task_issues(state_doc, task_id)

    output = _task_result_from_output(run_id, task_id)
    summary = output.summary if output else "_approved_"
    artifacts = list(output.artifacts.keys()) if output else []
    evidence = _evidence_lines(output) if output else []
    if output:
        _write_task_artifacts(run_id, output, artifacts)

    set_task_status(graph, task_id, "done")
    state_doc = update_task_graph(state_doc, graph)
    state_doc = update_task_board(state_doc, graph)
    state_doc = update_results_ledger(
        state_doc,
        task_id,
        task.get("title"),
        "done",
        summary,
        artifacts,
        evidence,
        issues or None,
    )
    state_doc = update_evidence_ledger(state_doc, task_id, evidence)
    state_doc = append_history(state_doc, f"{task_id} approved")
    state_doc = touch_last_updated(state_doc)
    write_state_doc(state_doc_path, state_doc)
    refresh_final_output(run_id)


def modify_task(
    run_id: str,
    task_id: str,
    summary: str | None = None,
    artifacts: dict[str, str] | None = None,
    evidence: list[str] | None = None,
) -> None:
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    state_doc = load_state_doc(state_doc_path)
    graph = yaml_to_graph(extract_task_graph_yaml(state_doc))
    validate_task_graph(graph)
    task = find_task(graph, task_id)
    if task is None:
        raise ValueError(f"Unknown task id: {task_id}")
    issues = _existing_task_issues(state_doc, task_id)

    output = _task_result_from_output(run_id, task_id)
    resolved_summary = summary or (output.summary if output else "_modified_by_human_")

    artifact_map = artifacts or {}
    if output:
        artifact_map = {**output.artifacts, **artifact_map}

    for name, content in artifact_map.items():
        (run_dir(run_id) / name).write_text(content)

    resolved_evidence = evidence or (_evidence_lines(output) if output else [])

    set_task_status(graph, task_id, "done")
    state_doc = update_task_graph(state_doc, graph)
    state_doc = update_task_board(state_doc, graph)
    state_doc = update_results_ledger(
        state_doc,
        task_id,
        task.get("title"),
        "done",
        resolved_summary,
        list(artifact_map.keys()),
        resolved_evidence,
        issues or None,
    )
    state_doc = update_evidence_ledger(state_doc, task_id, resolved_evidence)
    if "final_report.md" in artifact_map:
        state_doc = update_current_best_answer(state_doc, artifact_map["final_report.md"])
    state_doc = append_history(state_doc, f"{task_id} modified")
    state_doc = touch_last_updated(state_doc)
    write_state_doc(state_doc_path, state_doc)
    refresh_final_output(run_id)
