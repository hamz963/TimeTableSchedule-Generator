"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export function useConstraints() {
  const [constraints, setConstraints] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setConstraints(await api("/constraints"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const remove = async (id: number) => {
    await api(`/constraints/${id}`, { method: "DELETE" });
    await refresh();
  };

  return { constraints, loading, refresh, remove };
}
