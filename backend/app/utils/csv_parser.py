"""CSV parsing: teacher/course datasets -> Easy Builder payloads.

Teachers CSV:  name[, max_hours_per_day][, day1;day2...]   (# comments + header skipped)
Courses CSV:   name, teacher[, credit_hours][, capacity_required]
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _rows(text: str) -> List[List[str]]:
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append([c.strip() for c in line.split(",")])
    # drop a header row if it looks like one
    if rows and any(h in rows[0][0].lower() for h in ("name", "teacher", "course")):
        if len(rows[0]) > 1 or "name" in rows[0][0].lower():
            rows = rows[1:]
    return rows


def _num(value: str, default: int) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def parse_teachers_csv(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    teachers, warnings = [], []
    for i, r in enumerate(_rows(text), start=1):
        if not r[0]:
            warnings.append(f"teachers line {i}: missing name, skipped")
            continue
        days = [d.strip() for reply in [r[2] if len(r) > 2 else ""] for d in reply.replace(";", " ").split() if d.strip()]
        teachers.append(
            {
                "name": r[0],
                "max_hours_per_day": _num(r[1], 6) if len(r) > 1 and r[1] else 6,
                "unavailable_days": days,
            }
        )
    return teachers, warnings


def parse_courses_csv(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    courses, warnings = [], []
    for i, r in enumerate(_rows(text), start=1):
        if len(r) < 2 or not r[0] or not r[1]:
            warnings.append(f"courses line {i}: need 'name, teacher', skipped")
            continue
        courses.append(
            {
                "name": r[0],
                "teacher": r[1],
                "credit_hours": _num(r[2], 3) if len(r) > 2 and r[2] else 3,
                "capacity_required": _num(r[3], 30) if len(r) > 3 and r[3] else 30,
            }
        )
    return courses, warnings
