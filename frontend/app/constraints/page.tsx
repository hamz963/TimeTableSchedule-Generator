"use client";
import ConstraintForm from "@/components/ConstraintForm";
import { useConstraints } from "@/hooks/useConstraints";

export default function ConstraintsPage() {
  const { constraints, loading, refresh, remove } = useConstraints();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Constraints</h1>
      <ConstraintForm onCreated={refresh} />
      {loading ? (
        <p>Loading…</p>
      ) : (
        <ul className="space-y-2">
          {constraints.map((c) => (
            <li key={c.id} className="flex items-center justify-between rounded border p-3">
              <div>
                <span
                  className={`mr-2 rounded px-2 py-0.5 text-xs ${
                    c.type === "hard" ? "bg-red-100" : "bg-yellow-100"
                  }`}
                >
                  {c.type}
                </span>
                <strong>{c.name}</strong>
                <p className="text-sm text-gray-500">{c.description} (weight {c.weight})</p>
              </div>
              <button onClick={() => remove(c.id)} className="rounded border px-3 py-1 text-sm">
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
