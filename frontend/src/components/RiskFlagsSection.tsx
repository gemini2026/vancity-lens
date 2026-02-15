"use client";

import type { RiskFlag } from "@/lib/types";

const SEVERITY_ICON: Record<string, string> = {
  red: "\u{1F534}",
  yellow: "\u{1F7E1}",
  green: "\u{1F7E2}",
};

const SEVERITY_COLOR: Record<string, string> = {
  red: "text-red-400",
  yellow: "text-amber-400",
  green: "text-green-300",
};

export default function RiskFlagsSection({ flags }: { flags: RiskFlag[] }) {
  if (!flags || flags.length === 0) return null;

  const redCount = flags.filter((f) => f.severity === "red").length;
  const yellowCount = flags.filter((f) => f.severity === "yellow").length;
  const greenCount = flags.filter((f) => f.severity === "green").length;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[13px] font-semibold text-gray-100">
          Risk Assessment
        </div>
        <div className="flex gap-2 text-[11px]">
          {redCount > 0 && <span className="text-red-400">{redCount} red</span>}
          {yellowCount > 0 && <span className="text-amber-400">{yellowCount} yellow</span>}
          {greenCount > 0 && <span className="text-green-300">{greenCount} green</span>}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        {flags.map((flag, i) => (
          <div
            key={`${flag.code}-${i}`}
            className="flex items-start gap-2 p-2 bg-white/[0.02] rounded-md border border-white/[0.04]"
          >
            <span className="text-xs shrink-0 mt-px">
              {SEVERITY_ICON[flag.severity] || "\u26AA"}
            </span>
            <div className="flex-1">
              <div
                className={`text-xs font-semibold ${SEVERITY_COLOR[flag.severity] || "text-gray-300"}`}
              >
                {flag.label}
              </div>
              <div className="text-[11px] text-gray-400 mt-0.5">
                {flag.detail}
              </div>
              {flag.cost_impact && (
                <div className="text-[10px] text-amber-500 mt-0.5">
                  Impact: {flag.cost_impact}
                </div>
              )}
            </div>
            {flag.verify_url && (
              <a
                href={flag.verify_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 text-[10px] shrink-0 no-underline"
              >
                verify
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
