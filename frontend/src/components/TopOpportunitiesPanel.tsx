"use client";

import { useEffect, useState } from "react";
import { fetchTopOpportunities, type TopOpportunity } from "@/lib/api";

interface TopOpportunitiesPanelProps {
  onClose: () => void;
  onSelectParcel: (pid: string, lng: number, lat: number) => void;
}

const TIER_BADGE_COLORS: Record<number, string> = {
  1: "bg-red-600",
  2: "bg-orange-600",
  3: "bg-yellow-600",
};

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

export default function TopOpportunitiesPanel({
  onClose,
  onSelectParcel,
}: TopOpportunitiesPanelProps) {
  const [opportunities, setOpportunities] = useState<TopOpportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTopOpportunities(10)
      .then((data) => {
        if (!cancelled) {
          setOpportunities(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError("Failed to load opportunities");
          setLoading(false);
          console.error("TopOpportunities fetch error:", err);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="absolute top-4 right-16 md:right-48 z-20 w-[340px] max-h-[calc(100vh-120px)] bg-gray-900/95 backdrop-blur-sm border border-gray-700 rounded-xl shadow-2xl flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div>
          <h2 className="text-sm font-bold text-gray-100">Top Opportunities</h2>
          <p className="text-[10px] text-gray-500 mt-0.5">
            Ranked by composite score (uplift x teardown potential)
          </p>
        </div>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors cursor-pointer"
          aria-label="Close top opportunities panel"
        >
          x
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
            Loading top deals...
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center py-12 text-red-400 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && opportunities.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500 text-sm">
            <span className="text-2xl mb-2">--</span>
            No opportunities found
          </div>
        )}

        {!loading &&
          !error &&
          opportunities.map((opp, index) => (
            <button
              key={opp.pid}
              onClick={() => onSelectParcel(opp.pid, opp.lng, opp.lat)}
              className="w-full text-left px-4 py-3 border-b border-gray-800 hover:bg-gray-800/60 transition-colors cursor-pointer"
            >
              {/* Rank + Address */}
              <div className="flex items-start gap-2 mb-1.5">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-700 text-gray-300 text-[10px] font-bold flex items-center justify-center mt-0.5">
                  {index + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-gray-200 truncate">
                    {opp.civic_address || opp.pid}
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    {opp.current_zoning || "Unknown zone"} | {opp.station_name}
                  </div>
                </div>
              </div>

              {/* Metrics row */}
              <div className="flex items-center gap-1.5 flex-wrap ml-7">
                {/* Tier badge */}
                <span
                  className={`text-[9px] font-bold px-1.5 py-0.5 rounded text-white ${
                    TIER_BADGE_COLORS[opp.tier] || "bg-gray-600"
                  }`}
                >
                  T{opp.tier}
                </span>

                {/* Storey uplift */}
                <span className="text-[10px] text-green-400 font-semibold">
                  +{opp.storey_uplift}st
                </span>

                {/* ILR */}
                <span className="text-[10px] text-gray-400">
                  ILR:{" "}
                  {opp.ilr != null
                    ? `${(opp.ilr * 100).toFixed(0)}%`
                    : "N/A"}
                </span>

                {/* Signal count */}
                {opp.signal_count > 0 && (
                  <span className="text-[10px] text-yellow-400 font-medium">
                    {opp.signal_count} sig
                  </span>
                )}

                {/* Asking price */}
                {opp.asking_price != null && opp.asking_price > 0 && (
                  <span className="text-[10px] text-yellow-300 font-medium">
                    {fmt(opp.asking_price)}
                  </span>
                )}
              </div>

              {/* Composite score bar */}
              <div className="flex items-center gap-2 ml-7 mt-1.5">
                <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-green-500 to-emerald-400 rounded-full"
                    style={{
                      width: `${Math.min(
                        100,
                        (opp.composite_score /
                          (opportunities[0]?.composite_score || 1)) *
                          100
                      )}%`,
                    }}
                  />
                </div>
                <span className="text-[10px] font-bold text-emerald-400 flex-shrink-0 w-10 text-right">
                  {opp.composite_score?.toFixed(1) ?? "0.0"}
                </span>
              </div>
            </button>
          ))}
      </div>
    </div>
  );
}
