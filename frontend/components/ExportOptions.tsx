"use client";
import { useState } from "react";
import { API_URL, authHeaders } from "@/lib/api";

const FORMATS = [
  { value: "csv", label: "CSV (Excel Compatible)" },
  { value: "xlsx", label: "Excel Workbook (.XLSX)" },
  { value: "pdf", label: "PDF Document" },
  { value: "png", label: "PNG Image" },
  { value: "jpg", label: "JPG Image" },
  { value: "json", label: "JSON Data" },
  { value: "html", label: "HTML (Web)" },
];

const ALL_VIEWS = ["master", "teacher", "student", "staff", "canteen"];

export default function ExportOptions({
  scheduleId,
  onlyViews,
}: {
  scheduleId: number | string;
  onlyViews?: string[];
}) {
  const VIEWS = onlyViews ?? ALL_VIEWS;
  const [exporting, setExporting] = useState<string | null>(null);
  const [view, setView] = useState(onlyViews?.[0] ?? "master");
  const [bulkFormats, setBulkFormats] = useState<string[]>(["xlsx", "pdf"]);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const downloadOne = async (v: string, format: string) => {
    const res = await fetch(`${API_URL}/export/${scheduleId}?view=${v}&format=${format}`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `timetable-${scheduleId}-${v}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleExport = async (format: string) => {
    setExporting(format);
    setError(null);
    try {
      await downloadOne(view, format);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setExporting(null);
    }
  };

  const handleExportAll = async () => {
    setBulkBusy(true);
    setError(null);
    try {
      for (const v of VIEWS) {
        for (const f of bulkFormats) {
          await downloadOne(v, f);
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBulkBusy(false);
    }
  };

  const toggleBulk = (f: string) =>
    setBulkFormats(bulkFormats.includes(f) ? bulkFormats.filter((x) => x !== f) : [...bulkFormats, f]);

  return (
    <div className="rounded-lg border bg-white p-6 shadow-md dark:bg-gray-900">
      <h3 className="mb-4 text-xl font-bold">Export Timetable</h3>
      <label className="mb-3 block text-sm">
        Audience view{" "}
        <select value={view} onChange={(e) => setView(e.target.value)} className="rounded border p-1.5">
          {VIEWS.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {FORMATS.map((f) => (
          <button
            key={f.value}
            onClick={() => handleExport(f.value)}
            disabled={exporting !== null}
            className="rounded bg-blue-500 p-3 text-sm text-white transition hover:bg-blue-600 disabled:bg-gray-400"
          >
            {exporting === f.value ? "Exporting…" : f.label}
          </button>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <div className="mt-4 border-t pt-3 text-sm">
        <p className="mb-2 font-semibold">Export all views at once:</p>
        <div className="mb-2 flex flex-wrap gap-2">
          {FORMATS.map((f) => (
            <label key={f.value} className="flex items-center gap-1 rounded border px-2 py-1 text-xs">
              <input
                type="checkbox"
                checked={bulkFormats.includes(f.value)}
                onChange={() => toggleBulk(f.value)}
              />
              {f.value.toUpperCase()}
            </label>
          ))}
        </div>
        <button
          onClick={handleExportAll}
          disabled={bulkBusy || !bulkFormats.length}
          className="rounded bg-green-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {bulkBusy ? "Exporting…" : `Export all (${VIEWS.length} views × ${bulkFormats.length} formats)`}
        </button>
      </div>
      <div className="mt-4 text-sm text-gray-600 dark:text-gray-400">
        <p>✓ Every view exports in every format</p>
        <p>✓ Excel &amp; CSV open in Google Sheets</p>
        <p>✓ PNG/JPG are high-resolution for printing</p>
      </div>
    </div>
  );
}
