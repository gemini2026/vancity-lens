"use client";

const BADGE_COLORS: Record<string, string> = {
  verified: "#22c55e",
  calculated: "#3b82f6",
  estimated: "#f59e0b",
};

const BADGE_LABELS: Record<string, string> = {
  verified: "GOV",
  calculated: "CALC",
  estimated: "EST",
};

export default function SourceBadge({
  confidence,
  tooltip,
}: {
  confidence: string;
  tooltip?: string;
}) {
  return (
    <span
      title={tooltip}
      style={{
        display: "inline-block",
        fontSize: "9px",
        fontWeight: 700,
        padding: "1px 5px",
        borderRadius: "3px",
        background: BADGE_COLORS[confidence] || "#6b7280",
        color: "#fff",
        verticalAlign: "middle",
        cursor: tooltip ? "help" : "default",
      }}
    >
      {BADGE_LABELS[confidence] || confidence.toUpperCase()}
    </span>
  );
}
