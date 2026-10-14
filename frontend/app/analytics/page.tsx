"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import Analytics from "@/components/Analytics";
import MLStatus from "@/components/MLStatus";

export default function AnalyticsPage() {
  const [id, setId] = useState("");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      setData(await api(`/analytics/schedule/${id}`));
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Analytics</h1>
      <div className="flex gap-2">
        <input
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="Schedule run ID"
          className="rounded border p-2"
        />
        <button onClick={load} className="rounded bg-blue-600 px-4 py-2 text-white">Load</button>
      </div>
      {error && <p className="text-red-600">{error}</p>}
      <Analytics data={data} />
      <h2 className="text-xl font-bold">Machine learning</h2>
      <MLStatus />
    </div>
  );
}
