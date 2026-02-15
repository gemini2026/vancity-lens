"use client";

import React, { useState, useEffect, useCallback } from "react";
import { formatDateTimePT, formatRelativeTimePT } from "@/lib/format-date";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DataSource {
  name: string;
  origin: string;
  table: string;
  last_updated: string | null;
  record_count: number;
  staleness: "fresh" | "aging" | "stale" | "unknown" | "unavailable";
  days_old: number | null;
}

interface FreshnessSummary {
  total_sources: number;
  fresh: number;
  aging: number;
  stale: number;
  unavailable: number;
}

interface DataFreshnessDashboardProps {
  token?: string;
}

const STALENESS_CONFIG = {
  fresh: { label: "Fresh", color: "text-green-400", bg: "bg-green-900/30", border: "border-green-700" },
  aging: { label: "Aging", color: "text-yellow-400", bg: "bg-yellow-900/30", border: "border-yellow-700" },
  stale: { label: "Stale", color: "text-red-400", bg: "bg-red-900/30", border: "border-red-700" },
  unknown: { label: "Unknown", color: "text-gray-400", bg: "bg-gray-800", border: "border-gray-700" },
  unavailable: { label: "N/A", color: "text-gray-500", bg: "bg-gray-800", border: "border-gray-700" },
};

export default function DataFreshnessDashboard({ token }: DataFreshnessDashboardProps) {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [summary, setSummary] = useState<FreshnessSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${API_BASE}/api/v1/admin/data-freshness`, { headers });
      if (res.ok) {
        const data = await res.json();
        setSources(data.sources || []);
        setSummary(data.summary || null);
      } else if (res.status === 403) {
        setError("Admin access required");
      } else {
        setError("Failed to load freshness data");
      }
    } catch {
      setError("Failed to connect to API");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) return <div className="p-4 text-gray-400">Loading data freshness...</div>;
  if (error) return <div className="p-4 text-red-400">{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Data Freshness</h3>
        <button
          onClick={() => { setLoading(true); fetchData(); }}
          className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
        >
          Refresh
        </button>
      </div>

      {summary && (
        <div className="grid grid-cols-4 gap-2">
          <div className="p-2 bg-green-900/20 rounded border border-green-800 text-center">
            <div className="text-lg font-bold text-green-400">{summary.fresh}</div>
            <div className="text-xs text-green-500">Fresh</div>
          </div>
          <div className="p-2 bg-yellow-900/20 rounded border border-yellow-800 text-center">
            <div className="text-lg font-bold text-yellow-400">{summary.aging}</div>
            <div className="text-xs text-yellow-500">Aging</div>
          </div>
          <div className="p-2 bg-red-900/20 rounded border border-red-800 text-center">
            <div className="text-lg font-bold text-red-400">{summary.stale}</div>
            <div className="text-xs text-red-500">Stale</div>
          </div>
          <div className="p-2 bg-gray-800 rounded border border-gray-700 text-center">
            <div className="text-lg font-bold text-gray-400">{summary.unavailable}</div>
            <div className="text-xs text-gray-500">N/A</div>
          </div>
        </div>
      )}

      <div className="space-y-1">
        {sources.map((src) => {
          const cfg = STALENESS_CONFIG[src.staleness] || STALENESS_CONFIG.unknown;
          return (
            <div
              key={src.table}
              className={`flex items-center justify-between p-2 rounded border ${cfg.border} ${cfg.bg}`}
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white font-medium truncate">{src.name}</div>
                <div className="text-xs text-gray-400 truncate">{src.origin}</div>
              </div>
              <div className="text-right ml-3 flex-shrink-0">
                <div className={`text-xs font-medium ${cfg.color}`}>
                  {src.last_updated ? formatRelativeTimePT(src.last_updated) : "No data"}
                </div>
                <div className="text-xs text-gray-500">
                  {src.record_count.toLocaleString()} records
                </div>
              </div>
              <div className="ml-2 flex-shrink-0">
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${cfg.color} ${cfg.bg}`}>
                  {cfg.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
