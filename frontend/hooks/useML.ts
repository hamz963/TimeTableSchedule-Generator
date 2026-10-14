"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export function useML() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStats(await api("/ml/model-stats"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const retrain = useCallback(async () => {
    const r = await api("/ml/retrain", { method: "POST" });
    await refresh();
    return r;
  }, [refresh]);

  return { stats, loading, refresh, retrain };
}
