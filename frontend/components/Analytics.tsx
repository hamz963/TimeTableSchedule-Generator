"use client";

export default function Analytics({ data }: { data: any }) {
  if (!data) return <p className="text-gray-500">No analytics yet.</p>;
  const rooms = Object.values<any>(data.room_utilization ?? {});
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Preference satisfaction" value={`${data.preference_satisfaction_pct}%`} />
        <Stat label="Slots filled" value={`${data.slots_filled_pct}%`} />
        <Stat label="Solver time" value={`${data.solver_time_ms} ms`} />
        <Stat label="Status" value={data.solver_status} />
      </div>
      <div>
        <h3 className="mb-2 font-semibold">Room utilization</h3>
        {rooms.map((r: any) => (
          <div key={r.name} className="mb-1 flex items-center gap-2 text-sm">
            <span className="w-24">{r.name || "Room"}</span>
            <div className="h-3 flex-1 rounded bg-gray-200">
              <div
                className="h-3 rounded bg-blue-500"
                style={{ width: `${Math.min(100, r.utilization_pct)}%` }}
              />
            </div>
            <span>{r.utilization_pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  );
}
