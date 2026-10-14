"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ConstraintForm({ onCreated }: { onCreated?: () => void }) {
  const [form, setForm] = useState({ type: "hard", name: "", description: "", weight: 1 });
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/constraints", {
        method: "POST",
        body: JSON.stringify({ ...form, constraint_data: {} }),
      });
      setForm({ type: "hard", name: "", description: "", weight: 1 });
      onCreated?.();
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3 rounded border p-4">
      <div className="flex gap-3">
        <select
          value={form.type}
          onChange={(e) => setForm({ ...form, type: e.target.value })}
          className="rounded border p-2"
        >
          <option value="hard">hard</option>
          <option value="soft">soft</option>
        </select>
        <input
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="flex-1 rounded border p-2"
          required
        />
        <input
          type="number"
          step="0.1"
          value={form.weight}
          onChange={(e) => setForm({ ...form, weight: Number(e.target.value) })}
          className="w-24 rounded border p-2"
        />
      </div>
      <input
        placeholder="Description"
        value={form.description}
        onChange={(e) => setForm({ ...form, description: e.target.value })}
        className="w-full rounded border p-2"
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button className="rounded bg-blue-600 px-4 py-2 text-white">Add constraint</button>
    </form>
  );
}
