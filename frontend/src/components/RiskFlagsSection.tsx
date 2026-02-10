"use client";

import type { RiskFlag } from "@/lib/types";

const SEVERITY_ICON: Record<string, string> = {
  red: "🔴",
  yellow: "🟡",
  green: "🟢",
};

const SEVERITY_COLOR: Record<string, string> = {
  red: "#f87171",
  yellow: "#fbbf24",
  green: "#86efac",
};

export default function RiskFlagsSection({ flags }: { flags: RiskFlag[] }) {
  if (!flags || flags.length === 0) return null;

  const redCount = flags.filter((f) => f.severity === "red").length;
  const yellowCount = flags.filter((f) => f.severity === "yellow").length;
  const greenCount = flags.filter((f) => f.severity === "green").length;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "8px",
        }}
      >
        <div style={{ fontSize: "13px", fontWeight: 600, color: "#f3f4f6" }}>
          Risk Assessment
        </div>
        <div style={{ display: "flex", gap: "8px", fontSize: "11px" }}>
          {redCount > 0 && <span style={{ color: "#f87171" }}>{redCount} red</span>}
          {yellowCount > 0 && <span style={{ color: "#fbbf24" }}>{yellowCount} yellow</span>}
          {greenCount > 0 && <span style={{ color: "#86efac" }}>{greenCount} green</span>}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {flags.map((flag, i) => (
          <div
            key={`${flag.code}-${i}`}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "8px",
              padding: "8px",
              background: "rgba(255,255,255,0.02)",
              borderRadius: "6px",
              border: "1px solid rgba(255,255,255,0.04)",
            }}
          >
            <span style={{ fontSize: "12px", flexShrink: 0, marginTop: "1px" }}>
              {SEVERITY_ICON[flag.severity] || "⚪"}
            </span>
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: SEVERITY_COLOR[flag.severity] || "#d1d5db",
                }}
              >
                {flag.label}
              </div>
              <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>
                {flag.detail}
              </div>
              {flag.cost_impact && (
                <div style={{ fontSize: "10px", color: "#f59e0b", marginTop: "2px" }}>
                  Impact: {flag.cost_impact}
                </div>
              )}
            </div>
            {flag.verify_url && (
              <a
                href={flag.verify_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: "#60a5fa",
                  fontSize: "10px",
                  flexShrink: 0,
                  textDecoration: "none",
                }}
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
