"use client";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";

export function useFeedback(scheduleRunId: number) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api(`/feedback/schedule/${scheduleRunId}`));
    } finally {
      setLoading(false);
    }
  }, [scheduleRunId]);

  const submit = useCallback(
    async (payload: {
      teacher_name: string;
      satisfaction_score: number;
      preferred_time?: string;
      workload_satisfaction?: number;
      comments?: string;
    }) => {
      const created = await api("/feedback", {
        method: "POST",
        body: JSON.stringify({ schedule_run_id: scheduleRunId, ...payload }),
      });
      await refresh();
      return created;
    },
    [scheduleRunId, refresh]
  );

  return { items, loading, refresh, submit };
}
