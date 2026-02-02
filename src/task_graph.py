from __future__ import annotations

from typing import Any

import yaml

VALID_STATUSES = {
    "todo",
    "running",
    "done",
    "blocked",
    "skipped",
    "superseded",
}


def default_task_graph() -> dict[str, Any]:
    return {
        "version": 2,
        "stages": [
            {
                "id": 1,
                "name": "Literature + definitions",
                "verifier": {
                    "agent": "verifier",
                    "criteria": ["citations_present", "notation_defined"],
                },
                "tasks": [
                    {
                        "id": "1.1",
                        "title": "Search + rank candidate papers",
                        "agent": "literature_scout",
                        "status": "todo",
                        "depends_on": [],
                        "parallel_group": "search",
                        "acceptance_criteria": [
                            "paper_candidates_written",
                            "citations_present",
                        ],
                        "inputs": {"query_hints": []},
                        "outputs": [{"artifacts": ["paper_candidates.json"]}],
                    },
                    {
                        "id": "1.2",
                        "title": "Extract definitions + assumptions from paper pool",
                        "agent": "paper_reader",
                        "status": "todo",
                        "depends_on": ["1.1"],
                        "parallel_group": "extraction",
                        "acceptance_criteria": [
                            "notation_defined",
                            "assumptions_listed",
                            "citations_present",
                        ],
                        "inputs": {"focus": "definitions + assumptions"},
                        "outputs": [
                            {
                                "artifacts": [
                                    "equation_bank.md",
                                    "assumptions.md",
                                    "extractions.json",
                                ]
                            }
                        ],
                    },
                ],
            },
            {
                "id": 2,
                "name": "Derivation + computational checks",
                "verifier": {
                    "agent": "verifier",
                    "criteria": ["dimensions_ok", "limit_cases_ok"],
                },
                "tasks": [
                    {
                        "id": "2.1",
                        "title": "Main derivation + executable checks",
                        "agent": "derivation_coder",
                        "status": "todo",
                        "depends_on": [],
                        "parallel_group": "derivation",
                        "acceptance_criteria": [
                            "derivation_written",
                            "checks_runnable",
                            "dimensions_ok",
                            "limit_cases_ok",
                        ],
                        "inputs": {"target": "main derivation"},
                        "outputs": [{"artifacts": ["derivation.md", "checks.py"]}],
                    }
                ],
            },
            {
                "id": 3,
                "name": "Synthesis",
                "verifier": {
                    "agent": "verifier",
                    "criteria": ["final_report_complete"],
                },
                "tasks": [
                    {
                        "id": "3.1",
                        "title": "Assemble final report",
                        "agent": "orchestrator",
                        "status": "todo",
                        "depends_on": [],
                        "parallel_group": "synthesis",
                        "acceptance_criteria": ["final_report_complete"],
                        "inputs": {
                            "include": [
                                "equation_bank",
                                "derivation",
                                "verifier_summary",
                            ]
                        },
                        "outputs": [{"artifacts": ["final_report.md"]}],
                    }
                ],
            },
        ],
    }


def validate_task_graph(graph: dict[str, Any]) -> None:
    if graph.get("version") != 2:
        raise ValueError("Task graph version must be 2.")
    stages = graph.get("stages", [])
    if not isinstance(stages, list) or not stages:
        raise ValueError("Task graph must include stages.")
    task_ids: set[str] = set()
    for stage in stages:
        if "id" not in stage or "tasks" not in stage:
            raise ValueError("Each stage must include id and tasks.")
        for task in stage.get("tasks", []):
            tid = task.get("id")
            if not tid:
                raise ValueError("Task missing id.")
            if tid in task_ids:
                raise ValueError(f"Duplicate task id: {tid}")
            task_ids.add(tid)
            status = task.get("status")
            if status not in VALID_STATUSES:
                raise ValueError(f"Invalid status {status} for task {tid}")
            if status == "blocked" and not task.get("blocked_reason"):
                raise ValueError(f"blocked_reason is required for blocked task {tid}")
            if status == "skipped" and not task.get("skip_reason"):
                raise ValueError(f"skip_reason is required for skipped task {tid}")
            depends_on = task.get("depends_on", [])
            if not isinstance(depends_on, list):
                raise ValueError(f"depends_on must be list for task {tid}")
    for stage in stages:
        for task in stage.get("tasks", []):
            for dep in task.get("depends_on", []):
                if dep not in task_ids:
                    raise ValueError(f"Task {task['id']} depends on unknown {dep}")


def iter_tasks(graph: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for stage in graph.get("stages", []):
        tasks.extend(stage.get("tasks", []))
    return tasks


def find_task(graph: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in iter_tasks(graph):
        if task.get("id") == task_id:
            return task
    return None


def stage_for_task(graph: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for stage in graph.get("stages", []):
        for task in stage.get("tasks", []):
            if task.get("id") == task_id:
                return stage
    return None


def current_stage(graph: dict[str, Any]) -> dict[str, Any] | None:
    for stage in graph.get("stages", []):
        tasks = stage.get("tasks", [])
        if any(task.get("status") not in {"done", "skipped"} for task in tasks):
            return stage
    return None


def dependencies_satisfied(graph: dict[str, Any], task: dict[str, Any]) -> bool:
    for dep in task.get("depends_on", []):
        dep_task = find_task(graph, dep)
        if dep_task is None:
            return False
        if dep_task.get("status") not in {"done", "skipped"}:
            return False
    return True


def runnable_tasks(graph: dict[str, Any], stage: dict[str, Any]) -> list[dict[str, Any]]:
    runnable: list[dict[str, Any]] = []
    for task in stage.get("tasks", []):
        if task.get("status") == "todo" and dependencies_satisfied(graph, task):
            runnable.append(task)
    return runnable


def set_task_status(
    graph: dict[str, Any], task_id: str, status: str, **kwargs: Any
) -> None:
    task = find_task(graph, task_id)
    if task is None:
        raise ValueError(f"Unknown task id: {task_id}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    task["status"] = status
    for key, value in kwargs.items():
        task[key] = value


def stage_complete(stage: dict[str, Any]) -> bool:
    return all(task.get("status") in {"done", "skipped"} for task in stage.get("tasks", []))


def next_subtask_index(stage: dict[str, Any]) -> int:
    max_idx = 0
    for task in stage.get("tasks", []):
        task_id = str(task.get("id", ""))
        if "." in task_id:
            _, sub = task_id.split(".", 1)
            try:
                max_idx = max(max_idx, int(sub))
            except ValueError:
                continue
    return max_idx + 1


def add_followup_tasks(
    stage: dict[str, Any],
    follow_ups: list[str],
    agent: str,
) -> list[dict[str, Any]]:
    existing = {
        task.get("inputs", {}).get("instruction")
        for task in stage.get("tasks", [])
    }
    created: list[dict[str, Any]] = []
    sub_idx = next_subtask_index(stage)
    for follow_up in follow_ups:
        if not follow_up or follow_up in existing:
            continue
        task_id = f"{stage.get('id')}.{sub_idx}"
        sub_idx += 1
        title = follow_up.strip()
        if len(title) > 80:
            title = title[:77] + "..."
        task = {
            "id": task_id,
            "title": f"Follow-up: {title}",
            "agent": agent,
            "status": "todo",
            "depends_on": [],
            "parallel_group": "follow_up",
            "acceptance_criteria": ["follow_up_resolved"],
            "inputs": {"instruction": follow_up},
            "outputs": [{"artifacts": []}],
        }
        stage.setdefault("tasks", []).append(task)
        created.append(task)
    return created


def graph_to_yaml(graph: dict[str, Any]) -> str:
    body = yaml.safe_dump(graph, sort_keys=False).strip()
    return f"# TASK_GRAPH_V2\n{body}"


def yaml_to_graph(yaml_text: str) -> dict[str, Any]:
    payload = yaml.safe_load(yaml_text)
    if not isinstance(payload, dict):
        raise ValueError("Task graph YAML must be a mapping.")
    return payload
