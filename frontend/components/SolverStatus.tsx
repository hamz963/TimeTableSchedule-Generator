"use client";

export default function SolverStatus({ loading, status }: { loading: boolean; status?: string }) {
  if (loading)
    return (
      <div className="rounded border border-blue-300 bg-blue-50 p-3 text-sm">
        Solver running… (target &lt; 5 s)
      </div>
    );
  if (!status) return null;
  const ok = status === "optimal" || status === "feasible";
  return (
    <div
      className={`rounded border p-3 text-sm ${
        ok ? "border-green-300 bg-green-50" : "border-red-300 bg-red-50"
      }`}
    >
      Solver status: <strong>{status}</strong>
    </div>
  );
}
