"use client";

import { useState } from "react";
import { type HBUAnalysis, getHBUAnalysis, runHBUAnalysis } from "../lib/hbu-api";

interface Props {
  pid: string;
}

export default function HBUAnalysisPanel({ pid }: Props) {
  const [data, setData] = useState<HBUAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNarrative, setShowNarrative] = useState(false);
  const [showConstraints, setShowConstraints] = useState(false);

  async function handleAnalyze(forceRefresh = false) {
    setLoading(true);
    setError(null);
    try {
      // Try cached first
      if (!forceRefresh) {
        const cached = await getHBUAnalysis(pid);
        if (cached) {
          setData(cached);
          setLoading(false);
          return;
        }
      }
      // Run fresh analysis
      const result = await runHBUAnalysis(pid, forceRefresh);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  if (!data && !loading && !error) {
    return (
      <div className="mt-2">
        <button
          onClick={() => handleAnalyze()}
          className="w-full py-2 px-3 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition-colors"
        >
          Analyze Highest &amp; Best Use
        </button>
        <p className="text-[10px] text-gray-500 mt-1 text-center">
          AI-powered analysis using zoning bylaws &amp; community plans
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mt-2 space-y-2 animate-pulse">
        <div className="h-4 bg-white/[0.06] rounded w-3/4" />
        <div className="h-3 bg-white/[0.06] rounded w-1/2" />
        <div className="h-16 bg-white/[0.06] rounded" />
        <p className="text-[10px] text-gray-500 text-center">
          Analyzing zoning bylaws &amp; community plans...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-2 p-2 rounded bg-red-500/10 border border-red-500/20">
        <p className="text-xs text-red-400">{error}</p>
        <button
          onClick={() => handleAnalyze(true)}
          className="text-[10px] text-red-300 underline mt-1"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const hbu = data.highest_best_use;
  const verdictColor =
    hbu.feasibility_verdict === "pencils"
      ? "text-green-400"
      : hbu.feasibility_verdict === "marginal"
        ? "text-yellow-400"
        : "text-red-400";
  const verdictLabel =
    hbu.feasibility_verdict === "pencils"
      ? "Pencils"
      : hbu.feasibility_verdict === "marginal"
        ? "Marginal"
        : hbu.feasibility_verdict === "does_not_pencil"
          ? "Does Not Pencil"
          : "Unknown";

  const cachedAgo = data.cached_at
    ? Math.round((Date.now() - new Date(data.cached_at).getTime()) / 3600000)
    : null;

  return (
    <div className="mt-2 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-indigo-300">
          {hbu.recommended_use}
        </span>
        <button
          onClick={() => handleAnalyze(true)}
          className="text-[10px] text-gray-500 hover:text-gray-300"
          title="Re-analyze"
        >
          &#x27F3;
        </button>
      </div>

      <p className="text-[10px] text-gray-400">{hbu.zoning_basis}</p>

      {/* Key Metrics */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {hbu.max_height_storeys != null && (
          <div className="bg-white/[0.04] rounded p-1.5">
            <div className="text-sm font-bold text-white">{hbu.max_height_storeys} st</div>
            <div className="text-[9px] text-gray-500">Height</div>
          </div>
        )}
        {hbu.max_fsr != null && (
          <div className="bg-white/[0.04] rounded p-1.5">
            <div className="text-sm font-bold text-white">{hbu.max_fsr}</div>
            <div className="text-[9px] text-gray-500">FSR</div>
          </div>
        )}
        {hbu.estimated_units != null && (
          <div className="bg-white/[0.04] rounded p-1.5">
            <div className="text-sm font-bold text-white">~{hbu.estimated_units}</div>
            <div className="text-[9px] text-gray-500">Units</div>
          </div>
        )}
      </div>

      {/* Buildable + Feasibility */}
      {hbu.buildable_sqft && (
        <div className="flex justify-between text-xs">
          <span className="text-gray-400">Buildable</span>
          <span className="text-white font-medium">
            {Number(hbu.buildable_sqft).toLocaleString()} SF
          </span>
        </div>
      )}
      <div className="flex justify-between text-xs">
        <span className="text-gray-400">Feasibility</span>
        <span className={`font-semibold ${verdictColor}`}>{verdictLabel}</span>
      </div>

      {/* Constraints */}
      {hbu.key_constraints.length > 0 && (
        <div>
          <button
            onClick={() => setShowConstraints(!showConstraints)}
            className="bg-transparent border-none text-gray-400 cursor-pointer flex items-center gap-1 p-0 text-[11px]"
          >
            <span className="text-[9px]">{showConstraints ? "\u25BC" : "\u25B6"}</span>
            Constraints ({hbu.key_constraints.length})
          </button>
          {showConstraints && (
            <ul className="mt-1 space-y-0.5">
              {hbu.key_constraints.map((c, i) => (
                <li key={i} className="text-[10px] text-yellow-400/80 pl-3">
                  &bull; {c}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* AI Narrative */}
      {hbu.narrative && (
        <div>
          <button
            onClick={() => setShowNarrative(!showNarrative)}
            className="bg-transparent border-none text-gray-400 cursor-pointer flex items-center gap-1 p-0 text-[11px]"
          >
            <span className="text-[9px]">{showNarrative ? "\u25BC" : "\u25B6"}</span>
            AI Analysis
          </button>
          {showNarrative && (
            <div className="mt-1 text-[10px] text-gray-300 leading-relaxed whitespace-pre-line">
              {hbu.narrative}
            </div>
          )}
        </div>
      )}

      {/* Sources */}
      {data.sources.length > 0 && (
        <div className="text-[9px] text-gray-600">
          Sources: {data.sources.map((s) => s.title).join(", ")}
        </div>
      )}

      {/* Cache indicator */}
      {cachedAgo != null && cachedAgo > 0 && (
        <div className="text-[9px] text-gray-600 text-center">
          Cached {cachedAgo}h ago
        </div>
      )}

      {/* Confidence */}
      {data.confidence_score != null && (
        <div className="flex items-center gap-1 justify-center">
          <div className="h-1 flex-1 bg-white/[0.06] rounded overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded"
              style={{ width: `${data.confidence_score * 100}%` }}
            />
          </div>
          <span className="text-[9px] text-gray-500">
            {Math.round(data.confidence_score * 100)}% confidence
          </span>
        </div>
      )}
    </div>
  );
}
