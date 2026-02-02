from __future__ import annotations

import argparse
from pathlib import Path
from .config import load_config, save_config
from .review import (
    approve_task,
    list_review_queue,
    modify_task,
    refresh_final_output,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controller for run customization")
    subparsers = parser.add_subparsers(dest="command", required=True)

    model_parser = subparsers.add_parser("set-model", help="Set model for an agent")
    model_parser.add_argument("--config", default="configs/agents.yaml")
    model_parser.add_argument("--agent", required=True)
    model_parser.add_argument("--model", required=True)

    provider_parser = subparsers.add_parser("set-provider", help="Set provider config")
    provider_parser.add_argument("--config", default="configs/agents.yaml")
    provider_parser.add_argument("--agent", default="default")
    provider_parser.add_argument("--api-key-env")
    provider_parser.add_argument("--base-url")
    provider_parser.add_argument("--organization")
    provider_parser.add_argument("--project")
    provider_parser.add_argument("--use-responses", choices=["true", "false"])

    prompt_parser = subparsers.add_parser("set-prompt", help="Set prompt path for an agent")
    prompt_parser.add_argument("--config", default="configs/agents.yaml")
    prompt_parser.add_argument("--agent", required=True)
    prompt_parser.add_argument("--path", required=True)

    review_parser = subparsers.add_parser("set-review", help="Set review policy")
    review_parser.add_argument("--config", default="configs/agents.yaml")
    review_parser.add_argument("--agent", default="default")
    review_parser.add_argument("--task", help="Apply to a specific task id (e.g. 3.1)")
    review_parser.add_argument("--policy", choices=["auto", "human"], required=True)

    task_verify_parser = subparsers.add_parser(
        "set-task-verify", help="Set task-level self-verification policy"
    )
    task_verify_parser.add_argument("--config", default="configs/agents.yaml")
    scope = task_verify_parser.add_mutually_exclusive_group()
    scope.add_argument("--agent", help="Apply to all tasks for this agent")
    scope.add_argument("--task", help="Apply to a specific task id (e.g. 2.1)")
    task_verify_parser.add_argument("--policy", choices=["none", "llm"], required=True)

    approve_parser = subparsers.add_parser("approve", help="Approve a blocked task")
    approve_parser.add_argument("--run", required=True)
    approve_parser.add_argument("--task", required=True)

    modify_parser = subparsers.add_parser("modify", help="Modify task outputs")
    modify_parser.add_argument("--run", required=True)
    modify_parser.add_argument("--task", required=True)
    modify_parser.add_argument("--summary")
    modify_parser.add_argument("--summary-file")
    modify_parser.add_argument("--artifact", action="append", default=[])
    modify_parser.add_argument("--evidence", action="append", default=[])

    patch_parser = subparsers.add_parser(
        "apply-prompt-patch", help="Apply a prompt patch"
    )
    patch_parser.add_argument("--config", default="configs/agents.yaml")
    patch_parser.add_argument("--agent", required=True)
    patch_parser.add_argument("--patch", required=True)
    patch_parser.add_argument("--mode", choices=["append", "replace"], default="append")

    refresh_parser = subparsers.add_parser(
        "refresh-output", help="Regenerate final_output.md"
    )
    refresh_parser.add_argument("--run", required=True)

    queue_parser = subparsers.add_parser(
        "review-queue", help="List tasks awaiting human review"
    )
    queue_parser.add_argument("--run", required=True)

    return parser


def _set_model(args: argparse.Namespace) -> None:
    config = load_config(args.config, resolve_env=False)
    config.setdefault("models", {})
    config["models"][args.agent] = args.model
    save_config(args.config, config)


def _set_provider(args: argparse.Namespace) -> None:
    config = load_config(args.config, resolve_env=False)
    providers = config.setdefault("providers", {})
    target = providers.setdefault("per_agent", {})
    if args.agent == "default":
        target = providers.setdefault("default", {})
    agent_cfg = target.setdefault(args.agent, {}) if args.agent != "default" else target
    openai_cfg = agent_cfg.setdefault("openai", {}) if args.agent != "default" else agent_cfg.setdefault("openai", {})
    if args.api_key_env:
        openai_cfg["api_key"] = f"${{{args.api_key_env}}}"
    if args.base_url is not None:
        openai_cfg["base_url"] = args.base_url
    if args.organization is not None:
        openai_cfg["organization"] = args.organization
    if args.project is not None:
        openai_cfg["project"] = args.project
    if args.use_responses is not None:
        openai_cfg["use_responses"] = args.use_responses == "true"
    save_config(args.config, config)


def _set_prompt(args: argparse.Namespace) -> None:
    config = load_config(args.config, resolve_env=False)
    prompts = config.setdefault("prompts", {})
    per_agent = prompts.setdefault("per_agent", {})
    per_agent[args.agent] = args.path
    save_config(args.config, config)


def _set_review(args: argparse.Namespace) -> None:
    config = load_config(args.config, resolve_env=False)
    review = config.setdefault("review", {})
    if getattr(args, "task", None):
        per_task = review.setdefault("per_task", {})
        per_task[args.task] = args.policy
    elif args.agent == "default":
        review["default"] = args.policy
    else:
        per_agent = review.setdefault("per_agent", {})
        per_agent[args.agent] = args.policy
    save_config(args.config, config)


def _set_task_verify(args: argparse.Namespace) -> None:
    config = load_config(args.config, resolve_env=False)
    verification = config.setdefault("task_verification", {})
    if args.task:
        per_task = verification.setdefault("per_task", {})
        per_task[args.task] = args.policy
    elif args.agent:
        per_agent = verification.setdefault("per_agent", {})
        per_agent[args.agent] = args.policy
    else:
        verification["default"] = args.policy
    save_config(args.config, config)


def _apply_prompt_patch(args: argparse.Namespace) -> None:
    config = load_config(args.config, resolve_env=False)
    prompts = config.get("prompts", {})
    per_agent = prompts.get("per_agent", {})
    default_dir = Path(prompts.get("default_dir", "prompts"))
    prompt_path = Path(per_agent.get(args.agent, default_dir / f"{args.agent}.md"))
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    patch_text = Path(args.patch).read_text()
    if args.mode == "replace":
        new_text = patch_text
    else:
        new_text = prompt_path.read_text().rstrip() + "\n\n" + patch_text.strip() + "\n"
    prompt_path.write_text(new_text)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "set-model":
        _set_model(args)
    elif args.command == "set-provider":
        _set_provider(args)
    elif args.command == "set-prompt":
        _set_prompt(args)
    elif args.command == "set-review":
        _set_review(args)
    elif args.command == "set-task-verify":
        _set_task_verify(args)
    elif args.command == "approve":
        approve_task(args.run, args.task)
    elif args.command == "modify":
        summary = args.summary
        if args.summary_file:
            summary = Path(args.summary_file).read_text().strip()
        artifact_map: dict[str, str] = {}
        for item in args.artifact:
            if "=" not in item:
                raise ValueError("Artifact must be name=path")
            name, path = item.split("=", 1)
            artifact_map[name] = Path(path).read_text()
        modify_task(
            args.run,
            args.task,
            summary=summary,
            artifacts=artifact_map or None,
            evidence=args.evidence or None,
        )
    elif args.command == "apply-prompt-patch":
        _apply_prompt_patch(args)
    elif args.command == "refresh-output":
        refresh_final_output(args.run)
    elif args.command == "review-queue":
        items = list_review_queue(args.run)
        if not items:
            print("No tasks awaiting review.")
        else:
            for item in items:
                print(
                    f"{item['task_id']} | {item['title']} | {item['agent']} | {item['blocked_reason']}"
                )


if __name__ == "__main__":
    main()
