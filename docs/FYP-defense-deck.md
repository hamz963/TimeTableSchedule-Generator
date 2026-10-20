---
marp: true
theme: default
paginate: true
header: "FYP Defence — Time Table Schedule Generator"
---

<!--
SOURCE OF TRUTH for the defence deck.
Render to HTML with:  python docs/build_deck.py
(also prints a PDF via the browser's Print → Save as PDF, landscape.)

Replace every [BRACKETED] placeholder before the defence.
-->

# Time Table Schedule Generator
## Constraint-based university timetable optimization

**Final Year Project — Defence Presentation**

**[Your Full Name]** · [Registration No.]
Supervisor: **[Supervisor Name]**
[Department], [University]
[Month Year]

---

## Agenda

1. Problem & motivation
2. Aim, objectives, scope
3. Literature review & the gap
4. Methodology
5. System architecture & algorithms
6. Implementation
7. Testing & evaluation
8. **Results** (measured, with numbers)
9. Contributions, limitations, future work
10. FYP compliance, project management, ethics
11. Demo & Q&A

---

# 1. The problem

<!-- the "why" of the project -->

---

## Timetabling is a solved-looking, unsolved problem

- Every university must place **every course session** into a **(time slot, room, teacher)** triple.
- Doing it **by hand** in a spreadsheet/ERP takes **days to weeks**, and every change cascades.
- Constraints are **hard** (no teacher/room/student-group can be in two places at once) and **soft** (preferences, fairness, compactness).
- The problem is **NP-hard**: search space for a modest college (400 sessions × 60 slots × 40 rooms) is astronomically large.
- Result in practice: clashes, overloaded teachers, half-empty rooms, timetable pages republished all semester.

**Core problem statement**

> University timetabling is a constraint-satisfaction and optimization problem that humans solve slowly, inconsistently and without any measure of *quality* — and that commercial tools solve behind a closed, expensive box.

---

## Stakeholders & impact

| Stakeholder | Pain today | What this project changes |
|---|---|---|
| Timetable / academic office | Days of manual work per semester, error-prone edits | Generates a conflict-free timetable in **seconds**, with a re-solve button |
| Teachers | Unfair day loads, ignored preferences | Preferences and fairness are **optimized and measurable** |
| Students | Clashes, long idle gaps, late/evening sessions | Fewer clashes, preferred time bands honoured |
| Rooms & labs | Wasted capacity, blocked labs | Room-fit and utilisation are part of the objective |
| Institution | Licensing cost of commercial schedulers | Deployable, containerized, self-hosted, open stack |

---

# 2. Aim, objectives, scope

---

## Aim

> Build a **constraint-based optimization engine** that turns a university's teachers, rooms, slots and courses into a conflict-free, quality-optimized timetable in seconds, exposes *why* the timetable looks the way it does, and lets a scheduler express real institutional policy as declarative rules.

---

## Objectives (SMART) — and how each is verified

| # | Objective | Verification (Evidence) | Status |
|---|---|---|---|
| O1 | Model the timetabling problem as a constraint-satisfaction + optimization problem | `ProblemContext` model + normalized problem definition | ✅ |
| O2 | Produce conflict-free schedules (all hard constraints) | `engine/constraints.py` independent auditor; **0 violations** on every test instance | ✅ |
| O3 | Optimize *quality*, not just feasibility | 0–100 composite score (5 weighted sub-scores) + optimizer vs greedy benchmark | ✅ |
| O4 | Let non-programmers express policy as rules | 7 declarative rule kinds, all enforced by optimizer **and** verifier; the 5 hard ones compiled into CP-SAT | ✅ |
| O5 | Handle realistic scale with bounded time | **1 200-session realistic instance in 3.67 s** (0 violations); 2 000 sessions in 7.8 s; 64 concurrent solves | ✅ |
| O6 | Explain the result and learn preferences | Explainability endpoint + ML preference model from feedback | ✅ |
| O7 | Package for real deployment | Docker Compose (API + Postgres + Redis + dashboard), 137 tests | ✅ |

---

## Scope

**In scope**
- University *course* timetabling (lectures/tutorials sections, weekly slot grid)
- Hard constraints: teacher, room, student-group clash-freedom; availability; capacity
- Soft objectives: preferences, time bands, room efficiency, fairness, compactness
- Multi-user scheduler workflow (auth, roles, run history, versioned edits)
- Web dashboard, CSV/Excel data import, export to file

**Out of scope (deliberate)**
- Full exam timetabling & invigilation
- ERP/student-record integration (single sign-on, SIS APIs)
- Payroll/HR workflows, mobile apps
- Guaranteed *proof* of optimality at scale (see limitations)

---

# 3. Literature & the gap

---

## Related work

| Approach | Representative | Strength | Weakness |
|---|---|---|---|
| Graph colouring / heuristics | Classic timetabling literature | Fast, simple | Feasibility only, no quality objective |
| Metaheuristics (SA, GA, TS) | Simulated annealing / genetic timetabling | Good quality at scale | No optimality guarantee; tuning-heavy |
| Constraint programming / SAT | CP / CP-SAT models | Provably optimal on small/medium instances | Blows up beyond a size threshold |
| Commercial schedulers | Vendor ERP modules | Feature-rich | Closed, expensive, inflexible policy model |

---

## The gap this project fills

1. Most academic prototypes stop at **feasibility** — they never quantify *how good* the timetable is.
2. Rules are hard-coded in the solver, so **institutional policy can't be changed without editing code**.
3. Feasibility and quality are rarely **verified by an independent auditor** — the solver's own word is taken.
4. Little attention to the **human workflow**: who edits, who approves, how changes are audited, what the result *means*.

---

## Research / technical questions

- **RQ1** — Can a two-tier solver (exact CP-SAT + simulated annealing) give **provably-optimal** results on small instances and **bounded-time, verified-feasible** results at scale?
- **RQ2** — Does metaheuristic optimization measurably beat a constructive greedy baseline on *quality*, and by how much per second of compute?
- **RQ3** — Can institutional policy be expressed as **declarative rules** that simultaneously drive the solver, the objective function and the verifier?
- **RQ4** — Can the system state a **transparent, reproducible quality score** with human-readable explanations, instead of an opaque success/failure?

---

# 4. Methodology

---

## Design & development methodology

- **Design Science Research** framing: artefact → demonstration → evaluation (Hevner-style), because the contribution is a *working engineering artefact* plus measured evidence.
- **Agile/incremental sprints** for build: each sprint ends in a green test suite + a demo-able increment.
- **Evidence-first engineering**: every performance claim in this deck is a number produced by a script in the repository, reproducible by the examiner.
- **Correctness strategy**: the verifier is written **independently** of the solver and used as the test oracle (never trust the optimizer's own report).

```
Design → Implement → Verify (independent auditor) → Measure → Report → Iterate
```

---

## Tools & technology stack

| Layer | Technology | Why |
|---|---|---|
| Optimization | Python 3.12, **OR-Tools CP-SAT 9.15** | State-of-the-art CP-SAT solver |
| Metaheuristic | Custom simulated annealing + greedy descent | Scales past the exact solver's limit |
| Backend API | **FastAPI**, Pydantic, SQLAlchemy, Alembic | Typed, async-capable, auto-documented |
| Storage | **PostgreSQL 16** (SQLite in tests) | Relational integrity for runs/rules/users |
| Cache & bus | **Redis 7** | Shared chat state + cross-replica event bus |
| ML | scikit-learn RandomForest | Learn teacher preferences from feedback |
| Frontend | **Next.js 14 / React / TypeScript / Tailwind** | Modern dashboard with SSR + typed API client |
| Real-time | Server-Sent Events | Live solve/progress updates without polling |
| Packaging | **Docker + Docker Compose**, pytest, GitHub | One-command reproducible deployment |

---

# 5. Architecture

---

## Layered engine architecture

```
┌─────────────┐   POST /schedule/generate-simple   ┌────────────────────────────────┐
│  Next.js    │ ─────────────────────────────────▶ │  FastAPI                       │
│  dashboard  │ ◀───────────────────────────────── │  ┌──────────────────────────┐  │
└─────────────┘   assignments + quality + engine    │  │ engine/pipeline.py       │  │
      ▲  SSE /events/stream                         │  │ exact | heuristic path   │  │
      └───────────────────────────────────────────┐ │  ├ exact.py      (CP-SAT)  │  │
                                                  │ │  ├ heuristic.py  (greedy)  │  │
                                                  │ │  ├ optimizer.py  (SA)      │  │
                                                  │ │  ├ rules.py      (policy)  │  │
                                                  │ │  ├ objectives.py (soft)    │  │
                                                  │ │  ├ constraints.py(verify)  │  │
                                                  │ │  └ metrics.py    (score)   │  │
                                                  │ └──────────────────────────┘  │
                                                  └───────────────┬────────────────┘
                                                                  │ persist
                                                       ┌──────────▼──────────┐
                                                       │  PostgreSQL · Redis │
                                                       └─────────────────────┘
```

**Key design decision:** every derived structure (day order, slot indexes, occupancy keys) is computed **once** in a shared `ProblemContext` and reused by the heuristic, the optimizer, the verifier and the metrics — so all four agree by construction.

---

## Two-tier solve pipeline

```
request ─▶ build_context ─▶ greedy feasible seed
                                   │
                ┌──────────────────┴───────────────────┐
                │                                      │
        small instance                          large instance
        (≤ threshold)                            (> threshold)
                │                                      │
       CP-SAT exact search                simulated annealing + greedy descent
       "optimal"/"feasible"               time-budgeted "feasible, improved"
                │                                      │
                └──────────────┬───────────────────────┘
                               ▼
            independent hard-constraint audit (constraints.verify)
                               ▼
           0–100 quality score + explanation + engine telemetry
                               ▼
                  persist run → SSE event → dashboard
```

**Why two tiers:** CP-SAT gives *proven* optimality where it fits; SA keeps the system useful where it doesn't. The API reports honestly which path ran (`engine.path`) and whether the search had settled (`converged`).

---

## Algorithm 1 — CP-SAT exact model

- Boolean variable `x[course, venue, slot]` for every allowed placement.
- **Hard**: exactly one placement per course; at-most-one per (teacher, slot), (room, slot), (student group, slot); availability and capacity filters; every declarative hard rule encoded as `Add(var == 0)` / `Add(var == 1)`.
- **Soft**: weighted objective terms for preference hits, time-band fit, room waste, fairness (max day load), compactness.
- **Budget**: `solver_time_limit_seconds` (default 5 s) + 8 parallel search workers.
- Reports `OPTIMAL` / `FEASIBLE` / `INFEASIBLE`. The result is audited before it is returned; if a hard rule could not be encoded, or the audit fails, the solver falls back to the verified heuristic path instead of labelling a broken timetable "optimal".

---

## Algorithm 2 — simulated annealing

- Starts from the greedy seed; moves a random session to a new (venue, slot).
- **Acceptance**: improvement always; worsening accepted with `exp(-Δ/T)`, geometric cooling.
- **Move legality** enforced by the same rule registry (`placement_allowed`, `move_ok`) → hard constraints never break.
- **Guarantee added during this project**: the optimizer never returns a result with a higher internal cost than the seed it started from, and on 25 randomised instances the reported quality score never dropped (median +3.90).
- **Deterministic mode**: `max_iterations` + fixed seed ⇒ byte-identical results for reproducibility.

---

## Declarative rule engine (policy as data)

Seven built-in rule kinds. All seven are enforced by the metaheuristic and audited by the independent verifier; the five hard kinds are also compiled into the CP-SAT model:

| Kind | Type | Meaning |
|---|---|---|
| `forbid_slot` | hard | course/teacher/room may not use given slots or days |
| `fixed_slot` | hard | pin a course to a slot (optionally a room) |
| `course_before` | hard | every session of course A precedes every session of B |
| `same_day` | hard | listed courses meet on the same day |
| `no_same_day` | hard | two courses never share a day |
| `preferred_day` | soft | reward placing a course on given days |
| `spread_sessions` | soft | reward spreading a course's sessions across days |

Each rule implements: `placement_allowed` (hard, local) · `move_ok` (hard, relational) · `penalty` (soft cost) · `full_check` (hard audit) · `cp_compile` (encode into CP-SAT).

⇒ **The same rule object drives the exact solver, the metaheuristic, the objective function and the independent verifier.** Policy changes require no code changes.

---

# 6. Implementation

---

## Quality score & explainability

Composite 0–100 score from five transparent sub-scores (weights renormalized over the components a problem actually has):

| Sub-score | Weight | Measures |
|---|---|---|
| Preference satisfaction | 35% | sessions in a teacher-preferred slot |
| Time-band satisfaction | 20% | Morning/Afternoon/Evening request honoured |
| Room efficiency | 20% | required seats ÷ room capacity (waste penalty) |
| Fairness | 15% | busiest day vs. the lightest day-load the sessions allow |
| Compactness | 10% | idle gaps inside a teacher's day |

Grades: `excellent ≥90`, `good ≥75`, `fair ≥60`, `weak ≥40`, else `poor`.

`GET /quality/{run_id}` returns the score, sub-scores, per-teacher workload/notes and **plain-language reasons** ("34/41 sessions landed in a teacher-preferred slot"). Each sub-score is a 0–1 normalisation of the *same* objective term the optimizer minimises, so score and search can't drift apart.

---

## Service & API surface

- **33 REST paths / 36 operations across 14 router modules** (OpenAPI-verified): `schedule`, `constraints`, `timetable`, `quality`, `events`, `views`, `export`, `upload`, `teachers`, `chat`, `feedback`, `ml`, `auth`, `health`.
- **Auth & authorization**: JWT login, `admin` / `scheduler` / `viewer` roles, row-scoped access to runs.
- **Data import**: CSV **and** Excel (`.xlsx`) upload with per-row validation errors and preview — an equivalence test proves uploaded data and typed table data produce a **byte-identical solver problem**.
- **Edits & versioning**: manual session moves are re-verified against the rule set; rejected moves return the violated rule.
- **Export**: CSV/ICS/printable views; saved view configurations.
- **Rate limiting**: pure-ASGI per-IP token bucket (SSE-safe), configurable, disabled in tests.
- **Real-time**: SSE progress + completion events; `GET /events/recent` for backfill.

---

## Dashboard (Next.js 14)

| Page | Purpose |
|---|---|
| `/schedule/easy` | guided builder: teachers, courses, rooms, days, breaks |
| `/data` | CSV/Excel upload, validation report, preview |
| `/schedule/[id]` | timetable grid, quality panel, manual drag-edit, export |
| `/constraints` | create/toggle declarative rules with live validation |
| `/analytics` | score breakdown, room utilisation, per-teacher load |
| `/benchmark` | run greedy-vs-optimized comparison from the UI |
| `/chat` | AI assistant: explains the timetable, proposes rules |
| `/teacher` | teacher profile & preferences |
| `/login` | JWT sign-in and session handling |
| `/health` | live component status (API, DB, Redis, solver, ML) |

Production build: **13 pages (14 built routes)**, 87.3 kB shared JS — a lightweight front-end for a heavy back-end.

---

## ML & AI components

**Preference learning (supervised)**
- Feedback (accept/reject + reason) on generated timetables → feature extraction → **RandomForest** classifier + scaler persisted with a version, sample count and accuracy.
- `POST /ml/retrain` trains synchronously and records the evaluation; `POST /ml/suggest` returns suggested preferred time-of-day and candidate slot ids for a teacher's load.
- Honest caveat surfaced on the dashboard: with little feedback, reported accuracy is close to memorization — the loop is designed to improve as real feedback accumulates.

**Rule-aware chat assistant**
- Deterministic intent layer answers scheduling questions from the *live* problem state ("which teachers are overloaded on Thursday?", "add a rule: Dr Ali never on Friday").
- Optional LLM (Gemini) polishing when `GEMINI_API_KEY` is set — the system is fully functional without it (no external dependency in the critical path).
- Conversations are held in Redis when configured, so state survives restarts and is shared across replicas.

---

# 7. Testing & evaluation

---

## Testing strategy — 137 automated tests

| Layer | What it proves |
|---|---|
| Engine unit tests | greedy heuristic, rules, verifier, metrics, SA optimizer, CP-SAT path |
| Constraint tests | every declared rule is enforced (and reported when violated) |
| API/integration | schedule, quality, rules, views/export, teachers, upload, auth |
| **Equivalence tests** | CSV upload and typed input produce identical solver problems |
| Security tests | JWT required, role enforcement, row-scoping, rate-limit trips |
| Redis/state tests | chat state + event delivery across replicas, with memory fallback |
| Performance tests | bounded solve time, parallel solves |
| **Soak tests** | 200-faculty solve, 64 concurrent solves, 80-request latency distribution |

**Result: `137 passed` in 2 m 08 s** (`pytest tests/ -q`); the front-end passes ESLint, 11 Vitest tests and a clean `next build`.

*Note:* the soak/performance tests assert correctness + bounded time; they print the raw numbers (below) rather than hiding them behind a threshold.

---

## Evaluation method

- **Correctness oracle**: `engine/constraints.verify` — independent of the solver — must return **zero** violations. Every soak/perf test asserts this.
- **Quality benchmark**: same instance solved twice (greedy seed vs. optimizer) → cost, quality score, iterations, and post-optimization violations.
- **Scale test**: 200 faculty / 40 rooms / 400 courses / 60 slots, 5 s budget.
- **Concurrency test**: 64 solves of a 100-course instance across 16 threads.
- **API latency**: 80 sequential `POST /schedule/generate-simple` calls, p50/p95/max.
- **Reproducibility**: fixed seed + `max_iterations` ⇒ identical output; benchmark endpoint accepts seed & budget.

---

# 8. Results

---

## RQ2 — does optimization actually pay? (measured)

Instance: 50 teachers / 20 rooms / 100 courses / 40 slots, seed 12345. Greedy is identical in every run (objective cost **−1390.0**, quality **79.5**).

| Optimizer budget | Objective cost | Cost improvement | Quality score | Hard violations |
|---|---|---|---|---|
| 0.3 s | −1427.2 | +2.68 % | 83.0 | 0 |
| 1.0 s | −1474.2 | **+6.06 %** | **84.7** | 0 |
| 3.0 s | −1508.6 | **+8.53 %** | **86.4** | 0 |

- Improvement is **monotonic in time budget** and **never** costs quality (guaranteed, tested).
- Budgets are wall-clock, so the iteration count — and the exact percentage — depends on the machine; the direction, the zero violations and the never-worse guarantee do not.
- Quality gains come from resolving *simultaneous* preference conflicts, seat waste and day-load imbalance — the parts a greedy sweep cannot see ahead.
- The honest result: this is **improvement, not proof of optimality**; the response says so (`engine.path`, `converged`).

---

## RQ2b — university-shaped instance (measured)

Mixed 60/90/120-minute sessions, cohorts that cannot clash, lab equipment, teachers with unavailable days.

| Sessions | Teachers | Wall clock | Scheduled | Quality | Optimizer | Violations |
|---:|---:|---:|---:|---:|---|---:|
| 150 | 15 | 1.54 s | 150/150 | 86.8 | improved | 0 |
| 400 | 40 | 1.74 s | 400/400 | 85.7 | improved | 0 |
| 800 | 80 | 2.41 s | 800/800 | 82.8 | improved | 0 |
| 1 200 | 120 | 3.67 s | 1 200/1 200 | 81.2 | improved | 0 |
| 2 000 | 200 | 7.77 s | 2 000/2 000 | 80.8 | **budget-bound** | 0 |

`python backend/scripts/bench_realistic.py` — the 5 s budget holds to ~1 200 sessions; at 2 000 the constructor consumes it and the optimizer gets only its floor (reported honestly as `improved: false`).

---

## RQ1 / O5 — scale & concurrency (measured)

| Test | Instance | Result |
|---|---|---|
| 200-faculty soak | 200 teachers, 40 rooms, 400 courses, 60 slots (5 s budget) | **feasible, 400/400 scheduled, 0 hard violations, 3.63 s wall**, 516 SA iterations, best score 51.2, `converged=false` |
| 64 concurrent solves | 40 teachers, 20 rooms, 100 courses, 40 slots | **64/64 feasible, 0 violations**, 21.26 s wall, median engine time 4.75 s |
| API latency (n = 80) | 6 teachers, 12 courses | **p50 1.228 s, p95 1.447 s, max 1.709 s**, 80/80 HTTP 200 |

**Reading the numbers honestly:** the 200-faculty run finished well inside its 5 s budget but had **not converged** — more time would buy more quality. That is exactly the trade-off the design exposes instead of hiding.

---

## Results vs objectives (self-assessment)

| Objective | Evidence | Verdict |
|---|---|---|
| O1 Problem model | Shared `ProblemContext`; single normalized problem definition | Met |
| O2 Conflict-free output | Independent verifier: 0 violations on every instance, incl. 2 000-session realistic runs | Met |
| O3 Quality optimization | +2.7 % / +6.1 % / +8.5 % cost, 79.5 → 86.4 score, never worse | Met |
| O4 Policy as rules | 7 rule kinds → solver + objective + verifier; UI create/toggle | Met |
| O5 Scale & time | 1 200 sessions in 3.67 s (0 violations), 2 000 in 7.8 s; 64 concurrent solves; p95 1.45 s | Met |
| O6 Explainability + ML | Score breakdown, per-teacher reasons, feedback→retrain→suggest loop | Met |
| O7 Deployability | Docker Compose stack, migrations on boot, health endpoint, 137 tests | Met |

*Unmet / partial by design:* proof of optimality at 200-faculty scale; the 1,000-user load figure is a projection, not a measurement (stated as such).

---

# 9. Contributions & limitations

---

## Contributions and novelty

1. **Two-tier verified optimization** — exact CP-SAT where it fits, SA where it doesn't, with an **independent verifier** as the test oracle rather than trusting the solver.
2. **Policy-as-data** — one declarative rule object compiles into *four* consumers (exact model, local move checks, objective penalty, audit) so institutional policy changes without code changes.
3. **Measurable quality, not just feasibility** — a 0–100 score with weights, sub-scores, grades and human-readable explanations; optimizer↔score coherence is **guaranteed and tested**.
4. **Honest optimization telemetry** — the API reports the path taken, iterations, best score and a `converged` signal instead of implying optimality.
5. **Complete workflow artefact** — auth/roles, import, rule authoring, manual re-verified edits, export, live events, containerized deployment: a system a real timetable office could pilot.
6. **Reproducible evidence** — every claim above is produced by a test or script in the repository.

---

## Limitations (stated deliberately)

1. **Not a proof of optimality at scale** — the metaheuristic returns *improved feasible* solutions.
2. **Load figures are partial** — 200-faculty and 64-concurrent are measured; the 1,000-user criterion is projected, not executed.
3. **ML is a starter loop** — accuracy on small feedback volumes is close to memorization until real data accumulates.
4. **Single-dataset evaluation** — results come from synthetic + test instances; a real institutional dataset would strengthen external validity.
5. **ML artefacts on local disk** — multi-replica deployment needs a shared volume (chat state and event bus already use Redis).
6. **Domain scope** — course timetabling only; exams/invigilation and SIS integration are out of scope.

---

## Future work

- **Real institutional dataset** + a pilot with the department timetable office (external validity).
- **Exact-solver decomposition** (e.g. Benders/column generation or per-day decomposition) to extend provable optimality to larger instances.
- **Multi-objective front (Pareto)** — let a scheduler pick between "fairest" and "most compact" timetables rather than one weighted blend.
- **Explainable-ML preference model** — learn per-teacher utility functions from edit history instead of a classifier.
- **SIS/ERP integration** and single sign-on; exam-timetabling module.
- **Observability** — Prometheus metrics + tracing; CI matrix (Python 3.11/3.12, larger soak instances).
- **Accessibility & i18n** for the dashboard; mobile-friendly scheduling approvals.

---

# 10. FYP compliance

---

## How this project satisfies typical FYP criteria

| FYP factor | Where it is evidenced in this project |
|---|---|
| Problem identification & justification | §1 problem statement, stakeholders, impact table |
| Literature review & gap analysis | §3 related-work comparison + 4 stated gaps |
| Clear aim, SMART objectives | §2 aim + O1–O7 table, each with verification method |
| Novelty / contribution | §9 contributions 1–6 (verification oracle, policy-as-data, guaranteed score coherence) |
| Technical depth & difficulty | NP-hard optimization, CP-SAT modelling, SA implementation, distributed state, ML loop |
| System design & architecture | Layered engine, shared context, two-tier pipeline, rule registry |
| Implementation quality | 33 REST endpoints, 14 dashboard routes, typed schemas, migrations, containerization |
| Testing & verification | **137 automated tests**, independent auditor, equivalence/security/soak tests |
| **Evaluation with real data** | Optimizer-vs-greedy benchmark, 200-faculty soak, concurrency, API latency |
| Documentation | README, architecture notes, OpenAPI docs, in-repo usage instructions |
| Project management | Sprint plan, milestones, risk register (next slide) |
| Ethics & professional practice | No personal student data; auth + row-scoping; honest limitations |
| Demo & viva readiness | Scripted demo + anticipated Q&A (closing slides) |
| Extensibility / future work | §9 future work list, each tied to a concrete gap |

> Match this to **[your university's] FYP rubric** weightings before submission — the categories line up, the percentages are local.

---

## Project management

**Phases (adjust dates to your actual schedule)**

| Phase | Weeks | Deliverable |
|---|---|---|
| P1 Requirements & literature | 1–3 | Problem definition, gap analysis, syllabus constraint catalogue |
| P2 Engine core | 4–8 | Context model, greedy heuristic, CP-SAT model, verifier |
| P3 Optimization & quality | 9–12 | SA optimizer, objectives, 0–100 score + explainability |
| P4 Application layer | 13–16 | API, auth/roles, planner, edits, export, upload |
| P5 Dashboard & AI | 17–19 | Next.js UI, rules authoring, ML loop, chat assistant |
| P6 Hardening & evaluation | 20–22 | Rate limiting, Redis state, soak/load tests, benchmark |
| P7 Documentation & defence | 23–24 | Final report, demo script, this deck |

**Risk register**

| Risk | Impact | Mitigation actually used |
|---|---|---|
| Large instances exceed solver budget | Unusable for real faculties | Two-tier pipeline + greedy seed + time budget + honest `converged` flag |
| Optimizer degrades quality while lowering cost | Confusing/wrong outputs | Guaranteed non-regression: rejected if score drops or cost rises (tested) |
| Scope creep (exams, SIS, mobile) | Nothing finished | Explicit out-of-scope list, tightened each sprint |
| Hidden single-replica state | Data loss on restart, no scaling | Redis-backed chat state + event bus with graceful memory fallback |
| Scheduler distrust of generated output | Artefact never adopted | Explainability endpoint, manual re-verified edits, export to familiar formats |
| Tiny ML dataset | Misleading accuracy | Accuracy surfaced with sample count; explicitly labelled as a starter loop |

---

## Ethics, privacy & professional practice

- **No student personal data** is processed; the system schedules courses, teachers, rooms and groups.
- **Least privilege**: JWT auth, `admin`/`scheduler`/`viewer` roles, row-scoped access to runs and edits.
- **Change accountability**: manual edits are re-verified against the rule set and recorded per run.
- **No external lock-in**: the LLM polishing step is optional; the system works fully offline of third-party APIs.
- **Transparency about limits**: the project documents what is *not* proven (optimality, projection-based load figures, starter ML) instead of over-claiming.
- Open-source stack; no licence conflicts introduced.

---

# 11. Demo & Q&A

---

## Live demo script (~6 minutes)

1. **Import** — upload the CSV of teachers/courses; show the validation report and rejected rows.
2. **Author policy** — create two rules in the UI: `no_same_day` for two courses and `forbid_slot` for a teacher on Friday. Show the catalog/validation.
3. **Generate** — run the solver on a medium instance; show live SSE progress and the completion event.
4. **Read the result** — the timetable grid, then the quality panel: 0–100 score, the five sub-scores, grade, per-teacher notes, and the rules honoured.
5. **Prove the rules bind** — ask the chat assistant which rules are active; attempt a manual drag that violates a rule → rejected with the rule name.
6. **Show the evidence** — `/benchmark` in the UI: greedy vs. optimized side by side, then the `/health` panel (API, DB, Redis, solver, ML).
7. *(closing)* `pytest tests/ -q` → **137 passed**.

**Fallback if the live stack fails:** recorded screen capture of the same seven steps + `pytest` output and benchmark JSON in the appendix.

---

## Anticipated questions (and short answers)

**Q: Is your solution optimal?**
Only the CP-SAT path is proven optimal, on instances small enough for it. At scale the optimizer returns *improved feasible* solutions — and the API says which path ran, how many iterations it did, the best score, and whether the search had converged. No over-claiming.

**Q: How do you know the timetable is valid?** An independent verifier (`engine/constraints.py`) written separately from the solver re-checks every hard constraint and every declared rule; every test asserts zero violations. The verifier is the test oracle, not the solver.

**Q: What's novel compared to existing schedulers?** Policy-as-data with a single rule object compiled into four consumers, plus a transparent quality score whose coherence with the optimizer's objective is guaranteed and tested.

**Q: Why two algorithms?** CP-SAT proves optimality but doesn't scale; SA scales but proves nothing. Together the system is useful at both ends, and reports honestly which one it used.

**Q: How did you test?** 137 tests across engine, rules, API, auth/security, upload equivalence, Redis state, performance and soak — plus a benchmark that measures optimizer gain per second.

**Q: What would you do with another semester?** Real institutional dataset and pilot; exact decomposition to push provable optimality further; Pareto multi-objective selection; SIS integration.

---

## Closing

> **Delivered:** a working, tested, containerized timetable optimization system that is conflict-free by verification, measurable in quality, honest about its limits, and operable by a real timetable office.
>
> **Evidence:** 137 backend tests + 11 frontend tests · optimizer +2.7 % → +8.5 % cost improvement (79.5 → 86.4 quality) · 1 200-session realistic instance in 3.67 s with 0 violations (2 000 in 7.8 s) · 64/64 concurrent solves · API p95 1.45 s.

**Thank you — questions welcome.**

References: OR-Tools CP-SAT documentation · Python-SAT/CP timetabling literature · scikit-learn RandomForest · FastAPI / Next.js / PostgreSQL / Redis documentation.

---

# Appendix

---

## A — Repository map

```
backend/app/engine/      context, heuristic, exact, optimizer, rules,
                         objectives, constraints, metrics, pipeline
backend/app/services/    planner, solver facade, edits, views, exporter,
                         validator, analytics, teachers, chat, chat_store,
                         ai_provider, events
backend/app/routers/     14 modules: schedule, quality, constraints, events,
                         timetable, feedback, ml, views, export, chat, upload,
                         teachers, auth, health
backend/app/ml/          features, learner (RandomForest), predictor
backend/app/middleware.py per-IP rate limiting (raw ASGI, SSE-safe)
backend/tests/           23 files, 137 tests
frontend/                13 pages, components + hooks
frontend/hooks/          useSchedule, useConstraints, useFeedback, useML
  docker-compose.yml     Postgres 16 · Redis 7 · API · dashboard
```

---

## B — Configuration & tuning knobs

| Variable | Purpose | Default |
|---|---|---|
| `SOLVER_TIME_LIMIT_SECONDS` | CP-SAT budget | 5.0 s |
| `SOLVER_OPTIMIZE_SECONDS` | SA budget on the large-instance path | 1.5 s |
| `SOLVER_NUM_WORKERS` | CP-SAT parallel search workers | 8 |
| `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_BURST` | per-IP throttling (0 disables) | 120 / 40 |
| `REDIS_URL`, `CHAT_TTL_SECONDS`, `EVENTS_CHANNEL` | shared chat state + event bus | redis://localhost:6379/0 |
| `EVENTS_REQUIRE_AUTH` | require JWT on the SSE stream | false |
| `ML_MODEL_DIR` | shared volume for model artefacts | app/ml/models |
| `GEMINI_API_KEY` | *optional* LLM polishing of chat replies | unset (offline) |
| `JWT_SECRET` | token signing key | change in production |

---

## C — How to reproduce every number in this deck

```bash
# 1. full suite -> 137 passed
cd backend && .venv/bin/python -m pytest tests/ -q

# 2. scale + latency numbers (prints the raw figures)
.venv/bin/python -m pytest tests/test_soak.py -s -q

# 3. optimizer vs greedy benchmark (seeded, reproducible)
curl -X POST localhost:8000/quality/benchmark \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"n_faculty":50,"n_rooms":20,"n_courses":100,"n_slots":40,"optimize_seconds":1.0,"seed":12345}'

# 4. front-end production build (13 pages / 14 built routes, 87.3 kB shared JS)
cd frontend && npx next build
```
