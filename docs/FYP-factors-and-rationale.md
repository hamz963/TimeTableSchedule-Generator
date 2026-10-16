# FYP factors & project rationale

Companion to `FYP-defense-deck.md`. Two things live here:

- **Part A — why this project was chosen** (the motivation narrative to open your defence with).
- **Part B — every factor that can matter for an FYP**, mapped onto what this repository
  actually contains, plus what you still have to prepare.

> **Read this first.** Part A is a *reconstruction* of the motivation from the artefact
> itself — the code, tests and docs. It is not a record of what you actually thought in
> week one. Pick the 3–4 reasons that are genuinely true for you, put them in your own
> words, and drop the rest: examiners ask "why did *you* choose this?" and expect a
> first-person answer, not a list.
>
> Your university's FYP handbook and rubric override everything below. Use Part B as a
> checklist against **your** weighting sheet, not as a substitute for it.

---

# Part A — Why this project was chosen

## The one-paragraph version

University timetabling is one of those problems every institution has, nobody enjoys, and
which is genuinely hard in the academic sense — it is an NP-hard constraint-satisfaction
and optimization problem, not a CRUD exercise. It was chosen because it lets a single FYP
demonstrate three different competencies end-to-end: **algorithmic optimization** (CP-SAT
and simulated annealing over real hard/soft constraints), **applied machine learning**
(preferences learned from scheduler feedback), and **professional software engineering**
(auth, roles, API design, real-time UI, containerized deployment, 131 tests). Crucially it
also has **objective, measurable success criteria** — zero hard-constraint violations,
a quality score, solve time — which makes the project defensible with evidence rather than
opinion.

## The reasons, one by one (with the line to use in the viva)

1. **A real, familiar, expensive pain point.**
   Every department repairs its timetable by hand every semester — days of spreadsheet
   work, clashes found late, dissatisfied staff. This is a problem the examiner recognises
   from their own institution.
   *Defence line:* "This is not a toy domain; the timetable office in any university
   performs this task manually every term."

2. **It has genuine academic depth, not just application plumbing.**
   Scheduling is NP-hard; the project required modelling hard vs. soft constraints,
   building a CP-SAT model, implementing simulated annealing, and reasoning about
   optimality vs. bounded-time feasibility.
   *Defence line:* "The interesting part is not the web app — it is that I had to build
   and then *verify* an optimizer for a provably hard problem."

3. **It bridges three areas of the degree in one artefact.**
   AI/optimization + machine learning + full-stack software engineering. Most FYPs prove
   competence in one; this one forces all three to work together.
   *Defence line:* "The ML only matters if it feeds the optimizer, and the optimizer only
   matters if the scheduler can operate it."

4. **Feasible within a final-year timeline.**
   The data is ordinary and always available (teachers, courses, rooms, time slots), no
   special hardware is needed, and the whole stack runs on a laptop via Docker Compose.
   The risk of "no data / no access" — a classic FYP killer — is close to zero.
   *Defence line:* "Nothing in the critical path depended on access I could not get."

5. **Success is measurable, so the evaluation chapter writes itself.**
   Violations count, quality score, cost improvement percentage, solve time, p95 latency,
   tests passing. Claims can be reproduced by the examiner from the repository.
   *Defence line:* "Every performance number in my report is produced by a script in the
   repository — you can rerun it."

6. **There is a visible gap in what already exists.**
   Academic prototypes stop at feasibility and rarely quantify quality; commercial
   schedulers are closed and expensive; policy is normally hard-coded. That gap is a
   legitimate research/engineering justification, not a made-up one.
   *Defence line:* "Existing tools answer 'is it valid?'. Very few answer 'how good is it,
   and why?'"

7. **Social and economic value (impact beyond the grade).**
   Staff time saved, fairer teacher workloads, fewer student clashes, no per-seat licence
   fees. Impact arguments strengthen the introduction and the conclusion.
   *Defence line:* "It targets an institutional cost that recurs every term."

8. **It is extensible — the project does not die at submission.**
   Multi-objective Pareto selection, exact decomposition, SIS integration, exam
   timetabling, explainable ML. A project with a future-work chapter that is *real* scores
   better than one that ends with "could add more features".
   *Defence line:* "The roadmap is tied to specific, acknowledged limitations."

9. **It produces a portfolio-grade artefact.**
   A deployed, tested system with an optimizer, an ML loop and a modern UI is directly
   useful in interviews and is a credible basis for a conference/student paper.

10. **Personal motivation that is easy to defend.**
    If you have ever waited for a timetable to be published, or seen a clash on day one,
    the motivation is authentic — and authenticity is what examiners are testing for when
    they ask "why this project?".

## How to phrase it if asked directly (30-second script)

> "I wanted an FYP where the difficulty was real and the result was measurable. Timetabling
> is NP-hard, every university does it painfully by hand, and — unlike a lot of final-year
> projects — success is not a matter of opinion: you either have zero clashes, or you don't.
> It also let me combine optimization, machine learning and full-stack engineering in one
> working system, which is the breadth I wanted to be able to show."

---

# Part B — Factors that matter for an FYP

## B1. Academic / assessment factors

| Factor | Why markers weigh it | Where it is evidenced here |
|---|---|---|
| Problem identification & justification | Shows you can find a defensible problem | deck §1, Part A above |
| Literature review & gap analysis | Shows scholarship and positioning | deck §3 related-work table + 4 gaps |
| Aim & SMART objectives | Objectives must be verifiable | deck §2, O1–O7 with a verification column |
| Novelty / contribution | Separates FYP from coursework | deck §9: verification oracle, policy-as-data, guaranteed score coherence |
| Technical complexity | Depth of the algorithmics | NP-hard domain, CP-SAT model, SA implementation |
| Methodology | Justified method, not ad-hoc building | Design Science + incremental sprints + evidence-first measurement |
| Correctness/evaluation rigor | Marks the difference between "works" and "proven" | independent verifier + benchmark + soak tests |
| Critical reflection | Limitations stated honestly | deck §9 limitations (6 items) |
| Future work | Shows you understand the field | deck §9, each tied to a limitation |

**Rubric mapping:** copy the categories from your course handbook next to the rows above and
check you have an artefact for each. Anything with no artefact is a deduction waiting to
happen.

## B2. Technical / engineering factors

| Factor | Status in this project |
|---|---|
| Feasibility (technical) | Runs from `docker compose up`; pure-Python + Node; no special hardware |
| Complexity / difficulty | Two solvers, rule registry, 14 backend router modules, 13 dashboard pages, ML loop |
| Scalability | Measured: 200 faculty / 400 courses in 3.63 s, 0 violations; 64 concurrent solves |
| Correctness guarantee | Independent auditor; 131 tests; equivalence tests (upload ↔ typed input) |
| Performance evidence | Optimizer +5.2 %/+7.8 % cost, quality 72.0 → 74.2; API p95 1.45 s |
| Security & privacy | JWT + roles + row-scoping, per-IP rate limiting, SSE token auth option |
| Data integrity & versioning | Run history, master snapshot per run, re-verified manual edits |
| Reliability / graceful degradation | Redis optional with in-memory fallback; API survives a DB-less boot |
| Maintainability | Layered engine, single shared context, typed schemas, migrations |
| Reproducibility | Seeded benchmark, deterministic optimizer mode, `pytest` one-liner |
| Portability / deployment | Docker Compose: Postgres 16, Redis 7, API, dashboard |
| Documentation | README (architecture, usage), OpenAPI at `/docs`, this deck + factors doc |

## B3. Deliverables an FYP is usually marked on

- [ ] **Final report** — abstract, intro, literature, methodology, design, implementation, testing, results, discussion, limitations, future work, references, appendices.
- [ ] **Working source code** — in a repository, with README and licence.
- [ ] **Test evidence** — `pytest` output (131 passed), benchmark JSON, soak numbers.
- [ ] **User documentation** — how a scheduler uses the system (data import → rules → generate → export).
- [ ] **Installation/deployment guide** — this project: `docker compose up` + env vars (`docs/` appendix B).
- [ ] **Poster / presentation** — this deck renders to PDF from the HTML via Ctrl+P.
- [ ] **Demo** — the 6-minute script in deck §11 (have a recording as fallback).
- [ ] **Logbook / supervisor meeting records** — *you must keep this; it is often a direct mark component.*
- [ ] **Plagiarism/AI-use declaration** — follow your institution's policy exactly.
- [ ] **Ethics/GDPR statement** — here: no student personal data, no third-party data sharing.

## B4. Project-management factors

| Factor | Evidence / action |
|---|---|
| Scope definition (in/out) | deck §2 scope; explicit out-of-scope list prevented scope creep |
| Timeline / Gantt | deck §10 phases P1–P7 — replace the week numbers with your real ones |
| Milestones & deliverables | each phase ends in a green test suite + demo-able increment |
| Risk register | deck §10, 6 risks with the mitigation actually used |
| Budget / cost | open-source, local Docker, no licence or cloud spend (state this explicitly — cost feasibility is a mark line) |
| Version control hygiene | meaningful commits, feature branches, README kept current |
| Change management | Redis/state, rate limiting and the optimizer guarantee were added as *hardening* after evaluation, and the README was updated to match |

## B5. Supervision, ethics & administration

- Weekly (or per-agreement) supervisor meetings **with written minutes** — this is the most commonly under-documented mark line.
- Get supervisor sign-off on: problem statement, objectives, scope, and the demo script.
- Keep an honest **AI-assistance declaration** if your institution requires one; describe *how* AI tooling was used (it was used for structure, tests and documentation here) — do not hide it in a project with this much generated code.
- Ethics: this system schedules courses, not people's personal records — say so explicitly in the report.
- IP/licence: confirm the repository's licence and any institutional claim before publishing.
- Verify the submission format (PDF, page limits, appendix rules, plagiarism checker) **before** the deadline, not after.

## B6. Evaluation factors (this is where marks are won or lost)

| Factor | Requirement | This project |
|---|---|---|
| Baseline for comparison | Something to beat | greedy constructive heuristic (identical in every run) |
| Objective metrics | Numbers, not adjectives | violations, quality score, cost improvement, iterations, p50/p95 latency |
| Realistic scale | Test beyond toy inputs | 200 faculty / 40 rooms / 400 courses / 60 slots |
| Concurrency / load | Show it survives demand | 64 concurrent solves, 16 threads, 80-request latency distribution |
| Statistical honesty | Repeat runs, report variance | seeded runs, monotonic time-budget sweep, raw figures printed by tests |
| External validity | Real-world data | **gap**: synthetic + test instances only — say so, and note the pilot as future work |
| Reproducibility | Examiner can rerun | one-line commands in deck appendix C |

## B7. Defence / viva factors

- **Timing discipline** — 50 slides is a *backup*, not a script: plan 12–15 minutes over the core 20 slides and keep the rest for questions.
- **Demo reliability** — run the stack *before* you present; have the recorded fallback ready; use a small instance live and quote the big-instance numbers from the appendix.
- **Expected questions** — deck §11 lists six, including the two that always come: "is it optimal?" and "how do you know it's valid?". Both have evidence-backed answers.
- **Code walkthrough** — be ready to open one file and explain it: `engine/optimizer.py` (SA + the non-regression guarantee) or `engine/rules.py` (policy-as-data) are the strongest two.
- **Know your numbers cold** — 131 tests · +5.2 %/+7.8 % · 72.0 → 74.2 · 400 courses in 3.63 s, 0 violations · 64/64 concurrent · p95 1.45 s.
- **Know your limitations cold** — examiners respect a candidate who states them before being asked.

## B8. Factors that carry value after the FYP

- **Employability** — optimization, distributed state, typed APIs, testing discipline, Docker: directly interviewable.
- **Publication potential** — "policy-as-data timetabling with a verified quality score" is a plausible student-paper or workshop submission.
- **Adoption potential** — a departmental pilot is the strongest possible impact statement in a conclusion.
- **Portfolio** — the repository plus this deck is a reusable artefact for job or postgraduate applications.

---

# Part C — Pre-defence readiness checklist

**Content**
- [ ] Every `[BRACKETED]` placeholder in the deck replaced (name, reg. no., supervisor, department, dates).
- [ ] Phase week-numbers in the project-management slide replaced with your real schedule.
- [ ] All six measured numbers verified on your machine (see deck appendix C) and matching the report.
- [ ] Objectives table in the report matches the deck (O1–O7) — no drift between documents.

**Evidence**
- [ ] `cd backend && .venv/bin/python -m pytest tests/ -q` → `131 passed` (screenshot it).
- [ ] `pytest tests/test_soak.py -s -q` output captured for the results chapter.
- [ ] Benchmark JSON saved (`/quality/benchmark` with seed 12345).
- [ ] `npx next build` output captured (13 pages / 14 built routes, 87.3 kB shared JS).
- [ ] Repository pushed and public/accessible to the examiner if required.

**Delivery**
- [ ] Deck exported to PDF from `FYP-defense-deck.html` (Ctrl+P, landscape, background graphics on).
- [ ] Demo rehearsal done twice, including the failure fallback.
- [ ] Supervisor has seen the final deck and the demo script.
- [ ] Logbook, ethics statement and any AI-use declaration submitted.

---

# Part D — Common FYP deduction risks and how this project avoids them

| Risk | Typical cause | Guard used here |
|---|---|---|
| "Where is the evaluation?" | Only a working demo, no measurements | seeded benchmark + soak numbers in the deck and tests |
| Objectives not verifiable | Vague aims ("improve scheduling") | each objective names its verification method |
| Over-claiming | "fully optimal", "scales to 1000 users" | `converged` flag, honest limitation slides, projections labelled as projections |
| Scope creep / unfinished scope | exams, SIS, mobile all attempted | explicit out-of-scope slide |
| Untested claims | no regression safety net | 131 tests, including equivalence and security tests |
| Unsafe defaults ignored | dev secrets shipped | `JWT_SECRET` warning, rate limiting, roles, row-scoping documented |
| Circular evidence | trusting the solver's own validation | independently written verifier as the test oracle |
| No reproducibility | "it worked on my laptop" | Docker Compose + one-line reproduction commands |
| Documentation gap | README stale relative to code | README updated in the same change as the code |
