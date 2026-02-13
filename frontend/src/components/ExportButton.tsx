"use client";

import { useState } from "react";
import { getApiBase } from "@/lib/api-base";

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

  const handleExport = async () => {
    setLoading(true);
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
        throw new Error(`Export failed: ${res.statusText}`);
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
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "8px 14px",
        background: loading ? "#374151" : "#1e293b",
        border: "1px solid #374151",
        borderRadius: "6px",
        color: loading ? "#6b7280" : "#60a5fa",
        fontSize: "12px",
        fontWeight: "600",
        cursor: loading ? "not-allowed" : "pointer",
        fontFamily: "system-ui, sans-serif",
        transition: "all 0.2s",
      }}
      onMouseEnter={(e) => {
        if (!loading) {
          e.currentTarget.style.background = "#374151";
          e.currentTarget.style.borderColor = "#4b5563";
        }
      }}
      onMouseLeave={(e) => {
        if (!loading) {
          e.currentTarget.style.background = "#1e293b";
          e.currentTarget.style.borderColor = "#374151";
        }
      }}
    >
      {loading ? (
        <>
          <span
            style={{
              display: "inline-block",
              width: "12px",
              height: "12px",
              border: "2px solid #4b5563",
              borderTopColor: "#60a5fa",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }}
          />
          Exporting...
        </>
      ) : (
        <>
          <span style={{ fontSize: "14px" }}>&#8615;</span>
          {label || `Export ${exportType}`}
        </>
      )}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </button>
  );
}
