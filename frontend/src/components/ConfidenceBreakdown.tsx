"use client";

import { useState } from "react";

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
        style={{
          background: "none",
          border: "none",
          color: "#fbbf24",
          fontSize: "11px",
          cursor: "pointer",
          padding: 0,
          fontWeight: 600,
        }}
      >
        {"★".repeat(confidenceStars)}{"☆".repeat(3 - confidenceStars)}{" "}
        <span style={{ color: "#6b7280", fontWeight: 400 }}>
          ({factors.final}%) {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div
          style={{
            marginTop: "6px",
            padding: "8px",
            background: "rgba(255,255,255,0.02)",
            borderRadius: "6px",
            border: "1px solid rgba(255,255,255,0.04)",
            fontSize: "11px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
            <span style={{ color: "#9ca3af" }}>Base confidence</span>
            <span style={{ color: "#d1d5db" }}>{factors.base}%</span>
          </div>
          {factors.factors.map((f, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                padding: "2px 0",
                borderBottom: "1px solid rgba(255,255,255,0.04)",
              }}
            >
              <span style={{ color: "#9ca3af" }} title={f.reason}>
                {f.name}
              </span>
              <span style={{ color: f.impact > 0 ? "#86efac" : "#f87171", fontWeight: 600 }}>
                {f.impact > 0 ? "+" : ""}{f.impact}%
              </span>
            </div>
          ))}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginTop: "4px",
              paddingTop: "4px",
              borderTop: "1px solid #374151",
              fontWeight: 600,
            }}
          >
            <span style={{ color: "#d1d5db" }}>Final confidence</span>
            <span style={{ color: "#fbbf24" }}>{factors.final}%</span>
          </div>
        </div>
      )}
    </div>
  );
}
