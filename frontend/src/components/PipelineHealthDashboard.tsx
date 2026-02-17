"use client";

import React, { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api-base";
import { formatRelativeTimePT } from "@/lib/format-date";
import { cn } from "@/lib/utils";

const API_BASE = getApiBase();

interface ScraperInfo {
  name: string;
  enabled: boolean;
  cron: string;
  has_function: boolean;
  last_run: string | null;
  status: "success" | "partial" | "failed" | "never_run";
  documents_found: number;
  documents_new: number;
  next_run: string | null;
}

interface HealthData {
  scrapers: ScraperInfo[];
  totals: {
    documents: number;
    signals: number;
  };
}

interface PipelineHealthDashboardProps {
  adminKey?: string;
}

const STATUS_CONFIG: Record<
  string,
  { label: string; dot: string; text: string }
> = {
  success: { label: "OK", dot: "bg-green-500", text: "text-green-400" },
  partial: { label: "Partial", dot: "bg-yellow-500", text: "text-yellow-400" },
  failed: { label: "Failed", dot: "bg-red-500", text: "text-red-400" },
  never_run: { label: "Never run", dot: "bg-gray-500", text: "text-gray-400" },
  running: { label: "Running", dot: "bg-yellow-400 animate-pulse", text: "text-yellow-300" },
};

export default function PipelineHealthDashboard({
  adminKey,
}: PipelineHealthDashboardProps) {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [runningScrapers, setRunningScrapers] = useState<Set<string>>(
    new Set()
  );

  const headers = useCallback((): Record<string, string> => {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (adminKey) h["X-Admin-Key"] = adminKey;
    return h;
  }, [adminKey]);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/scraper-health`, {
        headers: headers(),
      });
      if (res.ok) {
        setData(await res.json());
        setError(null);
      } else if (res.status === 401 || res.status === 403) {
        setError("Admin access required");
      } else {
        setError("Failed to load pipeline health");
      }
    } catch {
      setError("Failed to connect to API");
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  const handleRunScraper = async (name: string) => {
    setActionError(null);
    setRunningScrapers((prev) => new Set(prev).add(name));
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/admin/scraper/${name}/run`,
        { method: "POST", headers: headers() }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setActionError(`Failed to run ${name}: ${body.detail || res.statusText}`);
      }
      // Refresh health data after run
      await fetchHealth();
    } catch {
      setActionError(`Failed to trigger ${name}`);
    } finally {
      setRunningScrapers((prev) => {
        const next = new Set(prev);
        next.delete(name);
        return next;
      });
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-gray-400">Loading pipeline health...</div>
    );
  }
  if (error) {
    return <div className="p-4 text-red-400">{error}</div>;
  }
  if (!data) return null;

  return (
    <div className="space-y-4">
      {actionError && (
        <div className="flex items-center justify-between px-3 py-2 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-sm">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="ml-2 text-red-300 hover:text-white">&times;</button>
        </div>
      )}
      {/* Header with totals */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Pipeline Health</h3>
        <button
          onClick={() => {
            setLoading(true);
            fetchHealth();
          }}
          className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
        >
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="p-3 bg-blue-900/20 rounded border border-blue-800 text-center">
          <div className="text-lg font-bold text-blue-400">
            {data.totals.documents.toLocaleString()}
          </div>
          <div className="text-xs text-blue-500">Documents</div>
        </div>
        <div className="p-3 bg-purple-900/20 rounded border border-purple-800 text-center">
          <div className="text-lg font-bold text-purple-400">
            {data.totals.signals.toLocaleString()}
          </div>
          <div className="text-xs text-purple-500">Signals</div>
        </div>
      </div>

      {/* Scraper table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-700">
              <th className="pb-2 pr-3">Scraper</th>
              <th className="pb-2 pr-3">Status</th>
              <th className="pb-2 pr-3">Last Run</th>
              <th className="pb-2 pr-3">Docs</th>
              <th className="pb-2 pr-3">Schedule</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {data.scrapers.map((scraper) => {
              const isRunning = runningScrapers.has(scraper.name);
              const effectiveStatus = isRunning ? "running" : scraper.status;
              const cfg =
                STATUS_CONFIG[effectiveStatus] || STATUS_CONFIG.never_run;

              return (
                <tr
                  key={scraper.name}
                  className="border-b border-gray-800 hover:bg-gray-800/50"
                >
                  {/* Name */}
                  <td className="py-2.5 pr-3">
                    <div className="font-medium text-white">
                      {scraper.name}
                    </div>
                    {!scraper.enabled && (
                      <span className="text-[10px] text-gray-500">
                        disabled
                      </span>
                    )}
                  </td>

                  {/* Status dot + label */}
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          "inline-block w-2 h-2 rounded-full",
                          cfg.dot
                        )}
                      />
                      <span className={cfg.text}>{cfg.label}</span>
                    </div>
                  </td>

                  {/* Last run (relative) */}
                  <td className="py-2.5 pr-3 text-gray-300">
                    {scraper.last_run
                      ? formatRelativeTimePT(scraper.last_run)
                      : "Never"}
                  </td>

                  {/* Docs found / new */}
                  <td className="py-2.5 pr-3 text-gray-300">
                    {scraper.documents_found}/{scraper.documents_new}
                  </td>

                  {/* Cron schedule */}
                  <td className="py-2.5 pr-3">
                    <code className="text-[10px] text-gray-400 bg-gray-800 px-1 py-0.5 rounded">
                      {scraper.cron}
                    </code>
                  </td>

                  {/* Run Now button */}
                  <td className="py-2.5 text-right">
                    <button
                      onClick={() => handleRunScraper(scraper.name)}
                      disabled={isRunning || !scraper.has_function}
                      className={cn(
                        "px-2 py-1 rounded text-[10px] font-semibold transition-colors",
                        isRunning || !scraper.has_function
                          ? "bg-gray-700 text-gray-500 cursor-not-allowed"
                          : "bg-blue-600 hover:bg-blue-500 text-white cursor-pointer"
                      )}
                    >
                      {isRunning ? "Running..." : "Run Now"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
