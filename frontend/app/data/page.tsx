"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, API_URL, authHeaders } from "@/lib/api";

type Row = {
  teacher: string;
  course: string;
  credits: number;
  group: string;
  pref: string;
};

const EMPTY: Row = { teacher: "", course: "", credits: 3, group: "", pref: "" };
const DRAFT_KEY = "tte_draft";

function templateCsv(): string {
  return [
    "teacher_name,course_name,credit_hours,student_group,preferred_time",
    "Dr. Ahmad Ali,Data Structures,3,CS-2024-A,Morning",
    "Ms. Fatima Khan,Database Systems,4,CS-2024-A,Afternoon",
  ].join("\n");
}

export default function DataPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([{ ...EMPTY }, { ...EMPTY }, { ...EMPTY }]);
  const [uploadErrors, setUploadErrors] = useState<{ row: number; message: string }[]>([]);
  const [uploadInfo, setUploadInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (i: number, patch: Partial<Row>) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const downloadTemplate = () => {
    const blob = new Blob([templateCsv()], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const el = document.createElement("a");
    el.href = url;
    el.download = "timetable-template.csv";
    el.click();
    URL.revokeObjectURL(url);
  };

  const onFile = async (f: File) => {
    setBusy(true);
    setError(null);
    setUploadErrors([]);
    try {
      const form = new FormData();
      form.append("file", f);
      const res = await fetch(`${API_URL}/upload/file`, {
        method: "POST",
        headers: authHeaders(),
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setUploadErrors(data.errors ?? []);
      setUploadInfo(
        `${data.total_rows} row(s) read, ${data.courses.length} usable course(s).`
      );
      if (data.courses?.length) {
        setRows(
          data.courses.map((c: any) => ({
            teacher: c.teacher,
            course: c.name,
            credits: c.credit_hours,
            group: c.student_group ?? "",
            pref: c.preferred_time ?? "",
          }))
        );
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const saveAndContinue = () => {
    const filled = rows.filter((r) => r.teacher.trim() && r.course.trim());
    if (!filled.length) {
      setError("Add at least one row with a teacher and a course.");
      return;
    }
    const teachers = [...new Set(filled.map((r) => r.teacher.trim()))].map((name) => ({
      name,
      max_hours_per_day: 6,
      unavailable_days: "",
    }));
    const courses = filled.map((r) => ({
      name: r.course.trim(),
      teacher: r.teacher.trim(),
      credit_hours: Math.min(4, Math.max(1, r.credits)),
      capacity: 30,
      group: r.group.trim(),
      pref: r.pref,
    }));
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ teachers, courses }));
    router.push("/schedule/easy");
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Load your data</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Upload a CSV/Excel file <strong>or</strong> type rows below — both feed the
          same generator. Columns: teacher, course, credit hours (1–4), student
          group (optional), preferred time (optional).
        </p>
      </div>

      <section className="space-y-2 rounded border p-4">
        <h2 className="font-semibold">Option A — Upload a file</h2>
        <div className="flex flex-wrap items-center gap-3">
          <label className="cursor-pointer rounded border px-3 py-1.5 text-sm">
            {busy ? "Reading…" : "Choose CSV / Excel file"}
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
            />
          </label>
          <button onClick={downloadTemplate} className="rounded border px-3 py-1.5 text-sm">
            Download template
          </button>
        </div>
        {uploadInfo && <p className="text-sm text-gray-600">{uploadInfo}</p>}
        {uploadErrors.length > 0 && (
          <ul className="space-y-1 text-sm text-red-600">
            {uploadErrors.map((e, i) => (
              <li key={i}>Row {e.row}: {e.message}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2 rounded border p-4">
        <h2 className="font-semibold">Option B — Type the table</h2>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="overflow-x-auto">
          <table className="min-w-full border text-sm">
            <thead>
              <tr className="bg-gray-100 dark:bg-gray-800">
                <th className="border p-2 text-left">Teacher name</th>
                <th className="border p-2 text-left">Course name</th>
                <th className="border p-2">Credit hours</th>
                <th className="border p-2 text-left">Student group (optional)</th>
                <th className="border p-2">Preferred time</th>
                <th className="border p-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="border p-1">
                    <input value={r.teacher} onChange={(e) => set(i, { teacher: e.target.value })}
                      placeholder="Dr. Ahmad Ali" className="w-full rounded border p-1.5" />
                  </td>
                  <td className="border p-1">
                    <input value={r.course} onChange={(e) => set(i, { course: e.target.value })}
                      placeholder="Data Structures" className="w-full rounded border p-1.5" />
                  </td>
                  <td className="border p-1">
                    <select value={r.credits} onChange={(e) => set(i, { credits: Number(e.target.value) })}
                      className="rounded border p-1.5">
                      {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </td>
                  <td className="border p-1">
                    <input value={r.group} onChange={(e) => set(i, { group: e.target.value })}
                      placeholder="CS-2024-A" className="w-full rounded border p-1.5" />
                  </td>
                  <td className="border p-1">
                    <select value={r.pref} onChange={(e) => set(i, { pref: e.target.value })}
                      className="rounded border p-1.5">
                      <option value="">—</option>
                      <option value="Morning">Morning</option>
                      <option value="Afternoon">Afternoon</option>
                      <option value="Evening">Evening</option>
                    </select>
                  </td>
                  <td className="border p-1 text-center">
                    <button onClick={() => setRows(rows.filter((_, j) => j !== i))}
                      className="text-red-500" title="Remove row">🗑</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex gap-3">
          <button onClick={() => setRows([...rows, { ...EMPTY }])}
            className="rounded border px-3 py-1.5 text-sm">+ Add row</button>
          <button onClick={downloadTemplate} className="rounded border px-3 py-1.5 text-sm">
            Download template
          </button>
          <button onClick={saveAndContinue}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white">
            Save table & continue →
          </button>
        </div>
      </section>
    </div>
  );
}
