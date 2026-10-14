"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function HealthPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api("/health").then(setData).catch(() => setData({ status: "unreachable" }));
  }, []);

  if (!data) return <p>Checking system status…</p>;
  const components = data.components ?? {};
  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-2xl font-bold">System health</h1>
      <table className="min-w-full border text-sm">
        <tbody>
          {Object.entries(components).map(([name, status]) => (
            <tr key={name}>
              <td className="border p-2 font-medium capitalize">{name}</td>
              <td className="border p-2">{String(status)}</td>
            </tr>
          ))}
          <tr>
            <td className="border p-2 font-medium">App version</td>
            <td className="border p-2">{data.app_version ?? "—"}</td>
          </tr>
          <tr>
            <td className="border p-2 font-medium">Uptime</td>
            <td className="border p-2">{data.uptime_seconds ?? "—"} s</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
