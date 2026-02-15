"use client";

import React, { useState, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PoliticalRiskData {
  pid: string;
  neighborhood: string;
  risk_score: number | null;
  opposition_rate: number | null;
  parcel_signal_count: number;
  themes: Array<{ theme: string; count: number; example: string }>;
  narrative: string;
}

interface PoliticalRiskBadgeProps {
  pid: string;
  token?: string;
}

function getRiskColor(score: number): string {
  if (score <= 3) return "bg-green-600";
  if (score <= 6) return "bg-yellow-500";
  return "bg-red-600";
}

function getRiskLabel(score: number): string {
  if (score <= 3) return "Low Risk";
  if (score <= 6) return "Moderate Risk";
  return "High Risk";
}

export default function PoliticalRiskBadge({ pid, token }: PoliticalRiskBadgeProps) {
  const [data, setData] = useState<PoliticalRiskData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const fetchRisk = async () => {
      try {
        const headers: Record<string, string> = {};
        if (token) headers.Authorization = `Bearer ${token}`;

        const res = await fetch(`${API_BASE}/api/v1/political-risk/parcels/${pid}`, { headers });
        if (res.ok) {
          const json = await res.json();
          if (!json.error) setData(json);
        }
      } catch {
        // Silently fail — risk badge is supplementary
      } finally {
        setLoading(false);
      }
    };
    fetchRisk();
  }, [pid, token]);

  if (loading || !data || data.risk_score === null) return null;

  const score = data.risk_score;
  const colorClass = getRiskColor(score);
  const label = getRiskLabel(score);

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm"
      >
        <span className={`${colorClass} text-white px-2 py-0.5 rounded-full text-xs font-medium`}>
          {score.toFixed(1)}/10
        </span>
        <span className="text-gray-300">{label} — {data.neighborhood}</span>
        <span className="text-gray-500 text-xs">{expanded ? "[-]" : "[+]"}</span>
      </button>

      {expanded && (
        <div className="mt-2 p-3 bg-gray-800 rounded-lg border border-gray-700 text-sm">
          {data.narrative && (
            <p className="text-gray-300 mb-3">{data.narrative}</p>
          )}

          {data.themes && data.themes.length > 0 && (
            <div className="mb-3">
              <h5 className="text-gray-400 text-xs font-medium mb-1">Top Opposition Themes</h5>
              <div className="flex flex-wrap gap-1.5">
                {data.themes.map((t) => (
                  <span
                    key={t.theme}
                    className="px-2 py-0.5 bg-red-900/30 border border-red-800 rounded-full text-xs text-red-300"
                  >
                    {t.theme} ({t.count})
                  </span>
                ))}
              </div>
            </div>
          )}

          {data.opposition_rate !== null && (
            <div className="text-xs text-gray-500">
              Opposition rate: {data.opposition_rate.toFixed(0)}% of applications
              {data.parcel_signal_count > 0 && (
                <> | {data.parcel_signal_count} parcel-specific signals</>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
