"use client";
import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";

type Event = {
  type: string;
  run_id?: number;
  new_run_id?: number;
  sessions?: number;
  quality_score?: number;
  op?: string;
  seq?: number;
};

const LABELS: Record<string, (e: Event) => string> = {
  "schedule.created": (e) => `Timetable #${e.run_id} generated (${e.sessions} sessions)`,
  "schedule.rescheduled": (e) => `Timetable #${e.run_id} rescheduled (${e.sessions} sessions)`,
  "schedule.edited": (e) => `Timetable #${e.run_id} edited (${e.op}) → #${e.new_run_id}`,
};

export default function LiveEvents({
  onEvent,
}: {
  onEvent?: (event: Event) => void;
}) {
  const [connected, setConnected] = useState(false);
  const [toasts, setToasts] = useState<(Event & { id: number })[]>([]);
  const counter = useRef(0);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    const es = new EventSource(`${API_URL}/events/stream`);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    const handle = (raw: MessageEvent, type: string) => {
      let payload: Event;
      try {
        payload = JSON.parse(raw.data);
      } catch {
        return;
      }
      payload.type = type || payload.type;
      const id = ++counter.current;
      setToasts((prev) => [...prev, { ...payload, id }].slice(-4));
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
      onEventRef.current?.(payload);
    };

    // Named events (event: schedule.created) + default message events.
    const types = ["schedule.created", "schedule.edited", "schedule.rescheduled"];
    const listeners = types.map((t) => {
      const fn = (e: MessageEvent) => handle(e, t);
      es.addEventListener(t, fn as EventListener);
      return [t, fn] as const;
    });

    return () => {
      for (const [t, fn] of listeners) es.removeEventListener(t, fn as EventListener);
      es.close();
    };
  }, []);

  return (
    <>
      <span
        className="flex items-center gap-1.5 text-xs text-gray-500"
        title={connected ? "Live updates connected" : "Live updates disconnected"}
      >
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            connected ? "bg-green-500" : "bg-gray-400"
          }`}
        />
        {connected ? "live" : "offline"}
      </span>
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto rounded-lg border bg-white p-3 text-sm shadow-lg dark:bg-gray-900"
          >
            <div className="font-semibold capitalize">{t.type.replace(".", " · ")}</div>
            <div className="text-gray-600 dark:text-gray-400">
              {(LABELS[t.type] ?? (() => t.type))(t)}
            </div>
            {t.quality_score != null && (
              <div className="mt-1 text-xs text-gray-500">Quality score: {t.quality_score}</div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
