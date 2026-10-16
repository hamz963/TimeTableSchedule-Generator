"use client";

const GRADE_COLORS: Record<string, string> = {
  excellent: "text-green-600 border-green-300",
  good: "text-emerald-600 border-emerald-300",
  fair: "text-amber-600 border-amber-300",
  weak: "text-orange-600 border-orange-300",
  poor: "text-red-600 border-red-300",
};

const SUB_LABELS: Record<string, string> = {
  preference_satisfaction: "Teacher preferences",
  time_band_satisfaction: "Time-of-day fit",
  room_efficiency: "Room efficiency",
  fairness: "Fair day spread",
  compactness: "Compact days",
};

function Gauge({ value, grade }: { value: number; grade: string }) {
  const color = GRADE_COLORS[grade] ?? "text-blue-600 border-blue-300";
  return (
    <div className={`flex h-24 w-24 flex-col items-center justify-center rounded-full border-4 ${color}`}>
      <span className="text-3xl font-bold">{value}</span>
      <span className="text-xs uppercase tracking-wide">{grade}</span>
    </div>
  );
}

export default function QualityPanel({ report }: { report: any }) {
  if (!report) return null;
  const score = report.quality?.score ?? report.score;
  const teachers = report.quality?.teachers ?? report.teachers ?? [];
  const reasons = report.quality?.reasons ?? report.reasons ?? [];
  const rules = report.quality?.rules ?? report.rules ?? [];
  const engine = report.engine ?? {};
  if (!score) return null;

  return (
    <div className="space-y-4 rounded-lg border bg-white p-6 shadow-md dark:bg-gray-900">
      <h3 className="text-xl font-bold">Schedule quality</h3>
      <div className="flex flex-wrap items-center gap-6">
        <Gauge value={score.score} grade={score.grade} />
        <div className="min-w-[240px] flex-1 space-y-2">
          {Object.entries(score.sub_scores ?? {}).map(([key, val]: any) => (
            <div key={key} className="flex items-center gap-2 text-sm">
              <span className="w-40 text-gray-600 dark:text-gray-400">
                {SUB_LABELS[key] ?? key}
              </span>
              <div className="h-2.5 flex-1 rounded bg-gray-200 dark:bg-gray-700">
                <div
                  className="h-2.5 rounded bg-blue-500"
                  style={{ width: `${Math.min(100, Number(val))}%` }}
                />
              </div>
              <span className="w-12 text-right">{val}%</span>
            </div>
          ))}
        </div>
      </div>

      {engine.path && (
        <p className="text-xs text-gray-500">
          Engine path: <span className="font-mono">{engine.path}</span>
          {engine.optimizer?.improved && (
            <>
              {" "}· optimizer improved cost by{" "}
              <span className="font-semibold text-green-600">
                {engine.optimizer.improvement_pct}%
              </span>{" "}
              over {engine.optimizer.iterations?.toLocaleString()} iterations
            </>
          )}
        </p>
      )}

      {reasons.length > 0 && (
        <div>
          <h4 className="mb-1 font-semibold">Why this timetable</h4>
          <ul className="list-inside list-disc text-sm text-gray-700 dark:text-gray-300">
            {reasons.map((r: string, i: number) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {rules.length > 0 && (
        <div>
          <h4 className="mb-1 font-semibold">Declared rules</h4>
          <ul className="space-y-1 text-sm">
            {rules.map((r: any, i: number) => (
              <li key={i} className="flex items-center gap-2">
                <span className={r.satisfied ? "text-green-600" : "text-red-600"}>
                  {r.satisfied ? "✓" : "✗"}
                </span>
                <span className="font-medium">{r.name || r.kind}</span>
                <span className="rounded border px-1.5 text-xs text-gray-500">
                  {r.hard ? "hard" : "soft"}
                </span>
                {!r.satisfied && r.violations?.length > 0 && (
                  <span className="text-xs text-red-600">{r.violations[0]}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {teachers.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold">
            Per-teacher breakdown ({teachers.length})
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="min-w-full border text-xs">
              <thead>
                <tr>
                  <th className="border p-1.5 text-left">Teacher</th>
                  <th className="border p-1.5">Sessions</th>
                  <th className="border p-1.5">Hours</th>
                  <th className="border p-1.5 text-left">Days</th>
                  <th className="border p-1.5 text-left">Notes</th>
                </tr>
              </thead>
              <tbody>
                {teachers.map((t: any) => (
                  <tr key={t.id}>
                    <td className="border p-1.5">{t.name}</td>
                    <td className="border p-1.5 text-center">{t.sessions}</td>
                    <td className="border p-1.5 text-center">
                      {(t.total_minutes / 60).toFixed(1)}
                    </td>
                    <td className="border p-1.5">{t.days?.join(", ")}</td>
                    <td className="border p-1.5 text-orange-600">
                      {t.notes?.join("; ") || ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
