"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getNeighborhoodScorecards,
  getNeighborhoodScorecard,
  compareNeighborhoods,
} from "@/lib/intel-api";
import type {
  NeighborhoodSummary,
  NeighborhoodScorecard,
  NeighborhoodComparison,
  MetricCategory,
  CategoryScore,
  TrendDirection,
} from "@/lib/intel-types";
import ExportButton from "./ExportButton";

// ── Constants ────────────────────────────────────────────

const CATEGORY_ICONS: Record<MetricCategory, string> = {
  safety: "🛡️",
  schools: "🎓",
  transit: "🚌",
  parks: "🌳",
  development: "🏗️",
  air_quality: "💨",
  affordability: "💰",
  walkability: "🚶",
};

const CATEGORY_LABELS: Record<MetricCategory, string> = {
  safety: "Safety",
  schools: "Schools",
  transit: "Transit",
  parks: "Parks & Green",
  development: "Development",
  air_quality: "Air Quality",
  affordability: "Affordability",
  walkability: "Walkability",
};

const TREND_ICONS: Record<TrendDirection, string> = {
  improving: "↗",
  stable: "→",
  declining: "↘",
};

const TREND_COLORS: Record<TrendDirection, string> = {
  improving: "#10b981",
  stable: "#6b7280",
  declining: "#ef4444",
};

const CATEGORY_SOURCES: Record<MetricCategory, { source: string; metric: string; url?: string }> = {
  safety: {
    source: "Vancouver Police Dept.",
    metric: "Crime incidents per capita (lower = safer)",
    url: "https://geodash.vpd.ca/opendata/",
  },
  schools: {
    source: "BC Ministry of Education",
    metric: "Fraser Institute school ratings composite",
    url: "https://www.compareschoolrankings.org/",
  },
  transit: {
    source: "TransLink Open API",
    metric: "Transit stops within neighbourhood boundary",
    url: "https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources/gtfs",
  },
  parks: {
    source: "City of Vancouver Open Data",
    metric: "Total park hectares per neighbourhood",
    url: "https://opendata.vancouver.ca/explore/dataset/parks/",
  },
  development: {
    source: "VanCity Lens Intelligence",
    metric: "Active rezoning + permit signals (365-day lookback)",
  },
  air_quality: {
    source: "Metro Vancouver / BC AQHI",
    metric: "Avg. Air Quality Health Index reading (inverted)",
    url: "https://www.env.gov.bc.ca/epd/bcairquality/data/aqhi.html",
  },
  affordability: {
    source: "BC Assessment / CoV Property Tax",
    metric: "Avg. assessed property value per sq ft (lower = better)",
    url: "https://opendata.vancouver.ca/explore/dataset/property-tax-report/",
  },
  walkability: {
    source: "Walk Score",
    metric: "Walk Score rating (0-100 normalized to 0-10)",
    url: "https://www.walkscore.com/CA-BC/Vancouver",
  },
};

const CATEGORY_WEIGHTS: Record<MetricCategory, number> = {
  safety: 15,
  schools: 15,
  transit: 15,
  parks: 10,
  development: 15,
  air_quality: 5,
  affordability: 15,
  walkability: 10,
};

function getScoreColor(score: number): string {
  if (score >= 8) return "#10b981";
  if (score >= 6) return "#3b82f6";
  if (score >= 4) return "#f59e0b";
  return "#ef4444";
}

function getScoreLabel(score: number): string {
  if (score >= 9) return "Excellent";
  if (score >= 7) return "Very Good";
  if (score >= 5) return "Good";
  if (score >= 3) return "Fair";
  return "Needs Improvement";
}

// ── Score Ring Component ─────────────────────────────────

function ScoreRing({
  score,
  size = 80,
  strokeWidth = 6,
}: {
  score: number;
  size?: number;
  strokeWidth?: number;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 10) * circumference;
  const color = getScoreColor(score);

  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span
          style={{
            fontSize: size * 0.3,
            fontWeight: 700,
            color: "#f3f4f6",
            lineHeight: 1,
          }}
        >
          {score.toFixed(1)}
        </span>
        <span style={{ fontSize: size * 0.12, color: "#9ca3af" }}>/ 10</span>
      </div>
    </div>
  );
}

// ── Category Bar Component ───────────────────────────────

function CategoryBar({ item, showSource = false }: { item: CategoryScore; showSource?: boolean }) {
  const color = getScoreColor(item.score);
  const pct = (item.score / 10) * 100;
  const src = CATEGORY_SOURCES[item.category];
  const weight = CATEGORY_WEIGHTS[item.category];

  return (
    <div style={{ padding: "6px 0" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
        }}
        title={`${src.metric}\nSource: ${src.source}\nWeight: ${weight}%`}
      >
        <div style={{ width: "28px", textAlign: "center", fontSize: "16px" }}>
          {CATEGORY_ICONS[item.category]}
        </div>
        <div style={{ width: "100px", fontSize: "13px", color: "#d1d5db" }}>
          {CATEGORY_LABELS[item.category]}
        </div>
        <div
          style={{
            flex: 1,
            height: "8px",
            background: "rgba(255,255,255,0.06)",
            borderRadius: "4px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${pct}%`,
              height: "100%",
              background: color,
              borderRadius: "4px",
              transition: "width 0.6s ease",
            }}
          />
        </div>
        <div
          style={{
            width: "40px",
            textAlign: "right",
            fontSize: "14px",
            fontWeight: 600,
            color,
          }}
        >
          {item.score.toFixed(1)}
        </div>
        <div
          style={{
            width: "36px",
            textAlign: "center",
            fontSize: "10px",
            color: "#4b5563",
            fontWeight: 500,
          }}
        >
          {weight}%
        </div>
        <div
          style={{
            width: "20px",
            textAlign: "center",
            fontSize: "14px",
            color: TREND_COLORS[item.trend],
          }}
          title={`${item.trend} (${item.trend_delta >= 0 ? "+" : ""}${item.trend_delta.toFixed(1)})`}
        >
          {TREND_ICONS[item.trend]}
        </div>
      </div>
      {showSource && (
        <div
          style={{
            marginLeft: "40px",
            fontSize: "10px",
            color: "#4b5563",
            marginTop: "2px",
          }}
        >
          {src.url ? (
            <a
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "#475569", textDecoration: "none" }}
            >
              {src.source} — {src.metric}
            </a>
          ) : (
            <span>{src.source} — {src.metric}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ── Neighborhood Card (List View) ────────────────────────

function NeighborhoodCard({
  summary,
  onSelect,
  isSelected,
  onCompareToggle,
  isComparing,
}: {
  summary: NeighborhoodSummary;
  onSelect: () => void;
  isSelected: boolean;
  onCompareToggle: () => void;
  isComparing: boolean;
}) {
  const color = getScoreColor(summary.overall_score);

  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "16px",
        padding: "14px 16px",
        background: isSelected
          ? "rgba(59, 130, 246, 0.12)"
          : "rgba(255,255,255,0.03)",
        border: isSelected
          ? "1px solid rgba(59, 130, 246, 0.4)"
          : "1px solid rgba(255,255,255,0.06)",
        borderRadius: "10px",
        cursor: "pointer",
        transition: "all 0.15s",
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          e.currentTarget.style.background = "rgba(255,255,255,0.06)";
          e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)";
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          e.currentTarget.style.background = "rgba(255,255,255,0.03)";
          e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
        }
      }}
    >
      {/* Rank */}
      <div
        style={{
          width: "32px",
          height: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background:
            summary.rank <= 3 ? "rgba(59, 130, 246, 0.15)" : "rgba(255,255,255,0.05)",
          borderRadius: "8px",
          fontSize: "14px",
          fontWeight: 700,
          color: summary.rank <= 3 ? "#60a5fa" : "#9ca3af",
        }}
      >
        #{summary.rank}
      </div>

      {/* Name + categories */}
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "14px", fontWeight: 600, color: "#f3f4f6" }}>
          {summary.name}
        </div>
        <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "2px" }}>
          Best: {CATEGORY_LABELS[summary.top_category as MetricCategory] || summary.top_category}{" "}
          · Weakest:{" "}
          {CATEGORY_LABELS[summary.bottom_category as MetricCategory] || summary.bottom_category}
        </div>
      </div>

      {/* Score */}
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: "20px", fontWeight: 700, color, lineHeight: 1 }}>
          {summary.overall_score.toFixed(1)}
        </div>
        <div style={{ fontSize: "10px", color: "#6b7280" }}>
          {getScoreLabel(summary.overall_score)}
        </div>
      </div>

      {/* Compare checkbox */}
      <div
        onClick={(e) => {
          e.stopPropagation();
          onCompareToggle();
        }}
        style={{
          width: "24px",
          height: "24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: isComparing
            ? "2px solid #3b82f6"
            : "2px solid rgba(255,255,255,0.15)",
          borderRadius: "6px",
          background: isComparing ? "rgba(59, 130, 246, 0.2)" : "transparent",
          cursor: "pointer",
          fontSize: "14px",
          transition: "all 0.15s",
        }}
        title="Add to comparison"
      >
        {isComparing ? "✓" : ""}
      </div>
    </div>
  );
}

// ── Detail Panel ─────────────────────────────────────────

function ScorecardDetail({
  scorecard,
  onBack,
}: {
  scorecard: NeighborhoodScorecard;
  onBack: () => void;
}) {
  return (
    <div style={{ padding: "24px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
        <button
          onClick={onBack}
          style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "8px",
            color: "#9ca3af",
            padding: "6px 12px",
            cursor: "pointer",
            fontSize: "13px",
          }}
        >
          ← Back
        </button>
        <div style={{ flex: 1 }}>
          <h2
            style={{
              fontSize: "20px",
              fontWeight: 700,
              color: "#f3f4f6",
              margin: 0,
            }}
          >
            {scorecard.neighborhood.name}
          </h2>
          <div style={{ fontSize: "12px", color: "#6b7280" }}>
            Rank #{scorecard.rank} of 22 Vancouver neighborhoods
          </div>
        </div>
        <ScoreRing score={scorecard.overall_score} size={72} />
      </div>

      {/* Score label */}
      <div
        style={{
          textAlign: "center",
          padding: "10px",
          background: `${getScoreColor(scorecard.overall_score)}15`,
          borderRadius: "8px",
          marginBottom: "24px",
          fontSize: "13px",
          fontWeight: 600,
          color: getScoreColor(scorecard.overall_score),
        }}
      >
        {getScoreLabel(scorecard.overall_score)} Neighborhood
      </div>

      {/* Category Breakdown */}
      <div style={{ marginBottom: "24px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "12px",
          }}
        >
          <h3
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "#9ca3af",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              margin: 0,
            }}
          >
            Category Breakdown
          </h3>
          <span style={{ fontSize: "10px", color: "#4b5563" }}>
            Weight
          </span>
        </div>
        {scorecard.category_scores.map((cs) => (
          <CategoryBar key={cs.category} item={cs} showSource />
        ))}
      </div>

      {/* Context Stats */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "12px",
          marginBottom: "24px",
        }}
      >
        <div
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "10px",
            padding: "16px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "24px", fontWeight: 700, color: "#f59e0b" }}>
            {scorecard.active_rezonings}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            Active Rezonings
          </div>
        </div>
        <div
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "10px",
            padding: "16px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "24px", fontWeight: 700, color: "#3b82f6" }}>
            {scorecard.recent_permits}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            Recent Permits
          </div>
        </div>
      </div>

      {/* Methodology */}
      <div
        style={{
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: "10px",
          padding: "16px",
        }}
      >
        <h3
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: "#6b7280",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            marginBottom: "10px",
          }}
        >
          Scoring Methodology
        </h3>
        <div style={{ fontSize: "11px", color: "#6b7280", lineHeight: 1.6 }}>
          <p style={{ margin: "0 0 8px" }}>
            Scores are computed using a <strong style={{ color: "#9ca3af" }}>weighted composite</strong> of
            8 quality-of-life categories, each normalized to a 0-10 scale using min-max normalization
            across all 22 Vancouver neighbourhoods. Categories where lower values indicate better
            outcomes (safety, affordability) are inverted before scoring.
          </p>
          <p style={{ margin: "0 0 8px" }}>
            <strong style={{ color: "#9ca3af" }}>Overall score</strong> = weighted average of all category
            scores, with weights reflecting investment-relevance: Safety, Schools, Transit, Development,
            and Affordability each at 15%; Parks and Walkability at 10%; Air Quality at 5%.
          </p>
          <p style={{ margin: "0 0 10px" }}>
            <strong style={{ color: "#9ca3af" }}>Trends</strong> compare current period vs. prior period.
            Changes above +0.3 are marked improving; below -0.3 declining; otherwise stable.
          </p>
          <div
            style={{
              fontSize: "10px",
              color: "#4b5563",
              borderTop: "1px solid rgba(255,255,255,0.06)",
              paddingTop: "8px",
              display: "flex",
              flexWrap: "wrap",
              gap: "6px 16px",
            }}
          >
            <span style={{ fontWeight: 600, color: "#6b7280" }}>Data sources:</span>
            <a href="https://geodash.vpd.ca/opendata/" target="_blank" rel="noopener noreferrer" style={{ color: "#475569", textDecoration: "none" }}>VPD Crime Data</a>
            <a href="https://opendata.vancouver.ca/" target="_blank" rel="noopener noreferrer" style={{ color: "#475569", textDecoration: "none" }}>CoV Open Data</a>
            <a href="https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources/gtfs" target="_blank" rel="noopener noreferrer" style={{ color: "#475569", textDecoration: "none" }}>TransLink GTFS</a>
            <a href="https://www.walkscore.com/CA-BC/Vancouver" target="_blank" rel="noopener noreferrer" style={{ color: "#475569", textDecoration: "none" }}>Walk Score</a>
            <a href="https://www.env.gov.bc.ca/epd/bcairquality/data/aqhi.html" target="_blank" rel="noopener noreferrer" style={{ color: "#475569", textDecoration: "none" }}>BC AQHI</a>
            <a href="https://www.compareschoolrankings.org/" target="_blank" rel="noopener noreferrer" style={{ color: "#475569", textDecoration: "none" }}>Fraser Institute</a>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Compare Panel ────────────────────────────────────────

function CompareView({
  comparison,
  onBack,
}: {
  comparison: NeighborhoodComparison;
  onBack: () => void;
}) {
  const categories = comparison.categories;
  const hoods = comparison.neighborhoods;

  return (
    <div style={{ padding: "24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "24px" }}>
        <button
          onClick={onBack}
          style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "8px",
            color: "#9ca3af",
            padding: "6px 12px",
            cursor: "pointer",
            fontSize: "13px",
          }}
        >
          ← Back
        </button>
        <h2
          style={{
            fontSize: "18px",
            fontWeight: 700,
            color: "#f3f4f6",
            margin: 0,
          }}
        >
          Neighborhood Comparison
        </h2>
      </div>

      {/* Score headers */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `120px repeat(${hoods.length}, 1fr)`,
          gap: "8px",
          marginBottom: "20px",
          padding: "12px",
          background: "rgba(255,255,255,0.03)",
          borderRadius: "10px",
        }}
      >
        <div style={{ fontSize: "11px", color: "#6b7280", fontWeight: 600 }}>
          OVERALL
        </div>
        {hoods.map((h) => (
          <div key={h.neighborhood.slug} style={{ textAlign: "center" }}>
            <div
              style={{
                fontSize: "13px",
                fontWeight: 600,
                color: "#d1d5db",
                marginBottom: "4px",
              }}
            >
              {h.neighborhood.name}
            </div>
            <div
              style={{
                fontSize: "22px",
                fontWeight: 700,
                color: getScoreColor(h.overall_score),
              }}
            >
              {h.overall_score.toFixed(1)}
            </div>
            <div style={{ fontSize: "10px", color: "#6b7280" }}>
              Rank #{h.rank}
            </div>
          </div>
        ))}
      </div>

      {/* Category rows */}
      {categories.map((cat) => (
        <div
          key={cat}
          style={{
            display: "grid",
            gridTemplateColumns: `120px repeat(${hoods.length}, 1fr)`,
            gap: "8px",
            padding: "10px 12px",
            borderBottom: "1px solid rgba(255,255,255,0.04)",
            alignItems: "center",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              color: "#9ca3af",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span>{CATEGORY_ICONS[cat]}</span>
            <span>{CATEGORY_LABELS[cat]}</span>
          </div>
          {hoods.map((h) => {
            const cs = h.category_scores.find((c) => c.category === cat);
            if (!cs) return <div key={h.neighborhood.slug} />;
            const color = getScoreColor(cs.score);
            const bestScore = Math.max(
              ...hoods
                .map((hh) => hh.category_scores.find((c) => c.category === cat)?.score || 0)
            );
            const isBest = cs.score === bestScore;

            return (
              <div
                key={h.neighborhood.slug}
                style={{
                  textAlign: "center",
                  padding: "4px",
                  borderRadius: "6px",
                  background: isBest ? `${color}15` : "transparent",
                }}
              >
                <span
                  style={{
                    fontSize: "15px",
                    fontWeight: isBest ? 700 : 500,
                    color,
                  }}
                >
                  {cs.score.toFixed(1)}
                </span>
                <span
                  style={{
                    marginLeft: "4px",
                    fontSize: "12px",
                    color: TREND_COLORS[cs.trend],
                  }}
                >
                  {TREND_ICONS[cs.trend]}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────

type ViewState =
  | { type: "list" }
  | { type: "detail"; slug: string }
  | { type: "compare"; slugs: string[] };

export default function NeighborhoodPage() {
  const [view, setView] = useState<ViewState>({ type: "list" });
  const [summaries, setSummaries] = useState<NeighborhoodSummary[]>([]);
  const [scorecard, setScorecard] = useState<NeighborhoodScorecard | null>(null);
  const [comparison, setComparison] = useState<NeighborhoodComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [compareSet, setCompareSet] = useState<Set<string>>(new Set());
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);

  // Load neighborhood list
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getNeighborhoodScorecards()
      .then((data) => {
        if (!cancelled) {
          setSummaries(data);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError("Failed to load neighborhoods");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load detail when view changes to detail
  useEffect(() => {
    if (view.type !== "detail") return;
    let cancelled = false;
    setLoading(true);
    getNeighborhoodScorecard(view.slug)
      .then((data) => {
        if (!cancelled) {
          setScorecard(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Failed to load scorecard");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [view]);

  // Load comparison
  useEffect(() => {
    if (view.type !== "compare") return;
    let cancelled = false;
    setLoading(true);
    compareNeighborhoods(view.slugs)
      .then((data) => {
        if (!cancelled) {
          setComparison(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Failed to load comparison");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [view]);

  const handleSelect = useCallback((slug: string) => {
    setSelectedSlug(slug);
    setView({ type: "detail", slug });
  }, []);

  const handleCompareToggle = useCallback((slug: string) => {
    setCompareSet((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) {
        next.delete(slug);
      } else if (next.size < 4) {
        next.add(slug);
      }
      return next;
    });
  }, []);

  const handleCompare = useCallback(() => {
    const slugs = Array.from(compareSet);
    if (slugs.length >= 2) {
      setView({ type: "compare", slugs });
    }
  }, [compareSet]);

  const handleBack = useCallback(() => {
    setView({ type: "list" });
    setScorecard(null);
    setComparison(null);
  }, []);

  // ── Render ───────────────────────────────────────

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "#0f172a",
        color: "#f3f4f6",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Page Header */}
      <div
        style={{
          padding: "20px 24px 12px",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: "#f3f4f6",
                margin: 0,
              }}
            >
              Neighborhood Scorecards
            </h1>
            <p style={{ fontSize: "12px", color: "#6b7280", margin: "4px 0 0" }}>
              Quality-of-life ratings across 22 Vancouver neighborhoods
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {view.type === "list" && compareSet.size >= 2 && (
              <button
                onClick={handleCompare}
                style={{
                  background: "#3b82f6",
                  border: "none",
                  borderRadius: "8px",
                  color: "#fff",
                  padding: "8px 16px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "#2563eb";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "#3b82f6";
                }}
              >
                Compare ({compareSet.size})
              </button>
            )}
            <ExportButton exportType="neighborhoods" label="Export CSV" />
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {loading && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "200px",
              color: "#6b7280",
              fontSize: "14px",
            }}
          >
            Loading neighborhoods...
          </div>
        )}

        {error && (
          <div
            style={{
              margin: "24px",
              padding: "16px",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.2)",
              borderRadius: "10px",
              color: "#fca5a5",
              fontSize: "13px",
            }}
          >
            {error}
          </div>
        )}

        {!loading && !error && view.type === "list" && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              padding: "16px 24px",
            }}
          >
            {summaries.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "48px 24px",
                  color: "#6b7280",
                }}
              >
                <div style={{ fontSize: "32px", marginBottom: "12px" }}>📊</div>
                <div style={{ fontSize: "14px", fontWeight: 500 }}>
                  No neighborhood data yet
                </div>
                <div style={{ fontSize: "12px", marginTop: "4px" }}>
                  Run the data scrapers to populate quality-of-life scores
                </div>
              </div>
            ) : (
              summaries.map((s) => (
                <NeighborhoodCard
                  key={s.slug}
                  summary={s}
                  onSelect={() => handleSelect(s.slug)}
                  isSelected={selectedSlug === s.slug}
                  onCompareToggle={() => handleCompareToggle(s.slug)}
                  isComparing={compareSet.has(s.slug)}
                />
              ))
            )}
          </div>
        )}

        {!loading && !error && view.type === "detail" && scorecard && (
          <ScorecardDetail scorecard={scorecard} onBack={handleBack} />
        )}

        {!loading && !error && view.type === "compare" && comparison && (
          <CompareView comparison={comparison} onBack={handleBack} />
        )}
      </div>
    </div>
  );
}
