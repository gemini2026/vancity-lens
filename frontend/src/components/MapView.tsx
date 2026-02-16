"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import mapboxgl from "mapbox-gl";
import { cn } from "@/lib/utils";
import "mapbox-gl/dist/mapbox-gl.css";
import { fetchTOAGeoJSON, fetchEntitlement, fetchNearestParcel, fetchOpportunities } from "@/lib/api";
import { getSignalsForParcel, getSignalsGeoJSON } from "@/lib/intel-api";
import { fetchNeighborhoodRiskScores, type NeighborhoodRisk } from "@/lib/political-risk-api";
import type { ParcelEntitlement, EntitlementSignal } from "@/lib/types";
import type { IntelSignal } from "@/lib/intel-types";
import ParcelDetailPanel from "./ParcelDetailPanel";
import AddressSearchBar from "./AddressSearchBar";
import FinancingCalculator from "./FinancingCalculator";
import CaseStudyCarousel from "./CaseStudyCarousel";
import type { GeocodingResult } from "@/lib/geocoding";
import { getApiBase } from "@/lib/api-base";
import { useTheme } from "@/lib/theme-context";
import { Layers } from "lucide-react";

const API_BASE = getApiBase();

const TIER_COLORS: Record<number, string> = {
  1: "rgba(220, 38, 38, 0.18)",
  2: "rgba(234, 88, 12, 0.14)",
  3: "rgba(202, 138, 4, 0.10)",
};
const TIER_BORDERS: Record<number, string> = {
  1: "rgba(220, 38, 38, 0.6)",
  2: "rgba(234, 88, 12, 0.45)",
  3: "rgba(202, 138, 4, 0.3)",
};
const RISK_COLORS: Record<string, string> = {
  low: "rgba(34, 197, 94, 0.25)",      // green for 1-3
  medium: "rgba(234, 179, 8, 0.30)",    // yellow for 4-6
  high: "rgba(239, 68, 68, 0.35)",      // red for 7-10
};
const SIGNAL_COLORS: Record<EntitlementSignal, string> = {
  high_alpha: "#dc2626",
  moderate: "#ea580c",
  low: "#ca8a04",
  already_zoned: "#3b82f6",
  none: "#6b7280",
};
const SIGNAL_LABELS: Record<EntitlementSignal, string> = {
  high_alpha: "HIGH ALPHA",
  moderate: "MODERATE",
  low: "LOW",
  already_zoned: "ALREADY ZONED HIGHER",
  none: "NO ENTITLEMENT",
};

// Intelligence signal severity colors for map layer
const SEVERITY_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#eab308",
  low: "#6b7280",
};
const SEVERITY_SIZES: Record<string, number> = {
  critical: 12,
  high: 10,
  medium: 8,
  low: 6,
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

function escapeHtml(s: string | null | undefined): string {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

/** Detect WebGL availability without triggering an error overlay. */
function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    return gl instanceof WebGLRenderingContext;
  } catch {
    return false;
  }
}

export default function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const signalMarkersRef = useRef<mapboxgl.Marker[]>([]);
  const clusterMarkersRef = useRef<mapboxgl.Marker[]>([]);
  const selectionMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const [loading, setLoading] = useState(false);
  const [showSignals, setShowSignals] = useState(true);
  const [showClusters, setShowClusters] = useState(true);
  const [clusters, setClusters] = useState<any[]>([]);
  const [mapError, setMapError] = useState<string | null>(null);
  const [selectedParcel, setSelectedParcel] = useState<ParcelEntitlement | null>(null);
  const [selectedSignals, setSelectedSignals] = useState<IntelSignal[]>([]);
  const [showFinancing, setShowFinancing] = useState(false);
  const [financingPid, setFinancingPid] = useState<string>("");
  const [showCaseStudies, setShowCaseStudies] = useState(true);
  const [visibleTiers, setVisibleTiers] = useState<Record<number, boolean>>({ 1: true, 2: true, 3: true });
  const [showRiskChoropleth, setShowRiskChoropleth] = useState(false);
  const [riskScores, setRiskScores] = useState<NeighborhoodRisk[]>([]);
  const [showLayerMenu, setShowLayerMenu] = useState(false);
  const { resolvedTheme } = useTheme();
  const mapStyle = resolvedTheme === "dark" ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/light-v11";

  const toggleTier = useCallback((tier: number) => {
    setVisibleTiers(prev => {
      const next = { ...prev, [tier]: !prev[tier] };
      const m = map.current;
      if (m) {
        const vis = next[tier] ? "visible" : "none";
        if (m.getLayer(`toa-fill-t${tier}`)) m.setLayoutProperty(`toa-fill-t${tier}`, "visibility", vis);
        if (m.getLayer(`toa-border-t${tier}`)) m.setLayoutProperty(`toa-border-t${tier}`, "visibility", vis);
      }
      return next;
    });
  }, []);

  const openDetailPanel = useCallback((data: ParcelEntitlement, nearbySignals?: IntelSignal[]) => {
    popupRef.current?.remove();
    setSelectedParcel(data);
    setSelectedSignals(nearbySignals || []);
  }, []);

  const handleAddressSelect = useCallback((result: GeocodingResult) => {
    if (!map.current) return;
    map.current.flyTo({ center: [result.lng, result.lat], zoom: 16, duration: 1500 });
    // Trigger parcel analysis at the location
    setTimeout(async () => {
      setLoading(true);
      try {
        const nearest = await fetchNearestParcel(result.lng, result.lat, 150);
        if (!nearest) { setLoading(false); return; }
        const [data, signals] = await Promise.all([
          fetchEntitlement(nearest.pid),
          getSignalsForParcel(nearest.pid, 500).catch(() => [] as IntelSignal[]),
        ]);
        openDetailPanel(data, signals);
      } catch (err) {
        console.error("Address lookup failed:", err);
      } finally {
        setLoading(false);
      }
    }, 1600);
  }, [openDetailPanel]);

  const showPopup = useCallback((data: ParcelEntitlement, lngLat: mapboxgl.LngLat, nearbySignals?: IntelSignal[]) => {
    popupRef.current?.remove();
    const color = SIGNAL_COLORS[data.signal];
    const ve = data.value_estimate;
    const be = data.best_entitlement;
    const src = data.sources;
    const v = data.validation;

    // Grade color mapping
    const GRADE_COLORS: Record<string, string> = { A: "#22c55e", B: "#86efac", C: "#f59e0b", D: "#f87171", F: "#dc2626" };
    const gradeColor = v ? (GRADE_COLORS[v.deal_grade] || "#6b7280") : "#6b7280";

    // Confidence badge helper
    const badge = (c: string) => {
      const colors: Record<string, string> = { verified: "#22c55e", calculated: "#3b82f6", estimated: "#f59e0b" };
      const labels: Record<string, string> = { verified: "GOV", calculated: "CALC", estimated: "EST" };
      return `<span style="display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;background:${colors[c] || "#6b7280"};color:#fff;margin-left:4px;vertical-align:middle">${labels[c] || c}</span>`;
    };

    // Source row helper
    const srcRow = (field: string) => {
      const s = src?.sources?.find(x => x.field === field);
      if (!s) return "";
      const link = s.url ? `<a href="${s.url}" target="_blank" rel="noopener" style="color:#60a5fa;text-decoration:underline;font-size:10px;margin-left:4px">verify ↗</a>` : "";
      return `${badge(s.confidence)}${link}`;
    };

    // Risk flag HTML helper
    const flagIcon = (sev: string) => sev === "red" ? "🔴" : sev === "yellow" ? "🟡" : "🟢";
    const flagsHtml = v?.risk_flags?.length ? v.risk_flags.map((f: any) =>
      `<div style="display:flex;align-items:flex-start;gap:6px;padding:4px 0;border-bottom:1px solid #1f2937">
        <span style="font-size:10px;flex-shrink:0;margin-top:1px">${flagIcon(f.severity)}</span>
        <div style="flex:1">
          <div style="font-size:11px;font-weight:600;color:${f.severity === 'red' ? '#f87171' : f.severity === 'yellow' ? '#fbbf24' : '#86efac'}">${f.label}</div>
          <div style="font-size:10px;color:#9ca3af;margin-top:1px">${f.detail}</div>
          ${f.cost_impact ? `<div style="font-size:9px;color:#f59e0b;margin-top:2px">Impact: ${f.cost_impact}</div>` : ""}
        </div>
        ${f.verify_url ? `<a href="${f.verify_url}" target="_blank" rel="noopener" style="color:#60a5fa;font-size:9px;flex-shrink:0;margin-top:2px">verify↗</a>` : ""}
      </div>`
    ).join("") : "";

    // V3: Three-scenario pro forma
    const tsp = v?.three_scenario_proforma;
    const pf = v?.pro_forma;

    const scenarioHtml = (s: any) => s ? `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;font-size:10px">
        <span style="color:#6b7280">Construction</span><span style="color:#d1d5db;text-align:right">${s.construction_type.replace(/_/g, " ")}</span>
        <span style="color:#6b7280">Sellable sqft</span><span style="color:#d1d5db;text-align:right">${s.sellable_sqft}</span>
        <span style="color:#6b7280">Revenue/sqft</span><span style="color:#d1d5db;text-align:right">${s.revenue_per_sqft}</span>
        ${parseFloat(s.absorption_discount) > 0 ? `<span style="color:#6b7280">Absorption Disc</span><span style="color:#f87171;text-align:right">-${(parseFloat(s.absorption_discount)*100).toFixed(0)}%</span>` : ""}
        <span style="color:#6b7280">Net Revenue</span><span style="color:#d1d5db;text-align:right;font-weight:600">${fmt(s.net_revenue)}</span>
        <span style="color:#6b7280">Hard Costs</span><span style="color:#f87171;text-align:right">-${fmt(s.hard_cost_total)}</span>
        ${parseFloat(s.hard_cost_inflation) > 0 ? `<span style="color:#4b5563;font-size:9px;padding-left:8px">↳ incl ${(parseFloat(s.hard_cost_inflation)*100).toFixed(0)}% inflation</span><span></span>` : ""}
        <span style="color:#6b7280">Soft Costs</span><span style="color:#f87171;text-align:right">-${fmt(s.soft_cost_total)}</span>
        ${s.contingency_total > 0 ? `<span style="color:#6b7280">Contingency</span><span style="color:#f87171;text-align:right">-${fmt(s.contingency_total)}</span>` : ""}
        ${s.marketing_total > 0 ? `<span style="color:#6b7280">Marketing/Sales</span><span style="color:#f87171;text-align:right">-${fmt(s.marketing_total)}</span>` : ""}
        <span style="color:#6b7280">CAC + DCL</span><span style="color:#f87171;text-align:right">-${fmt(s.cac_dcl_total)}</span>
        ${s.hidden_costs_total > 0 ? `<span style="color:#f59e0b;font-weight:600">Hidden Costs ⚠</span><span style="color:#f59e0b;text-align:right;font-weight:600">-${fmt(s.hidden_costs_total)}</span>` : ""}
        <span style="color:#6b7280">Holding (${s.holding_months}mo)</span><span style="color:#f87171;text-align:right">-${fmt(s.holding_cost)}</span>
        <span style="color:#6b7280">Dev Profit</span><span style="color:#f87171;text-align:right">-${fmt(s.developer_profit)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:6px;padding-top:6px;border-top:1px solid #374151">
        <span style="color:#9ca3af;font-weight:600">Residual Land Value</span>
        <span style="color:#fff;font-weight:700">${fmt(s.residual_land_value)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:13px;margin-top:4px">
        <span style="color:#9ca3af;font-weight:600">True Alpha</span>
        <span style="color:${s.true_alpha > 0 ? "#4ade80" : "#f87171"};font-weight:700">
          ${s.true_alpha > 0 ? "+" : ""}${fmt(s.true_alpha)}
        </span>
      </div>
      ${!s.is_viable ? `<div style="text-align:center;margin-top:4px;font-size:10px;color:#f87171;font-weight:600;background:rgba(220,38,38,0.1);padding:3px;border-radius:3px">⚠ NOT VIABLE IN THIS SCENARIO</div>` : ""}
    ` : "";

    const proFormaHtml = tsp ? `
      <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
        <div style="font-size:11px;font-weight:600;color:#d1d5db;margin-bottom:6px">
          Three-Scenario Pro Forma
          <span style="font-size:9px;font-weight:400;color:#6b7280;margin-left:6px">Graded on BASE case</span>
        </div>
        <div style="display:flex;gap:0;margin-bottom:8px;border-radius:4px;overflow:hidden;border:1px solid #374151">
          ${["bull","base","bear"].map((sc, i) => `
            <button onclick="['bull','base','bear'].forEach(function(s){document.getElementById('pf-'+s+'-${data.pid}').style.display=s==='${sc}'?'block':'none'});this.parentElement.querySelectorAll('button').forEach(function(b,j){b.style.background=j===${i}?'#1e293b':'transparent';b.style.color=j===${i}?'#f3f4f6':'#6b7280'})"
              style="flex:1;background:${sc === 'base' ? '#1e293b' : 'transparent'};border:none;color:${sc === 'base' ? '#f3f4f6' : '#6b7280'};font-size:10px;font-weight:700;padding:5px 0;cursor:pointer;text-transform:uppercase">
              ${sc === 'bull' ? '🐂 Bull' : sc === 'base' ? '📊 Base' : '🐻 Bear'}
            </button>
          `).join("")}
        </div>
        ${["bull","base","bear"].map(sc => `
          <div id="pf-${sc}-${data.pid}" style="display:${sc === 'base' ? 'block' : 'none'}">
            ${scenarioHtml((tsp as any)[sc])}
          </div>
        `).join("")}
      </div>
    ` : (pf ? `
      <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
        <div style="font-size:11px;font-weight:600;color:#d1d5db;margin-bottom:4px">Developer Pro Forma</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;font-size:10px">
          <span style="color:#6b7280">Construction</span><span style="color:#d1d5db;text-align:right">${pf.construction_type.replace(/_/g, " ")}</span>
          <span style="color:#6b7280">Gross Revenue</span><span style="color:#d1d5db;text-align:right">${fmt(pf.gross_revenue)}</span>
          <span style="color:#6b7280">Hard Costs</span><span style="color:#f87171;text-align:right">-${fmt(pf.hard_cost_total)}</span>
          <span style="color:#6b7280">Soft Costs</span><span style="color:#f87171;text-align:right">-${fmt(pf.soft_cost_total)}</span>
          <span style="color:#6b7280">CAC + DCL</span><span style="color:#f87171;text-align:right">-${fmt(pf.cac_dcl_total)}</span>
          <span style="color:#6b7280">Dev Profit</span><span style="color:#f87171;text-align:right">-${fmt(pf.developer_profit)}</span>
          ${pf.holding_cost ? `<span style="color:#6b7280">Holding (${pf.holding_months}mo)</span><span style="color:#f87171;text-align:right">-${fmt(pf.holding_cost)}</span>` : ""}
        </div>
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:6px;padding-top:6px;border-top:1px solid #374151">
          <span style="color:#9ca3af;font-weight:600">Residual Land Value</span>
          <span style="color:#fff;font-weight:700">${fmt(pf.residual_land_value)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-top:4px">
          <span style="color:#9ca3af;font-weight:600">True Alpha</span>
          <span style="color:${pf.true_alpha > 0 ? "#4ade80" : "#f87171"};font-weight:700">
            ${pf.true_alpha > 0 ? "+" : ""}${fmt(pf.true_alpha)}
          </span>
        </div>
      </div>` : "");

    // Build sources section
    let sourcesHtml = "";
    if (src?.sources?.length) {
      const rows = src.sources.map(s => {
        const link = s.url
          ? `<a href="${s.url}" target="_blank" rel="noopener" style="color:#60a5fa;text-decoration:none">${s.label} ↗</a>`
          : s.label;
        return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid #1f2937">
          <div style="flex:1;font-size:10px">
            <div style="color:#d1d5db">${link}</div>
            <div style="color:#6b7280;font-size:9px;margin-top:1px">${s.origin}</div>
          </div>
          <div>${badge(s.confidence)}</div>
        </div>`;
      }).join("");
      sourcesHtml = `
        <div id="sources-panel-${data.pid}" style="display:none;padding:10px;background:#0d1117;border-radius:0 0 6px 6px;max-height:280px;overflow-y:auto">
          <div style="font-size:10px;color:#9ca3af;margin-bottom:6px">
            <span style="color:#22c55e">■</span> GOV = Government source &nbsp;
            <span style="color:#3b82f6">■</span> CALC = Derived from verified data &nbsp;
            <span style="color:#f59e0b">■</span> EST = Market estimate
          </div>
          ${rows}
          <div style="font-size:9px;color:#4b5563;margin-top:8px;font-style:italic">${src.disclaimer || ""}</div>
        </div>`;
    }

    const html = `
      <div style="font-family:system-ui,sans-serif;max-width:420px">
        <div style="background:${color};color:#fff;padding:8px 12px;border-radius:6px 6px 0 0;font-weight:700;font-size:13px;display:flex;justify-content:space-between;align-items:center">
          <span>${SIGNAL_LABELS[data.signal] || data.signal.toUpperCase()}</span>
          <div style="display:flex;align-items:center;gap:6px">
            ${v ? `<span style="font-size:12px;color:rgba(255,255,255,0.9)">${"★".repeat(v.confidence_stars || 1)}${"☆".repeat(3 - (v.confidence_stars || 1))}</span>` : ""}
            ${v ? `<span style="background:${v.friction_level === 'high' ? '#dc2626' : v.friction_level === 'medium' ? '#f59e0b' : '#22c55e'};color:#fff;font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px">${(v.friction_level || 'low').toUpperCase()} FRICTION</span>` : ""}
            ${v && v.execution_difficulty_score > 0 ? `<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:${v.execution_difficulty_score >= 7 ? '#dc2626' : v.execution_difficulty_score >= 4 ? '#f59e0b' : '#22c55e'};color:#fff;font-size:10px;font-weight:800;border:2px solid rgba(255,255,255,0.3)" title="Execution Difficulty: ${v.execution_difficulty_score}/10">${v.execution_difficulty_score}</span>` : ""}
            ${v ? `<span style="background:${gradeColor};color:#000;font-size:14px;font-weight:800;padding:2px 8px;border-radius:4px;letter-spacing:1px">Grade ${v.deal_grade}</span>` : ""}
          </div>
        </div>
        ${v ? `<div style="padding:6px 12px;background:#0f172a;border-bottom:1px solid #1e293b">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <div style="display:flex;gap:8px;align-items:center">
              <span style="font-size:10px;color:#9ca3af">Economics:</span>
              <span style="font-size:12px;font-weight:700;color:${gradeColor}">${v.deal_grade}</span>
              <span style="font-size:9px;color:#6b7280">(${v.deal_score}/100)</span>
              <span style="color:#374151">|</span>
              <span style="font-size:10px;color:#9ca3af">Friction:</span>
              <span style="font-size:10px;font-weight:600;color:${v.friction_level === 'high' ? '#f87171' : v.friction_level === 'medium' ? '#fbbf24' : '#86efac'}">${(v.friction_level || 'low').charAt(0).toUpperCase() + (v.friction_level || 'low').slice(1)}</span>
              <span style="color:#374151">|</span>
              <span style="font-size:10px;color:#9ca3af">Confidence:</span>
              <span style="font-size:11px;color:#fbbf24">${"★".repeat(v.confidence_stars || 1)}${"☆".repeat(3 - (v.confidence_stars || 1))}</span>
            </div>
          </div>
          <div style="font-size:11px;color:#d1d5db">
            ${v.one_liner}
            <span style="float:right;font-size:10px;color:#6b7280">${v.neighborhood ? v.neighborhood : ''}</span>
          </div>
        </div>` : ""}
        <div style="padding:12px;background:#111827;color:#f3f4f6;max-height:500px;overflow-y:auto">
          <div style="font-size:13px;font-weight:600;margin-bottom:2px">${data.civic_address || data.pid} ${srcRow("civic_address")}</div>
          <div style="font-size:11px;color:#6b7280;margin-bottom:8px">PID: ${data.pid} ${srcRow("pid")} &nbsp;|&nbsp; Zone: ${data.current_zoning || "?"} ${srcRow("current_zoning")}</div>
          ${be ? (be.zoning_already_exceeds ? `
            <div style="font-size:14px;font-weight:700;color:#60a5fa;margin-bottom:4px">
              Current zoning already allows ${be.current_storeys} storeys / FSR ${be.current_fsr}
            </div>
            <div style="font-size:12px;color:#d1d5db;margin-bottom:6px">
              Bill 47 Tier ${be.tier} only provides ${be.bill47_storeys} storeys / FSR ${be.bill47_fsr} ${srcRow("entitlement")}
            </div>
            <div style="font-size:12px;color:#9ca3af;margin-bottom:4px">
              ${parseFloat(String(be.distance_m)).toFixed(0)}m from ${be.station_name} ${srcRow("station")}
            </div>
          ` : `
            <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:4px">
              Approved for ${be.entitled_storeys} Stories ${srcRow("entitlement")}
            </div>
            <div style="font-size:12px;color:#d1d5db;margin-bottom:6px">
              Tier ${be.tier} · ${parseFloat(String(be.distance_m)).toFixed(0)}m from ${be.station_name} · FSR ${be.entitled_fsr} ${srcRow("station")}
            </div>
            <div style="font-size:12px;color:#86efac">+${be.storey_uplift} storeys · +${be.fsr_uplift} FSR uplift</div>
          `) : '<div style="color:#9ca3af">Outside all Transit-Oriented Areas</div>'}

          ${ve ? `
            <div style="border-top:1px solid #374151;margin-top:10px;padding-top:8px">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;font-size:11px">
                <span style="color:#6b7280">Lot Area ${srcRow("lot_area_sqm")}</span><span style="color:#d1d5db;text-align:right">${ve.lot_area_sqm} sqm</span>
                <span style="color:#6b7280">Assessed ${srcRow("assessed_value")}</span><span style="color:#d1d5db;text-align:right">${ve.current_assessed ? fmt(ve.current_assessed) : "N/A"}</span>
                <span style="color:#6b7280">Asking ${srcRow("asking_price")}</span><span style="color:#d1d5db;text-align:right">${ve.asking_price ? fmt(ve.asking_price) : "Unlisted"}</span>
                ${v?.price_per_buildable_sqft ? `<span style="color:#6b7280">$/Buildable sqft</span><span style="color:#f59e0b;text-align:right;font-weight:600">$${parseFloat(v.price_per_buildable_sqft).toFixed(0)}</span>` : ""}
                ${v?.assessed_ratio ? `<span style="color:#6b7280">Ask/Assessed Ratio</span><span style="color:${parseFloat(v.assessed_ratio) > 1.3 ? '#f87171' : parseFloat(v.assessed_ratio) < 1 ? '#86efac' : '#d1d5db'};text-align:right">${parseFloat(v.assessed_ratio).toFixed(2)}x</span>` : ""}
                ${v?.land_to_total_ratio ? `<span style="color:#6b7280">Land/Total Ratio</span><span style="color:${parseFloat(v.land_to_total_ratio) > 0.75 ? '#86efac' : '#d1d5db'};text-align:right">${(parseFloat(v.land_to_total_ratio)*100).toFixed(0)}%</span>` : ""}
              </div>
            </div>
          ` : ""}

          ${proFormaHtml}

          ${tsp?.hidden_costs?.length ? `
            <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
              <div style="font-size:11px;font-weight:600;color:#f59e0b;margin-bottom:4px;cursor:pointer"
                onclick="var hc=document.getElementById('hc-panel-${data.pid}');hc.style.display=hc.style.display==='none'?'block':'none';this.querySelector('span').textContent=hc.style.display==='none'?'▶':'▼'">
                <span>▶</span> Hidden Costs: ${fmt(tsp.hidden_costs_total)} (${tsp.hidden_costs.length} items)
              </div>
              <div id="hc-panel-${data.pid}" style="display:none">
                ${tsp.hidden_costs.map((hc: any) => `
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:4px 0;border-bottom:1px solid #1f2937">
                    <div style="flex:1">
                      <div style="font-size:10px;font-weight:600;color:#f59e0b">${hc.category}</div>
                      <div style="font-size:9px;color:#9ca3af;margin-top:1px">${hc.explanation}</div>
                    </div>
                    <span style="font-size:11px;color:#f59e0b;font-weight:700;flex-shrink:0;margin-left:8px">${fmt(hc.cost)}</span>
                  </div>
                `).join("")}
              </div>
            </div>
          ` : ""}

          ${v?.gap_analysis ? `
            <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
              <div style="font-size:11px;font-weight:600;color:#60a5fa;margin-bottom:4px">Why The Gap Exists</div>
              <div style="font-size:10px;color:#d1d5db;line-height:1.5;background:rgba(96,165,250,0.08);padding:8px;border-radius:4px;border:1px solid rgba(96,165,250,0.15)">
                ${v.gap_analysis}
              </div>
            </div>
          ` : ""}

          ${v?.execution_difficulty_factors?.length ? `
            <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
              <div style="font-size:11px;font-weight:600;color:#d1d5db;margin-bottom:4px">
                Execution Difficulty: <span style="color:${v.execution_difficulty_score >= 7 ? '#f87171' : v.execution_difficulty_score >= 4 ? '#fbbf24' : '#86efac'}">${v.execution_difficulty_score}/10</span>
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:4px">
                ${v.execution_difficulty_factors.map((f: string) => `<span style="font-size:9px;background:#1e293b;color:#9ca3af;padding:2px 6px;border-radius:3px;border:1px solid #374151">${f}</span>`).join("")}
              </div>
            </div>
          ` : ""}

          ${v?.risk_flags?.length ? `
            <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
              <div style="font-size:11px;font-weight:600;color:#d1d5db;margin-bottom:4px">
                Risk Assessment
                <span style="float:right;font-size:10px;font-weight:400;color:#6b7280">
                  ${v.red_flag_count ? `<span style="color:#f87171">${v.red_flag_count} red</span> ` : ""}${v.yellow_flag_count ? `<span style="color:#fbbf24">${v.yellow_flag_count} yellow</span> ` : ""}${v.green_flag_count ? `<span style="color:#86efac">${v.green_flag_count} green</span>` : ""}
                </span>
              </div>
              ${flagsHtml}
              ${v.competing_parcels ? `<div style="font-size:10px;color:#6b7280;margin-top:6px">Supply: ${v.competing_parcels} competing parcels in area (${v.supply_saturation} saturation)</div>` : ""}
            </div>
          ` : ""}

          ${v?.due_diligence_checklist?.length ? `
            <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
              <div style="font-size:11px;font-weight:600;color:#d1d5db;margin-bottom:4px;cursor:pointer"
                onclick="var dd=document.getElementById('dd-panel-${data.pid}');dd.style.display=dd.style.display==='none'?'block':'none';this.querySelector('span').textContent=dd.style.display==='none'?'▶':'▼'">
                <span>▶</span> Due Diligence Checklist (${v.due_diligence_checklist.length} items)
              </div>
              <div id="dd-panel-${data.pid}" style="display:none">
                ${v.due_diligence_checklist.map((dd: any) => `
                  <div style="display:flex;align-items:flex-start;gap:6px;padding:3px 0;border-bottom:1px solid #1f2937">
                    <span style="font-size:10px;flex-shrink:0;margin-top:1px">${dd.priority === 'critical' ? '🔴' : dd.priority === 'high' ? '🟡' : '🔵'}</span>
                    <div style="flex:1">
                      <div style="font-size:10px;font-weight:600;color:#d1d5db">${dd.item}</div>
                      <div style="font-size:9px;color:#9ca3af">${dd.description}</div>
                    </div>
                    ${dd.url ? `<a href="${dd.url}" target="_blank" rel="noopener" style="color:#60a5fa;font-size:9px;flex-shrink:0">check↗</a>` : ""}
                  </div>
                `).join("")}
              </div>
            </div>
          ` : ""}

          ${nearbySignals?.length ? `
            <div style="border-top:1px solid #374151;margin-top:8px;padding-top:8px">
              <div style="font-size:11px;font-weight:600;color:#60a5fa;margin-bottom:6px">
                🧠 ${nearbySignals.length} Intelligence Signal${nearbySignals.length > 1 ? 's' : ''} Nearby
              </div>
              ${nearbySignals.slice(0, 5).map(sig => `
                <div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid #1f2937">
                  <div style="flex-shrink:0;width:8px;height:8px;border-radius:50%;margin-top:4px;background:${SEVERITY_COLORS[sig.severity] || '#6b7280'}"></div>
                  <div style="flex:1;min-width:0">
                    <div style="font-size:10px;font-weight:600;color:#d1d5db;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                      ${SIGNAL_TYPE_ICONS[sig.signal_type] || '📌'} ${sig.headline || sig.summary.substring(0, 60)}
                    </div>
                    <div style="font-size:9px;color:#6b7280;margin-top:2px;display:flex;gap:6px">
                      <span style="background:${SEVERITY_COLORS[sig.severity] || '#6b7280'};color:#fff;padding:0 4px;border-radius:2px;font-weight:600">${sig.severity}</span>
                      ${sig.decision ? `<span>${sig.decision}</span>` : ''}
                      ${sig.event_date ? `<span>${sig.event_date}</span>` : ''}
                    </div>
                  </div>
                  ${sig.id ? `<a href="${API_BASE}/api/v1/intel/documents/${sig.id}/page" target="_blank" rel="noopener" style="color:#60a5fa;font-size:9px;flex-shrink:0">source↗</a>` : ''}
                </div>
              `).join('')}
              ${nearbySignals.length > 5 ? `<div style="font-size:9px;color:#6b7280;margin-top:4px;text-align:center">+ ${nearbySignals.length - 5} more signals</div>` : ''}
            </div>
          ` : ''}

          <div style="margin-top:10px;display:flex;gap:6px">
            <button onclick="var p=document.getElementById('sources-panel-${data.pid}');if(p.style.display==='none'){p.style.display='block';this.textContent='▲ Hide Sources'}else{p.style.display='none';this.textContent='▼ Sources (${src?.sources?.length || 0})'}"
              style="background:none;border:1px solid #374151;color:#9ca3af;font-size:10px;padding:4px 10px;border-radius:4px;cursor:pointer;flex:1">
              ▼ Sources (${src?.sources?.length || 0})
            </button>
          </div>
        </div>
        ${sourcesHtml}
      </div>`;
    popupRef.current = new mapboxgl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "440px" })
      .setLngLat(lngLat).setHTML(html).addTo(map.current!);
  }, []);

  const handleMapClick = useCallback(async (e: mapboxgl.MapMouseEvent) => {
    setLoading(true);
    try {
      const nearest = await fetchNearestParcel(e.lngLat.lng, e.lngLat.lat, 150);
      if (!nearest) { setLoading(false); return; }
      const [data, signals] = await Promise.all([
        fetchEntitlement(nearest.pid),
        getSignalsForParcel(nearest.pid, 500).catch(() => [] as IntelSignal[]),
      ]);
      openDetailPanel(data, signals);
      // Add pulsing selection marker at click location
      if (selectionMarkerRef.current) selectionMarkerRef.current.remove();
      const selEl = document.createElement("div");
      selEl.style.cssText = "width:24px;height:24px;border-radius:50%;border:3px solid #3b82f6;background:rgba(59,130,246,0.15);box-shadow:0 0 12px rgba(59,130,246,0.4);pointer-events:none";
      selectionMarkerRef.current = new mapboxgl.Marker({ element: selEl }).setLngLat(e.lngLat).addTo(map.current!);
    } catch (err) {
      console.error("Click lookup failed:", err);
    } finally {
      setLoading(false);
    }
  }, [openDetailPanel]);

  const handleCaseStudySelect = useCallback(async (pid: string, lng: number, lat: number) => {
    setShowCaseStudies(false);
    if (map.current) {
      map.current.flyTo({ center: [lng, lat], zoom: 16, duration: 1500 });
    }
    setLoading(true);
    try {
      const [data, signals] = await Promise.all([
        fetchEntitlement(pid),
        getSignalsForParcel(pid, 500).catch(() => [] as IntelSignal[]),
      ]);
      openDetailPanel(data, signals);
    } catch (err) {
      console.error("Case study lookup failed:", err);
    } finally {
      setLoading(false);
    }
  }, [openDetailPanel]);

  useEffect(() => {
    if (map.current || !mapContainer.current) return;
    const token = typeof window !== "undefined" ? (window as any).__ENV__?.MAPBOX_TOKEN : undefined;
    if (!token) {
      setMapError("Mapbox token not configured");
      return;
    }

    if (!isWebGLAvailable()) {
      setMapError("WebGL is not available in this browser");
      return;
    }

    let m: mapboxgl.Map;
    try {
      mapboxgl.accessToken = token;
      m = new mapboxgl.Map({
        container: mapContainer.current,
        style: mapStyle,
        center: [-123.1148, 49.2632],
        zoom: 13,
      });
      map.current = m;
    } catch (err) {
      console.error("Failed to initialize map:", err);
      setMapError("Map failed to initialize");
      return;
    }
    m.addControl(new mapboxgl.NavigationControl(), "top-right");

    m.on("load", async () => {
      // Load TOA buffer zones
      try {
        const geojson = await fetchTOAGeoJSON();
        m.addSource("toa-buffers", { type: "geojson", data: geojson });
        [3, 2, 1].forEach((tier) => {
          m.addLayer({
            id: `toa-fill-t${tier}`, type: "fill", source: "toa-buffers",
            filter: ["==", ["get", "tier"], tier],
            paint: { "fill-color": TIER_COLORS[tier], "fill-outline-color": TIER_BORDERS[tier] },
          });
          m.addLayer({
            id: `toa-border-t${tier}`, type: "line", source: "toa-buffers",
            filter: ["==", ["get", "tier"], tier],
            paint: { "line-color": TIER_BORDERS[tier], "line-width": 1, "line-dasharray": [2, 2] },
          });
        });
      } catch (err) { console.error("Failed to load TOA zones:", err); }

      // Load opportunity markers
      try {
        const opps = await fetchOpportunities(200);
        opps.forEach((opp: any) => {
          const el = document.createElement("div");
          const alreadyExceeds = opp.already_exceeds;
          const uplift = opp.storey_uplift || 0;
          const hasPrice = opp.asking_price != null && opp.asking_price > 0;
          const isHighAlpha = !alreadyExceeds && uplift >= 15;
          const isMod = !alreadyExceeds && uplift >= 8;
          const dotColor = hasPrice ? "#22c55e" : alreadyExceeds ? "#3b82f6" : isHighAlpha ? "#dc2626" : isMod ? "#ea580c" : "#ca8a04";
          const dotSize = hasPrice ? 15 : isHighAlpha ? 14 : isMod ? 12 : 10;
          el.style.cssText = `width:${dotSize}px;height:${dotSize}px;border-radius:50%;background:${dotColor};border:2px solid rgba(255,255,255,0.85);cursor:pointer;box-shadow:0 0 ${hasPrice ? 12 : isHighAlpha ? 10 : 6}px ${dotColor}50`;
          el.title = `${opp.civic_address || opp.pid} — ${hasPrice ? `$${(opp.asking_price/1e6).toFixed(1)}M · ` : ""}${alreadyExceeds ? "already zoned" : `+${uplift}st uplift`}`;
          const marker = new mapboxgl.Marker({ element: el }).setLngLat([opp.lng, opp.lat]).addTo(m);
          markersRef.current.push(marker);
          el.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            setLoading(true);
            try {
              const [data, signals] = await Promise.all([
                fetchEntitlement(opp.pid),
                getSignalsForParcel(opp.pid, 500).catch(() => [] as IntelSignal[]),
              ]);
              openDetailPanel(data, signals);
            } catch {} finally { setLoading(false); }
          });
        });
      } catch (err) { console.error("Failed to load opportunities:", err); }

      // Load intelligence signal markers
      try {
        const geojson = await getSignalsGeoJSON(200, 365);
        if (geojson.features.length > 0) {
          geojson.features.forEach((feature: any) => {
            const props = feature.properties;
            const coords = feature.geometry.coordinates;
            const sevColor = SEVERITY_COLORS[props.severity] || "#6b7280";
            const icon = SIGNAL_TYPE_ICONS[props.signal_type] || "📌";
            const dotSize = SEVERITY_SIZES[props.severity] || 8;

            const el = document.createElement("div");
            el.style.cssText = `width:${dotSize + 10}px;height:${dotSize + 10}px;border-radius:50%;background:${sevColor}30;border:2px solid ${sevColor};cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:${dotSize}px;line-height:1`;
            el.textContent = icon;
            el.title = `${props.headline} (${props.severity})`;
            el.dataset.signalMarker = "true";

            const popup = new mapboxgl.Popup({ offset: 15, closeButton: true, maxWidth: "300px" })
              .setHTML(`
                <div style="font-family:system-ui,sans-serif;padding:8px;background:#111827;color:#f3f4f6;border-radius:6px">
                  <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                    <span style="font-size:16px">${escapeHtml(icon)}</span>
                    <span style="font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;background:${sevColor};color:#fff;text-transform:uppercase">${escapeHtml(props.severity)}</span>
                    <span style="font-size:9px;color:#6b7280">${escapeHtml(props.signal_type.replace(/_/g, ' '))}</span>
                  </div>
                  <div style="font-size:12px;font-weight:600;margin-bottom:4px">${escapeHtml(props.headline)}</div>
                  <div style="font-size:10px;color:#9ca3af;margin-bottom:6px;line-height:1.4">${escapeHtml(props.summary.substring(0, 150))}${props.summary.length > 150 ? '...' : ''}</div>
                  <div style="display:flex;justify-content:space-between;font-size:9px;color:#6b7280">
                    <span>${escapeHtml(props.neighborhood || '')}</span>
                    <span>${escapeHtml(props.event_date || '')}</span>
                  </div>
                  ${props.decision ? `<div style="font-size:9px;margin-top:4px;color:${props.decision === 'approved' ? '#86efac' : props.decision === 'denied' ? '#f87171' : '#fbbf24'};font-weight:600">Decision: ${escapeHtml(props.decision)}</div>` : ''}
                  ${props.id ? `<a href="${API_BASE}/api/v1/intel/documents/${escapeHtml(String(props.id))}/page" target="_blank" rel="noopener" style="display:block;margin-top:6px;font-size:9px;color:#60a5fa;text-decoration:underline">View source ↗</a>` : ''}
                </div>
              `);

            const marker = new mapboxgl.Marker({ element: el })
              .setLngLat(coords)
              .setPopup(popup)
              .addTo(m);
            signalMarkersRef.current.push(marker);
          });
        }
      } catch (err) { console.error("Failed to load signal markers:", err); }

      // Load development cluster markers
      try {
        const res = await fetch(`${API_BASE}/api/v1/intel/clusters`);
        if (res.ok) {
          const data = await res.json();
          setClusters(data.clusters || []);
          (data.clusters || []).forEach((cluster: any) => {
            const el = document.createElement("div");
            el.style.cssText = `
              width: 32px; height: 32px; border-radius: 50%;
              background: rgba(168, 85, 247, 0.35);
              border: 2px solid rgba(168, 85, 247, 0.8);
              cursor: pointer; display: flex; align-items: center;
              justify-content: center; font-size: 12px; font-weight: 700;
              color: #e9d5ff; animation: cluster-pulse 2s ease-in-out infinite;
            `;
            el.textContent = String(cluster.member_count);
            el.title = `Cluster: ${cluster.member_count} apps near ${cluster.center_address}`;
            el.dataset.clusterMarker = "true";

            const popup = new mapboxgl.Popup({ offset: 20, closeButton: true, maxWidth: "280px" })
              .setHTML(`
                <div style="font-family:system-ui,sans-serif;padding:8px;background:#111827;color:#f3f4f6;border-radius:6px">
                  <div style="font-size:12px;font-weight:700;color:#c084fc;margin-bottom:4px">
                    Development Cluster
                  </div>
                  <div style="font-size:11px;color:#d1d5db;margin-bottom:4px">
                    ${escapeHtml(cluster.center_address)}
                  </div>
                  <div style="font-size:10px;color:#9ca3af;margin-bottom:2px">
                    ${cluster.member_count} applications within ${cluster.radius_m}m
                  </div>
                  ${cluster.total_proposed_units > 0 ? `<div style="font-size:10px;color:#86efac">Total proposed units: ${cluster.total_proposed_units}</div>` : ""}
                  ${cluster.neighborhoods?.length ? `<div style="font-size:9px;color:#6b7280;margin-top:4px">${cluster.neighborhoods.join(", ")}</div>` : ""}
                </div>
              `);

            const marker = new mapboxgl.Marker({ element: el })
              .setLngLat([cluster.center_lng, cluster.center_lat])
              .setPopup(popup)
              .addTo(m);
            clusterMarkersRef.current.push(marker);
          });
        }
      } catch (err) { console.error("Failed to load cluster markers:", err); }

      // Click anywhere in TOA zone
      m.on("click", handleMapClick);
    });

    return () => {
      markersRef.current.forEach(mk => mk.remove());
      markersRef.current = [];
      signalMarkersRef.current.forEach(mk => mk.remove());
      signalMarkersRef.current = [];
      clusterMarkersRef.current.forEach(mk => mk.remove());
      clusterMarkersRef.current = [];
      if (selectionMarkerRef.current) selectionMarkerRef.current.remove();
      selectionMarkerRef.current = null;
      m.remove();
      map.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleMapClick, openDetailPanel]);

  // Toggle signal markers visibility
  useEffect(() => {
    signalMarkersRef.current.forEach(mk => {
      const el = mk.getElement();
      if (el) el.style.display = showSignals ? "flex" : "none";
    });
  }, [showSignals]);

  // Toggle cluster markers visibility
  useEffect(() => {
    clusterMarkersRef.current.forEach(mk => {
      const el = mk.getElement();
      if (el) el.style.display = showClusters ? "flex" : "none";
    });
  }, [showClusters]);

  // Fetch risk scores when choropleth is enabled
  useEffect(() => {
    if (showRiskChoropleth && riskScores.length === 0) {
      fetchNeighborhoodRiskScores().then(setRiskScores);
    }
  }, [showRiskChoropleth, riskScores.length]);

  return (
    <div className="relative w-full h-full">
      <style>{`
        @keyframes cluster-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(168,85,247,0.5); }
          50% { box-shadow: 0 0 0 10px rgba(168,85,247,0); }
        }
      `}</style>
      <div ref={mapContainer} className="w-full h-full bg-[var(--color-surface)]" />

      {/* Fallback when map cannot initialize */}
      {mapError && (
        <div className="absolute inset-0 flex items-center justify-center bg-[var(--color-surface)] text-[var(--color-foreground-muted)] text-sm z-5">
          <div className="text-center">
            <div className="text-5xl mb-4">🗺️</div>
            <div className="text-[var(--color-foreground-muted)] mb-1">Map unavailable</div>
            <div className="text-xs">{mapError}</div>
          </div>
        </div>
      )}

      {/* Address Search — top-left overlay */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
        <div className="hidden md:block bg-[var(--color-panel)] backdrop-blur-md rounded-lg px-4 py-3 border border-[var(--color-panel-border)]">
          <div className="text-[var(--color-foreground)] font-bold text-lg">VanCity Lens</div>
          <div className="text-[var(--color-foreground-muted)] text-[11px] mt-0.5">Bill 47 Entitlement Engine · 92K parcels</div>
        </div>
        <div className="w-[280px] md:w-[320px]">
          <AddressSearchBar onSelect={handleAddressSelect} placeholder="Search address in Vancouver" />
        </div>
      </div>

      {/* Legend — hidden on mobile, shown on desktop */}
      <div className="hidden md:block absolute bottom-8 left-4 z-10 bg-[var(--color-panel)] backdrop-blur-md rounded-lg px-4 py-3 border border-[var(--color-panel-border)] text-[11px] text-[var(--color-foreground-muted)]">
        <div className="font-semibold mb-1.5 text-[var(--color-foreground)]">TOA Zones (Bill 47)</div>
        {[
          { tier:1, label:"0–200m: 20 storeys / 5.5 FSR", color:TIER_COLORS[1], border:TIER_BORDERS[1] },
          { tier:2, label:"200–400m: 12 storeys / 4.0 FSR", color:TIER_COLORS[2], border:TIER_BORDERS[2] },
          { tier:3, label:"400–800m: 8 storeys / 3.0 FSR", color:TIER_COLORS[3], border:TIER_BORDERS[3] },
        ].map(t => (
          <label key={t.tier} className="flex items-center mt-1 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={visibleTiers[t.tier]}
              onChange={() => toggleTier(t.tier)}
              className="sr-only peer"
            />
            <div
              className="w-3.5 h-3.5 rounded-sm mr-2 flex items-center justify-center transition-opacity peer-checked:opacity-100 opacity-30"
              style={{ background:t.color, border:`1px solid ${t.border}` }}
            >
              {visibleTiers[t.tier] && <span className="text-[8px] text-white/80">&#10003;</span>}
            </div>
            <span className={visibleTiers[t.tier] ? "" : "text-gray-600 line-through"}>Tier {t.tier}: {t.label}</span>
          </label>
        ))}
        <div className="flex items-center mt-1.5 border-t border-gray-700 pt-1.5">
          <div className="w-3 h-3 rounded-full bg-green-500 border-2 border-white/85 mr-2" />
          <span className="text-[10px]">Green = has asking price</span>
        </div>
        <div className="flex items-center mt-1.5 border-t border-gray-700 pt-1.5">
          <div className="w-3 h-3 rounded-full bg-transparent border-2 border-orange-500 mr-2 flex items-center justify-center text-[7px]">🏗️</div>
          <span className="text-[10px]">Intelligence signals (emoji markers)</span>
        </div>
        <div className="mt-1.5 text-[10px] text-gray-500">
          Click anywhere on map to analyze a parcel
        </div>
      </div>

      {/* Desktop: individual toggles */}
      <div className="hidden md:flex absolute top-[90px] right-4 z-10 flex-col gap-2">
        <button
          onClick={() => setShowSignals(!showSignals)}
          className={cn(
            "px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer",
            showSignals
              ? "bg-blue-600/20 border border-blue-500/30 text-blue-400"
              : "bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)]"
          )}
        >
          <span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1.5" />
          {showSignals ? "Hide" : "Show"} Signals
        </button>
        <button
          onClick={() => setShowClusters(!showClusters)}
          className={cn(
            "px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer",
            showClusters
              ? "bg-blue-600/20 border border-blue-500/30 text-blue-400"
              : "bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)]"
          )}
        >
          <span className="inline-block w-2 h-2 rounded-full bg-purple-500 mr-1.5" />
          {showClusters ? "Hide" : "Show"} Clusters{clusters.length > 0 ? ` (${clusters.length})` : ""}
        </button>
        <button
          onClick={() => setShowRiskChoropleth(prev => !prev)}
          className={cn(
            "px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer",
            showRiskChoropleth
              ? "bg-blue-600/20 border border-blue-500/30 text-blue-400"
              : "bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)]"
          )}
          title="Toggle neighborhood risk overlay"
        >
          <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1.5" />
          Risk Map
        </button>
        {!showCaseStudies && (
          <button
            onClick={() => setShowCaseStudies(true)}
            className="px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)] hover:text-[var(--color-foreground)]"
          >
            Examples
          </button>
        )}
      </div>

      {/* Mobile: Layers FAB */}
      <div className="md:hidden absolute bottom-20 right-4 z-10">
        <button
          onClick={() => setShowLayerMenu(!showLayerMenu)}
          className="w-12 h-12 rounded-full bg-[var(--color-panel)] border border-[var(--color-panel-border)] backdrop-blur-md flex items-center justify-center text-[var(--color-foreground-muted)] shadow-lg"
        >
          <Layers className="w-5 h-5" />
        </button>
        {showLayerMenu && (
          <div className="absolute bottom-14 right-0 bg-[var(--color-panel)] border border-[var(--color-panel-border)] backdrop-blur-md rounded-xl p-3 flex flex-col gap-2 min-w-[160px] shadow-xl">
            <button
              onClick={() => setShowSignals(!showSignals)}
              className={cn(
                "px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer",
                showSignals
                  ? "bg-blue-600/20 border border-blue-500/30 text-blue-400"
                  : "bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)]"
              )}
            >
              <span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1.5" />
              {showSignals ? "Hide" : "Show"} Signals
            </button>
            <button
              onClick={() => setShowClusters(!showClusters)}
              className={cn(
                "px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer",
                showClusters
                  ? "bg-blue-600/20 border border-blue-500/30 text-blue-400"
                  : "bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)]"
              )}
            >
              <span className="inline-block w-2 h-2 rounded-full bg-purple-500 mr-1.5" />
              {showClusters ? "Hide" : "Show"} Clusters{clusters.length > 0 ? ` (${clusters.length})` : ""}
            </button>
            <button
              onClick={() => setShowRiskChoropleth(prev => !prev)}
              className={cn(
                "px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer",
                showRiskChoropleth
                  ? "bg-blue-600/20 border border-blue-500/30 text-blue-400"
                  : "bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)]"
              )}
              title="Toggle neighborhood risk overlay"
            >
              <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1.5" />
              Risk Map
            </button>
            {!showCaseStudies && (
              <button
                onClick={() => setShowCaseStudies(true)}
                className="px-3 py-2 rounded-lg text-[11px] font-semibold backdrop-blur-md transition-all cursor-pointer bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-[var(--color-foreground-muted)] hover:text-[var(--color-foreground)]"
              >
                Examples
              </button>
            )}
          </div>
        )}
      </div>

      {/* Loading overlay */}
      {loading && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[var(--color-panel)] backdrop-blur-md rounded-lg px-6 py-4 text-[var(--color-foreground)] text-sm z-20 border border-[var(--color-panel-border)]">
          Analyzing parcel…
        </div>
      )}

      {/* Parcel Detail Panel */}
      {selectedParcel && (
        <ParcelDetailPanel
          data={selectedParcel}
          nearbySignals={selectedSignals}
          onClose={() => { setSelectedParcel(null); setSelectedSignals([]); if (selectionMarkerRef.current) { selectionMarkerRef.current.remove(); selectionMarkerRef.current = null; } }}
          onRunDealModel={(pid) => { setFinancingPid(pid); setShowFinancing(true); }}
        />
      )}

      {/* Case Study Carousel */}
      {showCaseStudies && !selectedParcel && (
        <CaseStudyCarousel
          onSelectParcel={handleCaseStudySelect}
          onDismiss={() => setShowCaseStudies(false)}
        />
      )}

      {/* Financing Calculator Modal */}
      {showFinancing && (
        <FinancingCalculator
          parcelData={selectedParcel ? {
            pid: financingPid,
            acquisition_cost: selectedParcel.value_estimate?.asking_price || selectedParcel.value_estimate?.current_assessed || undefined,
            buildable_sqft: selectedParcel.value_estimate ? parseFloat(String(selectedParcel.value_estimate.buildable_sqft)) : undefined,
            asking_price: selectedParcel.value_estimate?.asking_price || undefined,
            construction_type: selectedParcel.validation?.pro_forma?.construction_type,
            gross_revenue: selectedParcel.validation?.three_scenario_proforma?.base?.gross_revenue || selectedParcel.validation?.pro_forma?.gross_revenue || undefined,
          } : undefined}
          onClose={() => setShowFinancing(false)}
        />
      )}
    </div>
  );
}
