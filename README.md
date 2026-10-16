# Time Table Schedule Generator

Constraint-based university timetable optimization. An **optimization engine**
(OR-Tools CP-SAT for exact search + a simulated-annealing metaheuristic for
large instances) produces conflict-free, *quality-optimized* timetables in
seconds — with declarative rules that actually drive the solver, a 0–100
quality score with explanations, and live updates over Server-Sent Events.

Stack: **FastAPI + OR-Tools CP-SAT** backend, **PostgreSQL** storage,
**Next.js 14** dashboard, fully containerized with Docker.

---

## Architecture

The heart of the system is a layered engine (`backend/app/engine/`). Every
derived structure is computed **once** in a shared context and reused by the
heuristic, the optimizer, the verifier and the metrics — replacing the earlier
monolith where each consumer rebuilt the same lookups.

```
┌─────────────┐    POST /schedule/generate-simple    ┌───────────────────────────────┐
│  Next.js    │ ───────────────────────────────────▶ │  FastAPI                      │
│  dashboard  │ ◀─────────────────────────────────── │  ┌─────────────────────────┐  │
└─────────────┘   assignments + quality + engine     │  │ engine/pipeline.py      │  │
      ▲  SSE /events/stream                          │  │  exact | heuristic path │  │
      └───────────────────────────────────────────┐  │  ├─ exact.py  (CP-SAT)    │  │
                                                   │  │  ├─ heuristic.py (greedy) │  │
                                                   │  │  ├─ optimizer.py  (SA)    │  │
                                                   │  │  ├─ rules.py  (constraints)│ │
                                                   │  │  ├─ objectives.py         │  │
                                                   │  │  ├─ constraints.py (verify)│ │
                                                   │  │  └─ metrics.py  (quality) │  │
                                                   │  └─────────────────────────┘  │
                                                   └──────────────┬────────────────┘
                                                                  │ persist
                                                         ┌────────▼─────────┐
                                                         │   PostgreSQL     │
                                                         └──────────────────┘
```

### Engine packages

| Module | Responsibility |
|---|---|
| `engine/context.py` | Normalizes a request into a `ProblemContext`; computes day ordering, slot indexes, time buckets, occupancy keys — once. |
| `engine/heuristic.py` | Constructive greedy (most-constrained-first), rule-aware. |
| `engine/constraints.py` | Hard-constraint verification (single source of truth). |
| `engine/objectives.py` | Soft objectives (preferences, time bands, room waste, fairness, compactness) — shared by the optimizer and metrics. |
| `engine/optimizer.py` | Simulated annealing + greedy descent (deterministic mode available). |
| `engine/rules.py` | Declarative constraint registry. |
| `engine/metrics.py` | 0–100 quality score + explainability. |
| `engine/exact.py` | The CP-SAT model (exact search). |
| `engine/pipeline.py` | Chooses and runs the solve path. |

`app/services/solver.py` is now a thin facade (`TimetableSolver.generate` /
`verify`) over the engine, so every existing caller keeps working.

### Two-tier solve pipeline

- **Small, rule-light instances → exact CP-SAT.** Warm-started by a greedy hint
  and guaranteed by a *verified* greedy fallback. Unchanged optimal behaviour.
- **Large instances, or instances carrying hard rules CP-SAT cannot encode
  exactly → verified greedy seed + simulated annealing.** The greedy baseline is
  improved by greedy descent (first-improvement) followed by annealing, under a
  wall-clock budget (`SOLVER_OPTIMIZE_SECONDS`, default 1.5s, capped by the
  request budget). Structural hard constraints are **never** violated;
  declarative-rule violations are heavily penalised so the search repairs them.

The path taken is reported in `engine.path` and the optimizer records
`cost_start` / `cost_end` so its improvement is auditable.

---

## Declarative rules (constraints that actually apply)

The `Constraint` CRUD is no longer decorative: rule rows are compiled into the
solver and audited on every result. Rules can also be passed inline on the
generate requests as `rules: [{kind, params, hard?, weight?, name?}]`.

| Kind | Hard? | Params | Meaning |
|---|---|---|---|
| `forbid_slot` | ✅ | `entity` (course/faculty/venue), `id`, `slots`/`days` | an entity may not use given slots or days |
| `fixed_slot` | ✅ | `course_id`, `slot_id`, `venue_id?` | pin a course to a slot/room |
| `course_before` | ✅ | `course_a`, `course_b` | every session of A precedes every session of B |
| `same_day` | ✅ | `courses` | listed courses all meet on the same day |
| `no_same_day` | ✅ | `course_a`, `course_b` | two courses never share a day |
| `preferred_day` | 💡 soft | `course_id`, `days` | reward placing a course on given days |
| `spread_sessions` | 💡 soft | `sessions` | reward spreading a course's sessions across days |

Requests may reference courses/teachers **by name** (resolved to ids in the
planner) or by id. Catalog: `GET /schedule/rules/catalog`.

```bash
curl -X POST localhost:8000/schedule/generate-simple -H 'Content-Type: application/json' \
  -d '{"teachers":[{"name":"Alice"},{"name":"Bob"}],
       "courses":[{"name":"Math","teacher":"Alice","credit_hours":1},
                  {"name":"Art","teacher":"Bob","credit_hours":1}],
       "days":["Mon","Tue","Wed","Thu","Fri"],
       "rules":[{"kind":"course_before","params":{"course_a":"Math","course_b":"Art"}},
                {"kind":"forbid_slot","params":{"entity":"faculty","id":"Bob","days":["Fri"]}}]}'
```

---

## Quality score + explainability

Every generated timetable gets a transparent 0–100 score with sub-scores
(teacher preferences, time-of-day fit, room efficiency, fairness, compactness)
and a plain-language explanation of *why* it looks the way it does.

```bash
curl localhost:8000/quality/1 -H "Authorization: Bearer <token>"     # per-run report
curl -X POST localhost:8000/quality/benchmark -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' \
  -d '{"n_faculty":50,"n_rooms":20,"n_courses":100,"n_slots":40,"optimize_seconds":1.0}'
# -> greedy baseline vs. optimized (cost + quality) — the optimizer's value, measured
```

---

## Real-time events

Schedule changes are broadcast over Server-Sent Events:

```bash
curl -N localhost:8000/events/stream                 # live stream (created/edited/rescheduled)
curl -N "localhost:8000/events/stream?token=$JWT"    # optional auth (see below)
curl localhost:8000/events/recent -H "Authorization: Bearer <token>"   # polling fallback
```

The dashboard mounts a global subscriber (`components/LiveEvents.tsx`) showing
live toast notifications and refreshing affected timetables. When Redis is
available the broker also publishes to a channel and each replica relays other
replicas' events (with an `origin` id so a replica never re-delivers its own).
With no Redis it degrades to a correct single-process bus.

## Shared state (Redis) + rate limiting

- **Chat conversations** live in Redis (`CHAT_TTL_SECONDS`, default 1h) so any
  replica can serve any conversation; without Redis they fall back to process
  memory (single replica).
- **Rate limiting:** a pure-ASGI token bucket per client IP
  (`RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_BURST`; `0` disables). It is raw ASGI
  rather than `BaseHTTPMiddleware` so it does **not** break SSE streaming.
  `/health`, `/docs`, `/openapi.json` are exempt; over-limit requests get
  `429` + `Retry-After`.
- **Stream auth:** `/events/stream` accepts an optional `?token=<JWT>` (browsers
  can't set headers on `EventSource`); set `EVENTS_REQUIRE_AUTH=true` to make it
  mandatory.

---

## Quickstart (Docker)

```bash
docker compose up --build
# backend  → http://localhost:8000  (Swagger: /docs)
# frontend → http://localhost:3000
# postgres + redis → storage + shared real-time state
```

The backend runs `alembic upgrade head` on boot (falls back to `create_all`,
never crashes boot if the DB is unreachable — `/health` reports
`database: unavailable`). Configure via `backend/.env` (see `.env.example`);
set `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` in production.

### Local development

```bash
# backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
# frontend
cd frontend && npm install && npm run dev
```

---

## Auth (roles: admin, scheduler, teacher)

```bash
curl -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}'
# -> {"access_token": "...", "role": "admin"}
```

- Reads (timetables, views, exports, analytics, chat, quality) need any login;
  writes (generate, edit, constraints, renames, retraining) need `scheduler`/`admin`.
  `/events/stream` authenticates via an optional `?token=` (mandatory when
  `EVENTS_REQUIRE_AUTH=true`); `recent`/`status` require the header.
- **Teacher row-scoping:** teacher accounts only see their own schedule; chat
  refuses edits for them.
- PBKDF2-HMAC-SHA256 passwords; HS256 JWTs (12h). Frontend stores the token in
  `localStorage` and redirects to `/login` on 401.

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/schedule/generate-simple` | Easy path: teachers + credit hours + rules → optimized timetable |
| POST | `/schedule/generate` | Advanced JSON path (faculty/venues/slots/courses + `rules`) |
| POST | `/schedule/reschedule` | Delta-reschedule around disruptions |
| GET | `/schedule/{id}` | Retrieve a generated timetable |
| POST | `/schedule/{id}/edit` | Move / cancel / swap (persisted as a new run) |
| GET | `/schedule/rules/catalog` | Supported rule kinds + params |
| GET | `/quality/{id}` | Quality score, sub-scores, per-teacher reasoning, rule audit |
| POST | `/quality/benchmark` | Greedy baseline vs. optimized on a real/synthetic instance |
| GET | `/events/stream` · `/events/recent` | Real-time schedule events (SSE / polling); `?token=` optional |
| GET | `/analytics/schedule/{id}` | Workload, utilization, preference satisfaction |
| GET | `/schedule/{id}/views?view=…` | master / teacher / student / staff / canteen |
| GET | `/export/{id}?view=…&format=…` | pdf / csv / xlsx / png / jpg / json / html |
| POST/GET/PATCH/DELETE | `/constraints…` | Constraint CRUD (now consumed by the solver) |
| GET | `/health`, `/docs` | Health (solver/DB/redis/ML) + Swagger |

---

## Testing

```bash
cd backend && pytest tests/ -q      # 131 tests (~2.5 min incl. the soak test)
```

Coverage includes: engine context/heuristic/optimizer/metrics/pipeline,
declarative rules (registry, name resolution, rebasing, end-to-end enforcement,
**persisted Constraint rows drive generation**), quality + event endpoints, the
Redis chat-store codec + broker identity, rate limiting + SSE auth, the original
solver/planner/API/edit/chat/export suite, request-size caps, and a
200-faculty / 64-concurrent soak test.

---

## Performance (measured)

| Scenario | Result |
|---|---|
| Small instances | optimal (CP-SAT), <0.5 s |
| 50 faculty / 20 rooms / 100 courses, 40 slots | feasible, **no hard violations**, greedy+descent+SA within the budget |
| Optimizer vs. greedy | **+2% (0.3 s) → +8% (1.5 s)**; the returned timetable **never** scores lower than greedy nor costs more |
| Soak: 200 faculty / 40 rooms / 400 courses / 60 slots | feasible, 400/400 scheduled, **0 hard violations**, ~4.3 s wall |
| Soak: 64 concurrent 100-course solves | all feasible, median engine time ~4.6 s |
| Soak: 80 sequential API generations | p50 ~1.2 s, p95 ~1.5 s |

The optimizer reports a `converged` flag (true when the last quarter of the
search found no further improvement) and the best quality score it reached —
an honest "settled" signal rather than a claim of proven optimality.

```bash
# reproduce the optimizer benchmark
curl -X POST localhost:8000/quality/benchmark -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' \
  -d '{"n_faculty":50,"n_rooms":20,"n_courses":100,"n_slots":40,"optimize_seconds":1.0}'
```

---

## Project layout

- `backend/app/engine/` — the optimization engine (context, heuristic, exact,
  optimizer, rules, constraints, objectives, metrics, pipeline)
- `backend/app/services/solver.py` — thin facade over the engine
- `backend/app/services/` — `planner.py`, `edits.py`, `views.py`, `exporter.py`,
  `validator.py`, `analytics.py`, `teachers.py`, `events.py`, `chat.py`
- `backend/app/routers/` — `schedule`, `quality`, `events`, `constraints`,
  `timetable`, `feedback`, `ml`, `views`, `export`, `chat`, `upload`, `teachers`,
  `auth`, `health`
- `backend/app/middleware.py` — per-IP rate limiting (raw ASGI, SSE-safe)
- `backend/app/services/chat_store.py` — Redis-backed chat state (memory fallback)
- `backend/app/ml/` — preference learning (RandomForest)
- `backend/tests/` — 131 tests
- `docs/` — `FYP-defense-deck.md` (+ rendered `FYP-defense-deck.html`,
  rebuilt by `python docs/build_deck.py`) and `FYP-factors-and-rationale.md`
- `frontend/` — Next.js dashboard (builder, grid, quality panel, view renderer,
  benchmark, live events)

---

## Production readiness — honest status

Verified in this overhaul: **131-test suite green** · engine refactor is
behaviour-preserving (original 100 tests pass unchanged) · frontend builds
(Next.js 14.2) · live HTTP smoke test (generate with a rule → quality report →
benchmark → events) passes against a real server · Redis-backed chat state and
cross-replica event delivery verified against a live Redis instance.

Known limits (not yet done, in priority order):

1. **Single-worker assumptions (partly resolved).** Chat conversations and the
event broker now use Redis with a graceful in-memory fallback, so replicas
share state when `REDIS_URL` is set. ML models still live on local disk — mount
a shared volume or pin training to one replica.
2. **Optimizer is a metaheuristic, not a proof of optimality.** On large
instances it returns *improved feasible* solutions (honest), not provably
optimal ones. The result carries a `converged` flag and the best score reached.
Deterministic mode (`max_iterations`) exists for reproducibility.
3. **Load testing is starter-level.** `tests/test_soak.py` covers a 200-faculty
solve, 64 concurrent solves and an 80-request API latency distribution; the
1,000-user criterion is still projection, not a measured result.
4. **ML is a starter loop.** Accuracy on tiny datasets is memorization; treat
`model_accuracy` accordingly until real feedback volume arrives.
5. **Events are best-effort.** `publish` never breaks a request; a dropped
subscriber simply misses the event (poll `/events/recent` for backfill).
