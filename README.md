# Physics research agent (MVP)

Multi-agent research framework for highly specific theoretical physics problems, with:
- a local CLI scheduler (`src/`)
- an optional Restate durable backend (`restate/app/`)
- a canonical, human-editable **Research State Doc** (`RESEARCH_STATE.md`) as the source of truth

If you only read one thing: **the scheduler executes the Task Graph YAML inside `RESEARCH_STATE.md`**. Everything else is notes, evidence, and ledgers around that graph.

## Quickstart (CLI)

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Set your API key:
```bash
export OPENAI_API_KEY=sk-...
```

### Start a run

Long prompts/TeX are easiest via a file:
```bash
python -m src.main init --question-file question.md --problem configs/problem_spec.md
```

You can also pipe from stdin (good for very long questions):
```bash
cat question.md | python -m src.main init --question - --problem configs/problem_spec.md
```

Or a short inline prompt:
```bash
python -m src.main init --question "Your question" --problem configs/problem_spec.md
```

This prints `<run_id>` and creates `artifacts/runs/<run_id>/RESEARCH_STATE.md`.

### (Optional) Enable retrieval + ingest PDFs

If you want `paper_reader` to use OpenAI FileSearch, set `vector_store_id` in `configs/agents.yaml`, then ingest PDFs:
```bash
python -m src.main ingest --run <run_id> --docs /path/to/paper1.pdf --docs /path/to/paper2.pdf
```

### Run

Run one “wave” (one scheduler cycle):
```bash
python -m src.main step --run <run_id>
```

Or run multiple cycles:
```bash
python -m src.main run --run <run_id> --max-cycles 8
```

## End-to-end walkthrough (recommended)

This is the most common “plan → run → review → iterate → finalize” loop.

### 0) Put your question in a file (recommended)

Create `question.md` (Markdown/TeX is fine):
```bash
cat > question.md <<'MD'
<paste your full research question here>
MD
```

### 1) Init (creates the Research State Doc)

```bash
python -m src.main init --question-file question.md --problem configs/problem_spec.md
```

This prints a `<run_id>` and creates `artifacts/runs/<run_id>/RESEARCH_STATE.md`.

### 2) Review/edit the plan (this is the “proposal” step)

Open `artifacts/runs/<run_id>/RESEARCH_STATE.md` and edit **only** the YAML under:
- `## Task Graph (machine-readable)`

Edits that change execution:
- **serial vs parallel** within a stage: add `depends_on`
- route a task to a different subagent: change `task.agent`
- change quality gates: edit `acceptance_criteria` (task) and `stage.verifier.criteria` (stage)

Edits that do *not* change execution:
- the Task Board (it’s regenerated)
- freeform notes elsewhere in the doc

### 3) Configure how tasks are reviewed / judged (optional but recommended)

Defaults are in `configs/agents.yaml`. You can edit YAML directly or use the controller.

Common setup:
```bash
# Require human approval for a specific agent’s tasks:
python -m src.controller set-review --agent paper_reader --policy human

# Enable task-level LLM judging for a specific agent’s tasks:
python -m src.controller set-task-verify --agent derivation_coder --policy llm

# Require final human sign-off for the “final report task” (default is 3.1):
python -m src.controller set-review --task 3.1 --policy human
```

### 4) (Optional) Add papers and enable retrieval

If you want `paper_reader` / `verifier` to use OpenAI FileSearch:
1) set `vector_store_id` in `configs/agents.yaml`
2) ingest PDFs:
```bash
python -m src.main ingest --run <run_id> --docs /path/to/paper1.pdf --docs /path/to/paper2.pdf
```

### 5) Run one cycle at a time (recommended for HITL)

```bash
python -m src.main step --run <run_id>
```

Repeat `step` until it stops. Typical stop reasons:
- `awaiting_human_review`: at least one task is blocked for your approval/modification
- `verifier_blocked`: a task-level judge or stage verifier returned non-PASS and follow-ups were injected
- `complete`: all stages finished and the final verifier ran

### 6) Review → approve/modify → resume

When stopped for review:
```bash
python -m src.controller review-queue --run <run_id>
python -m src.controller approve --run <run_id> --task 1.2
# or:
# python -m src.controller modify --run <run_id> --task 1.2 --summary-file your_notes.txt
python -m src.main step --run <run_id>
```

When blocked by verification (`verifier_blocked`):
- open `artifacts/runs/<run_id>/RESEARCH_STATE.md`
- check `## Verifier status` + the task’s `- issues:`
- follow-up tasks were added to the Task Graph; you can edit the YAML if you want a different plan, then run `step` again

### 7) Read the outputs

Everything you need to read/share is under `artifacts/runs/<run_id>/`:
- `final_output.md` (Question + Summary + Final Result)
- `final_report.md` (if the Task Graph wrote it; default task is `3.1`)
- `RESEARCH_STATE.md` (audit log + task graph + ledgers)

## Quickstart (Restate durable mode)

Restate gives crash-safe retries + suspend/resume for human review.

1) Start Restate server (UI at `http://localhost:9070`):
```bash
restate-server
```

2) Run the service (port 9080):
```bash
cd restate
export OPENAI_API_KEY=sk-...
python -m app
```

3) Register it:
```bash
restate deployments register http://localhost:9080
```

4) Invoke:
```bash
curl localhost:8080/Orchestrator/init --json '{"question":"<your question>"}'
curl localhost:8080/Orchestrator/run --json '{"run_id":"<run_id>","max_cycles":8}'
```

For long prompts, put the JSON in a file:
```bash
cat > init.json <<'JSON'
{"question":"<long question (can include \\n and TeX)>","problem":"configs/problem_spec.md","config":"configs/agents.yaml"}
JSON
curl -H 'Content-Type: application/json' --data @init.json localhost:8080/Orchestrator/init
```

### Why Restate?

Use Restate when you want:
- **Durability**: if your process crashes/restarts, in-flight runs can resume without redoing completed work.
- **Human-in-the-loop suspension**: runs can pause on review and resume after you approve/modify.
- **Tracing/UI**: see invocations and timing in the Restate UI.

## What you get (per run)

Everything is under `artifacts/runs/<run_id>/`:
- `RESEARCH_STATE.md` — canonical memory (task graph + ledgers + verifier status + history)
- `agent_outputs/<task_id>.json` — raw structured outputs (TaskResult)
- `context_pack.md` — minimal context used in the last cycle
- `final_report.md` — if any task writes it (by default, stage `3.1` does)
- `final_output.md` — Question + Summary + Final Result (regenerated after each cycle; falls back to “Current best answer” if no `final_report.md`)
- `prompt_patches/` — optional self-evolution patches proposed by agents

## How it works (key concepts)

### Control surfaces (what to edit)

There are three main “control surfaces”:

1) `artifacts/runs/<run_id>/RESEARCH_STATE.md` (per-run; canonical)
   - The scheduler executes the **Task Graph YAML** under `## Task Graph (machine-readable)`.
   - The human-readable Task Board is regenerated; don’t edit it to change execution.
2) `configs/agents.yaml` (shared config)
   - models per agent, prompts, provider settings, review policy (human/auto), task-level LLM judging.
3) `prompts/*.md` (agent instructions)
   - can be overridden per agent in `configs/agents.yaml`.

Rule of thumb:
- If you want the scheduler to behave differently (tasks, ordering, criteria): edit the **Task Graph YAML**.
- If you want different models/prompts/review gates: edit `configs/agents.yaml` (or use the controller).

### Task ids (`a.b`)

Task ids follow the `a.b` convention:
- `a` = serial **stage** number (hard barrier)
- `b` = task/subtask number **within that stage**

Example: `3.1` = stage 3, task 1.

### Serial vs parallel scheduling

Two different things are called “orchestrator”:
- the **Python scheduler** (`src/orchestrator.py`) decides what to run next
- the **LLM Orchestrator agent** (`orchestrator` in config) is just another agent used by tasks (by default task `3.1`)

Scheduling rules:
- Stages are **serial barriers**: stage `a+1` won’t start until all tasks in stage `a` are `done`/`skipped` and the stage verifier PASSes.
- Within a stage, tasks run in **parallel waves**:
  - runnable = `status: todo` and all `depends_on` tasks are `done`/`skipped`
  - `step` runs one wave; `run` loops steps until a stop reason.
- `parallel_group` is currently a **label/hint** in the YAML; the MVP scheduler does not use it for scheduling decisions.

### How the scheduler “spawns” subagents

Each task in the Task Graph has an `agent` field (e.g. `literature_scout`, `paper_reader`, `derivation_coder`, `verifier`, `orchestrator`).

For every runnable task in a wave, the scheduler:
1) builds a minimal `context_pack.md` for the current stage
2) calls the OpenAI Agents SDK `Runner.run(...)` with the chosen agent and a structured payload (`task_id`, `acceptance_criteria`, `inputs`, `context_pack`, `run_id`)
3) waits for all tasks in that wave (`asyncio.gather(...)`)
4) writes artifacts + updates `RESEARCH_STATE.md` ledgers + (optionally) runs task-level verification

## Putting it together (proposal → execute/review → finalize)

This is the “1→2→3” workflow you described, using the current repo’s control surfaces.

1) **Proposal (plan)**
   - Run `init` → creates `artifacts/runs/<run_id>/RESEARCH_STATE.md` with an initial Task Graph.
   - Review/edit the **Task Graph YAML** to change tasks, `depends_on` (serial vs parallel), acceptance criteria, stage verifier criteria, and which agent runs each task.
   - Review/edit `configs/agents.yaml` (or use `python -m src.controller ...`) to choose models/prompts and review/judge policies.

2) **Execute + review + iterate**
   - Run `step` (one wave) or `run` (loop) until it stops.
   - Each task can be gated by any combination of:
     - **Human review** (`review: human`) → task becomes `blocked` and the scheduler stops with `awaiting_human_review` until you `approve`/`modify`.
     - **LLM judge** (`task_verification: llm`) → verifier judges against `acceptance_criteria`; non-PASS injects follow-ups and stops with `verifier_blocked`.
     - **Both** → the judge issues are recorded in that task’s Results ledger `- issues:` and the task still stays blocked for your approval.
   - You don’t need to know follow-up task ids ahead of time: set default/per-agent policies and they apply to newly added follow-up tasks too.

   Policy resolution order (most specific wins):
   - `per_task` → `per_agent` → `default`

3) **Finalize + final human sign-off**
   - By default, task `3.1` writes `final_report.md`, and `final_output.md` is regenerated every cycle.
   - `3.1` is not “special” in code: it’s just the default Task Graph. Any task can write `final_report.md` if it lists it in `outputs.artifacts`.
   - To require “final approval”, set `review` to human for the task that produces the final report (default is `3.1`), then approve/modify before you consider the run done.

## Keeping memory clean

- Treat `RESEARCH_STATE.md` as a ledger: short summaries + pointers to artifacts and `agent_outputs/*.json`.
- Put long content in run artifacts (e.g. `equation_bank.md`, `derivation.md`, `final_report.md`) and keep only the best current synthesis in `## Current best answer`.
- Re-plans should happen by editing the Task Graph YAML; record “why” in the History log. For big redesigns, start a new `run_id`.

## Human-in-the-loop (HITL) end-to-end

This repo supports flexible review gates per task:
- human review (`review: human`)
- task-level LLM judging (`task_verification: llm`)
- stage-level verification (the stage verifier runs when the stage finishes)
- (future) script evaluators (e.g. run `checks.py` and gate on pass/fail)

### A) Configure reviewers (before running)

In `configs/agents.yaml`:
- `review`: default / per-agent / per-task (auto vs human)
- `task_verification`: default / per-agent / per-task (none vs llm)

Or use the controller:
```bash
python -m src.controller set-review --agent literature_scout --policy human
python -m src.controller set-review --task 3.1 --policy human
python -m src.controller set-task-verify --agent derivation_coder --policy llm
```

Tip: if you don’t know task ids ahead of time (e.g. verifier-injected follow-ups), set policies by agent or as a default.

### B) Run until the scheduler stops

Run `step` or `run`. The scheduler stops when it hits one of these:
- `awaiting_human_review`: at least one task in the current stage is blocked on human approval/modification
- `verifier_blocked`: a task-level judge or a stage verifier returned non-PASS and follow-up tasks were injected
- `complete`: all stages completed and the final verifier ran

### C) Review and resolve

Look at:
- `artifacts/runs/<run_id>/RESEARCH_STATE.md` (Results/Evidence ledgers + verifier status)
- `artifacts/runs/<run_id>/agent_outputs/<task_id>.json` (full structured output)
- any artifacts written into the run directory (e.g. `equation_bank.md`, `derivation.md`, `final_report.md`)

Review queue:
```bash
python -m src.controller review-queue --run <run_id>
```

Approve:
```bash
python -m src.controller approve --run <run_id> --task 1.1
```

Modify:
```bash
python -m src.controller modify --run <run_id> --task 3.1 \
  --summary-file /path/to/summary.txt \
  --artifact final_report.md=/path/to/final_report.md
```

Then continue:
```bash
python -m src.main step --run <run_id>
```

### Example: full human-in-the-loop cycle (CLI)

This is the typical “pause → review → resume” loop:

1) Init and edit the proposal:
```bash
python -m src.main init --question-file question.md --problem configs/problem_spec.md
# open artifacts/runs/<run_id>/RESEARCH_STATE.md and edit the Task Graph YAML
```

2) Configure gates (optional):
```bash
python -m src.controller set-review --agent paper_reader --policy human
python -m src.controller set-task-verify --agent derivation_coder --policy llm
```

3) Run until it pauses:
```bash
python -m src.main run --run <run_id> --max-cycles 8
```

4) See what needs approval and approve/modify:
```bash
python -m src.controller review-queue --run <run_id>
python -m src.controller approve --run <run_id> --task 1.2
# or:
# python -m src.controller modify --run <run_id> --task 1.2 --summary-file your_notes.txt
```

5) Resume:
```bash
python -m src.main step --run <run_id>
```

### Restate HITL endpoints

If you are running via Restate and a run is suspended waiting for review, use:
```bash
curl localhost:8080/Orchestrator/review_queue --json '{"run_id":"<run_id>"}'
curl localhost:8080/Orchestrator/approve --json '{"run_id":"<run_id>","task_id":"1.1"}'
curl localhost:8080/Orchestrator/modify --json '{"run_id":"<run_id>","task_id":"3.1","summary":"..."}'
```

Calling `approve` / `modify` also resolves the stored awakeable so the suspended `Orchestrator/run` resumes.

## Editing / evolving the plan (Task Graph)

The Task Graph YAML inside `RESEARCH_STATE.md` is the **research proposal**.

You can evolve it by editing the YAML block under `## Task Graph (machine-readable)`:
- change `task.agent` to route work to a different agent
- add tasks, or mark tasks `skipped` (include `skip_reason`)
- add `depends_on` edges to serialize within a stage
- adjust per-task `acceptance_criteria` and per-stage verifier `criteria`

Automatic evolution also happens:
- if a stage verifier returns non-PASS, follow-up tasks are injected into the same stage
- if task-level `task_verification: llm` returns non-PASS, follow-up tasks are injected into the same stage

## Self-evolution (prompt patches)

Agents may propose prompt improvements as `prompt_patch*.md` artifacts. These are stored under:
`artifacts/runs/<run_id>/prompt_patches/`

Apply a patch (append/replace):
```bash
python -m src.controller apply-prompt-patch --agent paper_reader \
  --patch artifacts/runs/<run_id>/prompt_patches/1.2_prompt_patch.md \
  --mode append
```

## Customization

### Choosing models per agent

Edit `configs/agents.yaml` under `models:` (or use the controller):
```bash
python -m src.controller set-model --agent verifier --model gpt-4.1-mini
```

You can also set a different model for each agent directly in YAML:
```yaml
models:
  default: "gpt-4.1-mini"
  derivation_coder: "gpt-4.1"
  verifier: "gpt-4.1"
```

### Enabling a sandboxed “code tool” (Code Interpreter)

OpenAI provides a hosted **Code Interpreter** tool (a sandboxed container for Python). The repo wires it as `code_interpreter`.

Defaults:
- `derivation_coder` and `verifier` have `code_interpreter` enabled
- other agents do not (you can enable it)

Enable it for an agent by adding this to `configs/agents.yaml`:
```yaml
tools:
  per_agent:
    orchestrator: ["code_interpreter"]
```

You can also combine tools, e.g. `["file_search", "code_interpreter"]` (file search requires `vector_store_id`).

Important caveat:
- Code Interpreter runs in an **OpenAI-hosted sandbox**, not your local machine. It cannot directly read your local `artifacts/runs/<run_id>/...` files unless you upload them to OpenAI and pass file ids (not wired in this repo yet). Use it for calculations, simulations, and spot checks inside the tool session.
- If you want deterministic local evaluation, prefer writing `checks.py` as an artifact and running it locally as part of your review.

Optional config:
```yaml
code_interpreter:
  memory_limit: "1g"  # "1g" | "4g" | "16g" | "64g"
```

### Friendly input for long questions

Recommended: use `--question-file question.md`. You can also edit the question block in `RESEARCH_STATE.md` under `## Header`.

In Restate mode, the UI (`http://localhost:9070`) is usually the easiest way to paste long questions, or send JSON via `curl --data @init.json`.

## Troubleshooting

- If stage `1.2` output is generic, ingest docs and set `vector_store_id` in `configs/agents.yaml`.
- If you edit `RESEARCH_STATE.md` by hand, keep the Task Graph YAML valid (the scheduler validates it before every cycle).
