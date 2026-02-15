"use client";

import { useEffect, useState, useRef } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { getApiBase } from "@/lib/api-base";
import { cn } from "@/lib/utils";

const API_BASE = getApiBase();

interface CaseStudy {
  id: number;
  pid: string;
  title: string;
  narrative: string;
  highlight_metrics: Record<string, any>;
  civic_address: string | null;
  current_zoning: string | null;
  lot_area_sqm: number | null;
  assessed_value: number | null;
  lng: number | null;
  lat: number | null;
}

interface CaseStudyCarouselProps {
  onSelectParcel: (pid: string, lng: number, lat: number) => void;
  onDismiss: () => void;
}

function fmtValue(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

export default function CaseStudyCarousel({
  onSelectParcel,
  onDismiss,
}: CaseStudyCarouselProps) {
  const [studies, setStudies] = useState<CaseStudy[]>([]);
  const [loading, setLoading] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/case-studies`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setStudies(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const scroll = (dir: "left" | "right") => {
    if (!scrollRef.current) return;
    const amount = 300;
    scrollRef.current.scrollBy({
      left: dir === "left" ? -amount : amount,
      behavior: "smooth",
    });
  };

  if (loading || studies.length === 0) return null;

  return (
    <div className="absolute bottom-4 left-4 right-4 md:left-16 md:right-16 z-20">
      <div className="bg-gray-900/95 backdrop-blur-md rounded-xl border border-white/10 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]">
          <div>
            <span className="text-[13px] font-semibold text-gray-100">
              Case Studies
            </span>
            <span className="text-[10px] text-gray-500 ml-2">
              {studies.length} curated examples
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => scroll("left")}
              className="w-6 h-6 rounded flex items-center justify-center bg-white/5 text-gray-400 hover:bg-white/10 cursor-pointer border-none transition-colors"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => scroll("right")}
              className="w-6 h-6 rounded flex items-center justify-center bg-white/5 text-gray-400 hover:bg-white/10 cursor-pointer border-none transition-colors"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onDismiss}
              className="w-6 h-6 rounded flex items-center justify-center bg-white/5 text-gray-400 hover:bg-white/10 cursor-pointer border-none transition-colors ml-1"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Cards */}
        <div
          ref={scrollRef}
          className="flex gap-3 overflow-x-auto p-3 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-gray-700"
          style={{ scrollbarWidth: "thin" }}
        >
          {studies.map((cs) => {
            const m = cs.highlight_metrics;
            const alreadyExceeds = m.zoning_already_exceeds;
            return (
              <button
                key={cs.id}
                onClick={() => {
                  if (cs.lng != null && cs.lat != null) {
                    onSelectParcel(cs.pid, cs.lng, cs.lat);
                  }
                }}
                className={cn(
                  "flex-shrink-0 w-[260px] rounded-lg border text-left p-3 cursor-pointer transition-all",
                  "bg-slate-800/80 border-white/[0.08] hover:border-white/20 hover:bg-slate-800",
                )}
                style={{ fontFamily: "inherit" }}
              >
                {/* Title */}
                <div className="text-[12px] font-semibold text-gray-100 leading-tight mb-1.5 line-clamp-2">
                  {cs.title}
                </div>

                {/* Narrative snippet */}
                <div className="text-[10px] text-gray-400 leading-relaxed mb-2 line-clamp-2">
                  {cs.narrative}
                </div>

                {/* Metrics */}
                <div className="flex gap-2 flex-wrap">
                  {alreadyExceeds ? (
                    <span className="text-[9px] bg-blue-500/15 text-blue-400 px-1.5 py-0.5 rounded font-semibold">
                      ALREADY EXCEEDS
                    </span>
                  ) : (
                    <>
                      {m.storey_uplift != null && m.storey_uplift > 0 && (
                        <span className="text-[9px] bg-green-500/15 text-green-400 px-1.5 py-0.5 rounded font-semibold">
                          +{m.storey_uplift} storeys
                        </span>
                      )}
                      {m.entitled_fsr && (
                        <span className="text-[9px] bg-green-500/15 text-green-300 px-1.5 py-0.5 rounded font-semibold">
                          FSR {m.entitled_fsr}
                        </span>
                      )}
                    </>
                  )}
                  {cs.assessed_value && (
                    <span className="text-[9px] bg-gray-700/50 text-gray-400 px-1.5 py-0.5 rounded">
                      {fmtValue(cs.assessed_value)}
                    </span>
                  )}
                  {m.lot_area_sqm && (
                    <span className="text-[9px] bg-gray-700/50 text-gray-400 px-1.5 py-0.5 rounded">
                      {m.lot_area_sqm.toLocaleString()} sqm
                    </span>
                  )}
                </div>

                {/* Address */}
                <div className="text-[9px] text-gray-600 mt-2 truncate">
                  {cs.civic_address || cs.pid}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
