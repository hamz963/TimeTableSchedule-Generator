"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function FeedbackForm({
  scheduleRunId,
  teacherNames,
}: {
  scheduleRunId: number;
  teacherNames: string[];
}) {
  const [teacher, setTeacher] = useState(teacherNames[0] ?? "");
  const [satisfaction, setSatisfaction] = useState(4);
  const [preferredTime, setPreferredTime] = useState("");
  const [workload, setWorkload] = useState(3);
  const [comments, setComments] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSending(true);
    setStatus(null);
    try {
      await api("/feedback", {
        method: "POST",
        body: JSON.stringify({
          schedule_run_id: scheduleRunId,
          teacher_name: teacher,
          satisfaction_score: satisfaction,
          preferred_time: preferredTime,
          workload_satisfaction: workload,
          comments,
        }),
      });
      setStatus("Thanks! Your feedback trains the preference model for future schedules.");
      setComments("");
    } catch (e: any) {
      setStatus(`Failed: ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3 rounded border p-4">
      <h3 className="font-semibold">Rate this schedule (trains the AI)</h3>
      <div className="flex flex-wrap gap-3 text-sm">
        <label>
          Teacher{" "}
          <select value={teacher} onChange={(e) => setTeacher(e.target.value)} className="rounded border p-1.5">
            {teacherNames.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <label>
          Satisfaction (1–5){" "}
          <input type="number" min={1} max={5} value={satisfaction} onChange={(e) => setSatisfaction(Number(e.target.value))} className="w-16 rounded border p-1.5" />
        </label>
        <label>
          Prefer more{" "}
          <select value={preferredTime} onChange={(e) => setPreferredTime(e.target.value)} className="rounded border p-1.5">
            <option value="">No preference</option>
            <option value="Morning">Morning classes</option>
            <option value="Afternoon">Afternoon classes</option>
            <option value="Evening">Evening classes</option>
          </select>
        </label>
        <label>
          Workload happy? (1–5){" "}
          <input type="number" min={1} max={5} value={workload} onChange={(e) => setWorkload(Number(e.target.value))} className="w-16 rounded border p-1.5" />
        </label>
      </div>
      <input
        value={comments}
        onChange={(e) => setComments(e.target.value)}
        placeholder="Any comments? (optional)"
        className="w-full rounded border p-2 text-sm"
      />
      {status && <p className="text-sm text-gray-600 dark:text-gray-400">{status}</p>}
      <button disabled={sending || !teacher} className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">
        {sending ? "Sending…" : "Submit feedback"}
      </button>
    </form>
  );
}
