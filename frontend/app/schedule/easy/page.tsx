"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import SolverStatus from "@/components/SolverStatus";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DRAFT_KEY = "tte_draft";

type Teacher = { name: string; max_hours_per_day: number; unavailable_days: string };
type Course = { name: string; teacher: string; credit_hours: number; group: string; pref: string };

const DEMO_TEACHERS: Teacher[] = [
  { name: "Alice", max_hours_per_day: 6, unavailable_days: "" },
  { name: "Bob", max_hours_per_day: 6, unavailable_days: "Fri" },
  { name: "Carol", max_hours_per_day: 4, unavailable_days: "" },
];
const DEMO_COURSES: Course[] = [
  { name: "Math", teacher: "Alice", credit_hours: 3, group: "CS-A", pref: "Morning" },
  { name: "Physics", teacher: "Alice", credit_hours: 2, group: "CS-A", pref: "" },
  { name: "Chemistry", teacher: "Bob", credit_hours: 2, group: "CS-B", pref: "" },
  { name: "Biology", teacher: "Carol", credit_hours: 2, group: "CS-B", pref: "" },
];

/** CSV split that respects "quoted, values". */
function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (ch === "," && !quoted) {
      out.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur.trim());
  return out;
}

function parseCsv(text: string): string[][] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .filter((l) => !l.startsWith("#"))
    .map(splitCsvLine);
}

function isHeaderRow(r: string[]): boolean {
  const head = (r[0] ?? "").toLowerCase();
  return head.includes("teacher") || head.includes("name");
}

export default function EasySchedulePage() {
  const [teachers, setTeachers] = useState<Teacher[]>(DEMO_TEACHERS);
  const [courses, setCourses] = useState<Course[]>(DEMO_COURSES);
  const [days, setDays] = useState<string[]>(["Mon", "Tue", "Wed", "Thu", "Fri"]);
  const [dayStart, setDayStart] = useState("09:00");
  const [dayEnd, setDayEnd] = useState("17:00");
  const [period, setPeriod] = useState(60);
  const [gap, setGap] = useState(30);
  const [lunch, setLunch] = useState(true);
  const [lunchStart, setLunchStart] = useState("12:00");
  const [lunchEnd, setLunchEnd] = useState("14:00");
  const [maxConsec, setMaxConsec] = useState(2);
  const [autoRooms, setAutoRooms] = useState(true);
  const [roomsText, setRoomsText] = useState("");

  // Prefill from the Data page draft (/data saves teachers+courses here).
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const draft = JSON.parse(raw);
      if (draft.teachers?.length) setTeachers(draft.teachers);
      if (draft.courses?.length) {
        setCourses(
          draft.courses.map((c: any) => ({
            name: c.name ?? "",
            teacher: c.teacher ?? "",
            credit_hours: Math.min(4, Math.max(1, Number(c.credit_hours) || 3)),
            group: c.group ?? "",
            pref: c.pref ?? "",
          }))
        );
      }
    } catch {
      /* ignore bad drafts */
    }
  }, []);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const teacherNames = useMemo(() => teachers.map((t) => t.name).filter(Boolean), [teachers]);

  const importTeachers = async (f: File) => {
    const rows = parseCsv(await f.text());
    setTeachers(
      rows.map((r) => ({
        name: r[0] ?? "",
        max_hours_per_day: Number(r[1]) || 6,
        unavailable_days: r[2] ?? "",
      }))
    );
  };

  const importCourses = async (f: File) => {
    const rows = parseCsv(await f.text()).filter((r) => !isHeaderRow(r));
    setCourses(
      rows.map((r) => ({
        name: r[0] ?? "",
        teacher: r[1] ?? "",
        credit_hours: Math.min(4, Math.max(1, Number(r[2]) || 3)),
        group: r[3] ?? "",
        pref: ["Morning", "Afternoon", "Evening"].includes((r[4] ?? "").trim())
          ? (r[4] ?? "").trim()
          : "",
      }))
    );
  };

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const rooms = autoRooms
        ? []
        : parseCsv(roomsText).map((r) => ({
            name: r[0],
            capacity: Number(r[1]) || 30,
          }));
      const payload = {
        teachers: teachers
          .filter((t) => t.name.trim())
          .map((t) => ({
            name: t.name.trim(),
            max_hours_per_day: t.max_hours_per_day,
            unavailable_days: t.unavailable_days
              .split(/[;\s]+/)
              .map((d) => d.trim())
              .filter(Boolean),
          })),
        courses: courses
          .filter((c) => c.name.trim() && c.teacher.trim())
          .map((c) => ({
            name: c.name.trim(),
            teacher: c.teacher.trim(),
            credit_hours: Math.min(4, Math.max(1, c.credit_hours)),
            student_group: c.group.trim(),
            preferred_time: c.pref,
          })),
        rooms,
        days,
        day_start: dayStart,
        day_end: dayEnd,
        period_minutes: period,
        gap_minutes: gap,
        lunch_break: lunch,
        lunch_start: lunchStart,
        lunch_end: lunchEnd,
        max_consecutive_periods: maxConsec,
      };
      setResult(await api("/schedule/generate-simple", { method: "POST", body: JSON.stringify(payload) }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const summary = result?.summary ?? {};
  const downloadCsv = () => {
    if (!result) return;
    const cl = summary.course_labels ?? {};
    const sl = summary.slot_labels ?? {};
    const tn = summary.teacher_names ?? {};
    const rn = summary.room_names ?? {};
    const rows = ["course,teacher,room,slot"];
    for (const a of result.assignments) {
      const q = (s: any) => `"${String(s ?? a.course_id).replace(/"/g, '""')}"`;
      rows.push(
        [q(cl[a.course_id]), q(tn[a.faculty_id]), q(rn[a.venue_id]), q(sl[a.slot_id])].join(",")
      );
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const el = document.createElement("a");
    el.href = url;
    el.download = `timetable-${result.schedule_run_id}.csv`;
    el.click();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Easy Timetable Builder</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Just list <strong>teachers</strong>, <strong>courses with credit hours</strong>, and the{" "}
          <strong>school day window</strong>. Periods, gaps, lunch breaks, rooms, and fair
          spreading across the week are handled automatically. Or import CSV files.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="space-y-2 rounded border p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">1. Teachers</h2>
            <label className="cursor-pointer rounded border px-2 py-1 text-xs">
              Import CSV
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && importTeachers(e.target.files[0])}
              />
            </label>
          </div>
          <p className="text-xs text-gray-500">CSV: <code>name, max_hours_per_day, unavailable_days</code> (e.g. <code>Alice, 6, Fri</code>)</p>
          {teachers.map((t, i) => (
            <div key={i} className="flex gap-2">
              <input
                value={t.name}
                onChange={(e) => setTeachers(teachers.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                placeholder="Teacher name"
                className="flex-1 rounded border p-1.5 text-sm"
              />
              <input
                type="number"
                min={1}
                max={12}
                value={t.max_hours_per_day}
                onChange={(e) => setTeachers(teachers.map((x, j) => (j === i ? { ...x, max_hours_per_day: Number(e.target.value) } : x)))}
                title="Max hours per day"
                className="w-16 rounded border p-1.5 text-sm"
              />
              <input
                value={t.unavailable_days}
                onChange={(e) => setTeachers(teachers.map((x, j) => (j === i ? { ...x, unavailable_days: e.target.value } : x)))}
                placeholder="Off days"
                title="Unavailable days, e.g. Fri"
                className="w-24 rounded border p-1.5 text-sm"
              />
              <button onClick={() => setTeachers(teachers.filter((_, j) => j !== i))} className="text-red-500">×</button>
            </div>
          ))}
          <button
            onClick={() => setTeachers([...teachers, { name: "", max_hours_per_day: 6, unavailable_days: "" }])}
            className="rounded border px-3 py-1 text-sm"
          >
            + Add teacher
          </button>
        </section>

        <section className="space-y-2 rounded border p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">2. Courses</h2>
            <label className="cursor-pointer rounded border px-2 py-1 text-xs">
              Import CSV
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && importCourses(e.target.files[0])}
              />
            </label>
          </div>
          <p className="text-xs text-gray-500">CSV: <code>course, teacher, credit_hours (1–4), student_group, preferred_time</code> — or use the <a href="/data" className="underline">Data page</a> for Excel upload</p>
          {courses.map((c, i) => (
            <div key={i} className="flex flex-wrap gap-2">
              <input
                value={c.name}
                onChange={(e) => setCourses(courses.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                placeholder="Course"
                className="flex-1 rounded border p-1.5 text-sm"
              />
              <select
                value={c.teacher}
                onChange={(e) => setCourses(courses.map((x, j) => (j === i ? { ...x, teacher: e.target.value } : x)))}
                className="rounded border p-1.5 text-sm"
              >
                <option value="">Teacher…</option>
                {teacherNames.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                max={4}
                value={c.credit_hours}
                onChange={(e) => setCourses(courses.map((x, j) => (j === i ? { ...x, credit_hours: Number(e.target.value) } : x)))}
                title="Credit hours (classes per week, 1–4)"
                className="w-16 rounded border p-1.5 text-sm"
              />
              <input
                value={c.group}
                onChange={(e) => setCourses(courses.map((x, j) => (j === i ? { ...x, group: e.target.value } : x)))}
                placeholder="Group (e.g. CS-A)"
                title="Student group — same group never has two classes at once"
                className="w-28 rounded border p-1.5 text-sm"
              />
              <select
                value={c.pref}
                onChange={(e) => setCourses(courses.map((x, j) => (j === i ? { ...x, pref: e.target.value } : x)))}
                title="Preferred time of day (soft suggestion)"
                className="rounded border p-1.5 text-sm"
              >
                <option value="">Any time</option>
                <option value="Morning">Morning</option>
                <option value="Afternoon">Afternoon</option>
                <option value="Evening">Evening</option>
              </select>
              <button onClick={() => setCourses(courses.filter((_, j) => j !== i))} className="text-red-500">×</button>
            </div>
          ))}
          <button
            onClick={() => setCourses([...courses, { name: "", teacher: "", credit_hours: 3, group: "", pref: "" }])}
            className="rounded border px-3 py-1 text-sm"
          >
            + Add course
          </button>
        </section>
      </div>

      <section className="space-y-3 rounded border p-4">
        <h2 className="font-semibold">3. School day &amp; breaks</h2>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span>Days:</span>
          {DAYS.map((d) => (
            <label key={d} className="flex items-center gap-1 rounded border px-2 py-1">
              <input
                type="checkbox"
                checked={days.includes(d)}
                onChange={() => setDays(days.includes(d) ? days.filter((x) => x !== d) : [...days, d])}
              />
              {d}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <label>Day start <input type="time" value={dayStart} onChange={(e) => setDayStart(e.target.value)} className="rounded border p-1" /></label>
          <label>Day end <input type="time" value={dayEnd} onChange={(e) => setDayEnd(e.target.value)} className="rounded border p-1" /></label>
          <label>Period (min) <input type="number" min={15} max={240} value={period} onChange={(e) => setPeriod(Number(e.target.value))} className="w-20 rounded border p-1" /></label>
          <label>Gap between classes (min) <input type="number" min={0} max={60} value={gap} onChange={(e) => setGap(Number(e.target.value))} className="w-20 rounded border p-1" /></label>
          <label title="Max back-to-back periods per teacher per day (0 = no limit)">
            Max in a row <input type="number" min={0} max={8} value={maxConsec} onChange={(e) => setMaxConsec(Number(e.target.value))} className="w-16 rounded border p-1" />
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={lunch} onChange={(e) => setLunch(e.target.checked)} /> Lunch break
          </label>
          {lunch && (
            <>
              <label>Lunch start <input type="time" value={lunchStart} onChange={(e) => setLunchStart(e.target.value)} className="rounded border p-1" /></label>
              <label>Lunch end <input type="time" value={lunchEnd} onChange={(e) => setLunchEnd(e.target.value)} className="rounded border p-1" /></label>
            </>
          )}
        </div>
        <div className="text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={autoRooms} onChange={(e) => setAutoRooms(e.target.checked)} />
            Create rooms automatically
          </label>
          {!autoRooms && (
            <textarea
              value={roomsText}
              onChange={(e) => setRoomsText(e.target.value)}
              rows={3}
              placeholder={"One per line: Room A, 30"}
              className="mt-2 w-full rounded border p-2 font-mono text-xs"
            />
          )}
        </div>
        <div className="flex gap-3">
          <button onClick={generate} disabled={loading} className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
            {loading ? "Solving…" : "Generate Timetable"}
          </button>
          {result && (
            <>
              <button onClick={downloadCsv} className="rounded border px-4 py-2">Export CSV</button>
              <button onClick={() => window.print()} className="rounded border px-4 py-2">Print / PDF</button>
            </>
          )}
        </div>
        <SolverStatus loading={loading} status={result?.status} />
        {error && <p className="text-sm text-red-600">{error}</p>}
      </section>

      {result && (
        <section className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Class sessions" value={String(summary.sessions ?? "—")} />
            <Stat label="Time slots" value={String(summary.total_slots ?? "—")} />
            <Stat label="Rooms" value={(summary.rooms ?? []).join(", ") || "—"} />
            <Stat label="Solver time" value={`${result.solver_time_ms} ms (${result.status})`} />
          </div>
          {summary.fairness && (
            <div className="rounded border border-green-300 bg-green-50 p-3 text-sm dark:bg-green-950">
              <strong>Fairness guarantees applied:</strong>
              <ul className="list-disc pl-5">
                {summary.fairness.map((f: string) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
          )}
          <DayGrid result={result} summary={summary} />
          <a href={`/schedule/${result.schedule_run_id}`} className="text-sm text-blue-600 hover:underline">
            Open full timetable #{result.schedule_run_id} with analytics →
          </a>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-bold">{value}</div>
    </div>
  );
}

function DayGrid({ result, summary }: { result: any; summary: any }) {
  const cl = summary.course_labels ?? {};
  const sl = summary.slot_labels ?? {};
  const tn = summary.teacher_names ?? {};
  const rn = summary.room_names ?? {};
  const days: string[] = summary.days ?? [];
  const bySlot: Record<string, any[]> = {};
  for (const a of result.assignments) {
    (bySlot[a.slot_id] ??= []).push(a);
  }
  const slotIds = Object.keys(bySlot).map(Number).sort((a, b) => a - b);
  const rooms: string[] = summary.rooms ?? [];
  const roomIds = Object.keys(rn).map(Number).sort((a, b) => a - b);
  return (
    <div className="space-y-6">
      {days.map((day) => {
        const daySlots = slotIds.filter((sid) => String(sl[sid] ?? "").startsWith(day));
        if (!daySlots.length) return null;
        return (
          <div key={day}>
            <h3 className="mb-1 font-semibold">{day}</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full border text-sm">
                <thead>
                  <tr>
                    <th className="border p-2">Time</th>
                    {(roomIds.length ? roomIds : [0]).map((rid) => (
                      <th key={rid} className="border p-2">{rn[rid] ?? rooms[rid] ?? "Room"}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {daySlots.map((sid) => (
                    <tr key={sid}>
                      <td className="border p-2 font-medium">{sl[sid]}</td>
                      {(roomIds.length ? roomIds : [0]).map((rid) => {
                        const a = (bySlot[sid] ?? []).find((x: any) => x.venue_id === rid);
                        return (
                          <td key={rid} className={`border p-2 ${a ? "bg-blue-50 dark:bg-blue-950" : ""}`}>
                            {a ? (
                              <>
                                <div className="font-semibold">{cl[a.course_id] ?? a.course_id}</div>
                                <div className="text-xs text-gray-600 dark:text-gray-400">{tn[a.faculty_id]}</div>
                              </>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}
