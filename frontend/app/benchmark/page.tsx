"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function BenchmarkPage() {
  const [size, setSize] = useState({ n_faculty: 50, n_rooms: 20, n_courses: 100, n_slots: 40 });
  const [seconds, setSeconds] = useState(1.0);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api("/quality/benchmark", {
          method: "POST",
          body: JSON.stringify({ ...size, optimize_seconds: seconds }),
        }),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const field = (key: keyof typeof size, label: string) => (
    <label className="flex flex-col text-sm">
      <span className="text-gray-500">{label}</span>
      <input
        type="number"
        min={1}
        value={size[key]}
        onChange={(e) => setSize({ ...size, [key]: Number(e.target.value) })}
        className="w-28 rounded border p-1.5"
      />
    </label>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Optimizer benchmark</h1>
      <p className="max-w-2xl text-gray-600 dark:text-gray-400">
        Proves the metaheuristic's value: the same synthetic instance is solved
        with a greedy constructor alone, then improved by simulated annealing.
        Lower cost is better; the quality score is 0–100.
      </p>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-white p-4 dark:bg-gray-900">
        {field("n_faculty", "Teachers")}
        {field("n_rooms", "Rooms")}
        {field("n_courses", "Courses")}
        {field("n_slots", "Slots")}
        <label className="flex flex-col text-sm">
          <span className="text-gray-500">Optimize (s)</span>
          <input
            type="number"
            min={0.05}
            step={0.1}
            value={seconds}
            onChange={(e) => setSeconds(Number(e.target.value))}
            className="w-24 rounded border p-1.5"
          />
        </label>
        <button
          onClick={run}
          disabled={busy}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Running…" : "Run benchmark"}
        </button>
      </div>

      {error && <p className="text-red-600">{error}</p>}

      {result && result.feasible === false && (
        <p className="text-red-600">{result.detail}</p>
      )}

      {result && result.feasible !== false && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-lg border bg-white p-4 dark:bg-gray-900">
            <h3 className="mb-2 font-semibold">Objective cost (lower is better)</h3>
            <Row label="Greedy baseline" value={result.greedy_cost} />
            <Row label="After optimization" value={result.optimized_cost} highlight />
            <p className="mt-2 text-sm">
              Improvement:{" "}
              <span className="font-bold text-green-600">{result.improvement_pct}%</span>
            </p>
          </div>
          <div className="rounded-lg border bg-white p-4 dark:bg-gray-900">
            <h3 className="mb-2 font-semibold">Quality score</h3>
            <Row label="Greedy baseline" value={result.greedy_quality} />
            <Row label="After optimization" value={result.optimized_quality} highlight />
            <p className="mt-2 text-sm text-gray-500">
              {result.iterations?.toLocaleString()} iterations ·{" "}
              {result.optimize_seconds}s budget
            </p>
            <p className="mt-1 text-sm">
              Hard violations after optimize:{" "}
              <span
                className={
                  result.hard_violations_after_optimize?.length ? "text-red-600" : "text-green-600"
                }
              >
                {result.hard_violations_after_optimize?.length ?? 0}
              </span>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between border-b py-1.5 text-sm last:border-0">
      <span className="text-gray-600 dark:text-gray-400">{label}</span>
      <span className={`font-mono ${highlight ? "font-bold text-blue-600" : ""}`}>{value}</span>
    </div>
  );
}
