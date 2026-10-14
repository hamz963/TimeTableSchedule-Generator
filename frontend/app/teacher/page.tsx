"use client";
import { useEffect, useState } from "react";
import { api, getUser } from "@/lib/api";
import ExportOptions from "@/components/ExportOptions";
import FeedbackForm from "@/components/FeedbackForm";

type Run = {
  schedule_run_id: number;
  solver_status: string;
  total_courses_scheduled: number;
  started_at: string | null;
};

export default function TeacherPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState<string>("");
  const [view, setView] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const user = typeof window !== "undefined" ? getUser() : null;

  useEffect(() => {
    api("/schedule/runs")
      .then((list) => {
        setRuns(list);
        if (list.length && !runId) setRunId(String(list[0].schedule_run_id));
      })
      .catch((e: any) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!runId) return;
    setError(null);
    api(`/schedule/${runId}/views?view=teacher`)
      .then(setView)
      .catch((e: any) => {
        setView(null);
        setError(e.message);
      });
  }, [runId]);

  const mine = (view?.teachers ?? [])[0];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">My Schedule</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {user ? (
            <>Signed in as <strong>{user.username}</strong> — showing only your classes.</>
          ) : (
            <>Your personal timetable. Sign in as a linked teacher account.</>
          )}
        </p>
      </div>

      <label className="block text-sm">
        Timetable{" "}
        <select
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          className="rounded border p-2"
        >
          <option value="">Choose…</option>
          {runs.map((r) => (
            <option key={r.schedule_run_id} value={r.schedule_run_id}>
              #{r.schedule_run_id} — {r.total_courses_scheduled} sessions ({r.solver_status})
            </option>
          ))}
        </select>
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {mine ? (
        <div className="space-y-2">
          <h2 className="text-xl font-bold">{mine.name}</h2>
          <table className="min-w-full border text-sm">
            <thead>
              <tr className="bg-gray-100 dark:bg-gray-800">
                <th className="border p-2 text-left">When</th>
                <th className="border p-2 text-left">Course</th>
                <th className="border p-2 text-left">Room</th>
              </tr>
            </thead>
            <tbody>
              {mine.sessions.map((s: any, i: number) => (
                <tr key={i}>
                  <td className="border p-2">{s.day_slot}</td>
                  <td className="border p-2 font-medium">{s.course}</td>
                  <td className="border p-2">{s.room}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        runId && !error && <p className="text-sm text-gray-500">No sessions for you in this timetable.</p>
      )}

      {runId && mine && (
        <>
          <ExportOptions scheduleId={runId} onlyViews={["teacher"]} />
          <FeedbackForm scheduleRunId={Number(runId)} teacherNames={[mine.name]} />
        </>
      )}
    </div>
  );
}
