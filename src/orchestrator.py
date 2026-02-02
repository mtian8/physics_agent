from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Type

from agents import Runner

from .agents import build_agents
from .config import load_config, snapshot_config
from .context_pack import build_context_pack, write_context_pack
from .models import TaskResult, VerifierResult
from .paths import db_path as metadata_db_path
from .paths import run_dir, run_outputs_dir
from .state_doc import (
    append_history,
    extract_section,
    extract_task_graph_yaml,
    extract_header_field,
    load_state_doc,
    render_state_doc,
    render_final_output,
    touch_last_updated,
    update_current_best_answer,
    update_evidence_ledger,
    update_final_verifier,
    update_results_ledger,
    update_task_board,
    update_task_graph,
    update_verifier_status,
    write_state_doc,
)
from .storage import record_run
from .task_graph import (
    add_followup_tasks,
    current_stage,
    default_task_graph,
    runnable_tasks,
    set_task_status,
    stage_complete,
    validate_task_graph,
    yaml_to_graph,
)
from .tools_ingest import ingest_docs

@dataclass
class StepOutcome:
    run_id: str
    stage_id: int | None
    tasks_run: list[str]
    verifier_verdict: str | None
    stop_reason: str | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = random.randint(1000, 9999)
    return f"run_{stamp}_{suffix}"


def _ensure_run_dirs(run_id: str) -> None:
    run_dir(run_id).mkdir(parents=True, exist_ok=True)
    run_outputs_dir(run_id).mkdir(parents=True, exist_ok=True)


def init_run(
    question: str,
    problem_spec_path: str,
    config_path: str,
    docs: list[str] | None = None,
    run_id: str | None = None,
) -> str:
    config_raw = load_config(config_path, resolve_env=False)
    config = load_config(config_path, resolve_env=True)
    run_id = run_id or _generate_run_id()
    _ensure_run_dirs(run_id)
    problem_spec_text = Path(problem_spec_path).read_text()
    task_graph = default_task_graph()
    state_doc = render_state_doc(
        run_id=run_id,
        question=question,
        problem_spec_text=problem_spec_text,
        config_snapshot=snapshot_config(config_raw),
        task_graph=task_graph,
    )
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    write_state_doc(state_doc_path, state_doc)
    record_run(metadata_db_path(), run_id, question, _now_iso())
    if docs:
        ingest_docs(run_id, docs, config=config)
        updated = append_history(state_doc, f"ingested {len(docs)} docs")
        write_state_doc(state_doc_path, updated)
    return run_id


async def _run_task(
    runner: Type[Runner],
    agent,
    task: dict[str, Any],
    run_id: str,
    context_pack: str,
) -> TaskResult:
    input_payload = {
        "task_id": task.get("id"),
        "task_title": task.get("title"),
        "acceptance_criteria": task.get("acceptance_criteria", []),
        "inputs": task.get("inputs", {}),
        "context_pack": context_pack,
        "run_id": run_id,
    }
    result = await runner.run(agent, input_payload)
    return result.final_output_as(TaskResult)


def _write_task_artifacts(run_id: str, output: TaskResult, task: dict[str, Any]) -> list[str]:
    written: list[str] = []
    outputs = task.get("outputs", [])
    output_names: set[str] = set()
    for entry in outputs:
        for name in entry.get("artifacts", []):
            output_names.add(name)
    for name in output_names:
        if name in output.artifacts:
            dest = run_dir(run_id) / name
            dest.write_text(output.artifacts[name])
            written.append(name)
    return written


def _evidence_lines(output: TaskResult) -> list[str]:
    lines: list[str] = []
    for item in output.evidence:
        note = item.note or ""
        location = item.location or ""
        lines.append(f"{item.source_id} | {location} | {note}".strip(" |"))
    return lines


def _truncate_text(text: str, max_lines: int = 120, max_chars: int = 6000) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["... (truncated)"]
    truncated = "\n".join(lines)
    if len(truncated) > max_chars:
        truncated = truncated[:max_chars] + "\n... (truncated)"
    return truncated


def _review_policy(task: dict[str, Any], config: dict[str, Any]) -> str:
    review_cfg = config.get("review", {})
    per_task = review_cfg.get("per_task", {})
    per_agent = review_cfg.get("per_agent", {})
    default_policy = review_cfg.get("default", "auto")
    task_id = task.get("id")
    agent_key = task.get("agent")
    if task_id in per_task:
        return per_task[task_id]
    if agent_key in per_agent:
        return per_agent[agent_key]
    return default_policy


def _task_verification_policy(task: dict[str, Any], config: dict[str, Any]) -> str:
    verify_cfg = config.get("task_verification", {})
    per_task = verify_cfg.get("per_task", {})
    per_agent = verify_cfg.get("per_agent", {})
    default_policy = verify_cfg.get("default", "none")
    task_id = task.get("id")
    agent_key = task.get("agent")
    if task_id in per_task:
        return per_task[task_id]
    if agent_key in per_agent:
        return per_agent[agent_key]
    return default_policy


def _write_prompt_patches(run_id: str, task_id: str, output: TaskResult) -> list[str]:
    prompt_dir = run_dir(run_id) / "prompt_patches"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, content in output.artifacts.items():
        if name.startswith("prompt_patch"):
            dest_name = f"{task_id}_{name}"
            dest = prompt_dir / dest_name
            dest.write_text(content)
            written.append(dest_name)
    return written


async def _run_task_verifier(
    runner: Type[Runner],
    verifier_agent,
    task: dict[str, Any],
    output: TaskResult,
    run_id: str,
    context_pack: str,
) -> VerifierResult:
    output_names: set[str] = set()
    for entry in task.get("outputs", []):
        for name in entry.get("artifacts", []):
            output_names.add(name)
    relevant_artifacts = {
        name: _truncate_text(output.artifacts.get(name, ""))
        for name in sorted(output_names)
        if name in output.artifacts
    }
    payload = {
        "task_id": task.get("id"),
        "task_title": task.get("title"),
        "task_agent": task.get("agent"),
        "acceptance_criteria": task.get("acceptance_criteria", []),
        "task_output": {
            "summary": output.summary,
            "artifacts": relevant_artifacts,
            "evidence": _evidence_lines(output),
            "follow_ups": output.follow_ups,
            "metrics": output.metrics,
        },
        "context_pack": context_pack,
        "run_id": run_id,
    }
    result = await runner.run(verifier_agent, payload)
    return result.final_output_as(VerifierResult)


def _write_final_output(run_id: str, state_doc_text: str) -> None:
    question = extract_header_field(state_doc_text, "question") or "_unknown_"
    summary = extract_section(state_doc_text, "Current best answer")
    final_report_path = run_dir(run_id) / "final_report.md"
    if final_report_path.exists():
        final_report = final_report_path.read_text()
    else:
        final_report = summary
    output_text = render_final_output(question, summary, final_report)
    (run_dir(run_id) / "final_output.md").write_text(output_text)


def _write_verifier_prompt_patch(
    run_id: str, label: str, output: VerifierResult
) -> str | None:
    if not output.prompt_patch:
        return None
    prompt_dir = run_dir(run_id) / "prompt_patches"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    dest = prompt_dir / f"{label}_prompt_patch.md"
    dest.write_text(output.prompt_patch)
    return dest.name


def _default_agent_for_stage(stage_id: int | None) -> str:
    if stage_id == 1:
        return "paper_reader"
    if stage_id == 2:
        return "derivation_coder"
    if stage_id == 3:
        return "orchestrator"
    return "orchestrator"


def _add_followup_placeholders(
    doc_text: str, tasks: list[dict[str, Any]]
) -> str:
    updated = doc_text
    for task in tasks:
        updated = update_results_ledger(
            updated,
            task.get("id"),
            task.get("title"),
            "todo",
            "_pending_",
            [],
            [],
        )
        updated = update_evidence_ledger(updated, task.get("id"), [])
    return updated


async def _run_stage_verifier(
    runner: Type[Runner],
    verifier_agent,
    stage: dict[str, Any],
    run_id: str,
    context_pack: str,
) -> VerifierResult:
    task_summaries = {
        task.get("id"): {
            "title": task.get("title"),
            "status": task.get("status"),
        }
        for task in stage.get("tasks", [])
    }
    payload = {
        "stage_id": stage.get("id"),
        "stage_name": stage.get("name"),
        "criteria": stage.get("verifier", {}).get("criteria", []),
        "tasks": task_summaries,
        "context_pack": context_pack,
        "run_id": run_id,
    }
    result = await runner.run(verifier_agent, payload)
    return result.final_output_as(VerifierResult)


async def run_step(
    run_id: str,
    config_path: str,
    runner: Type[Runner] = Runner,
) -> StepOutcome:
    config = load_config(config_path)
    prompts_dir = Path("prompts")
    agents = build_agents(config, prompts_dir)
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    state_doc_text = load_state_doc(state_doc_path)

    task_graph_yaml = extract_task_graph_yaml(state_doc_text)
    graph = yaml_to_graph(task_graph_yaml)
    validate_task_graph(graph)

    stage = current_stage(graph)
    if stage is None:
        return StepOutcome(run_id, None, [], None, "complete")

    if any(
        task.get("status") == "blocked"
        and task.get("blocked_reason") == "awaiting_human_review"
        for task in stage.get("tasks", [])
    ):
        return StepOutcome(run_id, stage.get("id"), [], None, "awaiting_human_review")

    context_pack = build_context_pack(run_id, state_doc_text, stage)
    write_context_pack(run_id, context_pack)

    runnable = runnable_tasks(graph, stage)
    if not runnable:
        return StepOutcome(run_id, stage.get("id"), [], None, "no_runnable_tasks")

    for task in runnable:
        set_task_status(graph, task.get("id"), "running")
    updated_doc = update_task_graph(state_doc_text, graph)
    updated_doc = update_task_board(updated_doc, graph)
    updated_doc = touch_last_updated(updated_doc)
    write_state_doc(state_doc_path, updated_doc)

    results = await asyncio.gather(
        *[
            _run_task(runner, agents[task.get("agent")], task, run_id, context_pack)
            for task in runnable
        ],
        return_exceptions=True,
    )

    updated_doc = load_state_doc(state_doc_path)
    verifier_blocked = False
    followup_tasks_added: list[dict[str, Any]] = []
    tasks_run: list[str] = []
    for task, output in zip(runnable, results):
        task_id = task.get("id")
        tasks_run.append(task_id)
        if isinstance(output, Exception):
            set_task_status(graph, task_id, "blocked", blocked_reason=str(output))
            updated_doc = update_results_ledger(
                updated_doc,
                task_id,
                task.get("title"),
                "blocked",
                f"_error_: {output}",
                [],
                [],
                [str(output)],
            )
            updated_doc = update_evidence_ledger(updated_doc, task_id, [])
            updated_doc = append_history(updated_doc, f"{task_id} blocked: {output}")
            continue

        policy = _review_policy(task, config)
        verify_policy = _task_verification_policy(task, config)
        written = _write_task_artifacts(run_id, output, task)
        evidence_lines = _evidence_lines(output)
        prompt_patches = _write_prompt_patches(run_id, task_id, output)
        task_verifier: VerifierResult | None = None
        if verify_policy == "llm":
            try:
                task_verifier = await _run_task_verifier(
                    runner, agents["verifier"], task, output, run_id, context_pack
                )
            except Exception as exc:
                task_verifier = VerifierResult(
                    verdict="FAIL",
                    summary=f"task verifier errored: {exc}",
                    issues=[str(exc)],
                    follow_ups=[],
                    prompt_patch=None,
                )
        issues: list[str] | None = None
        if task_verifier and task_verifier.verdict != "PASS":
            verifier_blocked = True
            follow_ups = task_verifier.follow_ups or task_verifier.issues
            if not follow_ups:
                follow_ups = [
                    f"Resolve task verifier verdict {task_verifier.verdict} for task {task_id}: {task_verifier.summary}"
                ]
            followup_tasks_added.extend(
                add_followup_tasks(
                    stage,
                    follow_ups,
                    _default_agent_for_stage(stage.get("id")),
                )
            )
            issues = [f"task_verifier: {task_verifier.verdict}", *task_verifier.issues]
            updated_doc = append_history(
                updated_doc, f"{task_id} task verifier: {task_verifier.verdict}"
            )

        if policy == "human":
            set_task_status(
                graph, task_id, "blocked", blocked_reason="awaiting_human_review"
            )
            status = "blocked"
        else:
            set_task_status(graph, task_id, "done")
            status = "done"
        updated_doc = update_results_ledger(
            updated_doc,
            task_id,
            task.get("title"),
            status,
            output.summary,
            written,
            evidence_lines,
            issues,
        )
        updated_doc = update_evidence_ledger(updated_doc, task_id, evidence_lines)
        if prompt_patches:
            updated_doc = append_history(
                updated_doc, f"{task_id} prompt patches: {', '.join(prompt_patches)}"
            )
        updated_doc = append_history(updated_doc, f"{task_id} {status}")

        output_path = run_outputs_dir(run_id) / f"{task_id}.json"
        output_path.write_text(output.model_dump_json(indent=2))

        if "final_report.md" in written and output.artifacts.get("final_report.md"):
            updated_doc = update_current_best_answer(
                updated_doc, output.artifacts["final_report.md"]
            )

    updated_doc = update_task_graph(updated_doc, graph)
    updated_doc = update_task_board(updated_doc, graph)
    if followup_tasks_added:
        updated_doc = _add_followup_placeholders(updated_doc, followup_tasks_added)
        updated_doc = append_history(
            updated_doc,
            f"added follow-ups: {', '.join(t.get('id') for t in followup_tasks_added)}",
        )
    updated_doc = touch_last_updated(updated_doc)

    verifier_verdict: str | None = None
    stop_reason: str | None = None
    if any(
        task.get("status") == "blocked"
        and task.get("blocked_reason") == "awaiting_human_review"
        for task in stage.get("tasks", [])
    ):
        stop_reason = "awaiting_human_review"
    if verifier_blocked and stop_reason is None:
        stop_reason = "verifier_blocked"
    if stage_complete(stage):
        verifier_context_pack = build_context_pack(run_id, updated_doc, stage)
        verifier_output = await _run_stage_verifier(
            runner, agents["verifier"], stage, run_id, verifier_context_pack
        )
        verifier_verdict = verifier_output.verdict
        patch_name = _write_verifier_prompt_patch(
            run_id, f"stage_{stage.get('id')}_verifier", verifier_output
        )
        if patch_name:
            updated_doc = append_history(
                updated_doc, f"verifier prompt patch: {patch_name}"
            )
        updated_doc = update_verifier_status(
            updated_doc,
            stage.get("id"),
            verifier_output.verdict,
            verifier_output.issues,
        )
        updated_doc = append_history(
            updated_doc,
            f"stage {stage.get('id')} verifier: {verifier_output.verdict}",
        )
        if verifier_output.verdict != "PASS":
            follow_ups = verifier_output.follow_ups or verifier_output.issues
            if not follow_ups:
                follow_ups = [
                    f"Resolve verifier verdict {verifier_output.verdict} for stage {stage.get('id')}: {verifier_output.summary}"
                ]
            new_tasks = add_followup_tasks(
                stage,
                follow_ups,
                _default_agent_for_stage(stage.get("id")),
            )
            if new_tasks:
                updated_doc = update_task_graph(updated_doc, graph)
                updated_doc = update_task_board(updated_doc, graph)
                updated_doc = _add_followup_placeholders(updated_doc, new_tasks)
                updated_doc = append_history(
                    updated_doc,
                    f"added follow-ups: {', '.join(t.get('id') for t in new_tasks)}",
                )
            stop_reason = "verifier_blocked"
    write_state_doc(state_doc_path, updated_doc)
    _write_final_output(run_id, updated_doc)

    return StepOutcome(
        run_id=run_id,
        stage_id=stage.get("id"),
        tasks_run=tasks_run,
        verifier_verdict=verifier_verdict,
        stop_reason=stop_reason,
    )


async def run_until_complete(
    run_id: str,
    config_path: str,
    max_cycles: int = 8,
    runner: Type[Runner] = Runner,
) -> StepOutcome:
    last_outcome = StepOutcome(run_id, None, [], None, None)
    for _ in range(max_cycles):
        last_outcome = await run_step(run_id, config_path, runner=runner)
        if last_outcome.stop_reason in {
            "complete",
            "verifier_blocked",
            "no_runnable_tasks",
            "awaiting_human_review",
        }:
            break
    if last_outcome.stop_reason == "complete":
        await run_final_verifier(run_id, config_path, runner=runner)
    return last_outcome


async def run_final_verifier(
    run_id: str,
    config_path: str,
    runner: Type[Runner] = Runner,
) -> None:
    config = load_config(config_path)
    prompts_dir = Path("prompts")
    agents = build_agents(config, prompts_dir)
    state_doc_path = run_dir(run_id) / "RESEARCH_STATE.md"
    state_doc_text = load_state_doc(state_doc_path)
    payload = {
        "run_id": run_id,
        "final_check": True,
        "context_pack": build_context_pack(run_id, state_doc_text, {"id": "final", "name": "final", "tasks": []}),
    }
    result = await runner.run(agents["verifier"], payload)
    final_output = result.final_output_as(VerifierResult)
    updated_doc = update_final_verifier(state_doc_text, final_output.verdict)
    patch_name = _write_verifier_prompt_patch(run_id, "final_verifier", final_output)
    if patch_name:
        updated_doc = append_history(updated_doc, f"verifier prompt patch: {patch_name}")
    updated_doc = append_history(updated_doc, f"final verifier: {final_output.verdict}")
    write_state_doc(state_doc_path, updated_doc)
    _write_final_output(run_id, updated_doc)
