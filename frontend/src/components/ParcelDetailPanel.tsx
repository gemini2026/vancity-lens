"use client";

import { useEffect, useState, useCallback } from "react";
import { X, Star } from "lucide-react";
import type { ParcelEntitlement, DataSource } from "@/lib/types";
import type { IntelSignal } from "@/lib/intel-types";
import ProFormaSection from "./ProFormaSection";
import RiskFlagsSection from "./RiskFlagsSection";
import ShareButton from "./ShareButton";
import BeforeAfterComparison from "./BeforeAfterComparison";
import HBUAnalysisPanel from "./HBUAnalysis";
import { saveParcel, unsaveParcel, checkParcelSaved } from "@/lib/saved-parcels-api";
import { cn } from "@/lib/utils";
import { getApiBase } from "@/lib/api-base";

const API_BASE = getApiBase();

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

const SIGNAL_COLORS: Record<string, string> = {
  high_alpha: "#dc2626", moderate: "#ea580c", low: "#ca8a04",
  already_zoned: "#3b82f6", none: "#6b7280",
};
const SIGNAL_LABELS: Record<string, string> = {
  high_alpha: "HIGH ALPHA", moderate: "MODERATE", low: "LOW",
  already_zoned: "ALREADY ZONED HIGHER", none: "NO ENTITLEMENT",
};
const GRADE_COLORS: Record<string, string> = {
  A: "#22c55e", B: "#86efac", C: "#f59e0b", D: "#f87171", F: "#dc2626",
};
const SEVERITY_COLORS: Record<string, string> = {
  critical: "#dc2626", high: "#f97316", medium: "#eab308", low: "#6b7280",
};
const SIGNAL_TYPE_ICONS: Record<string, string> = {
  rezoning_decision: "🏗️", permit_approval: "📋", policy_change: "📜",
  community_opposition: "🗣️", density_change: "🏢", infrastructure_announcement: "🚇",
  legal_precedent: "⚖️", land_sale: "💰", other: "📌",
};

function SourceBadge({ confidence }: { confidence: string }) {
  const bg: Record<string, string> = { verified: "bg-green-500", calculated: "bg-blue-500", estimated: "bg-amber-500" };
  const labels: Record<string, string> = { verified: "GOV", calculated: "CALC", estimated: "EST" };
  return (
    <span className={cn("inline-block text-[9px] font-bold px-1.5 py-px rounded text-white ml-1 align-middle", bg[confidence] || "bg-gray-500")}>
      {labels[confidence] || confidence}
    </span>
  );
}

function CollapsibleSection({ title, defaultOpen = false, badge, children }: {
  title: string; defaultOpen?: boolean; badge?: React.ReactNode; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-white/[0.06] pt-3 mt-3">
      <button
        onClick={() => setOpen(!open)}
        className="bg-transparent border-none text-gray-300 cursor-pointer flex items-center gap-1.5 w-full p-0 text-[13px] font-semibold font-[inherit]"
      >
        <span className="text-[10px] text-gray-500">{open ? "▼" : "▶"}</span>
        {title}
        {badge}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

interface ParcelDetailPanelProps {
  data: ParcelEntitlement;
  nearbySignals?: IntelSignal[];
  onClose: () => void;
  onRunDealModel?: (pid: string) => void;
}

export default function ParcelDetailPanel({ data, nearbySignals, onClose, onRunDealModel }: ParcelDetailPanelProps) {
  const [dueDiligenceEvidence, setDueDiligenceEvidence] = useState<any>(null);
  const [dueDiligenceEvidenceLoading, setDueDiligenceEvidenceLoading] = useState(false);
  const [dueDiligenceEvidenceError, setDueDiligenceEvidenceError] = useState<string | null>(null);
  const [isSaved, setIsSaved] = useState(false);
  const [savePending, setSavePending] = useState(false);
  const isAuthenticated = typeof window !== "undefined" && !!localStorage.getItem("token");

  const color = SIGNAL_COLORS[data.signal] || "#6b7280";
  const ve = data.value_estimate;
  const be = data.best_entitlement;
  const v = data.validation;
  const src = data.sources;
  const gradeColor = v ? GRADE_COLORS[v.deal_grade] || "#6b7280" : "#6b7280";

  useEffect(() => {
    if (!data?.pid) return;
    let cancelled = false;
    const controller = new AbortController();
    setDueDiligenceEvidenceLoading(true);
    setDueDiligenceEvidenceError(null);

    fetch(`${API_BASE}/api/v1/parcels/${data.pid}/due-diligence/evidence`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.text().catch(() => "")) || `HTTP ${res.status}`);
        return res.json();
      })
      .then((json) => { if (!cancelled) setDueDiligenceEvidence(json); })
      .catch((err: any) => {
        if (err?.name === "AbortError") return;
        if (!cancelled) setDueDiligenceEvidenceError(err?.message || "Failed to load evidence");
      })
      .finally(() => { if (!cancelled) setDueDiligenceEvidenceLoading(false); });

    return () => { cancelled = true; controller.abort(); };
  }, [data?.pid]);

  // Check if parcel is saved (bookmark state)
  useEffect(() => {
    if (!data?.pid || !isAuthenticated) return;
    let cancelled = false;
    checkParcelSaved(data.pid).then((res) => {
      if (!cancelled) setIsSaved(res.saved);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [data?.pid, isAuthenticated]);

  const handleToggleSave = useCallback(async () => {
    if (savePending) return;
    setSavePending(true);
    try {
      if (isSaved) {
        await unsaveParcel(data.pid);
        setIsSaved(false);
      } else {
        await saveParcel(data.pid);
        setIsSaved(true);
      }
    } catch {} finally {
      setSavePending(false);
    }
  }, [data.pid, isSaved, savePending]);

  const handleDownloadReport = () => window.open(`${API_BASE}/api/v1/parcels/${data.pid}/report.pdf`, "_blank");
  const handleDownloadMemo = () => window.open(`${API_BASE}/api/v1/parcels/${data.pid}/memo.pdf`, "_blank");

  return (
    <div className="absolute inset-0 md:inset-y-0 md:left-auto md:right-0 md:w-[440px] bg-[var(--color-surface)] md:border-l md:border-[var(--color-panel-border)] z-30 flex flex-col text-gray-100 shadow-[-4px_0_20px_rgba(0,0,0,0.3)]">
      {/* Header */}
      <div className="flex justify-between items-center px-4 py-3 text-white" style={{ background: color }}>
        <span className="font-bold text-sm">
          {SIGNAL_LABELS[data.signal] || data.signal.toUpperCase()}
        </span>
        <div className="flex items-center gap-2">
          {v && (
            <>
              <span className="text-[13px]">
                {"★".repeat(v.confidence_stars || 1)}{"☆".repeat(3 - (v.confidence_stars || 1))}
              </span>
              <span
                className="text-[9px] font-bold px-1.5 py-0.5 rounded text-white"
                style={{ background: v.friction_level === "high" ? "#dc2626" : v.friction_level === "medium" ? "#f59e0b" : "#22c55e" }}
              >
                {(v.friction_level || "low").toUpperCase()} FRICTION
              </span>
              {v.execution_difficulty_score > 0 && (
                <span
                  className="inline-flex items-center justify-center w-[22px] h-[22px] rounded-full text-[10px] font-extrabold text-white border-2 border-white/30"
                  style={{ background: v.execution_difficulty_score >= 7 ? "#dc2626" : v.execution_difficulty_score >= 4 ? "#f59e0b" : "#22c55e" }}
                  title={`Execution Difficulty: ${v.execution_difficulty_score}/10`}
                >
                  {v.execution_difficulty_score}
                </span>
              )}
              <span
                className="text-sm font-extrabold px-2 py-0.5 rounded text-black tracking-wider"
                style={{ background: gradeColor }}
              >
                {v.deal_grade}
              </span>
            </>
          )}
          {isAuthenticated && (
            <button
              onClick={handleToggleSave}
              disabled={savePending}
              className="w-6 h-6 rounded flex items-center justify-center bg-white/20 text-white cursor-pointer border-none disabled:opacity-50"
              title={isSaved ? "Unsave parcel" : "Save parcel"}
            >
              <Star className={cn("w-3.5 h-3.5", isSaved && "fill-yellow-400 text-yellow-400")} />
            </button>
          )}
          <button
            onClick={onClose}
            className="w-6 h-6 rounded flex items-center justify-center bg-white/20 text-white cursor-pointer border-none"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* One-liner summary */}
      {v && (
        <div className="px-4 py-2 bg-slate-950 border-b border-slate-800 text-xs text-gray-300">
          <div className="flex gap-2 items-center mb-1">
            <span className="text-[10px] text-gray-400">Economics:</span>
            <span className="font-bold" style={{ color: gradeColor }}>{v.deal_grade}</span>
            <span className="text-[9px] text-gray-500">({v.deal_score}/100)</span>
            <span className="text-gray-700">|</span>
            <span className="text-[10px] text-gray-400">Friction:</span>
            <span className={cn("text-[10px] font-semibold", v.friction_level === "high" ? "text-red-400" : v.friction_level === "medium" ? "text-amber-300" : "text-green-300")}>
              {(v.friction_level || "low").charAt(0).toUpperCase() + (v.friction_level || "low").slice(1)}
            </span>
          </div>
          <div className="text-[11px]">
            {v.one_liner}
            {v.neighborhood && <span className="float-right text-[10px] text-gray-500">{v.neighborhood}</span>}
          </div>
        </div>
      )}

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Address & PID */}
        <div className="mb-3">
          <div className="text-[15px] font-semibold">{data.civic_address || data.pid}</div>
          <div className="text-[11px] text-gray-500 mt-0.5">
            PID: {data.pid} &nbsp;|&nbsp; Zone: {data.current_zoning || "?"}
          </div>
        </div>

        {/* Entitlement Summary */}
        {be && (be.zoning_already_exceeds ? (
          <div className="mb-3">
            <div className="text-sm font-bold text-blue-400 mb-1">
              Current zoning already allows {be.current_storeys} storeys / FSR {be.current_fsr}
            </div>
            <div className="text-xs text-gray-300 mb-1">
              Bill 47 Tier {be.tier} only provides {be.bill47_storeys} storeys / FSR {be.bill47_fsr}
            </div>
            <div className="text-xs text-gray-400">
              {parseFloat(String(be.distance_m)).toFixed(0)}m from {be.station_name}
            </div>
          </div>
        ) : (
          <div className="mb-3">
            <div className="text-lg font-bold text-white mb-1">
              Approved for {be.entitled_storeys} Stories
            </div>
            <div className="text-xs text-gray-300 mb-1">
              Tier {be.tier} · {parseFloat(String(be.distance_m)).toFixed(0)}m from {be.station_name} · FSR {be.entitled_fsr}
            </div>
            <div className="text-xs text-green-300">
              +{be.storey_uplift} storeys · +{be.fsr_uplift} FSR uplift
            </div>
          </div>
        ))}
        {!be && <div className="text-gray-400 mb-3">Outside all Transit-Oriented Areas</div>}

        {/* Before/After Comparison */}
        {be && (
          <CollapsibleSection title="Before / After Bill 47" defaultOpen>
            <BeforeAfterComparison
              entitlement={be}
              valueEstimate={ve}
              currentZoning={data.current_zoning}
            />
          </CollapsibleSection>
        )}

        {/* Highest & Best Use Analysis */}
        <CollapsibleSection title="Highest & Best Use" defaultOpen>
          <HBUAnalysisPanel pid={data.pid} />
        </CollapsibleSection>

        {/* Bill 44 Small-Scale Multi-Unit Housing */}
        {data.bill44?.is_eligible && (
          <CollapsibleSection title="Bill 44 Multiplex" defaultOpen>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <span className="text-gray-500">Eligible</span>
              <span className="text-green-400 text-right font-semibold">Yes</span>
              <span className="text-gray-500">Zone Category</span>
              <span className="text-gray-300 text-right">{data.bill44.zone_category?.replace('_', ' ')}</span>
              <span className="text-gray-500">Lot Size</span>
              <span className="text-gray-300 text-right">{data.bill44.lot_size_category}</span>
              <span className="text-gray-500">Base Units</span>
              <span className="text-gray-300 text-right">{data.bill44.max_units}</span>
              {data.bill44.transit_bonus && (
                <>
                  <span className="text-gray-500">Transit Bonus</span>
                  <span className="text-green-400 text-right">+{data.bill44.transit_bonus_units}</span>
                </>
              )}
              <span className="text-gray-500 font-semibold">Max Units</span>
              <span className="text-green-400 text-right font-bold">{data.bill44.effective_max_units}</span>
            </div>
          </CollapsibleSection>
        )}

        {/* Community Plan Density Bonus */}
        {data.community_plan?.has_bonus && data.community_plan.best_bonus && (
          <CollapsibleSection title="Community Plan Bonus">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <span className="text-gray-500">Plan</span>
              <span className="text-gray-300 text-right">{data.community_plan.best_bonus.plan_name}</span>
              <span className="text-gray-500">Area</span>
              <span className="text-gray-300 text-right">{data.community_plan.best_bonus.plan_area}</span>
              {data.community_plan.best_bonus.max_fsr && (
                <>
                  <span className="text-gray-500">Plan Max FSR</span>
                  <span className="text-green-400 text-right font-semibold">{data.community_plan.best_bonus.max_fsr}</span>
                </>
              )}
              {data.community_plan.best_bonus.max_storeys && (
                <>
                  <span className="text-gray-500">Plan Max Storeys</span>
                  <span className="text-green-400 text-right font-semibold">{data.community_plan.best_bonus.max_storeys}</span>
                </>
              )}
              {data.community_plan.best_bonus.conditions && (
                <>
                  <span className="text-gray-500">Conditions</span>
                  <span className="text-amber-500 text-right text-[10px]">{data.community_plan.best_bonus.conditions}</span>
                </>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* Value Estimate */}
        {ve && (
          <CollapsibleSection title="Value Estimate" defaultOpen>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <span className="text-gray-500">Lot Area</span>
              <span className="text-gray-300 text-right">{ve.lot_area_sqm} sqm</span>
              <span className="text-gray-500">Assessed</span>
              <span className="text-gray-300 text-right">{ve.current_assessed ? fmt(ve.current_assessed) : "N/A"}</span>
              <span className="text-gray-500">Asking</span>
              <span className="text-gray-300 text-right">{ve.asking_price ? fmt(ve.asking_price) : "Unlisted"}</span>
              {v?.price_per_buildable_sqft && (
                <>
                  <span className="text-gray-500">$/Buildable sqft</span>
                  <span className="text-amber-500 text-right font-semibold">${parseFloat(v.price_per_buildable_sqft).toFixed(0)}</span>
                </>
              )}
              {v?.assessed_ratio && (
                <>
                  <span className="text-gray-500">Ask/Assessed Ratio</span>
                  <span className={cn("text-right", parseFloat(v.assessed_ratio) > 1.3 ? "text-red-400" : parseFloat(v.assessed_ratio) < 1 ? "text-green-300" : "text-gray-300")}>
                    {parseFloat(v.assessed_ratio).toFixed(2)}x
                  </span>
                </>
              )}
              {v?.land_to_total_ratio && (
                <>
                  <span className="text-gray-500">Land/Total Ratio</span>
                  <span className={cn("text-right", parseFloat(v.land_to_total_ratio) > 0.75 ? "text-green-300" : "text-gray-300")}>
                    {(parseFloat(v.land_to_total_ratio) * 100).toFixed(0)}%
                  </span>
                </>
              )}
              {ve.estimated_units && (
                <>
                  <span className="text-gray-500">Est. Units</span>
                  <span className="text-gray-300 text-right">{ve.estimated_units}</span>
                </>
              )}
              {ve.nla_sqft && (
                <>
                  <span className="text-gray-500">Net Leasable Area</span>
                  <span className="text-gray-300 text-right">{ve.nla_sqft.toLocaleString()} sqft</span>
                </>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* Pro Forma */}
        {(v?.three_scenario_proforma || v?.pro_forma) && (
          <CollapsibleSection title="Pro Forma Analysis" defaultOpen>
            <ProFormaSection threeScenario={v.three_scenario_proforma || null} singleProForma={v.pro_forma || null} />
          </CollapsibleSection>
        )}

        {/* Hidden Costs */}
        {v?.three_scenario_proforma?.hidden_costs?.length ? (
          <CollapsibleSection
            title="Hidden Costs"
            badge={<span className="text-[11px] text-amber-500 font-semibold ml-1.5">{fmt(v.three_scenario_proforma.hidden_costs_total)} ({v.three_scenario_proforma.hidden_costs.length} items)</span>}
          >
            <div className="flex flex-col gap-1">
              {v.three_scenario_proforma.hidden_costs.map((hc: any, i: number) => (
                <div key={i} className="flex justify-between items-start py-1.5 border-b border-gray-800">
                  <div>
                    <div className="text-[11px] font-semibold text-amber-500">{hc.category}</div>
                    <div className="text-[10px] text-gray-400 mt-px">{hc.explanation}</div>
                  </div>
                  <span className="text-[11px] text-amber-500 font-bold shrink-0 ml-2">{fmt(hc.cost)}</span>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        ) : null}

        {/* Gap Analysis */}
        {v?.gap_analysis && (
          <CollapsibleSection title="Why The Gap Exists">
            <div className="text-[11px] text-gray-300 leading-relaxed bg-blue-400/[0.08] p-2.5 rounded-md border border-blue-400/15">
              {v.gap_analysis}
            </div>
          </CollapsibleSection>
        )}

        {/* Execution Difficulty */}
        {v?.execution_difficulty_factors?.length ? (
          <CollapsibleSection title={`Execution Difficulty: ${v.execution_difficulty_score}/10`}>
            <div className="flex flex-wrap gap-1">
              {v.execution_difficulty_factors.map((f: string, i: number) => (
                <span key={i} className="text-[10px] bg-slate-800 text-gray-400 px-2 py-0.5 rounded border border-gray-700">
                  {f}
                </span>
              ))}
            </div>
          </CollapsibleSection>
        ) : null}

        {/* Risk Flags */}
        {v?.risk_flags?.length ? (
          <CollapsibleSection
            title="Risk Assessment"
            badge={
              <span className="flex gap-1.5 ml-1.5">
                {v.red_flag_count ? <span className="text-[10px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded font-medium">{v.red_flag_count} Risk</span> : null}
                {v.yellow_flag_count ? <span className="text-[10px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded font-medium">{v.yellow_flag_count} Caution</span> : null}
                {v.green_flag_count ? <span className="text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded font-medium">{v.green_flag_count} Clear</span> : null}
              </span>
            }
          >
            <RiskFlagsSection flags={v.risk_flags} />
            {v.competing_parcels > 0 && (
              <div className="text-[10px] text-gray-500 mt-2">
                Supply: {v.competing_parcels} competing parcels ({v.supply_saturation} saturation)
              </div>
            )}
          </CollapsibleSection>
        ) : null}

        {/* Due Diligence */}
        {v?.due_diligence_checklist?.length ? (
          <CollapsibleSection title={`Due Diligence (${v.due_diligence_checklist.length} items)`}>
            {/* Evidence */}
            <div className="text-[10px] text-gray-400 leading-snug bg-[#0b1220] border border-gray-800 rounded-md p-2.5 mb-2.5">
              <div className="text-[11px] font-bold text-gray-300">Evidence (Auto-Collected)</div>
              {dueDiligenceEvidenceLoading ? (
                <div className="mt-1.5">Loading evidence...</div>
              ) : dueDiligenceEvidenceError ? (
                <div className="mt-1.5 text-amber-500">Evidence unavailable: {dueDiligenceEvidenceError}</div>
              ) : dueDiligenceEvidence ? (
                <div className="mt-1.5 flex flex-col gap-2">
                  {/* Utilities */}
                  <div>
                    <div className="text-[10px] font-bold text-gray-300">Utilities (proximity)</div>
                    {(["water", "sewer"] as const).map((t) => {
                      const u = dueDiligenceEvidence?.utilities?.[t];
                      if (!u) return null;
                      return (
                        <div key={t} className="mt-0.5">
                          <span className="text-gray-200">{t === "water" ? "Water" : "Sewer"}:</span>{" "}
                          {u.status === "ok" && u.nearest_distance_m != null ? (
                            <>nearest line ~{u.nearest_distance_m}m{u.source?.url && <> <a href={u.source.url} target="_blank" rel="noopener noreferrer" className="text-blue-400">source</a></>}</>
                          ) : <>{u.status}{u.note ? `: ${u.note}` : ""}</>}
                        </div>
                      );
                    })}
                  </div>
                  {/* Encumbrances */}
                  <div>
                    <div className="text-[10px] font-bold text-gray-300">Encumbrances proxy (easements)</div>
                    {(() => {
                      const e = dueDiligenceEvidence?.encumbrances_proxy;
                      if (!e) return null;
                      return (
                        <div className="mt-0.5">
                          {e.status === "ok" ? (
                            <>{e.easement_count ?? 0} easement(s) intersect this parcel{e.source?.url && <> <a href={e.source.url} target="_blank" rel="noopener noreferrer" className="text-blue-400">source</a></>}</>
                          ) : <>{e.status}{e.note ? `: ${e.note}` : ""}</>}
                        </div>
                      );
                    })()}
                  </div>
                  {/* Policy excerpts */}
                  <div>
                    <div className="text-[10px] font-bold text-gray-300">OCP / policy excerpts</div>
                    {(() => {
                      const p = dueDiligenceEvidence?.ocp_policy_excerpts;
                      if (!p) return null;
                      if (p.status !== "ok") return <div className="mt-0.5">{p.status}{p.note ? `: ${p.note}` : ""}</div>;
                      const excerpts = (p.excerpts || []).slice(0, 2);
                      return (
                        <div className="mt-1 flex flex-col gap-1.5">
                          {excerpts.length ? excerpts.map((ex: any, idx: number) => (
                            <div key={idx} className="border-t border-gray-900 pt-1.5">
                              <div className="text-gray-200 text-[10px] font-semibold">
                                {ex.title || ex.source_type || "Source"}{ex.section_header ? ` - ${ex.section_header}` : ""}
                              </div>
                              <div className="mt-0.5">{ex.excerpt ? `${String(ex.excerpt).slice(0, 180)}${String(ex.excerpt).length > 180 ? "..." : ""}` : ""}</div>
                              {ex.source_url && <a href={ex.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-400">source</a>}
                            </div>
                          )) : <div className="mt-0.5">No excerpts found for: {p.query}</div>}
                        </div>
                      );
                    })()}
                  </div>
                </div>
              ) : <div className="mt-1.5">No evidence available.</div>}
            </div>

            <div className="flex flex-col gap-1">
              {v.due_diligence_checklist.map((dd: any, i: number) => (
                <div key={i} className="flex items-start gap-1.5 py-1 border-b border-gray-800">
                  <span className="text-[10px] shrink-0 mt-px">
                    {dd.priority === "critical" ? "🔴" : dd.priority === "high" ? "🟡" : "🔵"}
                  </span>
                  <div className="flex-1">
                    <div className="text-[11px] font-semibold text-gray-300">{dd.item}</div>
                    <div className="text-[10px] text-gray-400">{dd.description}</div>
                  </div>
                  {dd.url && <a href={dd.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 text-[9px] shrink-0">check</a>}
                </div>
              ))}
            </div>
          </CollapsibleSection>
        ) : null}

        {/* Nearby Intelligence Signals */}
        {nearbySignals && nearbySignals.length > 0 && (
          <CollapsibleSection title={`${nearbySignals.length} Intelligence Signal${nearbySignals.length > 1 ? "s" : ""} Nearby`}>
            <div className="flex flex-col gap-1.5">
              {nearbySignals.slice(0, 8).map((sig) => (
                <div key={sig.id} className="flex gap-2 items-start py-1.5 border-b border-gray-800">
                  <div className="shrink-0 w-2 h-2 rounded-full mt-1" style={{ background: SEVERITY_COLORS[sig.severity] || "#6b7280" }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-semibold text-gray-300 truncate">
                      {SIGNAL_TYPE_ICONS[sig.signal_type] || "📌"} {sig.headline || sig.summary.substring(0, 60)}
                    </div>
                    <div className="text-[9px] text-gray-500 mt-0.5 flex gap-1.5">
                      <span className="text-white px-1 rounded-sm font-semibold" style={{ background: SEVERITY_COLORS[sig.severity] || "#6b7280" }}>
                        {sig.severity}
                      </span>
                      {sig.decision && <span>{sig.decision}</span>}
                      {sig.event_date && <span>{sig.event_date}</span>}
                    </div>
                  </div>
                </div>
              ))}
              {nearbySignals.length > 8 && (
                <div className="text-[10px] text-gray-500 text-center">+ {nearbySignals.length - 8} more signals</div>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* Sources */}
        {src?.sources?.length ? (
          <CollapsibleSection title={`Sources (${src.sources.length})`}>
            <div className="text-[10px] text-gray-400 mb-2">
              <span className="text-green-500">■</span> GOV &nbsp;
              <span className="text-blue-500">■</span> CALC &nbsp;
              <span className="text-amber-500">■</span> EST
            </div>
            {src.sources.map((s: DataSource, i: number) => (
              <div key={i} className="flex justify-between items-center py-1 border-b border-gray-800">
                <div className="flex-1">
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 no-underline text-[11px]">{s.label}</a>
                  ) : (
                    <span className="text-[11px] text-gray-300">{s.label}</span>
                  )}
                  <div className="text-[9px] text-gray-500 mt-px">{s.origin}</div>
                </div>
                <SourceBadge confidence={s.confidence} />
              </div>
            ))}
            {src.disclaimer && <div className="text-[9px] text-gray-600 mt-2 italic">{src.disclaimer}</div>}
          </CollapsibleSection>
        ) : null}
      </div>

      {/* Action buttons footer */}
      <div className="px-4 py-3 border-t border-white/[0.06] bg-slate-950 flex gap-2">
        <ShareButton pid={data.pid} />
        <button onClick={handleDownloadReport} className="flex-1 py-2 bg-slate-800 border border-gray-700 rounded-md text-gray-300 text-[11px] font-semibold cursor-pointer hover:bg-slate-700 transition-colors">
          PDF Report
        </button>
        <button onClick={handleDownloadMemo} className="flex-1 py-2 bg-slate-800 border border-gray-700 rounded-md text-gray-300 text-[11px] font-semibold cursor-pointer hover:bg-slate-700 transition-colors">
          Investor Memo
        </button>
        {onRunDealModel && (
          <button onClick={() => onRunDealModel(data.pid)} className="flex-1 py-2 bg-blue-500 border-none rounded-md text-white text-[11px] font-semibold cursor-pointer hover:bg-blue-600 transition-colors">
            Deal Model
          </button>
        )}
      </div>
    </div>
  );
}
