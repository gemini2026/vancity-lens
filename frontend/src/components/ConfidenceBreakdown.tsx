"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

interface ConfidenceFactors {
  base: number;
  factors: { name: string; impact: number; reason: string }[];
  final: number;
}

export default function ConfidenceBreakdown({
  confidenceStars,
  factors,
}: {
  confidenceStars: number;
  factors?: ConfidenceFactors | null;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!factors) return null;

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="bg-transparent border-none text-amber-400 text-[11px] cursor-pointer p-0 font-semibold"
      >
        {"★".repeat(confidenceStars)}{"☆".repeat(3 - confidenceStars)}{" "}
        <span className="text-gray-500 font-normal">
          ({factors.final}%) {expanded ? "\u25B2" : "\u25BC"}
        </span>
      </button>

      {expanded && (
        <div className="mt-1.5 p-2 bg-white/[0.02] rounded-md border border-white/[0.04] text-[11px]">
          <div className="flex justify-between mb-1">
            <span className="text-gray-400">Base confidence</span>
            <span className="text-gray-300">{factors.base}%</span>
          </div>
          {factors.factors.map((f, i) => (
            <div
              key={i}
              className="flex justify-between py-0.5 border-b border-white/[0.04]"
            >
              <span className="text-gray-400" title={f.reason}>
                {f.name}
              </span>
              <span
                className={cn(
                  "font-semibold",
                  f.impact > 0 ? "text-green-300" : "text-red-400"
                )}
              >
                {f.impact > 0 ? "+" : ""}{f.impact}%
              </span>
            </div>
          ))}
          <div className="flex justify-between mt-1 pt-1 border-t border-gray-700 font-semibold">
            <span className="text-gray-300">Final confidence</span>
            <span className="text-amber-400">{factors.final}%</span>
          </div>
        </div>
      )}
    </div>
  );
}
