"use client";
import { useState } from "react";
import ChatBot from "@/components/ChatBot";

export default function ChatPage() {
  const [runId, setRunId] = useState("");
  const [activeRun, setActiveRun] = useState<number | undefined>(undefined);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Chat with the Scheduler</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Tell me which audience views and export formats you need. Attach a timetable
          ID to enable one-click generation and downloads.
        </p>
      </div>
      <div className="flex gap-2">
        <input
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          placeholder="Timetable ID (optional)"
          className="rounded border p-2 text-sm"
        />
        <button
          onClick={() => setActiveRun(runId ? Number(runId) : undefined)}
          className="rounded bg-blue-600 px-3 py-2 text-sm text-white"
        >
          Attach
        </button>
      </div>
      <ChatBot key={activeRun ?? "none"} scheduleRunId={activeRun} />
    </div>
  );
}
