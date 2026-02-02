# Research State Doc

## Header
- run_id: run_20260202_020706_5720
- created_at: 2026-02-02T02:07:06.121990+00:00
- last_updated: 2026-02-02T02:07:06.121990+00:00
- question:
  ````md
  Here is a question.
  
  ```tex
  E=mc^2
  ```
  
  More text.
  ````
- config_snapshot:
```yaml
models:
  default: gpt-4.1-mini
  orchestrator: gpt-4.1-mini
  literature_scout: gpt-4.1-mini
  paper_reader: gpt-4.1-mini
  derivation_coder: gpt-4.1-mini
  verifier: gpt-4.1-mini
vector_store_id: ''
model_settings:
  default:
    temperature: 0.2
    parallel_tool_calls: true
  per_agent: {}
prompts:
  default_dir: prompts
  per_agent:
    orchestrator: prompts/orchestrator.md
    literature_scout: prompts/literature_scout.md
    paper_reader: prompts/paper_reader.md
    derivation_coder: prompts/derivation_coder.md
    verifier: prompts/verifier.md
review:
  default: auto
  per_agent: {}
  per_task: {}
task_verification:
  default: none
  per_agent: {}
  per_task: {}
providers:
  default:
    openai:
      api_key: ''
      base_url: ''
      organization: ''
      project: ''
      use_responses: true
  per_agent: {}
tools:
  default: null
  per_agent: {}
code_interpreter:
  memory_limit: 1g
```

## Problem spec
# Problem Spec (edit me)

## Goal
Define the physics research question and expected deliverables.

## Constraints
- Cite primary sources when available.
- Provide clear assumptions and notation.
- Include dimensional and limit-case checks.

## Acceptance tests
- A coherent derivation is produced.
- Key equations and assumptions are listed.
- Verifier PASS for each stage.

## Current best answer
_TBD_

## Task Graph (machine-readable)
```yaml
# TASK_GRAPH_V2
version: 2
stages:
- id: 1
  name: Literature + definitions
  verifier:
    agent: verifier
    criteria:
    - citations_present
    - notation_defined
  tasks:
  - id: '1.1'
    title: Search + rank candidate papers
    agent: literature_scout
    status: todo
    depends_on: []
    parallel_group: search
    acceptance_criteria:
    - paper_candidates_written
    - citations_present
    inputs:
      query_hints: []
    outputs:
    - artifacts:
      - paper_candidates.json
  - id: '1.2'
    title: Extract definitions + assumptions from paper pool
    agent: paper_reader
    status: todo
    depends_on:
    - '1.1'
    parallel_group: extraction
    acceptance_criteria:
    - notation_defined
    - assumptions_listed
    - citations_present
    inputs:
      focus: definitions + assumptions
    outputs:
    - artifacts:
      - equation_bank.md
      - assumptions.md
      - extractions.json
- id: 2
  name: Derivation + computational checks
  verifier:
    agent: verifier
    criteria:
    - dimensions_ok
    - limit_cases_ok
  tasks:
  - id: '2.1'
    title: Main derivation + executable checks
    agent: derivation_coder
    status: todo
    depends_on: []
    parallel_group: derivation
    acceptance_criteria:
    - derivation_written
    - checks_runnable
    - dimensions_ok
    - limit_cases_ok
    inputs:
      target: main derivation
    outputs:
    - artifacts:
      - derivation.md
      - checks.py
- id: 3
  name: Synthesis
  verifier:
    agent: verifier
    criteria:
    - final_report_complete
  tasks:
  - id: '3.1'
    title: Assemble final report
    agent: orchestrator
    status: todo
    depends_on: []
    parallel_group: synthesis
    acceptance_criteria:
    - final_report_complete
    inputs:
      include:
      - equation_bank
      - derivation
      - verifier_summary
    outputs:
    - artifacts:
      - final_report.md
```

## Task Board (human-readable)
### Stage 1: Literature + definitions
- [ ] 1.1 Search + rank candidate papers (todo)
- [ ] 1.2 Extract definitions + assumptions from paper pool (todo)

### Stage 2: Derivation + computational checks
- [ ] 2.1 Main derivation + executable checks (todo)

### Stage 3: Synthesis
- [ ] 3.1 Assemble final report (todo)

## Results ledger
### 1.1 Search + rank candidate papers
- status: todo
- summary:
  _pending_
- artifacts:
  - _none_
- evidence:
  - _none_

### 1.2 Extract definitions + assumptions from paper pool
- status: todo
- summary:
  _pending_
- artifacts:
  - _none_
- evidence:
  - _none_

### 2.1 Main derivation + executable checks
- status: todo
- summary:
  _pending_
- artifacts:
  - _none_
- evidence:
  - _none_

### 3.1 Assemble final report
- status: todo
- summary:
  _pending_
- artifacts:
  - _none_
- evidence:
  - _none_

## Evidence / citations ledger
### 1.1
- evidence:
  - _none_

### 1.2
- evidence:
  - _none_

### 2.1
- evidence:
  - _none_

### 3.1
- evidence:
  - _none_

## Verifier status
- stage_verifier: not_run
- final_verifier: not_run

## History log
- 2026-02-02T02:07:06.121990+00:00: init run
