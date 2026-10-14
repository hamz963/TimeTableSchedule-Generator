"""Conversational scheduling assistant: rule-based intent parsing.

Detects requested audience views, export formats, and time-of-day leanings
from free text, asks one clarifying question at a time, then flips to
ready_to_generate. Deterministic and offline; replies are optionally
polished by Gemini (see ai_provider) when GEMINI_API_KEY is configured.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.services.ai_provider import polish_reply

VIEW_KEYWORDS = {
    "master": ["master", "university", "overall", "full", "complete", "entire", "all"],
    "teacher": ["teacher", "faculty", "instructor", "professor", "lecturer", "tutor"],
    "student": ["student", "pupil", "class", "cohort", "learner", "kids"],
    "staff": ["staff", "support", "admin", "worker", "cleaner", "security"],
    "canteen": ["canteen", "cafeteria", "food", "lunch", "meal", "kitchen", "dining", "mess"],
}

FORMAT_KEYWORDS = {
    "pdf": ["pdf"],
    "xlsx": ["xlsx", "excel", "spreadsheet"],
    "csv": ["csv"],
    "png": ["png", "image", "picture", "photo"],
    "jpg": ["jpg", "jpeg"],
    "json": ["json"],
    "html": ["html", "web", "webpage"],
}

TIME_KEYWORDS = {
    "morning": ["morning", "am ", "early"],
    "afternoon": ["afternoon", "pm ", "midday", "evening", "late"],
}

VIEW_ORDER = ["master", "teacher", "student", "staff", "canteen"]

_conversations: Dict[str, Dict[str, Any]] = {}


def start_conversation(schedule_run_id: Optional[int] = None) -> Dict[str, Any]:
    cid = uuid.uuid4().hex[:12]
    _conversations[cid] = {
        "schedule_run_id": schedule_run_id,
        "views": set(),
        "formats": set(),
        "time_pref": None,
        "asked_time": False,
        "history": [],
        "pending_edit": None,
    }
    greeting = (
        "Hi! I'm your scheduling assistant. "
        "Which schedules do you need? (e.g. teacher schedules, student schedules, canteen staff)"
    )
    if schedule_run_id is None:
        greeting += " Tip: start me from a generated timetable so I can export it for you."
    return {"conversation_id": cid, "reply": polish_reply(greeting), "status": "collecting",
            "mode": _mode()}


def _detect(text: str, table: Dict[str, List[str]]) -> List[str]:
    t = f" {text.lower()} "
    return [key for key, words in table.items() if any(w in t for w in words)]


def send_message(conversation_id: str, message: str, db=None,
                 actor_role: str = "scheduler") -> Dict[str, Any]:
    convo = _conversations.get(conversation_id)
    if convo is None:
        raise KeyError("conversation not found")
    text = message or ""
    lowered = f" {text.lower()} "

    is_teacher = actor_role == "teacher"
    if is_teacher and (_looks_like_edit(lowered) or _RENAME_RE.search(text.strip())):
        reply = ("Teacher accounts can't change timetables — ask a scheduler. "
                 "I can still show your own schedule: try 'my teacher schedule as PDF'.")
        return _answer(convo, conversation_id, reply, [], [], "collecting")

    # confirm / dismiss a proposed edit first (highest priority)
    if convo.get("pending_edit") is not None:
        if any(w in lowered for w in ("yes", "confirm", "do it", "apply", " ok ", "proceed", "sure")):
            return _confirm_edit(conversation_id, convo, db)
        if any(w in lowered for w in ("no", "never mind", "nevermind", "cancel that", "forget it", "drop")):
            convo["pending_edit"] = None
            reply = "OK, edit dropped. What else can I do for this timetable?"
            return _answer(convo, conversation_id, reply, [], [], "collecting")

    # rename intents: "rename Alice to Alicia" (safe: applied immediately)
    if db is not None and convo.get("schedule_run_id") is not None:
        renamed = _try_rename(db, convo["schedule_run_id"], text)
        if renamed is not None:
            return _answer(convo, conversation_id, renamed, [], [], "collecting")

    # edit intents: "move X to Tuesday", "cancel Physics", "swap A and B"
    if db is not None and convo.get("schedule_run_id") is not None and _looks_like_edit(lowered):
        result = propose_edit(db, convo["schedule_run_id"], text)
        if result.get("proposed") is not None:
            convo["pending_edit"] = result["proposed"]
            reply = f"I can {result['description']}. Reply 'yes' to apply it, or 'no' to drop it."
            return _answer(convo, conversation_id, reply, [], [], "confirm_edit",
                           pending_edit=result["description"])
        reply = result.get("reason", "I couldn't work out that edit.")
        return _answer(convo, conversation_id, reply, [], [], "collecting")
    if _looks_like_edit(lowered) and convo.get("schedule_run_id") is None:
        reply = "To edit a timetable, start me from a generated one (attach its ID) first."
        return _answer(convo, conversation_id, reply, [], [], "collecting")
    views = [v for v in _detect(text, VIEW_KEYWORDS) if v not in convo["views"]]
    formats = [f for f in _detect(text, FORMAT_KEYWORDS) if f not in convo["formats"]]
    convo["views"].update(views)
    convo["formats"].update(formats)
    for pref in _detect(text, TIME_KEYWORDS):
        convo["time_pref"] = "Morning" if pref == "morning" else "Afternoon"
    convo["history"].append({"user": text})

    if any(w in lowered for w in ("help", "what can you", "how do")):
        reply = (
            "I can generate timetable views for master, teacher, student, staff, "
            "and canteen audiences, and export them as PDF, Excel, CSV, PNG, JPG, "
            "JSON, or HTML. I can also edit this timetable: try 'move Math to "
            "Tuesday', 'cancel Art', or 'swap Math and Art'."
        )
        return _answer(convo, conversation_id, reply, views, formats, "collecting")

    if not convo["views"]:
        reply = (
            "Got it. Which audiences should I prepare schedules for? "
            "Choose any of: master, teacher, student, staff, canteen."
        )
        return _answer(convo, conversation_id, reply, views, formats, "collecting")

    if not convo["formats"]:
        reply = (
            f"Great — I'll prepare {', '.join(sorted(convo['views'], key=VIEW_ORDER.index))} "
            "schedules. Which export formats do you prefer? (PDF, Excel, CSV, PNG, JPG, JSON, HTML)"
        )
        return _answer(convo, conversation_id, reply, views, formats, "collecting")

    if not convo["asked_time"] and convo["time_pref"] is None:
        convo["asked_time"] = True
        reply = (
            f"Perfect! Noted formats: {', '.join(sorted(convo['formats']))}. "
            "One more thing for future schedules: should I prioritize morning or afternoon classes?"
        )
        return _answer(convo, conversation_id, reply, views, formats, "collecting")

    chosen_views = ", ".join(sorted(convo["views"], key=VIEW_ORDER.index))
    chosen_formats = ", ".join(sorted(convo["formats"]))
    reply = (
        f"Excellent! I'll generate {len(convo['views'])} schedule view(s) "
        f"({chosen_views}) in {chosen_formats}. Ready to generate?"
    )
    return _answer(convo, conversation_id, reply, views, formats, "ready_to_generate")


def _mode() -> str:
    """Which brain answered: 'ai' (Gemini key configured) or 'keyword'."""
    try:
        from app.config import get_settings

        return "ai" if (get_settings().gemini_api_key or "").strip() else "keyword"
    except Exception:
        return "keyword"


def _answer(convo, conversation_id, reply, views, formats, status,
            pending_edit=None, new_run_id=None):
    convo["history"].append({"bot": reply})
    out = {
        "conversation_id": conversation_id,
        "reply": polish_reply(reply),
        "detected_views": views,
        "detected_formats": formats,
        "selected_views": sorted(convo["views"], key=VIEW_ORDER.index),
        "selected_formats": sorted(convo["formats"]),
        "time_preference": convo["time_pref"],
        "status": status,
        "mode": _mode(),
    }
    if pending_edit is not None:
        out["pending_edit"] = pending_edit
    if new_run_id is not None:
        out["new_run_id"] = new_run_id
    return out


def get_conversation(conversation_id: str) -> Dict[str, Any]:
    convo = _conversations.get(conversation_id)
    if convo is None:
        raise KeyError("conversation not found")
    return convo


def clear_conversations() -> None:  # test isolation
    _conversations.clear()


# -- interactive editing ------------------------------------------------------

import re as _re

_RENAME_RE = _re.compile(r"(?:rename|change)\s+(?:teacher\s+)?(.+?)\s+to\s+(.+)", _re.IGNORECASE)
_NON_NAME_WORDS = ("view", "views", "format", "formats", "schedule", "schedules",
                   "export", "pdf", "xlsx", "excel", "csv")


def _try_rename(db, run_id: int, text: str):
    """Handle 'rename Alice to Alicia' / 'change teacher Alice to Alicia'.

    Returns the reply string, or None when the message is not a rename.
    Renames are constraint-free, so they apply immediately (no confirm step).
    """
    match = _RENAME_RE.search(text.strip())
    if not match:
        return None
    old_raw, new_name = match.group(1).strip().strip("'\""), match.group(2).strip().strip("'\"")
    if not old_raw or not new_name:
        return None
    # Don't hijack view/format requests like "change teacher view to pdf".
    if any(w in old_raw.lower() for w in _NON_NAME_WORDS):
        return None
    names = (db_get_summary(db, run_id) or {}).get("teacher_names", {})
    hits = [(fid, n) for fid, n in names.items() if old_raw.lower() in n.lower()]
    if not hits:
        return (f"I don't see a teacher matching '{old_raw}' in this timetable. "
                f"Teachers here: {', '.join(names.values()) or 'none'}.")
    if len(hits) > 1:
        options = ", ".join(f"'{n}'" for _, n in hits)
        return f"That matches several teachers: {options}. Which one, e.g. 'rename {hits[0][1]} to {new_name}'?"
    from app.services.teachers import rename_teacher

    try:
        result = rename_teacher(db, int(hits[0][0]), new_name)
    except Exception as exc:
        return f"Couldn't rename: {exc}"
    return (f"Renamed '{hits[0][1]}' to '{result['name']}' "
            f"across {result['runs_updated']} timetable(s).")

_EDIT_VERBS = ("move", "shift", "reschedule", "cancel", "remove", "drop", "delete",
               "swap", "switch", "exchange")


def _looks_like_edit(padded_lower: str) -> bool:
    return any(f" {v} " in f" {padded_lower} " or padded_lower.startswith(f"{v} ")
               or f" {v}" in padded_lower for v in _EDIT_VERBS)


def _start_minutes(value) -> int:
    from datetime import time as dtime

    if isinstance(value, dtime):
        return value.hour * 60 + value.minute
    try:
        h, m = str(value).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _bucket(start_minutes: int) -> str:
    if start_minutes < 12 * 60:
        return "morning"
    if start_minutes < 17 * 60:
        return "afternoon"
    return "evening"


def _match_courses(text: str, entries, course_labels) -> List[int]:
    """Match session ids by full label first, then base course name."""
    t = text.lower()
    full_hits = [
        e.course_id for e in entries
        if course_labels.get(str(e.course_id), "").lower() in t
        and course_labels.get(str(e.course_id), "")
    ]
    # full-label hits that are non-trivial (longer than 3 chars to avoid noise)
    full_hits = [c for c in full_hits if len(course_labels.get(str(c), "")) > 3]
    if full_hits:
        return sorted(set(full_hits))
    import re as _re

    bases = {}
    for e in entries:
        full = course_labels.get(str(e.course_id), f"Course {e.course_id}")
        base = _re.sub(r"\s*\(\d+/\d+\)$", "", full).lower()
        bases.setdefault(base, []).append(e.course_id)
    hits = []
    for base, cids in bases.items():
        if base and base in t:
            hits.extend(cids)
    return sorted(set(hits))


def _find_day(text: str):
    from app.services.planner import normalize_day

    for token in text.replace(",", " ").split():
        try:
            return normalize_day(token)
        except Exception:
            continue
    return None


def propose_edit(db, run_id: int, text: str) -> Dict[str, Any]:
    """Turn 'move Math to Tuesday' into a validated operation (dry run).

    Returns {proposed: op, description} or {proposed: None, reason}.
    """
    from app.services import edits as edit_service
    from app.services.views import get_run_context

    try:
        ctx = get_run_context(db, run_id)
    except KeyError:
        return {"proposed": None, "reason": "I can't find that timetable."}
    entries = ctx["entries"]
    labels = ctx["course_labels"]
    lowered = f" {text.lower()} "

    def verb(*words):
        return any(f" {w} " in lowered or lowered.startswith(f"{w} ") for w in words)

    # Dataset-scoped slots (global slot table accumulates many datasets).
    snap = (db_get_summary(db, run_id) or {}).get("masters") or {}
    dataset_slots = snap.get("slots") or [
        {"id": s.id, "day_of_week": s.day_of_week, "start_time": s.start_time}
        for s in ctx["slots"].values()
    ]

    if verb("swap", "switch", "exchange"):
        cands = _match_courses(text, entries, labels)
        if len(cands) < 2:
            return {"proposed": None,
                    "reason": "Which two sessions should I swap? Name both, e.g. 'swap Math (1/2) and Art'."}
        op = {"op": "swap", "course_id_a": cands[0], "course_id_b": cands[1]}
        return _dry_run(db, run_id, op, labels)

    if verb("cancel", "remove", "drop", "delete"):
        cands = _match_courses(text, entries, labels)
        if not cands:
            return {"proposed": None,
                    "reason": "Which session should I cancel? Name it as shown in the timetable."}
        if len(cands) > 1:
            options = ", ".join(f"'{labels.get(str(c), c)}'" for c in cands)
            return {"proposed": None,
                    "reason": f"That matches several sessions: {options}. Which exact one?"}
        return _dry_run(db, run_id, {"op": "cancel", "course_id": cands[0]}, labels)

    # move / shift / reschedule
    cands = _match_courses(text, entries, labels)
    if not cands:
        return {"proposed": None,
                "reason": "Which session should I move? Name it as shown in the timetable."}
    if len(cands) > 1:
        options = ", ".join(f"'{labels.get(str(c), c)}'" for c in cands)
        return {"proposed": None,
                "reason": f"That matches several sessions: {options}. Which exact one, e.g. 'move {labels.get(str(cands[0]), '')} to Friday'?"}
    cid = cands[0]
    day = _find_day(text)
    if day is None:
        return {"proposed": None,
                "reason": f"Where should I move '{labels.get(str(cid), cid)}'? Name a day, e.g. 'move it to Thursday'."}
    bucket = None
    for b in ("morning", "afternoon", "evening"):
        if b in lowered:
            bucket = b
    room_filter = None
    for rid, rname in ctx["room_names"].items():
        if rname.lower() in text.lower():
            room_filter = int(rid)
            break

    current = next(e for e in entries if e.course_id == cid)
    day_slots = sorted(
        [s for s in dataset_slots if s.get("day_of_week") == day],
        key=lambda s: str(s.get("start_time", "")),
    )
    if not day_slots:
        return {"proposed": None, "reason": f"There are no class slots on {day}."}
    if bucket:
        day_slots = [s for s in day_slots
                     if _bucket(_start_minutes(s.get("start_time"))) == bucket]
        if not day_slots:
            return {"proposed": None, "reason": f"No {bucket} slots on {day}."}
    venue_ids = sorted({e.venue_id for e in entries if e.venue_id is not None})
    if room_filter is not None:
        venue_ids = [room_filter] + [v for v in venue_ids if v != room_filter]
    # same room first = minimal disruption
    venue_ids = sorted(venue_ids, key=lambda v: 0 if v == current.venue_id else 1)
    tried = 0
    for s in day_slots:
        for vid in venue_ids:
            if s["id"] == current.slot_id and vid == current.venue_id:
                continue
            tried += 1
            op = {"op": "move", "course_id": cid, "to_slot_id": s["id"], "to_venue_id": vid}
            try:
                edit_service.apply_edit(db, run_id, op, persist=False)
            except Exception:
                continue
            room_name = ctx["room_names"].get(str(vid), f"room {vid}")
            desc = (f"move '{labels.get(str(cid), cid)}' to "
                    f"{ctx['slot_labels'].get(str(s['id']), s['id'])}"
                    f"{'' if vid == current.venue_id else f' in {room_name}'}")
            return {"proposed": op, "description": desc}
    return {"proposed": None,
            "reason": f"No free compliant slot found on {day}"
                      + (f" ({bucket})" if bucket else "")
                      + f" after checking {tried} options — try another day."}


def _dry_run(db, run_id, op, labels):
    from app.services import edits as edit_service
    from app.services.edits import describe

    try:
        edit_service.apply_edit(db, run_id, op, persist=False)
    except Exception as exc:
        return {"proposed": None, "reason": f"That edit won't work: {exc}"}
    return {"proposed": op, "description": describe(op, labels)}


def _confirm_edit(conversation_id: str, convo: Dict[str, Any], db) -> Dict[str, Any]:
    from app.services import edits as edit_service
    from app.services.edits import describe

    op = convo["pending_edit"]
    convo["pending_edit"] = None
    if db is None:
        reply = "I lost database access; please try again."
        return _answer(convo, conversation_id, reply, [], [], "collecting")
    try:
        result = edit_service.apply_edit(db, convo["schedule_run_id"], op, persist=True)
    except Exception as exc:
        reply = f"Couldn't apply it after all: {exc}"
        return _answer(convo, conversation_id, reply, [], [], "collecting")
    reply = (f"Done — {describe(op, db_get_summary(db, convo['schedule_run_id']))}. Saved as timetable "
             f"#{result['new_run_id']} (the original is untouched).")
    return _answer(convo, conversation_id, reply, [], [], "edit_applied",
                   new_run_id=result["new_run_id"])


def db_get_summary(db, run_id: int) -> Dict[str, Any]:
    from app.models.timetable import ScheduleRun

    run = db.get(ScheduleRun, run_id)
    return (run.summary_data or {}) if run else {}
