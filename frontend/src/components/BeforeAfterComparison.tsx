"use client";

import type { StationEntitlement, ValueEstimate } from "@/lib/types";

interface BeforeAfterComparisonProps {
  entitlement: StationEntitlement;
  valueEstimate: ValueEstimate | null;
  currentZoning: string | null;
}

function fmtNum(n: number, decimals = 1): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

export default function BeforeAfterComparison({
  entitlement,
  valueEstimate,
  currentZoning,
}: BeforeAfterComparisonProps) {
  const be = entitlement;

  if (be.zoning_already_exceeds) {
    return (
      <div className="mb-3 px-3 py-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20">
        <div className="text-[11px] font-semibold text-blue-400">
          Current zoning already exceeds Bill 47
        </div>
        <div className="text-[10px] text-gray-400 mt-1">
          Existing {currentZoning || "zoning"} allows {be.current_storeys} storeys / FSR{" "}
          {be.current_fsr}, which exceeds Tier {be.tier} entitlement of{" "}
          {be.bill47_storeys} storeys / FSR {be.bill47_fsr}.
        </div>
      </div>
    );
  }

  const lotAreaSqft = valueEstimate
    ? parseFloat(valueEstimate.lot_area_sqm) * 10.764
    : null;
  const currentFsr = be.current_fsr ? parseFloat(be.current_fsr) : 0;
  const beforeBuildable = lotAreaSqft ? lotAreaSqft * currentFsr : null;
  const afterBuildable = valueEstimate
    ? parseFloat(valueEstimate.buildable_sqft)
    : null;
  const buildableDelta =
    beforeBuildable != null && afterBuildable != null
      ? afterBuildable - beforeBuildable
      : null;

  const rows: {
    label: string;
    before: string;
    after: string;
    uplift: string;
    positive: boolean;
  }[] = [
    {
      label: "Zoning",
      before: currentZoning || "N/A",
      after: `TOD Tier ${be.tier}`,
      uplift: "-",
      positive: false,
    },
    {
      label: "Max Height",
      before: `${be.current_storeys ?? "?"} storeys`,
      after: `${be.entitled_storeys} storeys`,
      uplift: `+${be.storey_uplift} st`,
      positive: be.storey_uplift > 0,
    },
    {
      label: "Max FSR",
      before: be.current_fsr ?? "N/A",
      after: be.entitled_fsr,
      uplift: `+${be.fsr_uplift}`,
      positive: parseFloat(be.fsr_uplift) > 0,
    },
    {
      label: "Buildable SF",
      before: beforeBuildable != null ? fmtNum(Math.round(beforeBuildable), 0) : "N/A",
      after: afterBuildable != null ? fmtNum(Math.round(afterBuildable), 0) : "N/A",
      uplift:
        buildableDelta != null
          ? `+${fmtNum(Math.round(buildableDelta), 0)}`
          : "-",
      positive: buildableDelta != null && buildableDelta > 0,
    },
  ];

  return (
    <div className="mb-1">
      <table className="w-full text-[11px] border-collapse">
        <thead>
          <tr className="text-gray-500 text-[10px]">
            <th className="text-left py-1 pr-2 font-semibold">Field</th>
            <th className="text-left py-1 px-2 font-semibold">Before Bill 47</th>
            <th className="text-left py-1 px-2 font-semibold">After Bill 47</th>
            <th className="text-right py-1 pl-2 font-semibold">Uplift</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-white/[0.06]">
              <td className="py-1.5 pr-2 text-gray-400 font-medium">{row.label}</td>
              <td className="py-1.5 px-2 text-gray-300">{row.before}</td>
              <td className="py-1.5 px-2 text-white font-semibold">{row.after}</td>
              <td
                className={`py-1.5 pl-2 text-right font-semibold ${
                  row.positive
                    ? "text-green-400"
                    : row.uplift === "-"
                    ? "text-gray-600"
                    : "text-gray-400"
                }`}
              >
                {row.positive && (
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400/30 mr-1" />
                )}
                {row.uplift}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
