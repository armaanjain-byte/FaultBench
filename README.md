# FaultBench

> Stress-test coding agents under adversarial runtime conditions.

FaultBench benchmarks how reliably AI coding agents operate when the environment becomes unstable, corrupted, inconsistent, or partially broken.

Most agent benchmarks measure:

* correctness in ideal conditions
* task completion on static repos
* benchmark scores in clean environments

Real engineering environments are not clean.

Dependencies drift. Configs break. Files disappear. APIs change. Schemas mutate.

FaultBench measures whether agents can survive that reality.

---

# Core Idea

A coding agent is given a software engineering task inside an isolated sandbox.

FaultBench then injects controlled environmental mutations before execution:

* dependency drift
* schema drift
* config corruption
* missing files
* API contract changes

The platform measures:

* task success degradation
* retries
* runtime inflation
* token overhead
* failure patterns
* recovery behavior

The result is a reproducible robustness benchmark for AI coding agents.

---

# Why This Exists

Current benchmarks like SWE-bench primarily evaluate correctness under stable environments.

That leaves a major blind spot:

> Can the agent recover when the environment becomes unreliable?

A model that solves tasks in ideal conditions may completely collapse under small runtime perturbations.

FaultBench isolates and measures that robustness gap.

---

# Key Capabilities

## Benchmark Coding Agents

Evaluate:

* OpenHands
* Claude-based agents
* Cursor-style agents
* local autonomous agents
* future multi-agent systems

---

## Controlled Runtime Mutations

FaultBench injects deterministic failures such as:

| Mutation Type     | Example                      |
| ----------------- | ---------------------------- |
| Schema Drift      | rename DB column             |
| Dependency Drift  | incompatible package version |
| Config Corruption | malformed YAML               |
| Missing File      | deleted utility module       |
| API Drift         | changed response structure   |

---

## Execution Isolation

Every run executes inside Docker sandboxes for:

* reproducibility
* safety
* deterministic environments
* clean resets

---

## Rich Failure Metrics

FaultBench captures:

* success rate
* retries
* runtime
* token consumption
* crash count
* first failure step
* execution traces

---

## Comparative Reporting

Compare:

* baseline vs mutated
* agent vs agent
* mutation vs mutation
* task robustness distributions

---

# Example Finding

| Mutation          | Baseline | Mutated | Degradation |
| ----------------- | -------- | ------- | ----------- |
| Schema Drift      | 81%      | 34%     | -58%        |
| Dependency Drift  | 78%      | 41%     | -47%        |
| Config Corruption | 81%      | 29%     | -64%        |
| Missing File      | 81%      | 22%     | -73%        |

---

# System Architecture

```text
Task Repo
    ↓
Mutation Injector
    ↓
Sandbox Runner (Docker)
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

---

# Repository Structure

```text
faultbench/
│
├── backend/
├── frontend/
├── workers/
├── sdk/
├── benchmarks/
├── tasks/
├── reports/
├── docs/
├── docker/
├── scripts/
├── tests/
│
├── db/
├── logs/
│
├── config.yaml
├── docker-compose.yml
├── requirements.txt
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── .env.example
```

---

# Technical Stack

| Layer         | Stack                |
| ------------- | -------------------- |
| Backend       | Python + FastAPI     |
| Sandbox       | Docker               |
| Queue         | Celery / Dramatiq    |
| Database      | SQLite initially     |
| Reporting     | Jinja2 + Matplotlib  |
| Frontend      | Next.js              |
| Agent Runtime | OpenHands-compatible |
| Orchestration | Docker Compose       |

---

# Design Principles

## Reproducibility First

Every benchmark run must be reproducible on another machine.

No hidden infrastructure.
No cloud dependencies required.

---

## Mutations Must Be Causal

A mutation is only valid if it directly affects the execution path of the task.

Random corruption produces meaningless data.

---

## Aggregate Over Single Runs

Agents are nondeterministic.

FaultBench compares distributions and averages over multiple runs rather than isolated outcomes.

---

## Minimal Infrastructure

SQLite over Postgres initially.
Docker Compose over Kubernetes.

Complexity kills research tooling early.

---

# Metrics Collected

| Metric             | Purpose                   |
| ------------------ | ------------------------- |
| success            | primary completion signal |
| retry_count        | detects looping/flailing  |
| runtime_seconds    | execution overhead        |
| tokens_used        | instability cost          |
| exception_count    | crash frequency           |
| first_failure_step | degradation localization  |

---

# Initial Roadmap

## v1

* pre-execution mutations
* OpenHands integration
* SQLite benchmark storage
* HTML reports
* 5 benchmark tasks
* reproducible local runs

---

## v2

* mid-execution mutations
* multi-agent comparisons
* distributed benchmarking
* replayable traces
* visual benchmark dashboard

---

## v3

* mutation generation engine
* benchmark marketplace
* public leaderboard
* robustness scoring standard

---

# Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/faultbench.git

cd faultbench

cp .env.example .env

docker compose up

python main.py benchmark
```

---

# Differentiation

| Benchmark  | Measures                                   |
| ---------- | ------------------------------------------ |
| SWE-bench  | correctness                                |
| HumanEval  | code generation                            |
| MMLU       | reasoning                                  |
| FaultBench | robustness under environmental instability |

FaultBench is not competing with existing benchmarks.

It measures a different axis entirely.

---

# Research Questions

FaultBench aims to answer:

* Which mutations degrade agents most severely?
* Which agents recover effectively?
* Are retries useful or wasteful?
* How costly is environmental instability?
* Where do autonomous coding systems break first?

---

# Long-Term Goal

Create the standard robustness benchmark for autonomous software engineering agents.

Not “can the agent solve the task?”

But:

> “Can the agent still solve the task when reality becomes messy?”

Based on your uploaded baseline specification and architecture notes. 
