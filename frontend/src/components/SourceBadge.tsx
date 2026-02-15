"use client";

import { cn } from "@/lib/utils";

const BADGE_BG: Record<string, string> = {
  verified: "bg-green-500",
  calculated: "bg-blue-500",
  estimated: "bg-amber-500",
};

const BADGE_LABELS: Record<string, string> = {
  verified: "GOV",
  calculated: "CALC",
  estimated: "EST",
};

export default function SourceBadge({ confidence, tooltip }: { confidence: string; tooltip?: string }) {
  return (
    <span
      title={tooltip}
      className={cn(
        "inline-block text-[9px] font-bold px-1.5 py-px rounded text-white align-middle",
        tooltip ? "cursor-help" : "cursor-default",
        BADGE_BG[confidence] || "bg-gray-500"
      )}
    >
      {BADGE_LABELS[confidence] || confidence.toUpperCase()}
    </span>
  );
}
