"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function TeacherList({
  teachers,
  onRenamed,
}: {
  teachers: { id: number; name: string }[];
  onRenamed: () => void;
}) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async (id: number) => {
    const name = draft.trim();
    if (!name) {
      setError("Name must not be blank.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api(`/teachers/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
      setEditingId(null);
      onRenamed();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <h2 className="text-xl font-bold">Teachers</h2>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-1">
        {teachers.map((t) => (
          <li key={t.id} className="flex items-center gap-2 text-sm">
            {editingId === t.id ? (
              <>
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && save(t.id)}
                  autoFocus
                  className="rounded border px-2 py-1"
                />
                <button onClick={() => save(t.id)} disabled={busy} className="rounded bg-blue-600 px-2 py-1 text-white disabled:opacity-50">
                  Save
                </button>
                <button onClick={() => setEditingId(null)} className="rounded border px-2 py-1">
                  Cancel
                </button>
              </>
            ) : (
              <>
                <span className="font-medium">{t.name}</span>
                <button
                  onClick={() => { setEditingId(t.id); setDraft(t.name); setError(null); }}
                  title={`Rename ${t.name}`}
                  className="rounded border px-2 py-0.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  ✏️ Rename
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
