"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function MLStatus() {
  const [stats, setStats] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setStats(await api("/ml/model-stats"));
    } catch {
      setStats(null);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const retrain = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api("/ml/retrain", { method: "POST" });
      setMsg(`Retrained v${r.version} on ${r.samples} samples (accuracy ${r.accuracy}).`);
      await refresh();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!stats) return <p className="text-sm text-gray-500">ML status unavailable.</p>;
  return (
    <div className="rounded border p-4">
      <h3 className="mb-2 font-semibold">Preference-learning model</h3>
      <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
        <div><span className="text-gray-500">Version</span><div className="font-bold">v{stats.model_version}</div></div>
        <div><span className="text-gray-500">Accuracy</span><div className="font-bold">{Math.round(stats.model_accuracy * 100)}%</div></div>
        <div><span className="text-gray-500">Training samples</span><div className="font-bold">{stats.training_samples}</div></div>
        <div><span className="text-gray-500">Feedback rows</span><div className="font-bold">{stats.feedback_count}</div></div>
      </div>
      <button onClick={retrain} disabled={busy} className="mt-3 rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
        {busy ? "Retraining…" : "Retrain now"}
      </button>
      {msg && <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">{msg}</p>}
    </div>
  );
}
