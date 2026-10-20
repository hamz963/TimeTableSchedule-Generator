"use client";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";

type Maps = {
  courses: Record<number, string>;
  teachers: Record<number, string>;
  slots: { id: number; day: string; label: string }[];
  slotLabel: Record<number, string>;
  rooms: { id: number; name: string }[];
};

function mapsOf(schedule: any): Maps {
  const courses: Record<number, string> = {};
  for (const c of schedule.courses ?? []) courses[c.id] = c.name;
  const teachers: Record<number, string> = {};
  for (const t of schedule.teachers ?? []) teachers[t.id] = t.name;
  const slotLabel: Record<number, string> = {};
  for (const s of schedule.slots ?? []) slotLabel[s.id] = s.label;
  return { courses, teachers, slots: schedule.slots ?? [], slotLabel, rooms: schedule.rooms ?? [] };
}

export default function ScheduleEditor({
  runId,
  schedule,
}: {
  runId: number | string;
  schedule: any;
}) {
  const maps = useMemo(() => mapsOf(schedule), [schedule]);
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [toSlot, setToSlot] = useState<string>("");
  const [toRoom, setToRoom] = useState<string>("");
  const [swapWith, setSwapWith] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ newRunId: number; description: string } | null>(null);

  const sessions = useMemo(() => schedule.assignments ?? [], [schedule.assignments]);
  const byDay = useMemo(() => {
    const groups: Record<string, any[]> = {};
    for (const a of sessions) {
      const day = (maps.slots.find((s) => s.id === a.slot_id)?.day ?? "?").toString();
      (groups[day] ??= []).push(a);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [sessions, maps]);

  const reset = () => {
    setSelected(null);
    setToSlot("");
    setToRoom("");
    setSwapWith("");
    setError(null);
  };

  const callEdit = async (op: any) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api(`/schedule/${runId}/edit`, { method: "POST", body: JSON.stringify(op) });
      setDone({ newRunId: r.new_run_id, description: r.description });
      reset();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!editing) {
    return (
      <button onClick={() => setEditing(true)} className="rounded bg-amber-600 px-4 py-2 text-sm font-bold text-white">
        ✏️ Edit this timetable
      </button>
    );
  }

  const sel = sessions.find((a: any) => a.course_id === selected);

  return (
    <div className="space-y-3 rounded border border-amber-300 bg-amber-50 p-4 dark:bg-amber-950">
      <div className="flex items-center justify-between">
        <h3 className="font-bold">Edit mode — click a session, then move, swap, or cancel it</h3>
        <button onClick={() => { setEditing(false); reset(); setDone(null); }} className="text-sm underline">
          Done editing
        </button>
      </div>

      {done && (
        <div className="rounded border border-green-300 bg-green-50 p-2 text-sm dark:bg-green-950">
          ✅ {done.description} — saved as timetable{" "}
          <a href={`/schedule/${done.newRunId}`} className="font-bold text-blue-600 hover:underline">
            #{done.newRunId} →
          </a>{" "}
          (this one is unchanged)
        </div>
      )}
      {error && <p className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      <div className="space-y-4">
        {byDay.map(([day, list]) => (
          <div key={day}>
            <div className="text-sm font-semibold">{day}</div>
            <div className="flex flex-wrap gap-2">
              {list.map((a: any) => (
                <button
                  key={a.course_id}
                  onClick={() => { setSelected(a.course_id); setError(null); setDone(null); }}
                  className={`rounded border px-2 py-1 text-left text-xs ${
                    selected === a.course_id ? "border-blue-600 bg-blue-100 dark:bg-blue-900" : "bg-white dark:bg-gray-800"
                  }`}
                >
                  <div className="font-semibold">{maps.courses[a.course_id] ?? a.course_id}</div>
                  <div className="text-gray-500">{maps.slotLabel[a.slot_id]} · {(maps.rooms.find((r) => r.id === a.venue_id)?.name) ?? a.venue_id}</div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {sel && (
        <div className="space-y-2 rounded border bg-white p-3 text-sm dark:bg-gray-900">
          <p>
            Selected: <strong>{maps.courses[sel.course_id]}</strong> ({maps.slotLabel[sel.slot_id]})
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span>Move to</span>
            <select value={toSlot} onChange={(e) => setToSlot(e.target.value)} className="rounded border p-1.5">
              <option value="">Slot…</option>
              {maps.slots.map((s) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
            <select value={toRoom} onChange={(e) => setToRoom(e.target.value)} className="rounded border p-1.5">
              <option value="">Same room</option>
              {maps.rooms.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
            <button
              disabled={busy || !toSlot}
              onClick={() => callEdit({
                op: "move", course_id: sel.course_id, to_slot_id: Number(toSlot),
                ...(toRoom ? { to_venue_id: Number(toRoom) } : {}),
              })}
              className="rounded bg-blue-600 px-3 py-1.5 text-white disabled:opacity-50"
            >
              Apply move
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span>Swap with</span>
            <select value={swapWith} onChange={(e) => setSwapWith(e.target.value)} className="rounded border p-1.5">
              <option value="">Session…</option>
              {sessions.filter((a: any) => a.course_id !== sel.course_id).map((a: any) => (
                <option key={a.course_id} value={a.course_id}>
                  {maps.courses[a.course_id]} ({maps.slotLabel[a.slot_id]})
                </option>
              ))}
            </select>
            <button
              disabled={busy || !swapWith}
              onClick={() => callEdit({ op: "swap", course_id_a: sel.course_id, course_id_b: Number(swapWith) })}
              className="rounded border px-3 py-1.5 disabled:opacity-50"
            >
              Apply swap
            </button>
            <button
              disabled={busy}
              onClick={() => { if (confirm(`Cancel ${maps.courses[sel.course_id]}?`)) callEdit({ op: "cancel", course_id: sel.course_id }); }}
              className="rounded border border-red-300 px-3 py-1.5 text-red-600"
            >
              Cancel session
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
