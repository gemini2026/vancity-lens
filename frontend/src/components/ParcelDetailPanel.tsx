"use client";

import { useEffect, useState } from "react";
import type { ParcelEntitlement, DataSource } from "@/lib/types";
import type { IntelSignal } from "@/lib/intel-types";
import ProFormaSection from "./ProFormaSection";
import RiskFlagsSection from "./RiskFlagsSection";
import ShareButton from "./ShareButton";
import { getApiBase } from "@/lib/api-base";

const API_BASE = getApiBase();

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

const SIGNAL_COLORS: Record<string, string> = {
  high_alpha: "#dc2626",
  moderate: "#ea580c",
  low: "#ca8a04",
  already_zoned: "#3b82f6",
  none: "#6b7280",
};
const SIGNAL_LABELS: Record<string, string> = {
  high_alpha: "HIGH ALPHA",
  moderate: "MODERATE",
  low: "LOW",
  already_zoned: "ALREADY ZONED HIGHER",
  none: "NO ENTITLEMENT",
};
const GRADE_COLORS: Record<string, string> = {
  A: "#22c55e",
  B: "#86efac",
  C: "#f59e0b",
  D: "#f87171",
  F: "#dc2626",
};
const SEVERITY_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#eab308",
  low: "#6b7280",
};
const SIGNAL_TYPE_ICONS: Record<string, string> = {
  rezoning_decision: "🏗️",
  permit_approval: "📋",
  policy_change: "📜",
  community_opposition: "🗣️",
  density_change: "🏢",
  infrastructure_announcement: "🚇",
  legal_precedent: "⚖️",
  land_sale: "💰",
  other: "📌",
};

function SourceBadge({ confidence }: { confidence: string }) {
  const colors: Record<string, string> = {
    verified: "#22c55e",
    calculated: "#3b82f6",
    estimated: "#f59e0b",
  };
  const labels: Record<string, string> = {
    verified: "GOV",
    calculated: "CALC",
    estimated: "EST",
  };
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: "9px",
        fontWeight: 700,
        padding: "1px 5px",
        borderRadius: "3px",
        background: colors[confidence] || "#6b7280",
        color: "#fff",
        marginLeft: "4px",
        verticalAlign: "middle",
      }}
    >
      {labels[confidence] || confidence}
    </span>
  );
}

function CollapsibleSection({
  title,
  defaultOpen = false,
  badge,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      style={{
        borderTop: "1px solid rgba(255,255,255,0.06)",
        paddingTop: "12px",
        marginTop: "12px",
      }}
    >
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: "none",
          border: "none",
          color: "#d1d5db",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          width: "100%",
          padding: 0,
          fontSize: "13px",
          fontWeight: 600,
          fontFamily: "inherit",
        }}
      >
        <span style={{ fontSize: "10px", color: "#6b7280" }}>{open ? "▼" : "▶"}</span>
        {title}
        {badge}
      </button>
      {open && <div style={{ marginTop: "8px" }}>{children}</div>}
    </div>
  );
}

interface ParcelDetailPanelProps {
  data: ParcelEntitlement;
  nearbySignals?: IntelSignal[];
  onClose: () => void;
  onRunDealModel?: (pid: string) => void;
}

export default function ParcelDetailPanel({
  data,
  nearbySignals,
  onClose,
  onRunDealModel,
}: ParcelDetailPanelProps) {
  const [showSources, setShowSources] = useState(false);
  const [dueDiligenceEvidence, setDueDiligenceEvidence] = useState<any>(null);
  const [dueDiligenceEvidenceLoading, setDueDiligenceEvidenceLoading] =
    useState<boolean>(false);
  const [dueDiligenceEvidenceError, setDueDiligenceEvidenceError] = useState<
    string | null
  >(null);
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

    fetch(`${API_BASE}/api/v1/parcels/${data.pid}/due-diligence/evidence`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(text || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((json) => {
        if (!cancelled) setDueDiligenceEvidence(json);
      })
      .catch((err: any) => {
        if (err?.name === "AbortError") return;
        if (!cancelled) {
          setDueDiligenceEvidenceError(err?.message || "Failed to load evidence");
        }
      })
      .finally(() => {
        if (!cancelled) setDueDiligenceEvidenceLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [data?.pid]);

  const handleDownloadReport = () => {
    const url = `${API_BASE}/api/v1/parcels/${data.pid}/report.pdf`;
    window.open(url, "_blank");
  };

  const handleDownloadMemo = () => {
    const url = `${API_BASE}/api/v1/parcels/${data.pid}/memo.pdf`;
    window.open(url, "_blank");
  };

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        right: 0,
        width: "440px",
        height: "100%",
        background: "#111827",
        borderLeft: "1px solid rgba(255,255,255,0.1)",
        zIndex: 30,
        display: "flex",
        flexDirection: "column",
        fontFamily: "system-ui, sans-serif",
        color: "#f3f4f6",
        boxShadow: "-4px 0 20px rgba(0,0,0,0.3)",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: color,
          color: "#fff",
          padding: "12px 16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ fontWeight: 700, fontSize: "14px" }}>
          {SIGNAL_LABELS[data.signal] || data.signal.toUpperCase()}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {v && (
            <>
              <span style={{ fontSize: "13px" }}>
                {"★".repeat(v.confidence_stars || 1)}
                {"☆".repeat(3 - (v.confidence_stars || 1))}
              </span>
              <span
                style={{
                  background:
                    v.friction_level === "high"
                      ? "#dc2626"
                      : v.friction_level === "medium"
                        ? "#f59e0b"
                        : "#22c55e",
                  color: "#fff",
                  fontSize: "9px",
                  fontWeight: 700,
                  padding: "2px 6px",
                  borderRadius: "3px",
                }}
              >
                {(v.friction_level || "low").toUpperCase()} FRICTION
              </span>
              {v.execution_difficulty_score > 0 && (
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "22px",
                    height: "22px",
                    borderRadius: "50%",
                    background:
                      v.execution_difficulty_score >= 7
                        ? "#dc2626"
                        : v.execution_difficulty_score >= 4
                          ? "#f59e0b"
                          : "#22c55e",
                    color: "#fff",
                    fontSize: "10px",
                    fontWeight: 800,
                    border: "2px solid rgba(255,255,255,0.3)",
                  }}
                  title={`Execution Difficulty: ${v.execution_difficulty_score}/10`}
                >
                  {v.execution_difficulty_score}
                </span>
              )}
              <span
                style={{
                  background: gradeColor,
                  color: "#000",
                  fontSize: "14px",
                  fontWeight: 800,
                  padding: "2px 8px",
                  borderRadius: "4px",
                  letterSpacing: "1px",
                }}
              >
                {v.deal_grade}
              </span>
            </>
          )}
          <button
            onClick={onClose}
            style={{
              background: "rgba(255,255,255,0.2)",
              border: "none",
              color: "#fff",
              width: "24px",
              height: "24px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "14px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* One-liner summary bar */}
      {v && (
        <div
          style={{
            padding: "8px 16px",
            background: "#0f172a",
            borderBottom: "1px solid #1e293b",
            fontSize: "12px",
            color: "#d1d5db",
          }}
        >
          <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "4px" }}>
            <span style={{ fontSize: "10px", color: "#9ca3af" }}>Economics:</span>
            <span style={{ fontWeight: 700, color: gradeColor }}>{v.deal_grade}</span>
            <span style={{ fontSize: "9px", color: "#6b7280" }}>({v.deal_score}/100)</span>
            <span style={{ color: "#374151" }}>|</span>
            <span style={{ fontSize: "10px", color: "#9ca3af" }}>Friction:</span>
            <span
              style={{
                fontSize: "10px",
                fontWeight: 600,
                color:
                  v.friction_level === "high"
                    ? "#f87171"
                    : v.friction_level === "medium"
                      ? "#fbbf24"
                      : "#86efac",
              }}
            >
              {(v.friction_level || "low").charAt(0).toUpperCase() +
                (v.friction_level || "low").slice(1)}
            </span>
          </div>
          <div style={{ fontSize: "11px" }}>
            {v.one_liner}
            {v.neighborhood && (
              <span style={{ float: "right", fontSize: "10px", color: "#6b7280" }}>
                {v.neighborhood}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
        {/* Address & PID */}
        <div style={{ marginBottom: "12px" }}>
          <div style={{ fontSize: "15px", fontWeight: 600 }}>
            {data.civic_address || data.pid}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "2px" }}>
            PID: {data.pid} &nbsp;|&nbsp; Zone: {data.current_zoning || "?"}
          </div>
        </div>

        {/* Entitlement Summary */}
        {be &&
          (be.zoning_already_exceeds ? (
            <div style={{ marginBottom: "12px" }}>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "#60a5fa", marginBottom: "4px" }}>
                Current zoning already allows {be.current_storeys} storeys / FSR{" "}
                {be.current_fsr}
              </div>
              <div style={{ fontSize: "12px", color: "#d1d5db", marginBottom: "4px" }}>
                Bill 47 Tier {be.tier} only provides {be.bill47_storeys} storeys / FSR{" "}
                {be.bill47_fsr}
              </div>
              <div style={{ fontSize: "12px", color: "#9ca3af" }}>
                {parseFloat(String(be.distance_m)).toFixed(0)}m from {be.station_name}
              </div>
            </div>
          ) : (
            <div style={{ marginBottom: "12px" }}>
              <div style={{ fontSize: "18px", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
                Approved for {be.entitled_storeys} Stories
              </div>
              <div style={{ fontSize: "12px", color: "#d1d5db", marginBottom: "4px" }}>
                Tier {be.tier} · {parseFloat(String(be.distance_m)).toFixed(0)}m from{" "}
                {be.station_name} · FSR {be.entitled_fsr}
              </div>
              <div style={{ fontSize: "12px", color: "#86efac" }}>
                +{be.storey_uplift} storeys · +{be.fsr_uplift} FSR uplift
              </div>
            </div>
          ))}

        {!be && (
          <div style={{ color: "#9ca3af", marginBottom: "12px" }}>
            Outside all Transit-Oriented Areas
          </div>
        )}

        {/* Value Estimate */}
        {ve && (
          <CollapsibleSection title="Value Estimate" defaultOpen>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "4px 12px",
                fontSize: "12px",
              }}
            >
              <span style={{ color: "#6b7280" }}>Lot Area</span>
              <span style={{ color: "#d1d5db", textAlign: "right" }}>{ve.lot_area_sqm} sqm</span>
              <span style={{ color: "#6b7280" }}>Assessed</span>
              <span style={{ color: "#d1d5db", textAlign: "right" }}>
                {ve.current_assessed ? fmt(ve.current_assessed) : "N/A"}
              </span>
              <span style={{ color: "#6b7280" }}>Asking</span>
              <span style={{ color: "#d1d5db", textAlign: "right" }}>
                {ve.asking_price ? fmt(ve.asking_price) : "Unlisted"}
              </span>
              {v?.price_per_buildable_sqft && (
                <>
                  <span style={{ color: "#6b7280" }}>$/Buildable sqft</span>
                  <span style={{ color: "#f59e0b", textAlign: "right", fontWeight: 600 }}>
                    ${parseFloat(v.price_per_buildable_sqft).toFixed(0)}
                  </span>
                </>
              )}
              {v?.assessed_ratio && (
                <>
                  <span style={{ color: "#6b7280" }}>Ask/Assessed Ratio</span>
                  <span
                    style={{
                      color:
                        parseFloat(v.assessed_ratio) > 1.3
                          ? "#f87171"
                          : parseFloat(v.assessed_ratio) < 1
                            ? "#86efac"
                            : "#d1d5db",
                      textAlign: "right",
                    }}
                  >
                    {parseFloat(v.assessed_ratio).toFixed(2)}x
                  </span>
                </>
              )}
              {v?.land_to_total_ratio && (
                <>
                  <span style={{ color: "#6b7280" }}>Land/Total Ratio</span>
                  <span
                    style={{
                      color: parseFloat(v.land_to_total_ratio) > 0.75 ? "#86efac" : "#d1d5db",
                      textAlign: "right",
                    }}
                  >
                    {(parseFloat(v.land_to_total_ratio) * 100).toFixed(0)}%
                  </span>
                </>
              )}
              {ve.estimated_units && (
                <>
                  <span style={{ color: "#6b7280" }}>Est. Units</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>{ve.estimated_units}</span>
                </>
              )}
              {ve.nla_sqft && (
                <>
                  <span style={{ color: "#6b7280" }}>Net Leasable Area</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {ve.nla_sqft.toLocaleString()} sqft
                  </span>
                </>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* Pro Forma */}
        {(v?.three_scenario_proforma || v?.pro_forma) && (
          <CollapsibleSection title="Pro Forma Analysis" defaultOpen>
            <ProFormaSection
              threeScenario={v.three_scenario_proforma || null}
              singleProForma={v.pro_forma || null}
            />
          </CollapsibleSection>
        )}

        {/* Hidden Costs */}
        {v?.three_scenario_proforma?.hidden_costs?.length ? (
          <CollapsibleSection
            title="Hidden Costs"
            badge={
              <span
                style={{
                  fontSize: "11px",
                  color: "#f59e0b",
                  fontWeight: 600,
                  marginLeft: "6px",
                }}
              >
                {fmt(v.three_scenario_proforma.hidden_costs_total)} (
                {v.three_scenario_proforma.hidden_costs.length} items)
              </span>
            }
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              {v.three_scenario_proforma.hidden_costs.map((hc, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    padding: "6px 0",
                    borderBottom: "1px solid #1f2937",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "11px", fontWeight: 600, color: "#f59e0b" }}>
                      {hc.category}
                    </div>
                    <div style={{ fontSize: "10px", color: "#9ca3af", marginTop: "1px" }}>
                      {hc.explanation}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: "11px",
                      color: "#f59e0b",
                      fontWeight: 700,
                      flexShrink: 0,
                      marginLeft: "8px",
                    }}
                  >
                    {fmt(hc.cost)}
                  </span>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        ) : null}

        {/* Gap Analysis */}
        {v?.gap_analysis && (
          <CollapsibleSection title="Why The Gap Exists">
            <div
              style={{
                fontSize: "11px",
                color: "#d1d5db",
                lineHeight: 1.5,
                background: "rgba(96,165,250,0.08)",
                padding: "10px",
                borderRadius: "6px",
                border: "1px solid rgba(96,165,250,0.15)",
              }}
            >
              {v.gap_analysis}
            </div>
          </CollapsibleSection>
        )}

        {/* Execution Difficulty */}
        {v?.execution_difficulty_factors?.length ? (
          <CollapsibleSection
            title={`Execution Difficulty: ${v.execution_difficulty_score}/10`}
          >
            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
              {v.execution_difficulty_factors.map((f, i) => (
                <span
                  key={i}
                  style={{
                    fontSize: "10px",
                    background: "#1e293b",
                    color: "#9ca3af",
                    padding: "3px 8px",
                    borderRadius: "4px",
                    border: "1px solid #374151",
                  }}
                >
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
              <span style={{ fontSize: "10px", color: "#6b7280", marginLeft: "6px" }}>
                {v.red_flag_count ? `${v.red_flag_count} red ` : ""}
                {v.yellow_flag_count ? `${v.yellow_flag_count} yellow ` : ""}
                {v.green_flag_count ? `${v.green_flag_count} green` : ""}
              </span>
            }
          >
            <RiskFlagsSection flags={v.risk_flags} />
            {v.competing_parcels > 0 && (
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "8px" }}>
                Supply: {v.competing_parcels} competing parcels ({v.supply_saturation} saturation)
              </div>
            )}
          </CollapsibleSection>
        ) : null}

        {/* Due Diligence */}
        {v?.due_diligence_checklist?.length ? (
          <CollapsibleSection
            title={`Due Diligence (${v.due_diligence_checklist.length} items)`}
          >
            {/* Evidence */}
            <div
              style={{
                fontSize: "10px",
                color: "#9ca3af",
                lineHeight: 1.4,
                background: "#0b1220",
                border: "1px solid #1f2937",
                borderRadius: "6px",
                padding: "10px",
                marginBottom: "10px",
              }}
            >
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#d1d5db" }}>
                Evidence (Auto-Collected)
              </div>
              {dueDiligenceEvidenceLoading ? (
                <div style={{ marginTop: "6px" }}>Loading evidence...</div>
              ) : dueDiligenceEvidenceError ? (
                <div style={{ marginTop: "6px", color: "#f59e0b" }}>
                  Evidence unavailable: {dueDiligenceEvidenceError}
                </div>
              ) : dueDiligenceEvidence ? (
                <div style={{ marginTop: "6px", display: "flex", flexDirection: "column", gap: "8px" }}>
                  {/* Utilities */}
                  <div>
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#d1d5db" }}>
                      Utilities (proximity)
                    </div>
                    {(["water", "sewer"] as const).map((t) => {
                      const u = dueDiligenceEvidence?.utilities?.[t];
                      const label = t === "water" ? "Water" : "Sewer";
                      if (!u) return null;
                      return (
                        <div key={t} style={{ marginTop: "2px" }}>
                          <span style={{ color: "#e5e7eb" }}>{label}:</span>{" "}
                          {u.status === "ok" && u.nearest_distance_m != null ? (
                            <>
                              nearest line ~{u.nearest_distance_m}m
                              {u.source?.url ? (
                                <>
                                  {" "}
                                  <a
                                    href={u.source.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: "#60a5fa" }}
                                  >
                                    source
                                  </a>
                                </>
                              ) : null}
                            </>
                          ) : (
                            <>
                              {u.status}
                              {u.note ? `: ${u.note}` : ""}
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Encumbrances */}
                  <div>
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#d1d5db" }}>
                      Encumbrances proxy (easements)
                    </div>
                    {(() => {
                      const e = dueDiligenceEvidence?.encumbrances_proxy;
                      if (!e) return null;
                      return (
                        <div style={{ marginTop: "2px" }}>
                          {e.status === "ok" ? (
                            <>
                              {e.easement_count ?? 0} easement(s) intersect this parcel{" "}
                              {e.source?.url ? (
                                <a
                                  href={e.source.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: "#60a5fa" }}
                                >
                                  source
                                </a>
                              ) : null}
                            </>
                          ) : (
                            <>
                              {e.status}
                              {e.note ? `: ${e.note}` : ""}
                            </>
                          )}
                        </div>
                      );
                    })()}
                  </div>

                  {/* Policy excerpts */}
                  <div>
                    <div style={{ fontSize: "10px", fontWeight: 700, color: "#d1d5db" }}>
                      OCP / policy excerpts
                    </div>
                    {(() => {
                      const p = dueDiligenceEvidence?.ocp_policy_excerpts;
                      if (!p) return null;
                      if (p.status !== "ok") {
                        return (
                          <div style={{ marginTop: "2px" }}>
                            {p.status}
                            {p.note ? `: ${p.note}` : ""}
                          </div>
                        );
                      }
                      const excerpts = (p.excerpts || []).slice(0, 2);
                      return (
                        <div style={{ marginTop: "4px", display: "flex", flexDirection: "column", gap: "6px" }}>
                          {excerpts.length ? (
                            excerpts.map((ex: any, idx: number) => (
                              <div key={idx} style={{ borderTop: "1px solid #111827", paddingTop: "6px" }}>
                                <div style={{ color: "#e5e7eb", fontSize: "10px", fontWeight: 600 }}>
                                  {ex.title || ex.source_type || "Source"}
                                  {ex.section_header ? ` - ${ex.section_header}` : ""}
                                </div>
                                <div style={{ marginTop: "2px" }}>
                                  {ex.excerpt ? `${String(ex.excerpt).slice(0, 180)}${String(ex.excerpt).length > 180 ? "..." : ""}` : ""}
                                </div>
                                {ex.source_url ? (
                                  <a
                                    href={ex.source_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: "#60a5fa" }}
                                  >
                                    source
                                  </a>
                                ) : null}
                              </div>
                            ))
                          ) : (
                            <div style={{ marginTop: "2px" }}>No excerpts found for: {p.query}</div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: "6px" }}>No evidence available.</div>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              {v.due_diligence_checklist.map((dd: any, i: number) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "6px",
                    padding: "4px 0",
                    borderBottom: "1px solid #1f2937",
                  }}
                >
                  <span style={{ fontSize: "10px", flexShrink: 0, marginTop: "1px" }}>
                    {dd.priority === "critical" ? "🔴" : dd.priority === "high" ? "🟡" : "🔵"}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "11px", fontWeight: 600, color: "#d1d5db" }}>
                      {dd.item}
                    </div>
                    <div style={{ fontSize: "10px", color: "#9ca3af" }}>{dd.description}</div>
                  </div>
                  {dd.url && (
                    <a
                      href={dd.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#60a5fa", fontSize: "9px", flexShrink: 0 }}
                    >
                      check
                    </a>
                  )}
                </div>
              ))}
            </div>
          </CollapsibleSection>
        ) : null}

        {/* Nearby Intelligence Signals */}
        {nearbySignals && nearbySignals.length > 0 && (
          <CollapsibleSection
            title={`${nearbySignals.length} Intelligence Signal${nearbySignals.length > 1 ? "s" : ""} Nearby`}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {nearbySignals.slice(0, 8).map((sig) => (
                <div
                  key={sig.id}
                  style={{
                    display: "flex",
                    gap: "8px",
                    alignItems: "flex-start",
                    padding: "6px 0",
                    borderBottom: "1px solid #1f2937",
                  }}
                >
                  <div
                    style={{
                      flexShrink: 0,
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      marginTop: "4px",
                      background: SEVERITY_COLORS[sig.severity] || "#6b7280",
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "11px",
                        fontWeight: 600,
                        color: "#d1d5db",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {SIGNAL_TYPE_ICONS[sig.signal_type] || "📌"}{" "}
                      {sig.headline || sig.summary.substring(0, 60)}
                    </div>
                    <div
                      style={{
                        fontSize: "9px",
                        color: "#6b7280",
                        marginTop: "2px",
                        display: "flex",
                        gap: "6px",
                      }}
                    >
                      <span
                        style={{
                          background: SEVERITY_COLORS[sig.severity] || "#6b7280",
                          color: "#fff",
                          padding: "0 4px",
                          borderRadius: "2px",
                          fontWeight: 600,
                        }}
                      >
                        {sig.severity}
                      </span>
                      {sig.decision && <span>{sig.decision}</span>}
                      {sig.event_date && <span>{sig.event_date}</span>}
                    </div>
                  </div>
                </div>
              ))}
              {nearbySignals.length > 8 && (
                <div style={{ fontSize: "10px", color: "#6b7280", textAlign: "center" }}>
                  + {nearbySignals.length - 8} more signals
                </div>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* Sources */}
        {src?.sources?.length ? (
          <CollapsibleSection title={`Sources (${src.sources.length})`}>
            <div style={{ fontSize: "10px", color: "#9ca3af", marginBottom: "8px" }}>
              <span style={{ color: "#22c55e" }}>■</span> GOV &nbsp;
              <span style={{ color: "#3b82f6" }}>■</span> CALC &nbsp;
              <span style={{ color: "#f59e0b" }}>■</span> EST
            </div>
            {src.sources.map((s, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "4px 0",
                  borderBottom: "1px solid #1f2937",
                }}
              >
                <div style={{ flex: 1 }}>
                  {s.url ? (
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#60a5fa", textDecoration: "none", fontSize: "11px" }}
                    >
                      {s.label}
                    </a>
                  ) : (
                    <span style={{ fontSize: "11px", color: "#d1d5db" }}>{s.label}</span>
                  )}
                  <div style={{ fontSize: "9px", color: "#6b7280", marginTop: "1px" }}>
                    {s.origin}
                  </div>
                </div>
                <SourceBadge confidence={s.confidence} />
              </div>
            ))}
            {src.disclaimer && (
              <div
                style={{
                  fontSize: "9px",
                  color: "#4b5563",
                  marginTop: "8px",
                  fontStyle: "italic",
                }}
              >
                {src.disclaimer}
              </div>
            )}
          </CollapsibleSection>
        ) : null}
      </div>

      {/* Action buttons footer */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          background: "#0f172a",
          display: "flex",
          gap: "8px",
        }}
      >
        <ShareButton pid={data.pid} />
        <button
          onClick={handleDownloadReport}
          style={{
            flex: 1,
            padding: "8px",
            background: "#1e293b",
            border: "1px solid #374151",
            borderRadius: "6px",
            color: "#d1d5db",
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          PDF Report
        </button>
        <button
          onClick={handleDownloadMemo}
          style={{
            flex: 1,
            padding: "8px",
            background: "#1e293b",
            border: "1px solid #374151",
            borderRadius: "6px",
            color: "#d1d5db",
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Investor Memo
        </button>
        {onRunDealModel && (
          <button
            onClick={() => onRunDealModel(data.pid)}
            style={{
              flex: 1,
              padding: "8px",
              background: "#3b82f6",
              border: "none",
              borderRadius: "6px",
              color: "#fff",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Deal Model
          </button>
        )}
      </div>
    </div>
  );
}
