"use client";

import { useState } from "react";
import type { ThreeScenarioProForma, ScenarioProForma, DeveloperProForma } from "@/lib/types";

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

function ScenarioView({ scenario }: { scenario: ScenarioProForma }) {
  return (
    <div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "4px 12px",
          fontSize: "12px",
        }}
      >
        <span style={{ color: "#6b7280" }}>Construction</span>
        <span style={{ color: "#d1d5db", textAlign: "right" }}>
          {scenario.construction_type.replace(/_/g, " ")}
        </span>
        <span style={{ color: "#6b7280" }}>Sellable sqft</span>
        <span style={{ color: "#d1d5db", textAlign: "right" }}>{scenario.sellable_sqft}</span>
        <span style={{ color: "#6b7280" }}>Revenue/sqft</span>
        <span style={{ color: "#d1d5db", textAlign: "right" }}>{scenario.revenue_per_sqft}</span>
        {parseFloat(String(scenario.absorption_discount)) > 0 && (
          <>
            <span style={{ color: "#6b7280" }}>Absorption Disc</span>
            <span style={{ color: "#f87171", textAlign: "right" }}>
              -{(parseFloat(String(scenario.absorption_discount)) * 100).toFixed(0)}%
            </span>
          </>
        )}
        <span style={{ color: "#6b7280" }}>Net Revenue</span>
        <span style={{ color: "#d1d5db", textAlign: "right", fontWeight: 600 }}>
          {fmt(scenario.net_revenue)}
        </span>
        <span style={{ color: "#6b7280" }}>Hard Costs</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(scenario.hard_cost_total)}</span>
        <span style={{ color: "#6b7280" }}>Soft Costs</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(scenario.soft_cost_total)}</span>
        {scenario.contingency_total > 0 && (
          <>
            <span style={{ color: "#6b7280" }}>Contingency</span>
            <span style={{ color: "#f87171", textAlign: "right" }}>
              -{fmt(scenario.contingency_total)}
            </span>
          </>
        )}
        {scenario.marketing_total > 0 && (
          <>
            <span style={{ color: "#6b7280" }}>Marketing/Sales</span>
            <span style={{ color: "#f87171", textAlign: "right" }}>
              -{fmt(scenario.marketing_total)}
            </span>
          </>
        )}
        <span style={{ color: "#6b7280" }}>CAC + DCL</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(scenario.cac_dcl_total)}</span>
        {scenario.hidden_costs_total > 0 && (
          <>
            <span style={{ color: "#f59e0b", fontWeight: 600 }}>Hidden Costs</span>
            <span style={{ color: "#f59e0b", textAlign: "right", fontWeight: 600 }}>
              -{fmt(scenario.hidden_costs_total)}
            </span>
          </>
        )}
        <span style={{ color: "#6b7280" }}>Holding ({scenario.holding_months}mo)</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(scenario.holding_cost)}</span>
        <span style={{ color: "#6b7280" }}>Dev Profit</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(scenario.developer_profit)}</span>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "8px",
          paddingTop: "8px",
          borderTop: "1px solid #374151",
          fontSize: "13px",
        }}
      >
        <span style={{ color: "#9ca3af", fontWeight: 600 }}>Residual Land Value</span>
        <span style={{ color: "#f3f4f6", fontWeight: 700 }}>{fmt(scenario.residual_land_value)}</span>
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "4px",
          fontSize: "14px",
        }}
      >
        <span style={{ color: "#9ca3af", fontWeight: 600 }}>True Alpha</span>
        <span
          style={{
            color: scenario.true_alpha > 0 ? "#4ade80" : "#f87171",
            fontWeight: 700,
          }}
        >
          {scenario.true_alpha > 0 ? "+" : ""}
          {fmt(scenario.true_alpha)}
        </span>
      </div>
      {!scenario.is_viable && (
        <div
          style={{
            textAlign: "center",
            marginTop: "6px",
            fontSize: "11px",
            color: "#f87171",
            fontWeight: 600,
            background: "rgba(220,38,38,0.1)",
            padding: "4px",
            borderRadius: "4px",
          }}
        >
          NOT VIABLE IN THIS SCENARIO
        </div>
      )}
    </div>
  );
}

export default function ProFormaSection({
  threeScenario,
  singleProForma,
}: {
  threeScenario: ThreeScenarioProForma | null;
  singleProForma: DeveloperProForma | null;
}) {
  const [activeScenario, setActiveScenario] = useState<"bull" | "base" | "bear">("base");

  if (!threeScenario && !singleProForma) return null;

  if (threeScenario) {
    const tabLabels = {
      bull: "Bull",
      base: "Base",
      bear: "Bear",
    };

    return (
      <div>
        <div
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "#f3f4f6",
            marginBottom: "8px",
          }}
        >
          Three-Scenario Pro Forma
          <span style={{ fontSize: "10px", fontWeight: 400, color: "#6b7280", marginLeft: "8px" }}>
            Graded on BASE case
          </span>
        </div>

        <div
          style={{
            display: "flex",
            marginBottom: "12px",
            borderRadius: "6px",
            overflow: "hidden",
            border: "1px solid #374151",
          }}
        >
          {(["bull", "base", "bear"] as const).map((sc) => (
            <button
              key={sc}
              onClick={() => setActiveScenario(sc)}
              style={{
                flex: 1,
                background: activeScenario === sc ? "#1e293b" : "transparent",
                border: "none",
                color: activeScenario === sc ? "#f3f4f6" : "#6b7280",
                fontSize: "11px",
                fontWeight: 700,
                padding: "6px 0",
                cursor: "pointer",
                textTransform: "uppercase",
              }}
            >
              {sc === "bull" ? "Bull" : sc === "base" ? "Base" : "Bear"}
            </button>
          ))}
        </div>

        <ScenarioView scenario={threeScenario[activeScenario]} />
      </div>
    );
  }

  // Single pro forma fallback
  const pf = singleProForma!;
  return (
    <div>
      <div style={{ fontSize: "13px", fontWeight: 600, color: "#f3f4f6", marginBottom: "8px" }}>
        Developer Pro Forma
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "4px 12px",
          fontSize: "12px",
        }}
      >
        <span style={{ color: "#6b7280" }}>Construction</span>
        <span style={{ color: "#d1d5db", textAlign: "right" }}>
          {pf.construction_type.replace(/_/g, " ")}
        </span>
        <span style={{ color: "#6b7280" }}>Gross Revenue</span>
        <span style={{ color: "#d1d5db", textAlign: "right" }}>{fmt(pf.gross_revenue)}</span>
        <span style={{ color: "#6b7280" }}>Hard Costs</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(pf.hard_cost_total)}</span>
        <span style={{ color: "#6b7280" }}>Soft Costs</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(pf.soft_cost_total)}</span>
        <span style={{ color: "#6b7280" }}>CAC + DCL</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(pf.cac_dcl_total)}</span>
        <span style={{ color: "#6b7280" }}>Dev Profit</span>
        <span style={{ color: "#f87171", textAlign: "right" }}>-{fmt(pf.developer_profit)}</span>
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "8px",
          paddingTop: "8px",
          borderTop: "1px solid #374151",
          fontSize: "13px",
        }}
      >
        <span style={{ color: "#9ca3af", fontWeight: 600 }}>Residual Land Value</span>
        <span style={{ color: "#f3f4f6", fontWeight: 700 }}>{fmt(pf.residual_land_value)}</span>
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: "4px",
          fontSize: "14px",
        }}
      >
        <span style={{ color: "#9ca3af", fontWeight: 600 }}>True Alpha</span>
        <span
          style={{
            color: pf.true_alpha > 0 ? "#4ade80" : "#f87171",
            fontWeight: 700,
          }}
        >
          {pf.true_alpha > 0 ? "+" : ""}
          {fmt(pf.true_alpha)}
        </span>
      </div>
    </div>
  );
}
