"use client";

import type { DataSource } from "@/lib/types";
import SourceBadge from "./SourceBadge";

export default function SourcesPanel({ sources, disclaimer }: { sources: DataSource[]; disclaimer?: string }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div>
      <div className="text-[10px] text-gray-400 mb-2 flex gap-3">
        <span><span className="text-green-500">■</span> GOV = Government source</span>
        <span><span className="text-blue-500">■</span> CALC = Derived from verified data</span>
        <span><span className="text-amber-500">■</span> EST = Market estimate</span>
      </div>

      <div className="flex flex-col gap-1">
        {sources.map((s, i) => (
          <div key={`${s.field}-${i}`} className="flex justify-between items-center py-1.5 border-b border-gray-800">
            <div className="flex-1 text-[11px]">
              <div className="text-gray-300">
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 no-underline hover:underline">
                    {s.label} ↗
                  </a>
                ) : s.label}
              </div>
              <div className="text-gray-500 text-[9px] mt-px">{s.origin}</div>
            </div>
            <SourceBadge confidence={s.confidence} tooltip={s.note || undefined} />
          </div>
        ))}
      </div>

      {disclaimer && (
        <div className="text-[9px] text-gray-600 mt-2 italic">{disclaimer}</div>
      )}
    </div>
  );
}
