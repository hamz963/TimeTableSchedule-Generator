# Realistic-instance benchmark

The `/quality/benchmark` endpoint measures the optimizer on a uniform synthetic
grid (60-minute sessions, one teacher per course, no cohorts). That instance is
useful for comparing budgets, but it is not shaped like a university term.

`backend/scripts/bench_realistic.py` builds a harder, still reproducible
instance:

* **Mixed session lengths** — 60, 90 and 120-minute blocks, so labs and double
  periods exist and a 2-hour lab cannot be placed in a 1-hour slot.
* **Cohorts** — each student group takes 4–6 courses; no cohort may attend two
  classes at once.
* **Room types** — teaching labs (equipment + 30 seats), lecture halls (150
  seats) and seminar rooms (45 seats), sized from demand so the instance is hard
  but feasible by construction.
* **Teacher realism** — ~10 sessions per teacher, some with an unavailable day,
  capped at 6 teaching hours per day.

## Measured (seed 42, 5 s request budget, one run per size)

| Sessions | Teachers | Rooms | Wall clock | Status | Path | Scheduled | Quality | Optimizer improved | Hard violations |
|---:|---:|---:|---:|---|---|---:|---:|---|---:|
| 150 | 15 | 8 | 1.54 s | feasible | heuristic | 150/150 | 86.8 | yes | 0 |
| 400 | 40 | 20 | 1.74 s | feasible | heuristic | 400/400 | 85.7 | yes | 0 |
| 800 | 80 | 27 | 2.41 s | feasible | heuristic | 800/800 | 82.8 | yes | 0 |
| 1 200 | 120 | 39 | 3.67 s | feasible | heuristic | 1 200/1 200 | 81.2 | yes | 0 |
| 2 000 | 200 | 64 | 7.77 s | feasible | heuristic | 2 000/2 000 | 80.8 | **no** | 0 |

Reproduce:

```bash
cd backend
python scripts/bench_realistic.py --sessions 150 400 800 1200 2000
```

## What the numbers say

1. **Feasibility holds at realistic scale.** Every session is placed and the
   independent verifier finds zero hard violations at all five sizes — including
   cohorts, equipment and mixed durations.
2. **The 5-second promise holds up to ~1 200 sessions** (3.67 s including
   serialisation of the response). At 2 000 sessions the request takes 7.77 s,
   i.e. it overshoots its own budget by ~55 %.
3. **The optimizer stops mattering before the scheduler does.** It improves the
   greedy seed up to 1 200 sessions, but at 2 000 the wall-clock budget is
   consumed by the constructor and the optimizer is left with its 0.2 s floor
   (`improved: false`). Above that size the product is "greedy with a quality
   report", not "optimized".
4. **Quality declines with size** (86.8 → 80.8) because preference and fairness
   degrees of freedom shrink as the timetable fills — expected, and a more
   honest efficiency curve than a flat number.

## Caveats

* Wall-clock budgets mean the exact optimizer percentages move with machine
  speed; the feasibility, zero-violation and ordering results do not.
* The instance is *university-shaped*, not a real department's data. It does not
  model multi-room sessions, term-by-term recurrence or student enrolments — the
  data model still lacks those (see the README's honest-status section).
* One run per size; the pipeline is deterministic above the optimizer, and the
  optimizer's effect is reported separately (`improved`), so repeat runs do not
  change the feasibility conclusion.
