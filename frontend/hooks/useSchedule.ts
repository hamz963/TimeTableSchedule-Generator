"use client";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";

export function useSchedule() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const generate = useCallback(async (payload: any) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api("/schedule/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(data);
      return data;
    } catch (e: any) {
      setError(e.message);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  return { loading, error, result, generate };
}
