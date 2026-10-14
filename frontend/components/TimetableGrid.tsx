"use client";

const COLORS = [
  "bg-blue-100 border-blue-300",
  "bg-green-100 border-green-300",
  "bg-amber-100 border-amber-300",
  "bg-rose-100 border-rose-300",
  "bg-violet-100 border-violet-300",
  "bg-cyan-100 border-cyan-300",
];

export default function TimetableGrid({
  assignments,
  names,
}: {
  assignments: any[];
  names?: {
    courses?: Record<number, string>;
    teachers?: Record<number, string>;
    rooms?: Record<number, string>;
    slots?: Record<number, string>;
  };
}) {
  if (!assignments?.length)
    return <p className="text-gray-500">No assignments yet. Generate a timetable first.</p>;
  const slots = [...new Set(assignments.map((a) => a.slot_id))].sort((a, b) => a - b);
  const venues = [...new Set(assignments.map((a) => a.venue_id))].sort((a, b) => a - b);
  const cell = (s: number, v: number) =>
    assignments.find((a) => a.slot_id === s && a.venue_id === v);
  const courseName = (id: number) => names?.courses?.[id] ?? `Course ${id}`;
  const teacherName = (id: number) => names?.teachers?.[id] ?? `Faculty ${id}`;
  const roomName = (id: number) => names?.rooms?.[id] ?? `Room ${id}`;
  const slotName = (id: number) => names?.slots?.[id] ?? `Slot ${id}`;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border text-sm">
        <thead>
          <tr>
            <th className="border p-2">Slot \ Venue</th>
            {venues.map((v) => (
              <th key={v} className="border p-2">{roomName(v)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {slots.map((s) => (
            <tr key={s}>
              <td className="border p-2 font-medium">{slotName(s)}</td>
              {venues.map((v) => {
                const a = cell(s, v);
                const color = a ? COLORS[a.course_id % COLORS.length] : "";
                return (
                  <td key={v} className={`border p-2 ${color}`} title={a ? JSON.stringify(a) : ""}>
                    {a ? (
                      <div>
                        <div className="font-semibold">{courseName(a.course_id)}</div>
                        <div className="text-xs">{teacherName(a.faculty_id)}</div>
                      </div>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
