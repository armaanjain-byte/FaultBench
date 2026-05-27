# FaultBench

> Stress-test coding agents under adversarial runtime conditions.

FaultBench benchmarks AI coding agent robustness by injecting controlled environmental failures into software engineering tasks.

Most benchmarks measure correctness in clean environments. Real environments are not clean.

---

## The Problem

SWE-bench, HumanEval, and similar benchmarks answer: *can the agent solve the task?*

They don't answer: *can the agent solve the task when the environment breaks?*

Dependencies drift. Configs corrupt. Files disappear. APIs change schemas mid-workflow. A model that achieves 40% on SWE-bench in a stable sandbox may collapse entirely when a single config value is malformed.

FaultBench isolates and measures that robustness gap.

---

## How It Works

A coding agent is given a software engineering task inside a Docker sandbox.

FaultBench injects a controlled mutation into the environment before or during execution:

```
Task Repo
    ↓
Mutation Injector  ←── deterministic, causal, reproducible
    ↓
Docker Sandbox
    ↓
Coding Agent
    ↓
Execution Trace Collector
    ↓
Metrics Extractor
    ↓
SQLite Benchmark DB
    ↓
Comparator + Report Generator
```

After execution, FaultBench records success rate, retry count, runtime, token usage, crash count, and first failure step — then diffs baseline vs. mutated performance.

---

## Mutation Types

| Mutation | Example | What It Tests |
|---|---|---|
| **Schema Drift** | Rename a database column the agent depends on | Can the agent detect and adapt to interface changes? |
| **Dependency Drift** | Pin a package to an incompatible version | Does the agent handle import failures gracefully? |
| **Config Corruption** | Inject malformed YAML into the app config | Does the agent debug config errors or loop? |
| **Missing File** | Delete a utility module mid-task | Can the agent reconstruct or route around missing dependencies? |
| **API Drift** | Change a response schema the agent parses | Does the agent handle contract violations? |

All mutations are deterministic and causal — they directly affect the task execution path. Random corruption produces noise, not signal.

---

## Example Results

<!-- Results chart placeholder -->
![Robustness degradation chart](docs/results_chart.png)

| Mutation | Baseline | Mutated | Degradation |
|---|---|---|---|
| Schema Drift | 81% | 34% | **-58%** |
| Dependency Drift | 78% | 41% | **-47%** |
| Config Corruption | 81% | 29% | **-64%** |
| Missing File | 81% | 22% | **-73%** |

Config corruption and missing files are the hardest failures. Agents that handle dependency drift reasonably often collapse completely when a utility module disappears.

---

## Metrics Collected

| Metric | Purpose |
|---|---|
| `success` | Primary task completion signal |
| `retry_count` | Detects looping and flailing behavior |
| `runtime_seconds` | Measures execution overhead under instability |
| `tokens_used` | Quantifies recovery cost in context budget |
| `exception_count` | Crash frequency per run |
| `first_failure_step` | Localizes where degradation begins |

FaultBench aggregates over multiple runs rather than reporting single-trial outcomes. Agents are nondeterministic; distributions are meaningful, individual results are not.

---

## Differentiation

| Benchmark | What It Measures |
|---|---|
| SWE-bench | Correctness on real GitHub issues (stable env) |
| HumanEval | Code generation quality |
| MMLU | General reasoning |
| **FaultBench** | **Robustness under environmental instability** |

FaultBench is not a replacement for SWE-bench. It measures a different axis: not whether an agent can solve a task, but whether it can still solve it when the environment degrades.

---

## Technical Stack

| Layer | Technology |
|---|---|
| Backend | Python + FastAPI |
| Sandbox | Docker |
| Task Queue | Celery / Dramatiq |
| Database | SQLite |
| Reporting | Jinja2 + Matplotlib |
| Frontend | Next.js |
| Agent Runtime | OpenHands-compatible |
| Orchestration | Docker Compose |

---

## Design Principles

**Reproducibility first.** Every benchmark run must reproduce on another machine. No hidden infrastructure, no cloud dependencies required.

**Mutations must be causal.** A mutation only counts if it directly affects the task execution path. Irrelevant mutations produce noise, not signal.

**Aggregate, don't cherry-pick.** Metrics are distributions over multiple runs, not single-trial outcomes.

**Minimal infrastructure.** SQLite over Postgres. Docker Compose over Kubernetes. Complexity kills research tooling early.

---

## Repository Structure

```
faultbench/
│
├── backend/           # FastAPI server, job orchestration
├── frontend/          # Next.js dashboard
├── workers/           # Celery/Dramatiq task workers
├── sdk/               # Python SDK for defining tasks and mutations
├── benchmarks/        # pre-defined benchmark task definitions
├── tasks/             # individual task repos
├── reports/           # generated benchmark reports
├── docs/              # screenshots, architecture diagrams
├── docker/            # Dockerfile definitions
├── scripts/           # setup and utility scripts
├── tests/             # test suite
│
├── config.yaml
├── docker-compose.yml
├── requirements.txt
├── CONTRIBUTING.md
└── .env.example
```

---

## Quick Start

```bash
git clone https://github.com/armaanjain-byte/faultbench.git
cd faultbench

cp .env.example .env

docker compose up

python main.py benchmark
```

---

## Roadmap

**v1 — Local, reproducible benchmarks**
- Pre-execution mutations
- OpenHands agent integration
- SQLite benchmark storage
- HTML reports
- 5 benchmark tasks

**v2 — Scale + comparison**
- Mid-execution mutations (injected during agent run)
- Multi-agent comparisons
- Distributed benchmarking
- Replayable traces
- Visual benchmark dashboard

**v3 — Standard + ecosystem**
- Mutation generation engine
- Benchmark task marketplace
- Public leaderboard
- Robustness scoring standard

---

## Research Questions FaultBench Answers

- Which mutation types degrade agents most severely?
- Which agents exhibit robust recovery vs. hard failure?
- Are retry loops useful or wasteful under environmental instability?
- What is the token cost of degraded environments?
- Where do autonomous coding systems break first?

---

## Long-Term Goal

Establish the standard robustness benchmark for autonomous software engineering agents.

Not *"can the agent solve the task?"*

But: *"can the agent still solve it when reality becomes messy?"*

---

## Author

**Armaan Jain** · [github.com/armaanjain-byte](https://github.com/armaanjain-byte)

---

## License

Apache - 2.0 License
