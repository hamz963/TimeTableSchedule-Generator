"use client";
import { useEffect, useRef, useState } from "react";
import { api, API_URL } from "@/lib/api";

type Msg = {
  id: number;
  sender: "user" | "bot";
  text: string;
  detected_views?: string[];
  status?: string;
  pending_edit?: string;
  new_run_id?: number;
};

export default function ChatBot({ scheduleRunId }: { scheduleRunId?: number }) {
  const [messages, setMessages] = useState<Msg[]>([
    {
      id: 1,
      sender: "bot",
      text: "Hi! I'm your scheduling assistant. What schedules do you need? (e.g., teacher schedules, student schedules, canteen staff)",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("keyword");
  const [ready, setReady] = useState(false);
  const [downloads, setDownloads] = useState<Record<string, Record<string, string>> | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(2);

  useEffect(() => {
    api("/chat/start", {
      method: "POST",
      body: JSON.stringify({ schedule_run_id: scheduleRunId ?? null }),
    })
      .then((data) => {
        setConversationId(data.conversation_id);
        if (data.mode) setMode(data.mode);
        if (data.reply) {
          setMessages([{ id: 1, sender: "bot", text: data.reply }]);
        }
      })
      .catch(() => {});
  }, [scheduleRunId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const push = (m: Omit<Msg, "id">) => setMessages((prev) => [...prev, { ...m, id: idRef.current++ }]);

  const handleSendMessage = async () => {
    if (!input.trim() || !conversationId || loading) return;
    const text = input;
    setInput("");
    await sendText(text);
  };

  const sendText = async (text: string) => {
    if (!conversationId || loading) return;
    push({ sender: "user", text });
    setLoading(true);
    try {
      const data = await api(`/chat/${conversationId}/message`, {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      push({
        sender: "bot",
        text: data.reply,
        detected_views: data.detected_views,
        status: data.status,
        pending_edit: data.pending_edit,
        new_run_id: data.new_run_id,
      });
      if (data.mode) setMode(data.mode);
      setReady(data.status === "ready_to_generate");
    } catch (e: any) {
      push({ sender: "bot", text: `Sorry, something went wrong: ${e.message}` });
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateSchedules = async () => {
    if (!conversationId) return;
    setLoading(true);
    try {
      const data = await api(`/chat/${conversationId}/generate`, { method: "POST", body: "{}" });
      setDownloads(data.views);
      push({ sender: "bot", text: `✅ Generated ${data.schedules_generated} files! Downloads are ready below.` });
    } catch (e: any) {
      push({ sender: "bot", text: `Couldn't generate: ${e.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[540px] flex-col rounded-lg border bg-white shadow-lg dark:bg-gray-900">
      <div className="rounded-t-lg bg-blue-600 p-4 text-white">
        <h2 className="text-xl font-bold">Schedule Assistant</h2>
        <p className="text-sm">
          AI-powered schedule generation{scheduleRunId ? ` · timetable #${scheduleRunId}` : " · attach a timetable to export"}
          {" "}· {mode === "ai" ? "AI mode" : "keyword mode"}
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-xs px-4 py-2 rounded-lg ${
                msg.sender === "user" ? "bg-blue-500 text-white" : "bg-gray-200 text-black dark:bg-gray-700 dark:text-white"
              }`}
            >
              <p className="text-sm">{msg.text}</p>
              {msg.detected_views && msg.detected_views.length > 0 && (
                <p className="mt-2 text-xs opacity-80">Views: {msg.detected_views.join(", ")}</p>
              )}
              {msg.status === "ready_to_generate" && msg.sender === "bot" && (
                <button
                  onClick={handleGenerateSchedules}
                  disabled={loading}
                  className="mt-2 rounded bg-white px-3 py-1 text-xs font-bold text-blue-600 hover:bg-gray-100"
                >
                  Generate Schedules
                </button>
              )}
              {msg.status === "confirm_edit" && msg.sender === "bot" && (
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => sendText("yes")}
                    disabled={loading}
                    className="rounded bg-green-600 px-3 py-1 text-xs font-bold text-white hover:bg-green-700"
                  >
                    ✓ Yes, apply
                  </button>
                  <button
                    onClick={() => sendText("no")}
                    disabled={loading}
                    className="rounded bg-white px-3 py-1 text-xs font-bold text-gray-600 hover:bg-gray-100"
                  >
                    Drop it
                  </button>
                </div>
              )}
              {msg.status === "edit_applied" && msg.new_run_id && (
                <a
                  href={`/schedule/${msg.new_run_id}`}
                  className="mt-2 block text-xs font-bold text-blue-200 hover:underline"
                >
                  Open updated timetable #{msg.new_run_id} →
                </a>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {downloads && (
        <div className="border-t bg-green-50 p-4 dark:bg-green-950">
          <h3 className="mb-2 font-bold">📥 Download Your Schedules</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(downloads).map(([view, urls]) => (
              <div key={view} className="rounded border bg-white p-2 dark:bg-gray-800">
                <p className="font-bold capitalize">{view}</p>
                <div className="space-y-1">
                  {Object.entries(urls).map(([format, url]) => (
                    <a key={format} href={`${API_URL}${url}`} download className="block text-xs text-blue-600 hover:underline">
                      ↓ {format.toUpperCase()}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 border-t p-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
          placeholder="Tell me what schedules you need..."
          className="flex-1 rounded-lg border px-3 py-2"
        />
        <button
          onClick={handleSendMessage}
          disabled={loading}
          className="rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:bg-gray-400"
        >
          {loading ? "…" : "Send"}
        </button>
      </div>
      {ready && !downloads && (
        <div className="border-t p-3 text-center">
          <button onClick={handleGenerateSchedules} disabled={loading} className="rounded bg-green-600 px-4 py-2 text-sm font-bold text-white">
            Generate Schedules
          </button>
        </div>
      )}
    </div>
  );
}
