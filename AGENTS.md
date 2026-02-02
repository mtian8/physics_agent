# AGENTS.md

**Multi-agent research framework (MVP) for solving highly specific theoretical physics problems** using the OpenAI **Agents SDK** (Responses API tools), with an optional **Restate** backend for durable execution.

This file is written for:
- humans editing the system (prompts, criteria, tasks), and
- coding agents (e.g. Codex) that need **clear, executable steps** to run or extend the repo.

---

## Runtime map (OpenAI SDK + Restate)

This repo supports **two** execution backends for the same Task Graph + Research State Doc:

1) **Local CLI (`src/`)** — fast iteration with `asyncio` fan-out/fan-in.
2) **Durable mode (`restate/app/`)** — run the same agents under **Restate Server** for crash-safe retries, suspend/resume, and human-in-the-loop.

### Where things live in this repo

- `openai-agents-python/` — OpenAI Agents SDK (Python). Docs: https://openai.github.io/openai-agents-python/
- `restate/` — Restate server source tree (upstream), with the durable app in `restate/app/`. Docs: https://docs.restate.dev/ai/sdk-integrations/openai-agents-sdk (patterns: https://docs.restate.dev/ai/patterns/) (Upstream: https://github.com/restatedev/restate)

---

## 0) Non-negotiables

1) **The Research State Doc is the source of truth.**
   - Every run has a single Markdown file that stores: the plan, task graph, results, evidence, verifier status, and full history.
   - If there is disagreement between JSON logs and the doc, the doc wins.

2) **No hidden chain-of-thought storage.**
   - Store plans, intermediate artifacts, and short *reasoning summaries* suitable for debugging.
   - Never ask for or try to persist private chain-of-thought.

3) **Every step has a verifier.**
   - Each stage (serial) has a “stage verifier” that gates progress.
   - The whole run ends with a “final verifier” pass.
   - Optionally, tasks can also be gated by **task-level LLM verification** (`configs/agents.yaml` → `task_verification`).

4) **Reproducibility > eloquence.**
   - Prefer structured outputs, citations, and executable checks.

---

## 1) What this system does

**Input**
- A **research question** (natural language).
- A **document pool** (either provided by the user, or found via search and ingested into a vector store).

**Output**
- A versioned **Research State Doc** that includes:
  - a decomposed task plan (serial stages with parallel subtasks),
  - per-task results and evidence,
  - code artifacts for checks,
  - verifier outcomes,
  - a final report section.

---

## 2) Repo layout (recommended)

> Notes:
> - `openai-agents-python/` is the OpenAI Agents SDK (vendored or as a git submodule). If you don’t need to modify it, you can also just `pip install openai-agents`.
> - `restate/` contains the Restate server sources; the durable Python service for this repo lives in `restate/app/`.

```
.
├─ AGENTS.md
├─ openai-agents-python/          # OpenAI Agents SDK (Python); docs: https://openai.github.io/openai-agents-python/
├─ restate/                       # Restate server source tree (upstream)
│  ├─ app/                        # Durable services/workflows (Python) for this repo
│  └─ ...                         # Restate server sources (Rust)
├─ configs/
│  ├─ agents.yaml                 # model/tool knobs
│  └─ problem_spec.md             # per-problem acceptance tests & constraints
├─ prompts/
│  ├─ orchestrator.md
│  ├─ literature_scout.md
│  ├─ paper_reader.md
│  ├─ derivation_coder.md
│  ├─ verifier.md
│  └─ meta_review.md              # optional: proposes prompt/process improvements
├─ src/
│  ├─ main.py                     # CLI (init/step/run) for local mode
│  ├─ agents.py                   # agent definitions & tool wiring
│  ├─ state_doc.py                # read/write Research State Doc
│  ├─ task_graph.py               # parse/validate the task graph
│  ├─ context_pack.py             # context control (build the minimal context)
│  ├─ tools_ingest.py             # deterministic ingestion + vector store ops
│  └─ storage.py                  # sqlite + artifact paths
├─ db/
│  └─ metadata.sqlite             # papers, tasks, runs
└─ artifacts/
   ├─ papers/                     # cached PDFs
   └─ runs/<run_id>/              # per-run outputs
```


---

## 3) Quickstart (for Codex / contributors)

### 3.1 Prereqs

- Python 3.10+ (3.11 recommended)
- An OpenAI API key in `OPENAI_API_KEY`

### 3.2 Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip

# Option A (recommended): install from PyPI
pip install openai openai-agents pydantic pyyaml restate_sdk[serde] hypercorn

# Option B (repo-local dev): use the vendored SDK in ./openai-agents-python
# (use this only if you need to modify the SDK itself)
pip install -e ./openai-agents-python

# Or, if the repo includes it:
# pip install -r requirements.txt
```


### 3.3 Run the MVP

1) Edit:
- `configs/problem_spec.md` (goal + constraints + acceptance tests)
- `configs/agents.yaml` (models, budgets, allowed domains)

2) Start a run:

```bash
python -m src.main init \
  --question "<your research question>" \
  --problem configs/problem_spec.md \
  --docs "path/to/paper1.pdf" \
  --docs "path/to/paper2.pdf"
```

For long questions (incl. TeX/LaTeX), use `--question-file path/to/question.md`. You can also read from stdin with `--question -` or `--question-file -`.

If you don't have docs yet, you can omit `--docs`; stage `1.1` will write `paper_candidates.json`, then you can download PDFs and ingest them with `python -m src.main ingest`.

3) Execute one orchestration cycle (recommended for human-in-the-loop runs):

```bash
python -m src.main step --run <run_id>
```

Optional: (re)ingest docs deterministically without running a full cycle:

```bash
python -m src.main ingest \
  --run <run_id> \
  --docs "path/to/paper3.pdf"
```

4) Or run until completion (bounded by max cycles / budget):

```bash
python -m src.main run --run <run_id> --max-cycles 8
```

**Expected outputs**
- `artifacts/runs/<run_id>/RESEARCH_STATE.md` (canonical)
- `artifacts/runs/<run_id>/final_report.md` (if the Task Graph writes it; default stage `3.1`)
- `artifacts/runs/<run_id>/final_output.md` (Question + summary + final result)
- `artifacts/runs/<run_id>/agent_outputs/*.json`
- `artifacts/runs/<run_id>/checks.py` (and optional notebook)

### 3.4 Run with Restate (durable execution backend)

Restate runs your agent logic as HTTP-callable services and provides durability (automatic retries, suspend/resume, and captured traces). The Restate + OpenAI Agents SDK integration uses:
- `DurableRunner` to persist **LLM responses** so retries don’t re-call the model, and
- `ctx.run(...)` for non-deterministic steps (add `@durable_function_tool` wrappers if you add durable tool calls).

1) Start the Restate Server (and UI):

```bash
restate-server
# UI (invocations, traces): http://localhost:9070
```

2) Start the Restate services for this repo (the service should listen on port `9080` by convention):

```bash
cd restate
export OPENAI_API_KEY=sk-...

# Run the durable app:
python -m app
```

3) Register the service endpoint with Restate:

```bash
restate deployments register http://localhost:9080
# If Restate Server runs in Docker, register:
# restate deployments register http://host.docker.internal:9080
```

4) Invoke the orchestrator via Restate ingress (port `8080`):

```bash
# Example shape; define your handler input schema in restate/app/app.py
curl localhost:8080/Orchestrator/init --json '{"question":"<your research question>"}'
curl localhost:8080/Orchestrator/run --json '{"run_id":"<run_id>","max_cycles":8}'
```

**Recommended Restate handlers (mirror the CLI)**
- `Orchestrator/init` → returns `run_id` (creates `RESEARCH_STATE.md`)
- `Orchestrator/step` → executes one cycle (human-in-loop)
- `Orchestrator/run` → runs until completion/budget and returns a status summary (final report is written if the Task Graph produces `final_report.md`; default stage `3.1`)


---

## 4) The Research State Doc (canonical memory)

Path per run:

```
artifacts/runs/<run_id>/RESEARCH_STATE.md
```

### 4.1 Required sections

The orchestrator must keep these sections present **in this order**:

1) **Header** (run id, timestamps, config snapshot)
2) **Problem spec** (copied or referenced)
3) **Current best answer** (short, may be incomplete)
4) **Task Graph (machine-readable)** (YAML block)
5) **Task Board (human-readable)** (checkbox list)
6) **Results ledger** (one subsection per task id)
7) **Evidence / citations ledger** (paper ids + location hints)
8) **Verifier status** (stage + final)
9) **History log** (append-only)

### 4.2 Task graph semantics (layered DAG: serial stages + parallel subtasks)

We use the user’s `a.b` convention:
- `a` = **serial stage** (must finish before stage `a+1` starts)
- `b` = **subtask within stage a** (eligible to run in parallel with other `a.*` tasks)

**Important:** the graph is a *layered DAG*:
- stages impose a hard barrier (stage `a+1` cannot begin until stage `a` passes verification), and
- tasks may also declare explicit `depends_on` edges **within a stage** to serialize work when needed.

Example:
- Stage 1: `1.1`, `1.2`, `1.3` can run in parallel **unless** a task declares `depends_on`.
- Stage 2: `2.1`, `2.2` run after stage 1 passes.
- Stage 3: `3.1` runs (possibly alone).

A stage is “complete” when:
- all tasks in the stage are `done` (or explicitly `skipped`), and
- the stage verifier returns `PASS`.


### 4.3 Machine-readable Task Graph block

The orchestrator **parses this YAML** to decide what to run next.
Humans may edit it; the orchestrator must validate it before execution.

```yaml
# TASK_GRAPH_V2
version: 2
stages:
  - id: 1
    name: "Literature + definitions"
    verifier:
      agent: verifier
      criteria: ["citations_present", "notation_defined"]
    tasks:
      - id: "1.1"
        title: "Search + rank candidate papers"
        agent: literature_scout
        status: todo
        depends_on: []
        parallel_group: "search"
        acceptance_criteria: ["paper_candidates_written", "citations_present"]
        inputs:
          query_hints: []
        outputs:
          - artifacts: ["paper_candidates.json"]

      - id: "1.2"
        title: "Extract definitions + assumptions from paper pool"
        agent: paper_reader
        status: todo
        depends_on: ["1.1"]
        parallel_group: "extraction"
        acceptance_criteria: ["notation_defined", "assumptions_listed", "citations_present"]
        inputs:
          focus: "definitions + assumptions"
        outputs:
          - artifacts: ["equation_bank.md", "assumptions.md", "extractions.json"]

  - id: 2
    name: "Derivation + computational checks"
    verifier:
      agent: verifier
      criteria: ["dimensions_ok", "limit_cases_ok"]
    tasks:
      - id: "2.1"
        title: "Main derivation + executable checks"
        agent: derivation_coder
        status: todo
        depends_on: []
        parallel_group: "derivation"
        acceptance_criteria: ["derivation_written", "checks_runnable", "dimensions_ok", "limit_cases_ok"]
        inputs:
          target: "main derivation"
        outputs:
          - artifacts: ["derivation.md", "checks.py"]

  - id: 3
    name: "Synthesis"
    verifier:
      agent: verifier
      criteria: ["final_report_complete"]
    tasks:
      - id: "3.1"
        title: "Assemble final report"
        agent: orchestrator
        status: todo
        depends_on: []
        parallel_group: "synthesis"
        acceptance_criteria: ["final_report_complete"]
        inputs:
          include: ["equation_bank", "derivation", "verifier_summary"]
        outputs:
          - artifacts: ["final_report.md"]
```

**Task fields (V2)**
- `title`: human-readable description.
- `depends_on`: list of task ids that must be `done` or `skipped` before the task becomes runnable.
- `parallel_group`: optional batching label. The current MVP scheduler does **not** use this for decisions (it relies on stage barriers + `depends_on`), but it’s useful for humans and future schedulers.
- `acceptance_criteria`: per-task “definition of done” (drawn from the problem spec + plan config).
- `blocked_reason`: required when `status: blocked`.
- `skip_reason`: required when `status: skipped`.
- `superseded_by`: optional pointer when `status: superseded`.

**Status values**
- `todo` → `running` → `done`
- `blocked` (missing dependency or needs human input)
- `skipped` (explicitly not needed; requires `skip_reason`)
- `superseded` (replaced by a newer task; keep originals for audit)

---

## 5) Agents (hub-and-spoke)

Note on terminology in this repo:
- The **Python scheduler** in `src/orchestrator.py` owns execution (reads the Task Graph, selects runnable tasks, runs agents, updates `RESEARCH_STATE.md`).
- The **LLM Orchestrator agent** (`orchestrator` in `configs/agents.yaml`) is just another agent used by tasks (by default task `3.1`), not the scheduler.

### 5.1 Orchestrator (Supervisor / Manager)

**Responsibilities**
- Own the Task Graph and the Research State Doc.
- Build a minimal **context pack** each cycle.
- Spawn stage tasks (parallel) and wait for completion.
- Aggregate results and decide whether to re-plan.

**Key rule**
- If verifier is `FAIL` or `CONDITIONAL`, **do not proceed** to the next stage.
  Update the task graph with follow-ups (new tasks or modified criteria).

### 5.2 LiteratureScout (Search)

**Goal**: find relevant canonical references.

**Inputs**: research question + constraints + prior candidate list.

**Outputs (structured)**
- ranked candidate list (`paper_candidates.json`)
- suggested ingestion URLs

### 5.3 PaperPoolBuilder (Deterministic pipeline, not an LLM)

**Goal**: build the document pool.

Implement as plain Python functions (idempotent):
- download PDFs
- upload to OpenAI Files
- attach to a vector store
- record metadata in SQLite

### 5.4 PaperReader (Targeted extraction)

**Goal**: retrieve definitions, assumptions, equations, and “where in the paper” evidence.

**Output**
- `equation_bank.md`
- `assumptions.md`
- `extractions.json` (claim → evidence)

### 5.5 DerivationCoder (Math + code)

**Goal**: produce derivations and executable checks.

**Output**
- `derivation.md` (key steps)
- `checks.py` (unit tests / numeric spot checks)

### 5.6 Verifier (Reflection / Red team)

Two-pass verification is recommended:
1) **Initial review** (no tools): quickly reject flawed steps.
2) **Full review** (with retrieval + code): confirm citations and acceptance tests.

**Outputs**
- `PASS | CONDITIONAL | FAIL`
- issues list + exact follow-up tasks

---

## 6) Optional “self-evolution” agents (inspired by co-scientist systems)

These are optional, but map well to your “self-evolved but human-editable” requirement:

- **Evolution agent**: proposes *new candidate approaches* without overwriting current best.
- **Ranking agent**: prioritizes hypotheses/tasks via pairwise comparisons or a lightweight tournament.
- **Proximity agent**: clusters similar hypotheses/tasks to dedupe and improve coverage.
- **Meta-review agent**: summarizes recurring failure modes and proposes **prompt/config patches**.

**Important constraint**
- Meta-review outputs must go to a **patch file** (e.g. `artifacts/runs/<run_id>/prompt_patch.md`) and require human approval before changing prompts.

---

## 7) Context control (how we keep runs stable)

### 7.1 What goes into model context

Each cycle, the orchestrator builds `context_pack.md` containing only:
- the goal + constraints
- current stage + next tasks
- top equations (≤10)
- key assumptions (≤10)
- current best answer (≤200 lines)
- verifier status + issues
- paper pool summary (top N)

Everything else stays in:
- `RESEARCH_STATE.md`
- SQLite
- vector store
- artifacts

### 7.2 What *never* goes into model context

- full PDFs
- raw dumps of long notes
- large code outputs
- any hidden chain-of-thought

---

## 8) OpenAI SDK integration notes (implementation guide)


The **OpenAI Agents SDK** is available as:
- a PyPI package (`pip install openai-agents`), or
- a vendored copy in `openai-agents-python/` (docs: https://openai.github.io/openai-agents-python/).

This repo should be implemented with:
- **Responses API** for tool use (web search, file search, code interpreter)
- **Agents SDK** for agent/model execution (per-task agent calls) and tool wiring

Keep all OpenAI-related wiring in `src/agents.py` and `src/tools_ingest.py`.

Notes on tools:
- The OpenAI “Code Interpreter” tool is a hosted sandbox container. It does **not** automatically have access to your local `artifacts/` files unless you upload them to OpenAI and pass file ids.
- Tool enablement is configured per agent in `configs/agents.yaml` (see `tools:` and `code_interpreter:`).

### 8.1 Minimal wiring sketch (Python)

This repo’s implementation uses a **deterministic, Task-Graph-driven scheduler**:
- `src/orchestrator.py` reads the Task Graph from `RESEARCH_STATE.md`
- selects the agent via `task.agent`
- runs runnable tasks in parallel via `asyncio.gather(...)`
- executes each agent via the OpenAI Agents SDK `Runner.run(...)`

```python
import asyncio

from pathlib import Path

from agents import Runner

from src.agents import build_agents
from src.config import load_config

async def main():
    config = load_config("configs/agents.yaml")
    agents = build_agents(config, Path("prompts"))
    payload = {
        "task_id": "1.1",
        "task_title": "Search + rank candidate papers",
        "inputs": {"query_hints": []},
        "context_pack": "...",
        "run_id": "run_...",
    }
    result = await Runner.run(agents["literature_scout"], payload)
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

Notes:
- Deterministic fan-out/fan-in happens in `src/orchestrator.py` via `asyncio.gather(...)`.
- Treat ingestion (downloading/uploading/indexing PDFs) as **plain Python**, not an LLM agent.

---

## 9) Orchestration loops (local CLI + Restate)

### 9.1 Local deterministic loop (CLI)

For each cycle:

1) Load `RESEARCH_STATE.md`
2) Parse + validate `TASK_GRAPH_V*`
3) Pick the **lowest stage id** with unfinished tasks
4) Build `context_pack.md`
5) Pick the runnable set in that stage (one “wave”):
   - tasks with `status: todo` whose `depends_on` are all `done`/`skipped`
6) Run that runnable set in parallel (async gather)
7) Persist each task’s structured output to `agent_outputs/<task_id>.json`
8) Append summarized results into `RESEARCH_STATE.md` under that task id
9) Optional: if `task_verification` is enabled for a task, run the Verifier as an LLM judge against the task’s `acceptance_criteria`
10) If task verification is not PASS: inject follow-up tasks into the same stage and stop (`stop_reason=verifier_blocked`)
11) If the stage is now complete (`done`/`skipped`), run the **stage verifier**
12) If verifier PASS: next cycle advances to the next stage
13) If verifier not PASS: update the task graph with follow-ups, and stop (`stop_reason=verifier_blocked`)

Finalization:
- run final verifier
- write `final_report.md` (if the Task Graph includes a task that outputs it; default stage `3.1`)

### 9.2 Restate durable loop (service/workflow)

In durable mode, the *same* Task Graph is executed inside Restate handlers so the run can recover from crashes, retries, and long waits without losing progress. The core ideas (from the Restate OpenAI Agents SDK integration docs) are:

- Wrap agent runs with `DurableRunner.run(...)` so LLM calls are persisted and replayable.
- Wrap non-deterministic steps with `ctx.run(...)` (current implementation) or `@durable_function_tool` if you add durable tool wrappers.
- For parallel subtasks, you can start multiple durable calls and then `await restate.gather(...)` to fan-in.
  - Note: the current MVP implementation runs a whole “wave” inside a single `ctx.run(...)` call and parallelizes tasks via `asyncio.gather(...)`. For stronger per-task durability/isolation, refactor to `ctx.run(...)` per task + `restate.gather(...)`.

**Suggested handler flow**
1) `Orchestrator/init`: create `run_id`, write an initial `RESEARCH_STATE.md`, and return `run_id`.
2) `Orchestrator/step`: load doc → parse/validate task graph → execute *one* runnable wave (or one stage) → run verifier → persist updates → return a status summary.
3) `Orchestrator/run`: loop `step` until stop criteria are met, then return a status summary (the run artifacts include `final_output.md` and optionally `final_report.md`).

**Human-in-the-loop**
- When a task becomes `blocked` on human input, create an **awakeable** and store its id in the Research State Doc.
- The workflow can `await` the awakeable promise and resume when the human resolves it (approval/extra info).

Keep the canonical “Research State Doc is source of truth” invariant: Restate is the execution engine, but the doc remains the audit log + user-editable control surface.


---

## 10) Development rules (for Codex)

When Codex modifies the repo:

- Keep the system runnable end-to-end with the CLI (`init`, `step`, `run`).
- Add **at least one** smoke test (`python -m src.main --help` is acceptable for MVP).
- Avoid large refactors unless requested.
- Never hardcode secrets.
- Do not change the Task Graph schema without updating this file.

- If you change any agent execution semantics, update **both**:
  - local CLI mode (`src/`), and
  - Restate durable mode (`restate/`), including handler schemas and registration docs.
- Keep `restate/` runnable locally (start `restate-server`, run the service, register deployments, invoke a handler).
