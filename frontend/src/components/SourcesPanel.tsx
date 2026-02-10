"use client";

import type { DataSource } from "@/lib/types";
import SourceBadge from "./SourceBadge";

export default function SourcesPanel({
  sources,
  disclaimer,
}: {
  sources: DataSource[];
  disclaimer?: string;
}) {
  if (!sources || sources.length === 0) return null;

  return (
    <div>
      <div style={{ fontSize: "10px", color: "#9ca3af", marginBottom: "8px", display: "flex", gap: "12px" }}>
        <span><span style={{ color: "#22c55e" }}>■</span> GOV = Government source</span>
        <span><span style={{ color: "#3b82f6" }}>■</span> CALC = Derived from verified data</span>
        <span><span style={{ color: "#f59e0b" }}>■</span> EST = Market estimate</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {sources.map((s, i) => (
          <div
            key={`${s.field}-${i}`}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "6px 0",
              borderBottom: "1px solid #1f2937",
            }}
          >
            <div style={{ flex: 1, fontSize: "11px" }}>
              <div style={{ color: "#d1d5db" }}>
                {s.url ? (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "#60a5fa", textDecoration: "none" }}
                  >
                    {s.label} ↗
                  </a>
                ) : (
                  s.label
                )}
              </div>
              <div style={{ color: "#6b7280", fontSize: "9px", marginTop: "1px" }}>
                {s.origin}
              </div>
            </div>
            <SourceBadge confidence={s.confidence} tooltip={s.note || undefined} />
          </div>
        ))}
      </div>

      {disclaimer && (
        <div style={{ fontSize: "9px", color: "#4b5563", marginTop: "8px", fontStyle: "italic" }}>
          {disclaimer}
        </div>
      )}
    </div>
  );
}
