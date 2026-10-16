"use client";

function Table({ headers, rows }: { headers: string[]; rows: any[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border text-sm">
        <thead>
          <tr className="bg-gray-100 dark:bg-gray-800">
            {headers.map((h, i) => (
              <th key={i} className="border p-2 text-left font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="even:bg-gray-50 dark:even:bg-gray-900">
              {row.map((cell, j) => (
                <td key={j} className="border p-2 whitespace-pre-line">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Bar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-2.5 w-32 rounded bg-gray-200 dark:bg-gray-700">
        <div className="h-2.5 rounded bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs">{value}</span>
    </div>
  );
}

export default function ViewRenderer({ data }: { data: any }) {
  if (!data) return <p className="text-gray-500">Loading view…</p>;
  const view = data.view;

  if (view === "master") {
    if (data.headers && data.rows) return <Table headers={data.headers} rows={data.rows} />;
    return <p className="text-gray-500">No master grid available.</p>;
  }

  if (view === "teacher") {
    const teachers = data.teachers ?? [];
    return (
      <div className="space-y-4">
        {teachers.map((t: any) => (
          <div key={t.name} className="rounded border">
            <div className="border-b bg-gray-100 px-3 py-1.5 font-semibold dark:bg-gray-800">
              {t.name} · {t.sessions.length} session(s)
            </div>
            <table className="min-w-full text-sm">
              <tbody>
                {t.sessions.map((s: any, i: number) => (
                  <tr key={i} className="even:bg-gray-50 dark:even:bg-gray-900">
                    <td className="border-r p-2">{s.day_slot}</td>
                    <td className="border-r p-2 font-medium">{s.course}</td>
                    <td className="p-2 text-gray-600 dark:text-gray-400">{s.room}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    );
  }

  if (view === "student") {
    const courses = data.courses ?? [];
    return (
      <div className="space-y-4">
        {courses.map((c: any) => (
          <div key={c.course} className="rounded border">
            <div className="border-b bg-gray-100 px-3 py-1.5 font-semibold dark:bg-gray-800">
              {c.course} <span className="font-normal text-gray-500">— {c.teacher}</span>
            </div>
            <table className="min-w-full text-sm">
              <tbody>
                {c.sessions.map((s: any, i: number) => (
                  <tr key={i} className="even:bg-gray-50 dark:even:bg-gray-900">
                    <td className="border-r p-2">{s.meeting}</td>
                    <td className="border-r p-2">{s.day_slot}</td>
                    <td className="p-2 text-gray-600 dark:text-gray-400">{s.room}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    );
  }

  if (view === "staff") {
    const slots = data.slots ?? [];
    const max = Math.max(1, ...slots.map((s: any) => s.concurrent_classes));
    return (
      <div className="space-y-3">
        {data.lunch_break && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Lunch break (all free): <strong>{data.lunch_break}</strong>
          </p>
        )}
        <table className="min-w-full border text-sm">
          <thead>
            <tr className="bg-gray-100 dark:bg-gray-800">
              <th className="border p-2 text-left">Slot</th>
              <th className="border p-2 text-left">Concurrent</th>
              <th className="border p-2 text-left">Rooms in use</th>
              <th className="border p-2 text-left">Free rooms</th>
            </tr>
          </thead>
          <tbody>
            {slots.map((s: any, i: number) => (
              <tr key={i} className="even:bg-gray-50 dark:even:bg-gray-900">
                <td className="border p-2">{s.slot}</td>
                <td className="border p-2"><Bar value={s.concurrent_classes} max={max} /></td>
                <td className="border p-2 text-xs">{s.rooms_in_use?.join(", ")}</td>
                <td className="border p-2 text-center">{s.free_rooms}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (view === "canteen") {
    const slots = data.slots ?? [];
    const max = Math.max(1, ...slots.map((s: any) => s.concurrent_classes));
    const peaks = new Set(data.peak_slots ?? []);
    return (
      <div className="space-y-3">
        {data.lunch_window && (
          <p className="text-sm">Lunch window: <strong>{data.lunch_window}</strong></p>
        )}
        {data.note && <p className="text-xs text-gray-500">{data.note}</p>}
        <table className="min-w-full border text-sm">
          <tbody>
            {slots.map((s: any, i: number) => (
              <tr key={i} className={peaks.has(s.slot) ? "bg-amber-50 dark:bg-amber-950/30" : ""}>
                <td className="border p-2">{s.slot}</td>
                <td className="border p-2">
                  <Bar value={s.concurrent_classes} max={max} />
                  {peaks.has(s.slot) && <span className="ml-2 text-xs text-amber-700">peak</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return <pre className="max-h-96 overflow-auto rounded border bg-gray-50 p-3 text-xs dark:bg-gray-900">
    {JSON.stringify(data, null, 2)}
  </pre>;
}
