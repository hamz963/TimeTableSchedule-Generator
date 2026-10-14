# Time Table Schedule Generator

Engine autonomously generates optimal timetables in <5 seconds, minimizing conflicts,
balancing workload, respecting all preferences. Includes real-time rescheduling
(delta-scheduling) when conflicts arise.

Constraint-based university timetable optimization: **FastAPI + OR-Tools CP-SAT**
backend, **PostgreSQL** storage, **Next.js** dashboard, fully containerized with Docker.

## Architecture

```
                ┌─────────────┐     POST /schedule/generate      ┌──────────────────┐
                │  Next.js    │ ───────────────────────────────▶ │  FastAPI backend │
                │  dashboard  │ ◀─────────────────────────────── │  OR-Tools CP-SAT │
                └─────────────┘        timetable JSON + stats     └────────┬─────────┘
                                                                         │ persist
                                                                ┌────────▼─────────┐
                                                                │   PostgreSQL     │
                                                                └──────────────────┘
```

**Solver design (`backend/app/services/solver.py`)** — binary variables
`x[course, venue, slot]`; hard constraints (no faculty/venue double-booking,
unavailability, venue availability, capacity, equipment, daily workload); soft
objectives (preference reward, room-waste penalty, reschedule stability).
Two-tier strategy: small instances are solved exactly with CP-SAT (warm-started
by a greedy hint, guaranteed by a verified greedy fallback); large instances —
where exact model-building alone would blow the budget — are served directly by
the verified greedy heuristic (previous-assignment, preference- and
waste-aware ordering), so 50 faculty / 20 rooms / 100 courses return feasible,
zero-violation timetables in ~0.2 s.

## Quickstart (Docker)

```bash
docker compose up --build
# backend  → http://localhost:8000  (Swagger: /docs)
# frontend → http://localhost:3000
# worker   → Celery + Redis async solving queue
```

The backend runs `alembic upgrade head` on boot, so a fresh `up` creates the
full schema automatically (falls back to `create_all`, and never crashes boot
if the DB is unreachable — `/health` reports `database: unavailable`).

Configure via `backend/.env` (see `backend/.env.example`).
Set `JWT_SECRET`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` in production —
the backend seeds that admin account on first boot.

## Auth (roles: admin, scheduler, teacher)

```bash
curl -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}'
# -> {"access_token": "...", "role": "admin"}
curl localhost:8000/auth/me -H "Authorization: Bearer <token>"
```

- Reads (timetables, views, exports, analytics, chat) need any login;
  writes (generate, edit, constraints, renames, retraining) need
  `scheduler` or `admin`; user registration (`POST /auth/register`) is
  admin-only. Teachers get a read-only UI (no Builder/Constraint links).
- **Teacher row-scoping:** teacher accounts only see their own schedule —
  other views/exports/raw detail return 403, the teacher view and its exports
  are filtered to the linked `teacher_name`, and chat refuses edits for them.
  `/teacher` is their home page (run picker + sessions + feedback).
- Passwords are PBKDF2-HMAC-SHA256 (stdlib, 200k iterations); tokens are
  HS256 JWTs (12h expiry) via `Authorization: Bearer`.
- The frontend stores the token in `localStorage`, attaches it to every
  request (30s timeout), and redirects to `/login` on 401.

Smoke test against a running backend (proven against real Postgres):

```bash
# 1. generate (teacher-friendly path)
curl -X POST localhost:8000/schedule/generate-simple -H 'Content-Type: application/json' \
  -d '{"teachers":[{"name":"Alice"}],"courses":[{"name":"Math","teacher":"Alice","credit_hours":2}],"rooms":[],"days":["Mon","Tue"],"day_start":"08:00","day_end":"12:00","period_minutes":60,"gap_minutes":10,"lunch_break":false}'
# 2. views / analytics / export / edit / chat / rename from the returned schedule_run_id
curl "localhost:8000/schedule/1/views?view=teacher"
curl "localhost:8000/export/1?view=master&format=pdf" -o timetable.pdf
curl -X POST localhost:8000/schedule/1/edit -H 'Content-Type: application/json' \
  -d '{"op":"move","course_id":100001,"to_slot_id":100002}'
```

> Note: `POST /schedule/generate` and `/schedule/reschedule` (advanced JSON
> path) allocate every dataset a fresh server-side id block, so ids in
> responses are **rebased** (e.g. course 1 → 100001) and can never collide
> with other datasets' runs.

## Database migrations (Alembic)

```bash
cd backend
alembic upgrade head      # create all tables (initial schema: 0001)
alembic revision --autogenerate -m "describe change"  # after model edits
```

## Async solving (Celery + Redis)

The API solves synchronously for the <5 s real-time path. For batch/very large
problems, enqueue instead and poll the result backend:

```python
from app.tasks import solve_timetable_task
job = solve_timetable_task.delay(payload)
job.get(timeout=60)  # {"status": ..., "assignments": [...], ...}
```

## Local development

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install && npm run dev
```

## Easy path: data, settings, generate (`/data` → `/schedule/easy`)

Two input paths, one generator. Upload a **CSV/Excel** file
(`teacher_name,course_name,credit_hours,student_group,preferred_time`) with a
live preview and per-row errors, or type rows into the **manual table**
(credit hours 1–4 dropdown, preferred-time dropdown, CSV template download).
Both produce identical solver input (covered by test).

### Schedule settings (defaults pre-filled)

| Setting | Default | Meaning |
|---|---|---|
| Days | Monday to Friday | Days classes run |
| Day start / end | 09:00 / 17:00 | First class may start / last class must finish |
| Class length | 60 minutes | One teaching slot |
| Lunch | 12:00 to 14:00 | No classes (free for everyone) |
| Gap between classes | 30 minutes | Physical spacing built into the slot grid |
| Max back-to-back periods | 2 per teacher per day | Break rule (0 disables); enforced as a hard rule |
| Maximum teaching per day | 6 hours | Per teacher |
| Rooms | 5 rooms (Room 1 to Room 5) | Add explicit rooms if more are needed |

Fairness is enforced three ways: a course's sessions never share a slot
(hard), **no student group has two classes at once** (hard), sessions spread
across days + load spread evenly (soft objectives). Course preferred times
(Morning/Afternoon/Evening) are soft suggestions — they never override a hard
rule. Every result reports `OPTIMAL` (proven best), `FEASIBLE` (valid), or
`INFEASIBLE` with an actionable cause; large instances use the verified
greedy heuristic (reported as `feasible`).

- **Teachers:** names (+ optional max hours/day, off days), typed in or imported
  from CSV (`name, max_hours_per_day, unavailable_days`)
- **Courses:** name, teacher (dropdown), **credit hours 1–4** = classes per week,
  student group (optional), preferred time (dropdown) — or the guide-format CSV
  (`course, teacher, credit_hours, student_group, preferred_time`)

Before generating, the planner validates and reports field-level causes:

| Message | Fix |
|---|---|
| "Teacher name is missing" / "Course name is missing" | Fill in the row |
| "Credit hours must be 1 to 4" | Enter 1–4 |
| "Duplicate: teacher X already teaches Y" | Remove one row |
| "Teacher X needs N hours but only M are free" | Extend the day, add days, or reduce load |
| "No valid timetable found / infeasible" | Relax a setting (rooms, hours, consecutive limit) |

Example:

```bash
curl -X POST localhost:8000/schedule/generate-simple -H 'Content-Type: application/json' \
  -d '{"teachers":[{"name":"Alice"}],"courses":[{"name":"Math","teacher":"Alice","credit_hours":3,"student_group":"CS-A","preferred_time":"Morning"}],
       "days":["Mon","Tue","Wed","Thu","Fri"],"day_start":"09:00","day_end":"17:00"}'
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/schedule/generate-simple` | **Easy path:** teacher names + courses/credit hours + day window in, fair timetable out |
| POST | `/schedule/generate` | Generate optimal timetable (<5 s budget) |
| POST | `/schedule/reschedule` | Delta-reschedule around disruptions (blocked rooms, cancellations) |
| GET | `/schedule/{id}` | Retrieve generated timetable |
| GET | `/analytics/schedule/{id}` | Workload, utilization, preference satisfaction |
| POST/GET/PATCH/DELETE | `/constraints...` | Constraint CRUD |
| GET | `/health` | Solver version, DB status, uptime |
| GET | `/docs` | Auto-generated Swagger UI |

Example:

```bash
curl -X POST localhost:8000/schedule/generate -H 'Content-Type: application/json' \
  -d '{"faculty":[...],"venues":[...],"slots":[...],"courses":[...],"time_limit_seconds":5}'
```

## Testing

```bash
cd backend
pytest tests/ -q
# tests/test_solver.py       unit: feasibility, hard constraints, edge cases
# tests/test_constraints.py  validation logic
# tests/test_api.py          end-to-end API (generate, CRUD, analytics, health)
# tests/test_performance.py  50 faculty / 20 rooms / 100 courses in <5 s,
#                            100% hard-constraint satisfaction
```

## Project layout

- `backend/app/services/solver.py` — OR-Tools CP-SAT model + greedy matheuristic
- `backend/app/services/validator.py` — constraint validation
- `backend/app/services/analytics.py` — workload / utilization / satisfaction metrics
- `backend/app/routers/` — `schedule.py` (generate/reschedule/edit), `teachers.py`,
  `constraints.py`, `timetable.py`, `health.py`, `feedback.py`, `ml.py`,
  `views.py`, `export.py`, `chat.py`, `upload.py`
- `backend/app/services/` — `solver.py`, `planner.py`, `edits.py`, `chat.py`,
  `views.py`, `exporter.py`, `validator.py`, `analytics.py`, `teachers.py`
- `backend/app/ml/` — `features.py`, `learner.py`, `predictor.py` (RandomForest)
- `backend/app/models/` — SQLAlchemy schema (faculty, venue, slot, course, constraint, runs, entries)
- `backend/app/tasks.py` — Celery async solving task (Redis broker)
- `backend/alembic/` — versioned migrations (`alembic upgrade head`)
- `frontend/` — Next.js 14 dashboard (generate, grid visualization, constraints, analytics)

## Performance (2-CPU reference machine)

| Problem | Result |
|---------|--------|
| 5 faculty / 3 rooms / 5–20 courses | optimal, <0.5 s |
| 50 faculty / 20 rooms / 100 courses | feasible, ~0.2 s wall, 0 hard violations |

("Feasible" is honest: large instances use the verified greedy heuristic;
exact CP-SAT optimality is served on small instances.)

## Production readiness — honest status

Verified: 100-test suite green (incl. concurrency + caps tests) · both Docker
images build · migrations apply cleanly on Postgres · full API flow proven
live against real Postgres (generate → views → analytics → export → edit →
rename → feedback → retrain → chat) · `.gitignore` covers secrets/artifacts.

Request limits (HTTP 413 beyond these): 1000 faculty, 500 venues, 2000 slots,
5000 courses/sessions, 2M course×venue×slot combinations. Oversized payloads
fail fast instead of burning solver CPU.

Known limits (not yet done, in priority order):

Known limits (not yet done, in priority order):

1. **Single-worker assumptions.** Chat conversations live in process memory
   and ML model files on local disk — run one backend replica (or back them
   with Redis/shared volume; `ML_MODEL_DIR` env exists for the latter).
2. **Load testing is starter-level.** `tests/test_load.py` covers 8-way solver
   parallelism and API latency distribution, plus id-block retry on write
   conflicts — but the 1,000-user criterion and the 200-faculty run were never
   executed. Run those before any big rollout.
3. **`retrain-async` needs a live broker.** The Celery task exists and the
   worker ships in compose, but background retraining was only exercised via
   sync `/ml/retrain` + eager task tests.
4. **ML is a starter loop.** Accuracy on tiny datasets is memorization; treat
   `model_accuracy` accordingly until real feedback volume arrives.
5. **No rate-limiting.** Auth + row-scoping are done; per-IP throttling is not.
   Fine for a school intranet behind a proxy; not for the open internet.

## Conversational assistant (`/chat` → `POST /chat/...`)

Rule-based intent parsing (offline deterministic; optionally polished by
Gemini when `GEMINI_API_KEY` is set — install `google-generativeai` to enable):

```
POST /chat/start                  {"schedule_run_id": 7} -> {conversation_id, reply}
POST /chat/{cid}/message          {"message": "teacher and canteen schedules as PDF"}
POST /chat/{cid}/generate         {} -> download URLs per view x format
```

The bot detects audience views (master/teacher/student/staff/canteen) and
formats, asks one clarifying question at a time (formats, then
morning/afternoon lean), then flips to `ready_to_generate`. Every reply
carries `"mode": "keyword"` (or `"ai"` when `GEMINI_API_KEY` is configured);
the chat UI displays it. It also edits timetables conversationally
(`move`/`cancel`/`swap` with propose → confirm → apply, `rename X to Y`
applied directly).

## Multi-view + multi-format export

One timetable, five perspectives: `GET /schedule/{id}/views?view=master|teacher|student|staff|canteen`
(staff = per-slot occupancy/breaks; canteen = lunch window + demand peaks).
Every view exports in every format:

```
GET /export/{id}?view=teacher&format=pdf|csv|xlsx|png|jpg|json|html
```

## Preference learning loop (scikit-learn)

1. Teachers rate schedules: `POST /feedback` (satisfaction 1–5, preferred
   Morning/Afternoon/Evening, workload, comments) — form on every timetable page.
2. Retrain: `POST /ml/retrain` (or Celery `timetable.retrain` in background).
   RandomForest on 6 schedule-context features → `app/ml/models/*.pkl` + registry row.
   **Learning starts at 30 feedback responses** — below that the endpoint
   refuses honestly instead of fitting noise. Set `ML_MODEL_DIR` to share model
   files between workers via a volume.
3. Next generation applies it: `POST /schedule/generate-simple` with
   `"use_ml_preferences": true` fills each teacher's preferred slots from the model.
4. Inspect: `GET /ml/model-stats`, preview `POST /ml/suggest`, ML panel on `/analytics`.

## Dataset upload

- `POST /upload/file` (multipart `.csv`/`.xlsx`) with guide columns
  `teacher_name,course_name,credit_hours,student_group,preferred_time` →
  `{teachers, courses, preview, errors[]}` with per-row messages; the `/data`
  page renders the preview and row errors, plus a manual table, CSV template
  download, and one-click continue to the builder.
- `POST /upload/parse` turns raw CSV text into an Easy Builder draft (legacy helper).

## Editing timetables (tools UI + chatbot)

Every timetable stays editable after generation, and every edit is
re-validated against all hard constraints (including session-group
distinctness). Successful edits are saved as **new runs** — originals are
never mutated.

- **Edit-tools UI:** open any timetable → "✏️ Edit this timetable" →
  click a session to move it (slot + room pickers), swap two sessions, or
  cancel one. Rejected edits explain why (e.g. "venue double-booked").
- **Chatbot:** with a timetable attached, say things like
  *"move Math (1/2) to Wednesday"*, *"cancel Art"*, or *"swap Math and Art"*.
  The bot dry-runs the edit, proposes the first compliant option
  ("I can move 'Math (1/2)' to Wed 08:00–09:00 — reply 'yes'"), and applies
  it on confirmation, linking the new timetable.
- API: `POST /schedule/{id}/edit` with
  `{"op": "move", "course_id":…, "to_slot_id":…, "to_venue_id":…}`,
  `{"op": "cancel", "course_id":…}`, or
  `{"op": "swap", "course_id_a":…, "course_id_b":…}`.
- **Renaming teachers:** `PATCH /teachers/{id}` with `{"name": "…"}` updates
  the master record and every stored timetable summary, so all views, exports,
  and future edits show the new name. On the timetable page every teacher has
  an inline ✏️ Rename button; in chat just say *"rename Alice to Alicia"*.

Two data-model notes: `generate-simple` allocates each dataset a fresh
100k id block (`next_id_block`/`rebase_ids`), and every run snapshots its
masters into `summary_data`, so concurrent datasets can never corrupt each
other's edits, views, or exports.
