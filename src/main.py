from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import load_config
from .orchestrator import init_run, run_step, run_until_complete
from .paths import run_dir
from .state_doc import append_history, load_state_doc, touch_last_updated, write_state_doc
from .tools_ingest import ingest_docs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Physics research agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a new run")
    question_group = init_parser.add_mutually_exclusive_group(required=True)
    question_group.add_argument("--question", help="Research question text (use '-' to read from stdin)")
    question_group.add_argument("--question-file", help="Path to a text/Markdown file (use '-' to read from stdin)")
    init_parser.add_argument("--problem", required=True)
    init_parser.add_argument("--config", default="configs/agents.yaml")
    init_parser.add_argument("--docs", action="append", default=[])
    init_parser.add_argument("--run-id")

    step_parser = subparsers.add_parser("step", help="Run one orchestration cycle")
    step_parser.add_argument("--run", required=True)
    step_parser.add_argument("--config", default="configs/agents.yaml")

    run_parser = subparsers.add_parser("run", help="Run until completion or budget")
    run_parser.add_argument("--run", required=True)
    run_parser.add_argument("--config", default="configs/agents.yaml")
    run_parser.add_argument("--max-cycles", type=int, default=8)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents")
    ingest_parser.add_argument("--run", required=True)
    ingest_parser.add_argument("--docs", action="append", default=[])
    ingest_parser.add_argument("--config", default="configs/agents.yaml")

    return parser


async def _main_async(args: argparse.Namespace) -> None:
    if args.command == "init":
        if getattr(args, "question", None) is not None:
            question = sys.stdin.read().strip() if args.question == "-" else args.question
        else:
            question = (
                sys.stdin.read().strip()
                if args.question_file == "-"
                else open(args.question_file, "r", encoding="utf-8").read()
            )
        run_id = init_run(
            question=question,
            problem_spec_path=args.problem,
            config_path=args.config,
            docs=args.docs,
            run_id=args.run_id,
        )
        print(run_id)
        return

    if args.command == "step":
        outcome = await run_step(args.run, args.config)
        print(outcome)
        return

    if args.command == "run":
        outcome = await run_until_complete(
            args.run, args.config, max_cycles=args.max_cycles
        )
        print(outcome)
        return

    if args.command == "ingest":
        if not args.docs:
            raise SystemExit("No docs provided.")
        config = load_config(args.config)
        ingest_docs(args.run, args.docs, config=config)
        state_doc_path = run_dir(args.run) / "RESEARCH_STATE.md"
        state_doc = load_state_doc(state_doc_path)
        updated = append_history(state_doc, f"ingested {len(args.docs)} docs")
        updated = touch_last_updated(updated)
        write_state_doc(state_doc_path, updated)
        print("ingested")
        return


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
