"use client";
import { useState } from "react";
import { useSchedule } from "@/hooks/useSchedule";
import TimetableGrid from "@/components/TimetableGrid";
import SolverStatus from "@/components/SolverStatus";

const DEMO = {
  faculty: [
    { id: 1, name: "Alice", max_hours_per_day: 6, max_days_per_week: 5, preferences: [1], unavailable_slots: [3] },
    { id: 2, name: "Bob", max_hours_per_day: 6, max_days_per_week: 5, preferences: [], unavailable_slots: [] },
  ],
  venues: [
    { id: 1, name: "R101", capacity: 50, equipment: ["projector"], available_slots: [] },
    { id: 2, name: "R102", capacity: 30, equipment: [], available_slots: [] },
  ],
  slots: [
    { id: 1, day_of_week: "Mon", start_time: "09:00", end_time: "10:00", duration_minutes: 60 },
    { id: 2, day_of_week: "Mon", start_time: "10:00", end_time: "11:00", duration_minutes: 60 },
    { id: 3, day_of_week: "Tue", start_time: "09:00", end_time: "10:00", duration_minutes: 60 },
  ],
  courses: [
    { id: 1, name: "Math", code: "M101", faculty_id: 1, capacity_required: 40, duration_minutes: 60, required_equipment: ["projector"] },
    { id: 2, name: "Physics", code: "P101", faculty_id: 1, capacity_required: 20, duration_minutes: 60, required_equipment: [] },
    { id: 3, name: "Chem", code: "C101", faculty_id: 2, capacity_required: 25, duration_minutes: 60, required_equipment: [] },
  ],
  time_limit_seconds: 5,
};

export default function SchedulePage() {
  const { loading, error, result, generate } = useSchedule();
  const [json, setJson] = useState(JSON.stringify(DEMO, null, 2));

  const onGenerate = async () => {
    const data = await generate(JSON.parse(json));
    return data;
  };

  const download = () => {
    if (!result) return;
    const rows = ["course_id,faculty_id,venue_id,slot_id"];
    for (const a of result.assignments) rows.push(`${a.course_id},${a.faculty_id},${a.venue_id},${a.slot_id}`);
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const el = document.createElement("a");
    el.href = url;
    el.download = `timetable-${result.schedule_run_id}.csv`;
    el.click();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Generate Timetable</h1>
      <textarea
        value={json}
        onChange={(e) => setJson(e.target.value)}
        rows={14}
        className="w-full rounded border p-2 font-mono text-xs"
      />
      <div className="flex gap-3">
        <button
          onClick={onGenerate}
          disabled={loading}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {loading ? "Solving…" : "Generate Timetable"}
        </button>
        {result && (
          <>
            <button onClick={download} className="rounded border px-4 py-2">Export CSV</button>
            <button onClick={() => window.print()} className="rounded border px-4 py-2">
              Print / PDF
            </button>
            <a href={`/schedule/${result.schedule_run_id}`} className="rounded border px-4 py-2">
              View #{result.schedule_run_id}
            </a>
          </>
        )}
      </div>
      <SolverStatus loading={loading} status={result?.status} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && <TimetableGrid assignments={result.assignments} />}
    </div>
  );
}
