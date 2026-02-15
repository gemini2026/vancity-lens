"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ThreeScenarioProForma, ScenarioProForma, DeveloperProForma } from "@/lib/types";

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

function ScenarioView({ scenario }: { scenario: ScenarioProForma }) {
  return (
    <div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <span className="text-gray-500">Construction</span>
        <span className="text-gray-300 text-right">
          {scenario.construction_type.replace(/_/g, " ")}
        </span>
        <span className="text-gray-500">Sellable sqft</span>
        <span className="text-gray-300 text-right">{scenario.sellable_sqft}</span>
        <span className="text-gray-500">Revenue/sqft</span>
        <span className="text-gray-300 text-right">{scenario.revenue_per_sqft}</span>
        {parseFloat(String(scenario.absorption_discount)) > 0 && (
          <>
            <span className="text-gray-500">Absorption Disc</span>
            <span className="text-red-400 text-right">
              -{(parseFloat(String(scenario.absorption_discount)) * 100).toFixed(0)}%
            </span>
          </>
        )}
        <span className="text-gray-500">Net Revenue</span>
        <span className="text-gray-300 text-right font-semibold">
          {fmt(scenario.net_revenue)}
        </span>
        <span className="text-gray-500">Hard Costs</span>
        <span className="text-red-400 text-right">-{fmt(scenario.hard_cost_total)}</span>
        <span className="text-gray-500">Soft Costs</span>
        <span className="text-red-400 text-right">-{fmt(scenario.soft_cost_total)}</span>
        {scenario.contingency_total > 0 && (
          <>
            <span className="text-gray-500">Contingency</span>
            <span className="text-red-400 text-right">
              -{fmt(scenario.contingency_total)}
            </span>
          </>
        )}
        {scenario.marketing_total > 0 && (
          <>
            <span className="text-gray-500">Marketing/Sales</span>
            <span className="text-red-400 text-right">
              -{fmt(scenario.marketing_total)}
            </span>
          </>
        )}
        <span className="text-gray-500">CAC + DCL</span>
        <span className="text-red-400 text-right">-{fmt(scenario.cac_dcl_total)}</span>
        {scenario.hidden_costs_total > 0 && (
          <>
            <span className="text-amber-400 font-semibold">Hidden Costs</span>
            <span className="text-amber-400 text-right font-semibold">
              -{fmt(scenario.hidden_costs_total)}
            </span>
          </>
        )}
        <span className="text-gray-500">Holding ({scenario.holding_months}mo)</span>
        <span className="text-red-400 text-right">-{fmt(scenario.holding_cost)}</span>
        <span className="text-gray-500">Dev Profit</span>
        <span className="text-red-400 text-right">-{fmt(scenario.developer_profit)}</span>
      </div>

      <div className="flex justify-between mt-2 pt-2 border-t border-gray-700 text-[13px]">
        <span className="text-gray-400 font-semibold">Residual Land Value</span>
        <span className="text-gray-100 font-bold">{fmt(scenario.residual_land_value)}</span>
      </div>
      <div className="flex justify-between mt-1 text-sm">
        <span className="text-gray-400 font-semibold">True Alpha</span>
        <span
          className={cn(
            "font-bold",
            scenario.true_alpha > 0 ? "text-green-400" : "text-red-400"
          )}
        >
          {scenario.true_alpha > 0 ? "+" : ""}
          {fmt(scenario.true_alpha)}
        </span>
      </div>
      {!scenario.is_viable && (
        <div className="text-center mt-1.5 text-[11px] text-red-400 font-semibold bg-red-600/10 p-1 rounded">
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
    return (
      <div>
        <div className="text-[13px] font-semibold text-gray-100 mb-2">
          Three-Scenario Pro Forma
          <span className="text-[10px] font-normal text-gray-500 ml-2">
            Graded on BASE case
          </span>
        </div>

        <div className="flex mb-3 rounded-md overflow-hidden border border-gray-700">
          {(["bull", "base", "bear"] as const).map((sc) => (
            <button
              key={sc}
              onClick={() => setActiveScenario(sc)}
              className={cn(
                "flex-1 border-none text-[11px] font-bold py-1.5 cursor-pointer uppercase",
                activeScenario === sc
                  ? "bg-slate-800 text-gray-100"
                  : "bg-transparent text-gray-500"
              )}
            >
              {sc === "bull" ? "Bull" : sc === "base" ? "Base" : "Bear"}
            </button>
          ))}
        </div>

        <ScenarioView scenario={threeScenario[activeScenario]} />
      </div>
    );
  }

  const pf = singleProForma!;
  return (
    <div>
      <div className="text-[13px] font-semibold text-gray-100 mb-2">
        Developer Pro Forma
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <span className="text-gray-500">Construction</span>
        <span className="text-gray-300 text-right">
          {pf.construction_type.replace(/_/g, " ")}
        </span>
        <span className="text-gray-500">Gross Revenue</span>
        <span className="text-gray-300 text-right">{fmt(pf.gross_revenue)}</span>
        <span className="text-gray-500">Hard Costs</span>
        <span className="text-red-400 text-right">-{fmt(pf.hard_cost_total)}</span>
        <span className="text-gray-500">Soft Costs</span>
        <span className="text-red-400 text-right">-{fmt(pf.soft_cost_total)}</span>
        <span className="text-gray-500">CAC + DCL</span>
        <span className="text-red-400 text-right">-{fmt(pf.cac_dcl_total)}</span>
        <span className="text-gray-500">Dev Profit</span>
        <span className="text-red-400 text-right">-{fmt(pf.developer_profit)}</span>
      </div>
      <div className="flex justify-between mt-2 pt-2 border-t border-gray-700 text-[13px]">
        <span className="text-gray-400 font-semibold">Residual Land Value</span>
        <span className="text-gray-100 font-bold">{fmt(pf.residual_land_value)}</span>
      </div>
      <div className="flex justify-between mt-1 text-sm">
        <span className="text-gray-400 font-semibold">True Alpha</span>
        <span
          className={cn(
            "font-bold",
            pf.true_alpha > 0 ? "text-green-400" : "text-red-400"
          )}
        >
          {pf.true_alpha > 0 ? "+" : ""}
          {fmt(pf.true_alpha)}
        </span>
      </div>
    </div>
  );
}
