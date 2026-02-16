"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Shield,
  GraduationCap,
  Bus,
  Trees,
  Building2,
  Wind,
  DollarSign,
  Footprints,
  TrendingUp,
  ArrowRight,
  TrendingDown,
  ArrowLeft,
  Check,
  BarChart3,
} from "lucide-react";
import {
  getNeighborhoodScorecards,
  getNeighborhoodScorecard,
  compareNeighborhoods,
  getNeighborhoodInvestmentMetrics,
} from "@/lib/intel-api";
import type { NeighborhoodInvestmentMetrics } from "@/lib/intel-api";
import type {
  NeighborhoodSummary,
  NeighborhoodScorecard,
  NeighborhoodComparison,
  MetricCategory,
  CategoryScore,
  TrendDirection,
} from "@/lib/intel-types";
import { cn } from "@/lib/utils";
import ExportButton from "./ExportButton";

// ── Constants ────────────────────────────────────────────

const CATEGORY_ICONS: Record<MetricCategory, React.ReactNode> = {
  safety: <Shield className="size-4" />,
  schools: <GraduationCap className="size-4" />,
  transit: <Bus className="size-4" />,
  parks: <Trees className="size-4" />,
  development: <Building2 className="size-4" />,
  air_quality: <Wind className="size-4" />,
  affordability: <DollarSign className="size-4" />,
  walkability: <Footprints className="size-4" />,
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

const TREND_ICONS: Record<TrendDirection, React.ReactNode> = {
  improving: <TrendingUp className="size-3.5" />,
  stable: <ArrowRight className="size-3.5" />,
  declining: <TrendingDown className="size-3.5" />,
};

const TREND_COLORS: Record<TrendDirection, string> = {
  improving: "text-emerald-500",
  stable: "text-gray-500",
  declining: "text-red-500",
};

const TREND_RAW_COLORS: Record<TrendDirection, string> = {
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

interface ScoreRingProps {
  score: number;
  size?: number;
  strokeWidth?: number;
}

function ScoreRing({ score, size = 80, strokeWidth = 6 }: ScoreRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 10) * circumference;
  const color = getScoreColor(score);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
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
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-bold text-gray-100 leading-none"
          style={{ fontSize: size * 0.3 }}
        >
          {score.toFixed(1)}
        </span>
        <span className="text-gray-400" style={{ fontSize: size * 0.12 }}>
          / 10
        </span>
      </div>
    </div>
  );
}

// ── Category Bar Component ───────────────────────────────

interface CategoryBarProps {
  item: CategoryScore;
  showSource?: boolean;
}

function CategoryBar({ item, showSource = false }: CategoryBarProps) {
  const color = getScoreColor(item.score);
  const pct = (item.score / 10) * 100;
  const src = CATEGORY_SOURCES[item.category];
  const weight = CATEGORY_WEIGHTS[item.category];

  return (
    <div className="py-1.5">
      <div
        className="flex items-center gap-3"
        title={`${src.metric}\nSource: ${src.source}\nWeight: ${weight}%`}
      >
        <div className="w-7 flex items-center justify-center text-gray-400">
          {CATEGORY_ICONS[item.category]}
        </div>
        <div className="w-[100px] text-[13px] text-gray-300">
          {CATEGORY_LABELS[item.category]}
        </div>
        <div className="flex-1 h-2 bg-white/[0.06] rounded overflow-hidden">
          <div
            className="h-full rounded transition-[width] duration-500 ease-out"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
        <div
          className="w-10 text-right text-sm font-semibold"
          style={{ color }}
        >
          {item.score.toFixed(1)}
        </div>
        <div className="w-9 text-center text-[10px] text-gray-600 font-medium">
          {weight}%
        </div>
        <div
          className={cn("w-5 flex items-center justify-center", TREND_COLORS[item.trend])}
          title={`${item.trend} (${item.trend_delta >= 0 ? "+" : ""}${item.trend_delta.toFixed(1)})`}
        >
          {TREND_ICONS[item.trend]}
        </div>
      </div>
      {showSource && (
        <div className="ml-10 text-[10px] text-gray-600 mt-0.5">
          {src.url ? (
            <a
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-600 no-underline hover:text-slate-400 transition-colors"
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

interface NeighborhoodCardProps {
  summary: NeighborhoodSummary;
  onSelect: () => void;
  isSelected: boolean;
  onCompareToggle: () => void;
  isComparing: boolean;
}

function NeighborhoodCard({
  summary,
  onSelect,
  isSelected,
  onCompareToggle,
  isComparing,
}: NeighborhoodCardProps) {
  const color = getScoreColor(summary.overall_score);

  return (
    <div
      onClick={onSelect}
      className={cn(
        "flex items-center gap-3 sm:gap-4 px-3 sm:px-4 py-3.5 rounded-[10px] cursor-pointer transition-all duration-150",
        isSelected
          ? "bg-blue-500/[0.12] border border-blue-500/40"
          : "bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] hover:border-white/[0.12]",
      )}
    >
      {/* Rank */}
      <div
        className={cn(
          "w-8 h-8 flex items-center justify-center rounded-lg text-sm font-bold shrink-0",
          summary.rank <= 3
            ? "bg-blue-500/15 text-blue-400"
            : "bg-white/5 text-gray-400",
        )}
      >
        #{summary.rank}
      </div>

      {/* Name + categories */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-gray-100 truncate">
          {summary.name}
        </div>
        <div className="text-[11px] text-gray-500 mt-0.5 truncate">
          Best: {CATEGORY_LABELS[summary.top_category as MetricCategory] || summary.top_category}{" "}
          · Weakest:{" "}
          {CATEGORY_LABELS[summary.bottom_category as MetricCategory] || summary.bottom_category}
        </div>
      </div>

      {/* Score */}
      <div className="text-right shrink-0">
        <div className="text-xl font-bold leading-none" style={{ color }}>
          {summary.overall_score.toFixed(1)}
        </div>
        <div className="text-xs font-medium" style={{ color: getScoreColor(summary.overall_score) }}>
          {getScoreLabel(summary.overall_score)}
        </div>
      </div>

      {/* Compare checkbox */}
      <div
        onClick={(e) => {
          e.stopPropagation();
          onCompareToggle();
        }}
        className={cn(
          "w-6 h-6 flex items-center justify-center rounded-md cursor-pointer transition-all duration-150 shrink-0",
          isComparing
            ? "border-2 border-blue-500 bg-blue-500/20"
            : "border-2 border-white/15 hover:border-white/30",
        )}
        title="Add to comparison"
      >
        {isComparing && <Check className="size-3.5 text-blue-400" />}
      </div>
    </div>
  );
}

// ── Detail Panel ─────────────────────────────────────────

interface ScorecardDetailProps {
  scorecard: NeighborhoodScorecard;
  onBack: () => void;
}

function getMomentumColor(momentum: number | null): string {
  if (momentum === null) return "text-gray-500";
  if (momentum >= 1.5) return "text-emerald-500";
  if (momentum >= 0.5) return "text-amber-500";
  return "text-red-500";
}

function getMomentumBg(momentum: number | null): string {
  if (momentum === null) return "bg-gray-500/10 border-gray-500/20";
  if (momentum >= 1.5) return "bg-emerald-500/10 border-emerald-500/20";
  if (momentum >= 0.5) return "bg-amber-500/10 border-amber-500/20";
  return "bg-red-500/10 border-red-500/20";
}

function getMomentumLabel(momentum: number | null): string {
  if (momentum === null) return "No data";
  if (momentum >= 1.5) return "Strong growth";
  if (momentum >= 0.5) return "Stable";
  return "Cooling";
}

function ScorecardDetail({ scorecard, onBack }: ScorecardDetailProps) {
  const [investmentMetrics, setInvestmentMetrics] = useState<NeighborhoodInvestmentMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setMetricsLoading(true);
    getNeighborhoodInvestmentMetrics(scorecard.neighborhood.slug)
      .then((data) => {
        if (!cancelled) {
          setInvestmentMetrics(data);
          setMetricsLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMetricsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [scorecard.neighborhood.slug]);

  return (
    <div className="p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 bg-white/[0.06] border border-white/10 rounded-lg text-gray-400 px-3 py-1.5 cursor-pointer text-[13px] hover:bg-white/10 hover:text-gray-300 transition-colors"
        >
          <ArrowLeft className="size-3.5" />
          Back
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg sm:text-xl font-bold text-gray-100 m-0 truncate">
            {scorecard.neighborhood.name}
          </h2>
          <div className="text-xs text-gray-500">
            Rank #{scorecard.rank} of 22 Vancouver neighborhoods
          </div>
        </div>
        <ScoreRing score={scorecard.overall_score} size={72} />
      </div>

      {/* Score label */}
      <div
        className="text-center p-2.5 rounded-lg mb-6 text-[13px] font-semibold"
        style={{
          background: `${getScoreColor(scorecard.overall_score)}15`,
          color: getScoreColor(scorecard.overall_score),
        }}
      >
        {getScoreLabel(scorecard.overall_score)} Neighborhood
      </div>

      {/* Category Breakdown */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[13px] font-semibold text-gray-400 uppercase tracking-wide m-0">
            Category Breakdown
          </h3>
          <span className="text-[10px] text-gray-600">Weight</span>
        </div>
        {scorecard.category_scores.map((cs) => (
          <CategoryBar key={cs.category} item={cs} showSource />
        ))}
      </div>

      {/* Context Stats */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-[10px] p-4 text-center">
          <div className="text-2xl font-bold text-amber-500">
            {scorecard.active_rezonings}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">
            Active Rezonings
          </div>
        </div>
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-[10px] p-4 text-center">
          <div className="text-2xl font-bold text-blue-500">
            {scorecard.recent_permits}
          </div>
          <div className="text-[11px] text-gray-500 mt-1">
            Recent Permits
          </div>
        </div>
      </div>

      {/* Investment Metrics */}
      <div className="mb-6">
        <h3 className="text-[13px] font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Investment Metrics
        </h3>
        {metricsLoading ? (
          <div className="flex items-center justify-center h-[100px] text-gray-500 text-sm">
            Loading investment metrics...
          </div>
        ) : !investmentMetrics ? (
          <div className="bg-white/[0.03] border border-white/[0.06] rounded-[10px] p-4 text-center text-[13px] text-gray-500">
            Investment metrics not available for this neighborhood
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              {/* Active Projects */}
              <div className="bg-white/[0.03] border border-white/[0.06] rounded-[10px] p-4 text-center">
                <div className="text-2xl font-bold text-blue-500">
                  {investmentMetrics.active_projects}
                </div>
                <div className="text-[11px] text-gray-500 mt-1">
                  Active Projects
                </div>
              </div>

              {/* Proposed Units */}
              <div className="bg-white/[0.03] border border-white/[0.06] rounded-[10px] p-4 text-center">
                <div className="text-2xl font-bold text-purple-500">
                  {investmentMetrics.proposed_units.toLocaleString()}
                </div>
                <div className="text-[11px] text-gray-500 mt-1">
                  Proposed Units
                </div>
              </div>

              {/* Avg Approval Timeline */}
              <div className="bg-white/[0.03] border border-white/[0.06] rounded-[10px] p-4 text-center">
                <div className="text-2xl font-bold text-amber-500">
                  {investmentMetrics.avg_approval_months !== null
                    ? `${investmentMetrics.avg_approval_months}`
                    : "N/A"}
                </div>
                <div className="text-[11px] text-gray-500 mt-1">
                  Avg Approval (months)
                </div>
              </div>

              {/* Development Momentum */}
              <div className={cn(
                "rounded-[10px] p-4 text-center border",
                getMomentumBg(investmentMetrics.development_momentum),
              )}>
                <div className={cn(
                  "text-2xl font-bold",
                  getMomentumColor(investmentMetrics.development_momentum),
                )}>
                  {investmentMetrics.development_momentum !== null
                    ? `${investmentMetrics.development_momentum}x`
                    : "N/A"}
                </div>
                <div className="text-[11px] text-gray-500 mt-1">
                  Dev Momentum{" "}
                  <span className={cn(
                    "text-[10px]",
                    getMomentumColor(investmentMetrics.development_momentum),
                  )}>
                    ({getMomentumLabel(investmentMetrics.development_momentum)})
                  </span>
                </div>
              </div>
            </div>

            {/* Supply Pressure Footnote */}
            {investmentMetrics.supply_pressure !== null && (
              <div className="mt-2 text-[11px] text-gray-500 text-center">
                Supply pressure: {investmentMetrics.supply_pressure} proposed units per parcel
              </div>
            )}
          </>
        )}
      </div>

      {/* Methodology */}
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-[10px] p-4">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2.5">
          Scoring Methodology
        </h3>
        <div className="text-[11px] text-gray-500 leading-relaxed">
          <p className="mb-2">
            Scores are computed using a <strong className="text-gray-400">weighted composite</strong> of
            8 quality-of-life categories, each normalized to a 0-10 scale using min-max normalization
            across all 22 Vancouver neighbourhoods. Categories where lower values indicate better
            outcomes (safety, affordability) are inverted before scoring.
          </p>
          <p className="mb-2">
            <strong className="text-gray-400">Overall score</strong> = weighted average of all category
            scores, with weights reflecting investment-relevance: Safety, Schools, Transit, Development,
            and Affordability each at 15%; Parks and Walkability at 10%; Air Quality at 5%.
          </p>
          <p className="mb-2.5">
            <strong className="text-gray-400">Trends</strong> compare current period vs. prior period.
            Changes above +0.3 are marked improving; below -0.3 declining; otherwise stable.
          </p>
          <div className="text-[10px] text-gray-600 border-t border-white/[0.06] pt-2 flex flex-wrap gap-x-4 gap-y-1.5">
            <span className="font-semibold text-gray-500">Data sources:</span>
            <a href="https://geodash.vpd.ca/opendata/" target="_blank" rel="noopener noreferrer" className="text-slate-600 no-underline hover:text-slate-400 transition-colors">VPD Crime Data</a>
            <a href="https://opendata.vancouver.ca/" target="_blank" rel="noopener noreferrer" className="text-slate-600 no-underline hover:text-slate-400 transition-colors">CoV Open Data</a>
            <a href="https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources/gtfs" target="_blank" rel="noopener noreferrer" className="text-slate-600 no-underline hover:text-slate-400 transition-colors">TransLink GTFS</a>
            <a href="https://www.walkscore.com/CA-BC/Vancouver" target="_blank" rel="noopener noreferrer" className="text-slate-600 no-underline hover:text-slate-400 transition-colors">Walk Score</a>
            <a href="https://www.env.gov.bc.ca/epd/bcairquality/data/aqhi.html" target="_blank" rel="noopener noreferrer" className="text-slate-600 no-underline hover:text-slate-400 transition-colors">BC AQHI</a>
            <a href="https://www.compareschoolrankings.org/" target="_blank" rel="noopener noreferrer" className="text-slate-600 no-underline hover:text-slate-400 transition-colors">Fraser Institute</a>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Compare Panel ────────────────────────────────────────

interface CompareViewProps {
  comparison: NeighborhoodComparison;
  onBack: () => void;
}

function CompareView({ comparison, onBack }: CompareViewProps) {
  const categories = comparison.categories;
  const hoods = comparison.neighborhoods;

  return (
    <div className="p-4 sm:p-6">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 bg-white/[0.06] border border-white/10 rounded-lg text-gray-400 px-3 py-1.5 cursor-pointer text-[13px] hover:bg-white/10 hover:text-gray-300 transition-colors"
        >
          <ArrowLeft className="size-3.5" />
          Back
        </button>
        <h2 className="text-lg font-bold text-gray-100 m-0">
          Neighborhood Comparison
        </h2>
      </div>

      {/* Score headers */}
      <div
        className="gap-2 mb-5 p-3 bg-white/[0.03] rounded-[10px] overflow-x-auto"
        style={{
          display: "grid",
          gridTemplateColumns: `120px repeat(${hoods.length}, 1fr)`,
        }}
      >
        <div className="text-[11px] text-gray-500 font-semibold">
          OVERALL
        </div>
        {hoods.map((h) => (
          <div key={h.neighborhood.slug} className="text-center">
            <div className="text-[13px] font-semibold text-gray-300 mb-1 truncate">
              {h.neighborhood.name}
            </div>
            <div
              className="text-[22px] font-bold"
              style={{ color: getScoreColor(h.overall_score) }}
            >
              {h.overall_score.toFixed(1)}
            </div>
            <div className="text-[10px] text-gray-500">
              Rank #{h.rank}
            </div>
          </div>
        ))}
      </div>

      {/* Category rows */}
      {categories.map((cat) => (
        <div
          key={cat}
          className="gap-2 py-2.5 px-3 border-b border-white/[0.04] items-center"
          style={{
            display: "grid",
            gridTemplateColumns: `120px repeat(${hoods.length}, 1fr)`,
          }}
        >
          <div className="text-xs text-gray-400 flex items-center gap-1.5">
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
                className={cn(
                  "text-center p-1 rounded-md",
                  isBest && "bg-current/[0.08]",
                )}
                style={isBest ? { background: `${color}15` } : undefined}
              >
                <span
                  className={cn("text-[15px]", isBest ? "font-bold" : "font-medium")}
                  style={{ color }}
                >
                  {cs.score.toFixed(1)}
                </span>
                <span
                  className="ml-1 text-xs"
                  style={{ color: TREND_RAW_COLORS[cs.trend] }}
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
  const [searchText, setSearchText] = useState("");
  const [sortBy, setSortBy] = useState<"score-desc" | "score-asc" | "name-asc">("score-desc");

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
      .catch(() => {
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

  const filteredSummaries = summaries
    .filter(s => s.name.toLowerCase().includes(searchText.toLowerCase()))
    .sort((a, b) => {
      switch (sortBy) {
        case "score-asc": return a.overall_score - b.overall_score;
        case "name-asc": return a.name.localeCompare(b.name);
        default: return b.overall_score - a.overall_score;
      }
    });

  // ── Render ───────────────────────────────────────

  return (
    <div className="h-full flex flex-col bg-[var(--color-surface)] text-[var(--color-foreground)]">
      {/* Page Header */}
      <div className="px-4 sm:px-6 pt-5 pb-3 border-b border-[var(--color-border)]">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-[var(--color-foreground)] m-0">
              Neighborhood Scorecards
            </h1>
            <p className="text-xs text-[var(--color-foreground-muted)] mt-1 mb-0">
              Quality-of-life ratings across 22 Vancouver neighborhoods
            </p>
          </div>
          {view.type === "list" && (
            <div className="flex items-center gap-2">
              {compareSet.size >= 2 ? (
                <button
                  onClick={handleCompare}
                  className="bg-blue-500 border-none rounded-lg text-white px-4 py-2 text-[13px] font-semibold cursor-pointer transition-colors hover:bg-blue-600"
                >
                  Compare Selected ({compareSet.size})
                </button>
              ) : (
                <span className="text-[11px] text-[var(--color-foreground-muted)]">
                  Select 2-4 to compare
                </span>
              )}
              <ExportButton exportType="neighborhoods" label="Export CSV" />
            </div>
          )}
          {view.type !== "list" && (
            <ExportButton exportType="neighborhoods" label="Export CSV" />
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {loading && (
          <div className="flex items-center justify-center h-[200px] text-gray-500 text-sm">
            Loading neighborhoods...
          </div>
        )}

        {error && (
          <div className="mx-4 sm:mx-6 mt-6 p-4 bg-red-500/10 border border-red-500/20 rounded-[10px] text-red-300 text-[13px]">
            {error}
          </div>
        )}

        {!loading && !error && view.type === "list" && (
          <>
            <div className="px-4 sm:px-6 pt-3 pb-1 flex gap-2">
              <input
                type="text"
                placeholder="Search neighborhoods..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="flex-1 px-3 py-2 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg text-sm text-[var(--color-foreground)] placeholder-[var(--color-foreground-muted)] focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="px-2.5 py-2 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg text-sm text-[var(--color-foreground)] focus:outline-none focus:border-blue-500"
              >
                <option value="score-desc">Score: High &rarr; Low</option>
                <option value="score-asc">Score: Low &rarr; High</option>
                <option value="name-asc">Name: A &rarr; Z</option>
              </select>
            </div>
            <div className="flex flex-col gap-2 px-4 sm:px-6 py-4">
              {summaries.length === 0 ? (
                <div className="text-center py-12 px-6 text-[var(--color-foreground-muted)]">
                  <BarChart3 className="size-8 mx-auto mb-3 text-[var(--color-foreground-muted)]" />
                  <div className="text-sm font-medium">
                    No neighborhood data yet
                  </div>
                  <div className="text-xs mt-1">
                    Run the data scrapers to populate quality-of-life scores
                  </div>
                </div>
              ) : (
                <>
                  {filteredSummaries.map((s) => (
                    <NeighborhoodCard
                      key={s.slug}
                      summary={s}
                      onSelect={() => handleSelect(s.slug)}
                      isSelected={selectedSlug === s.slug}
                      onCompareToggle={() => handleCompareToggle(s.slug)}
                      isComparing={compareSet.has(s.slug)}
                    />
                  ))}
                  {compareSet.size === 0 && filteredSummaries.length > 0 && (
                    <div className="text-center text-[11px] text-[var(--color-foreground-muted)] py-2">
                      Tick the checkboxes on the right to compare neighborhoods side-by-side
                    </div>
                  )}
                </>
              )}
            </div>
          </>
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
