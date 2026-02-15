"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import {
  calculateFinancing,
  type FinancingRequest,
  type FinancingResult,
  type ScenarioResult,
} from "@/lib/financing-api";

interface ParcelData {
  pid: string;
  acquisition_cost?: number;
  buildable_sqft?: number;
  asking_price?: number;
  construction_type?: string;
  gross_revenue?: number;
}

interface FinancingCalculatorProps {
  parcelData?: ParcelData;
  onClose: () => void;
}

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

function pct(n: number): string {
  return `${(n * 100).toFixed(2)}%`;
}

const inputClasses =
  "w-full px-2.5 py-2 bg-slate-800 border border-gray-700 rounded text-gray-100 text-[13px]";

const labelClasses = "block text-[11px] text-gray-400 mb-1 font-semibold";

const sectionHeadingClasses =
  "text-xs font-bold text-gray-400 uppercase tracking-wide mb-2";

const gridClasses = "grid grid-cols-2 gap-x-3 gap-y-1 text-xs";

export default function FinancingCalculator({
  parcelData,
  onClose,
}: FinancingCalculatorProps) {
  const [acquisitionCost, setAcquisitionCost] = useState(
    parcelData?.asking_price || parcelData?.acquisition_cost || 0
  );
  const [equityPct, setEquityPct] = useState(25);
  const [interestRate, setInterestRate] = useState(6.5);
  const [holdPeriodMonths, setHoldPeriodMonths] = useState(24);
  const [constructionCost, setConstructionCost] = useState(0);
  const [grossRevenue, setGrossRevenue] = useState(
    parcelData?.gross_revenue || 0
  );
  const [softCostPct, setSoftCostPct] = useState(18);
  const [sellableSqft, setSellableSqft] = useState(
    parcelData?.buildable_sqft || 0
  );

  const [result, setResult] = useState<FinancingResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeScenario, setActiveScenario] = useState<string>("base");

  useEffect(() => {
    if (parcelData) {
      if (parcelData.asking_price)
        setAcquisitionCost(parcelData.asking_price);
      else if (parcelData.acquisition_cost)
        setAcquisitionCost(parcelData.acquisition_cost);
      if (parcelData.buildable_sqft)
        setSellableSqft(parcelData.buildable_sqft);
      if (parcelData.gross_revenue)
        setGrossRevenue(parcelData.gross_revenue);
    }
  }, [parcelData]);

  const handleSubmit = async () => {
    if (acquisitionCost <= 0) {
      setError("Acquisition cost must be greater than 0");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const request: FinancingRequest = {
        acquisition_cost: acquisitionCost,
        equity_pct: equityPct / 100,
        interest_rate: interestRate / 100,
        hold_period_months: holdPeriodMonths,
        construction_cost: constructionCost,
        gross_revenue: grossRevenue,
        soft_cost_pct: softCostPct / 100,
        sellable_sqft: sellableSqft,
      };
      const res = await calculateFinancing(request);
      setResult(res);
      setActiveScenario("base");
    } catch (err: any) {
      setError(err.message || "Calculation failed");
    } finally {
      setLoading(false);
    }
  };

  function renderScenario(scenario: ScenarioResult): React.ReactNode {
    return (
      <div className={gridClasses}>
        <span className="text-gray-400">Gross Revenue</span>
        <span className="text-gray-300 text-right">
          {fmt(scenario.gross_revenue)}
        </span>
        <span className="text-gray-400">Total Project Cost</span>
        <span className="text-gray-300 text-right">
          {fmt(scenario.total_project_cost)}
        </span>
        <span className="text-gray-400">Net Profit</span>
        <span
          className={cn(
            "text-right font-semibold",
            scenario.net_profit >= 0 ? "text-green-400" : "text-red-400"
          )}
        >
          {scenario.net_profit >= 0 ? "+" : ""}
          {fmt(scenario.net_profit)}
        </span>
        <span className="text-gray-400">ROI</span>
        <span className="text-gray-300 text-right">
          {pct(scenario.roi)}
        </span>
        <span className="text-gray-400">ROE</span>
        <span className="text-gray-300 text-right">
          {pct(scenario.roe)}
        </span>
        <div
          className={cn(
            "col-span-2 mt-1.5 p-1.5 rounded text-center text-[11px] font-bold border",
            scenario.is_viable
              ? "bg-green-500/10 text-green-400 border-green-500/20"
              : "bg-red-600/10 text-red-400 border-red-600/20"
          )}
        >
          {scenario.is_viable ? "VIABLE" : "NOT VIABLE"}
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-[600px] max-h-[90vh] overflow-y-auto bg-gray-900 rounded-xl border border-gray-800 text-gray-100">
        {/* Header */}
        <div className="flex justify-between items-center px-5 py-4 border-b border-gray-800 bg-slate-900 rounded-t-xl">
          <div>
            <div className="text-[15px] font-bold">
              Deal Model Calculator
            </div>
            {parcelData && (
              <div className="text-[11px] text-gray-500 mt-0.5">
                PID: {parcelData.pid}
                {parcelData.construction_type &&
                  ` | ${parcelData.construction_type.replace(/_/g, " ")}`}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="bg-none border-none text-gray-500 text-xl cursor-pointer px-2 py-1 leading-none hover:text-gray-300"
          >
            x
          </button>
        </div>

        {/* Form */}
        <div className="p-5 flex flex-col gap-4">
          {/* Acquisition Cost */}
          <div>
            <label className={labelClasses}>Acquisition Cost ($)</label>
            <input
              type="number"
              value={acquisitionCost || ""}
              onChange={(e) => setAcquisitionCost(Number(e.target.value))}
              placeholder="e.g. 2500000"
              className={inputClasses}
            />
          </div>

          {/* Equity % Slider */}
          <div>
            <label className={labelClasses}>
              Equity: {equityPct}%
            </label>
            <div className="flex items-center gap-2.5">
              <span className="text-[10px] text-gray-500">0%</span>
              <input
                type="range"
                min={0}
                max={100}
                value={equityPct}
                onChange={(e) => setEquityPct(Number(e.target.value))}
                className="flex-1 accent-blue-500"
              />
              <span className="text-[10px] text-gray-500">100%</span>
            </div>
          </div>

          {/* Interest Rate Slider */}
          <div>
            <label className={labelClasses}>
              Interest Rate: {interestRate.toFixed(1)}%
            </label>
            <div className="flex items-center gap-2.5">
              <span className="text-[10px] text-gray-500">0%</span>
              <input
                type="range"
                min={0}
                max={200}
                value={interestRate * 10}
                onChange={(e) => setInterestRate(Number(e.target.value) / 10)}
                className="flex-1 accent-blue-500"
              />
              <span className="text-[10px] text-gray-500">20%</span>
            </div>
          </div>

          {/* Hold Period Slider */}
          <div>
            <label className={labelClasses}>
              Hold Period: {holdPeriodMonths} months
            </label>
            <div className="flex items-center gap-2.5">
              <span className="text-[10px] text-gray-500">6</span>
              <input
                type="range"
                min={6}
                max={60}
                value={holdPeriodMonths}
                onChange={(e) => setHoldPeriodMonths(Number(e.target.value))}
                className="flex-1 accent-blue-500"
              />
              <span className="text-[10px] text-gray-500">60</span>
            </div>
          </div>

          {/* Construction Cost + Gross Revenue row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClasses}>Construction Cost ($)</label>
              <input
                type="number"
                value={constructionCost || ""}
                onChange={(e) => setConstructionCost(Number(e.target.value))}
                placeholder="e.g. 5000000"
                className={inputClasses}
              />
            </div>
            <div>
              <label className={labelClasses}>Gross Revenue ($)</label>
              <input
                type="number"
                value={grossRevenue || ""}
                onChange={(e) => setGrossRevenue(Number(e.target.value))}
                placeholder="e.g. 12000000"
                className={inputClasses}
              />
            </div>
          </div>

          {/* Soft Cost % + Sellable Sqft row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClasses}>Soft Cost % (of hard costs)</label>
              <input
                type="number"
                value={softCostPct || ""}
                onChange={(e) => setSoftCostPct(Number(e.target.value))}
                placeholder="18"
                className={inputClasses}
              />
            </div>
            <div>
              <label className={labelClasses}>Sellable Sqft</label>
              <input
                type="number"
                value={sellableSqft || ""}
                onChange={(e) => setSellableSqft(Number(e.target.value))}
                placeholder="e.g. 8000"
                className={inputClasses}
              />
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="px-3 py-2 bg-red-600/10 border border-red-600/20 rounded text-red-400 text-xs">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            className={cn(
              "py-3 border-none rounded-md text-white text-sm font-bold transition-colors",
              loading
                ? "bg-gray-700 cursor-not-allowed"
                : "bg-blue-500 cursor-pointer hover:bg-blue-600"
            )}
          >
            {loading ? "Calculating..." : "Calculate Deal"}
          </button>
        </div>

        {/* Results */}
        {result && (
          <div className="px-5 pb-5 flex flex-col gap-4">
            <div className="border-t border-gray-800 pt-4">
              {/* Capital Structure */}
              <div className="mb-4">
                <div className={sectionHeadingClasses}>
                  Capital Structure
                </div>
                <div className={gridClasses}>
                  <span className="text-gray-400">Equity Required</span>
                  <span className="text-gray-300 text-right">
                    {fmt(result.equity_required)}
                  </span>
                  <span className="text-gray-400">Debt Amount</span>
                  <span className="text-gray-300 text-right">
                    {fmt(result.debt_amount)}
                  </span>
                  <span className="text-gray-400">Soft Costs</span>
                  <span className="text-gray-300 text-right">
                    {fmt(result.soft_costs)}
                  </span>
                  <span className="text-gray-400">Total Interest</span>
                  <span className="text-gray-300 text-right">
                    {fmt(result.total_interest_cost)}
                  </span>
                  <span className="text-gray-400 font-semibold">
                    Total Project Cost
                  </span>
                  <span className="text-gray-100 text-right font-bold">
                    {fmt(result.total_project_cost)}
                  </span>
                </div>
              </div>

              {/* Return Metrics */}
              <div className="mb-4">
                <div className={sectionHeadingClasses}>
                  Return Metrics
                </div>
                <div className={gridClasses}>
                  <span className="text-gray-400">Net Profit</span>
                  <span
                    className={cn(
                      "text-right font-bold",
                      result.net_profit >= 0 ? "text-green-400" : "text-red-400"
                    )}
                  >
                    {result.net_profit >= 0 ? "+" : ""}
                    {fmt(result.net_profit)}
                  </span>
                  <span className="text-gray-400">ROI</span>
                  <span className="text-gray-300 text-right">
                    {pct(result.roi)}
                  </span>
                  <span className="text-gray-400">ROE</span>
                  <span className="text-gray-300 text-right">
                    {pct(result.roe)}
                  </span>
                  <span className="text-gray-400">Cash-on-Cash</span>
                  <span className="text-gray-300 text-right">
                    {pct(result.cash_on_cash)}
                  </span>
                  <span className="text-gray-400">IRR Estimate</span>
                  <span className="text-gray-300 text-right">
                    {pct(result.irr_estimate)}
                  </span>
                  {result.breakeven_price_psf != null && (
                    <>
                      <span className="text-gray-400">Breakeven PSF</span>
                      <span className="text-amber-500 text-right font-semibold">
                        ${result.breakeven_price_psf.toFixed(0)}/sqft
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* Viability Badge */}
              <div
                className={cn(
                  "p-2.5 rounded-md text-center text-[13px] font-bold mb-4 border",
                  result.is_viable
                    ? "bg-green-500/10 text-green-400 border-green-500/25"
                    : "bg-red-600/10 text-red-400 border-red-600/25"
                )}
              >
                {result.is_viable
                  ? "DEAL IS VIABLE"
                  : "DEAL IS NOT VIABLE"}
              </div>

              {/* Scenario Tabs */}
              {result.scenarios && Object.keys(result.scenarios).length > 0 && (
                <div>
                  <div className={sectionHeadingClasses}>
                    Scenarios
                  </div>
                  <div className="flex mb-3 rounded-md overflow-hidden border border-gray-700">
                    {["bull", "base", "bear"].map((sc) => (
                      <button
                        key={sc}
                        onClick={() => setActiveScenario(sc)}
                        className={cn(
                          "flex-1 py-2 border-none text-[11px] font-bold cursor-pointer uppercase transition-all",
                          activeScenario === sc
                            ? "bg-slate-800 text-gray-100"
                            : "bg-transparent text-gray-500"
                        )}
                      >
                        {sc === "bull"
                          ? "Bull"
                          : sc === "base"
                            ? "Base"
                            : "Bear"}
                      </button>
                    ))}
                  </div>
                  {result.scenarios[activeScenario] &&
                    renderScenario(result.scenarios[activeScenario])}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
