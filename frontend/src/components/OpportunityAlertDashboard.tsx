"use client";

import React, { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Opportunity {
  pid: string;
  civic_address: string;
  neighborhood: string;
  current_zoning: string;
  assessed_value: number;
  implied_value: number;
  buildable_sqft: number;
  discount_pct: number;
  repeat_signal: boolean;
  has_contamination: boolean;
  has_heritage: boolean;
  caveats: string[];
  comp_count: number;
  computed_at: string;
}

interface OpportunityAlertDashboardProps {
  token?: string;
  onSelectParcel?: (pid: string) => void;
}

export default function OpportunityAlertDashboard({
  token,
  onSelectParcel,
}: OpportunityAlertDashboardProps) {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOpportunities = useCallback(async () => {
    try {
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${API_BASE}/api/v1/opportunities?top=20`, { headers });
      if (res.ok) {
        const data = await res.json();
        setOpportunities(data.opportunities || []);
      } else {
        setError("Failed to load opportunities");
      }
    } catch {
      setError("Failed to connect to API");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchOpportunities();
  }, [fetchOpportunities]);

  if (loading) return <div className="p-4 text-gray-400">Loading opportunities...</div>;
  if (error) return <div className="p-4 text-red-400">{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">
          Opportunity Alerts
        </h3>
        <span className="text-sm text-gray-400">
          {opportunities.length} undervalued parcels
        </span>
      </div>

      {opportunities.length === 0 ? (
        <p className="text-gray-500 text-sm">No undervalued parcels found in current cycle.</p>
      ) : (
        <div className="space-y-2">
          {opportunities.map((opp, i) => (
            <button
              key={opp.pid}
              onClick={() => onSelectParcel?.(opp.pid)}
              className="w-full text-left p-3 bg-gray-800 rounded-lg border border-gray-700 hover:border-blue-600 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-white font-medium text-sm">
                      #{i + 1} {opp.civic_address || opp.pid}
                    </span>
                    {opp.repeat_signal && (
                      <span className="px-1.5 py-0.5 bg-yellow-900/30 border border-yellow-700 rounded text-xs text-yellow-400">
                        Repeat
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {opp.neighborhood} | {opp.current_zoning} | {opp.buildable_sqft?.toLocaleString()} SF buildable
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-green-400 font-bold text-sm">
                    {opp.discount_pct?.toFixed(1)}% below
                  </div>
                  <div className="text-xs text-gray-500">
                    ${opp.implied_value?.toLocaleString()} implied
                  </div>
                </div>
              </div>

              {opp.caveats && opp.caveats.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {opp.caveats.map((c, j) => (
                    <span
                      key={j}
                      className="px-1.5 py-0.5 bg-gray-700 rounded text-xs text-gray-400"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
