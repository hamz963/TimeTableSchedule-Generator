"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import TimetableGrid from "@/components/TimetableGrid";
import Analytics from "@/components/Analytics";
import FeedbackForm from "@/components/FeedbackForm";
import ExportOptions from "@/components/ExportOptions";
import ChatBot from "@/components/ChatBot";
import ScheduleEditor from "@/components/ScheduleEditor";
import TeacherList from "@/components/TeacherList";

export default function ScheduleDetail({ params }: { params: { id: string } }) {
  const [schedule, setSchedule] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [teacherView, setTeacherView] = useState<any>(null);
  const [viewName, setViewName] = useState("master");
  const [viewData, setViewData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = () => setRefreshKey((k) => k + 1);

  useEffect(() => {
    (async () => {
      try {
        setSchedule(await api(`/schedule/${params.id}`));
        setAnalytics(await api(`/analytics/schedule/${params.id}`));
        setTeacherView(await api(`/schedule/${params.id}/views?view=teacher`));
      } catch (e: any) {
        setError(e.message);
      }
    })();
  }, [params.id, refreshKey]);

  useEffect(() => {
    (async () => {
      try {
        setViewData(await api(`/schedule/${params.id}/views?view=${viewName}`));
      } catch {
        setViewData(null);
      }
    })();
  }, [params.id, viewName, refreshKey]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!schedule) return <p>Loading…</p>;
  const teacherNames = (teacherView?.teachers ?? []).map((t: any) => t.name);
  const summary = schedule.summary ?? {};
  const toMap = (rows: any[], labelMap: any, labelKey = "name") => {
    const m: Record<number, string> = {};
    for (const r of rows ?? []) m[r.id] = labelMap?.[r.id] ?? r[labelKey] ?? `${r.id}`;
    return m;
  };
  const gridNames = {
    courses: toMap(schedule.courses, summary.course_labels),
    teachers: toMap(schedule.teachers, summary.teacher_names),
    rooms: toMap(schedule.rooms, summary.room_names),
    slots: toMap(
      (schedule.slots ?? []).map((s: any) => ({ ...s, name: s.label })),
      summary.slot_labels,
    ),
  };
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Timetable #{params.id}</h1>
      <p className="text-sm text-gray-500">
        Status: {schedule.solver_status} · {schedule.total_time_ms} ms ·{" "}
        {schedule.total_courses_scheduled} courses
      </p>
      <TimetableGrid assignments={schedule.assignments} names={gridNames} />

      <TeacherList teachers={schedule.teachers ?? []} onRenamed={refresh} />

      <ScheduleEditor runId={params.id} schedule={schedule} />

      <div className="space-y-2">
        <h2 className="text-xl font-bold">Audience view</h2>
        <div className="flex gap-2 text-sm">
          {["master", "teacher", "student", "staff", "canteen"].map((v) => (
            <button
              key={v}
              onClick={() => setViewName(v)}
              className={`rounded border px-3 py-1 capitalize ${viewName === v ? "bg-blue-600 text-white" : ""}`}
            >
              {v}
            </button>
          ))}
        </div>
        <pre className="max-h-96 overflow-auto rounded border bg-gray-50 p-3 text-xs dark:bg-gray-900">
          {viewData ? JSON.stringify(viewData, null, 2) : "Loading…"}
        </pre>
      </div>

      <ExportOptions scheduleId={params.id} />

      <h2 className="text-xl font-bold">Analytics</h2>
      <Analytics data={analytics} />

      <FeedbackForm scheduleRunId={Number(params.id)} teacherNames={teacherNames} />

      <div className="space-y-2">
        <h2 className="text-xl font-bold">Ask the assistant</h2>
        <ChatBot scheduleRunId={Number(params.id)} />
      </div>
    </div>
  );
}
