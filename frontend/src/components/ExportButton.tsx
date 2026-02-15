"use client";

import { useState } from "react";
import { getApiBase } from "@/lib/api-base";
import { cn } from "@/lib/utils";

const API_BASE = getApiBase();

interface ExportButtonProps {
  exportType: "signals" | "parcels" | "neighborhoods";
  filters?: Record<string, string>;
  token?: string | null;
  label?: string;
}

const EXPORT_ENDPOINTS: Record<string, string> = {
  signals: "/api/v1/export/signals",
  parcels: "/api/v1/export/parcels",
  neighborhoods: "/api/v1/export/neighborhoods",
};

export default function ExportButton({
  exportType,
  filters,
  token,
  label,
}: ExportButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filters) {
        Object.entries(filters).forEach(([key, value]) => {
          if (value) params.set(key, value);
        });
      }
      const queryString = params.toString();
      const url = `${API_BASE}${EXPORT_ENDPOINTS[exportType]}${queryString ? `?${queryString}` : ""}`;

      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(url, { headers });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        let detail = res.statusText || `HTTP ${res.status}`;
        if (text) {
          try {
            const parsed = JSON.parse(text);
            detail = parsed?.detail || parsed?.message || detail;
          } catch {
            detail = text;
          }
        }
        throw new Error(`Export failed (${res.status}): ${detail}`);
      }

      const blob = await res.blob();
      const contentDisposition = res.headers.get("Content-Disposition");
      let filename = `${exportType}-export.csv`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
        if (match) filename = match[1];
      }

      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      console.error("Export failed:", err);
      const msg = err instanceof Error ? err.message : "Export failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="inline-flex flex-col items-end">
      <button
        onClick={handleExport}
        disabled={loading}
        className={cn(
          "inline-flex items-center gap-1.5 px-3.5 py-2 border rounded-md text-xs font-semibold transition-all",
          loading
            ? "bg-gray-700 border-gray-700 text-gray-500 cursor-not-allowed"
            : "bg-slate-800 border-gray-700 text-blue-400 cursor-pointer hover:bg-gray-700 hover:border-gray-600"
        )}
      >
        {loading ? (
          <>
            <span className="inline-block w-3 h-3 border-2 border-gray-600 border-t-blue-400 rounded-full animate-spin" />
            Exporting...
          </>
        ) : (
          <>
            <span className="text-sm">&#8615;</span>
            {label || `Export ${exportType}`}
          </>
        )}
      </button>

      {error && (
        <div className="mt-1.5 max-w-[320px] text-red-400 text-[11px] text-right">
          {error}
        </div>
      )}
    </div>
  );
}
