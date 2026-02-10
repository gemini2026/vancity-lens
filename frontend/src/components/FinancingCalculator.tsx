"use client";

import { useState, useEffect } from "react";
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

export default function FinancingCalculator({
  parcelData,
  onClose,
}: FinancingCalculatorProps) {
  // Form fields
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

  // Results
  const [result, setResult] = useState<FinancingResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeScenario, setActiveScenario] = useState<string>("base");

  // Pre-populate from parcelData
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

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 10px",
    background: "#1e293b",
    border: "1px solid #374151",
    borderRadius: "4px",
    color: "#f3f4f6",
    fontSize: "13px",
    fontFamily: "system-ui, sans-serif",
  };

  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: "11px",
    color: "#9ca3af",
    marginBottom: "4px",
    fontWeight: "600",
  };

  const sliderContainerStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  };

  const renderScenario = (scenario: ScenarioResult) => (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "4px 12px",
        fontSize: "12px",
      }}
    >
      <span style={{ color: "#9ca3af" }}>Gross Revenue</span>
      <span style={{ color: "#d1d5db", textAlign: "right" }}>
        {fmt(scenario.gross_revenue)}
      </span>
      <span style={{ color: "#9ca3af" }}>Total Project Cost</span>
      <span style={{ color: "#d1d5db", textAlign: "right" }}>
        {fmt(scenario.total_project_cost)}
      </span>
      <span style={{ color: "#9ca3af" }}>Net Profit</span>
      <span
        style={{
          color: scenario.net_profit >= 0 ? "#4ade80" : "#f87171",
          textAlign: "right",
          fontWeight: "600",
        }}
      >
        {scenario.net_profit >= 0 ? "+" : ""}
        {fmt(scenario.net_profit)}
      </span>
      <span style={{ color: "#9ca3af" }}>ROI</span>
      <span style={{ color: "#d1d5db", textAlign: "right" }}>
        {pct(scenario.roi)}
      </span>
      <span style={{ color: "#9ca3af" }}>ROE</span>
      <span style={{ color: "#d1d5db", textAlign: "right" }}>
        {pct(scenario.roe)}
      </span>
      <div
        style={{
          gridColumn: "1 / -1",
          marginTop: "6px",
          padding: "6px",
          borderRadius: "4px",
          textAlign: "center",
          fontSize: "11px",
          fontWeight: "700",
          background: scenario.is_viable
            ? "rgba(34, 197, 94, 0.1)"
            : "rgba(220, 38, 38, 0.1)",
          color: scenario.is_viable ? "#4ade80" : "#f87171",
          border: scenario.is_viable
            ? "1px solid rgba(34, 197, 94, 0.2)"
            : "1px solid rgba(220, 38, 38, 0.2)",
        }}
      >
        {scenario.is_viable ? "VIABLE" : "NOT VIABLE"}
      </div>
    </div>
  );

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0, 0, 0, 0.6)",
        backdropFilter: "blur(4px)",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "600px",
          maxHeight: "90vh",
          overflowY: "auto",
          background: "#111827",
          borderRadius: "12px",
          border: "1px solid #1f2937",
          fontFamily: "system-ui, sans-serif",
          color: "#f3f4f6",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "16px 20px",
            borderBottom: "1px solid #1f2937",
            background: "#0f172a",
            borderRadius: "12px 12px 0 0",
          }}
        >
          <div>
            <div style={{ fontSize: "15px", fontWeight: "700" }}>
              Deal Model Calculator
            </div>
            {parcelData && (
              <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "2px" }}>
                PID: {parcelData.pid}
                {parcelData.construction_type &&
                  ` | ${parcelData.construction_type.replace(/_/g, " ")}`}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#6b7280",
              fontSize: "20px",
              cursor: "pointer",
              padding: "4px 8px",
              lineHeight: "1",
            }}
          >
            x
          </button>
        </div>

        {/* Form */}
        <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* Acquisition Cost */}
          <div>
            <label style={labelStyle}>Acquisition Cost ($)</label>
            <input
              type="number"
              value={acquisitionCost || ""}
              onChange={(e) => setAcquisitionCost(Number(e.target.value))}
              placeholder="e.g. 2500000"
              style={inputStyle}
            />
          </div>

          {/* Equity % Slider */}
          <div>
            <label style={labelStyle}>
              Equity: {equityPct}%
            </label>
            <div style={sliderContainerStyle}>
              <span style={{ fontSize: "10px", color: "#6b7280" }}>0%</span>
              <input
                type="range"
                min={0}
                max={100}
                value={equityPct}
                onChange={(e) => setEquityPct(Number(e.target.value))}
                style={{ flex: 1, accentColor: "#3b82f6" }}
              />
              <span style={{ fontSize: "10px", color: "#6b7280" }}>100%</span>
            </div>
          </div>

          {/* Interest Rate Slider */}
          <div>
            <label style={labelStyle}>
              Interest Rate: {interestRate.toFixed(1)}%
            </label>
            <div style={sliderContainerStyle}>
              <span style={{ fontSize: "10px", color: "#6b7280" }}>0%</span>
              <input
                type="range"
                min={0}
                max={200}
                value={interestRate * 10}
                onChange={(e) => setInterestRate(Number(e.target.value) / 10)}
                style={{ flex: 1, accentColor: "#3b82f6" }}
              />
              <span style={{ fontSize: "10px", color: "#6b7280" }}>20%</span>
            </div>
          </div>

          {/* Hold Period Slider */}
          <div>
            <label style={labelStyle}>
              Hold Period: {holdPeriodMonths} months
            </label>
            <div style={sliderContainerStyle}>
              <span style={{ fontSize: "10px", color: "#6b7280" }}>6</span>
              <input
                type="range"
                min={6}
                max={60}
                value={holdPeriodMonths}
                onChange={(e) => setHoldPeriodMonths(Number(e.target.value))}
                style={{ flex: 1, accentColor: "#3b82f6" }}
              />
              <span style={{ fontSize: "10px", color: "#6b7280" }}>60</span>
            </div>
          </div>

          {/* Construction Cost + Gross Revenue row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={labelStyle}>Construction Cost ($)</label>
              <input
                type="number"
                value={constructionCost || ""}
                onChange={(e) => setConstructionCost(Number(e.target.value))}
                placeholder="e.g. 5000000"
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Gross Revenue ($)</label>
              <input
                type="number"
                value={grossRevenue || ""}
                onChange={(e) => setGrossRevenue(Number(e.target.value))}
                placeholder="e.g. 12000000"
                style={inputStyle}
              />
            </div>
          </div>

          {/* Soft Cost % + Sellable Sqft row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={labelStyle}>Soft Cost % (of hard costs)</label>
              <input
                type="number"
                value={softCostPct || ""}
                onChange={(e) => setSoftCostPct(Number(e.target.value))}
                placeholder="18"
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Sellable Sqft</label>
              <input
                type="number"
                value={sellableSqft || ""}
                onChange={(e) => setSellableSqft(Number(e.target.value))}
                placeholder="e.g. 8000"
                style={inputStyle}
              />
            </div>
          </div>

          {/* Error */}
          {error && (
            <div
              style={{
                padding: "8px 12px",
                background: "rgba(220, 38, 38, 0.1)",
                border: "1px solid rgba(220, 38, 38, 0.2)",
                borderRadius: "4px",
                color: "#f87171",
                fontSize: "12px",
              }}
            >
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              padding: "12px",
              background: loading ? "#374151" : "#3b82f6",
              border: "none",
              borderRadius: "6px",
              color: "#ffffff",
              fontSize: "14px",
              fontWeight: "700",
              cursor: loading ? "not-allowed" : "pointer",
              fontFamily: "system-ui, sans-serif",
              transition: "background 0.2s",
            }}
            onMouseEnter={(e) => {
              if (!loading)
                e.currentTarget.style.background = "#2563eb";
            }}
            onMouseLeave={(e) => {
              if (!loading)
                e.currentTarget.style.background = "#3b82f6";
            }}
          >
            {loading ? "Calculating..." : "Calculate Deal"}
          </button>
        </div>

        {/* Results */}
        {result && (
          <div
            style={{
              padding: "0 20px 20px",
              display: "flex",
              flexDirection: "column",
              gap: "16px",
            }}
          >
            <div
              style={{
                borderTop: "1px solid #1f2937",
                paddingTop: "16px",
              }}
            >
              {/* Capital Structure */}
              <div style={{ marginBottom: "16px" }}>
                <div
                  style={{
                    fontSize: "12px",
                    fontWeight: "700",
                    color: "#9ca3af",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "8px",
                  }}
                >
                  Capital Structure
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "4px 12px",
                    fontSize: "12px",
                  }}
                >
                  <span style={{ color: "#9ca3af" }}>Equity Required</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {fmt(result.equity_required)}
                  </span>
                  <span style={{ color: "#9ca3af" }}>Debt Amount</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {fmt(result.debt_amount)}
                  </span>
                  <span style={{ color: "#9ca3af" }}>Soft Costs</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {fmt(result.soft_costs)}
                  </span>
                  <span style={{ color: "#9ca3af" }}>Total Interest</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {fmt(result.total_interest_cost)}
                  </span>
                  <span style={{ color: "#9ca3af", fontWeight: "600" }}>
                    Total Project Cost
                  </span>
                  <span
                    style={{
                      color: "#f3f4f6",
                      textAlign: "right",
                      fontWeight: "700",
                    }}
                  >
                    {fmt(result.total_project_cost)}
                  </span>
                </div>
              </div>

              {/* Return Metrics */}
              <div style={{ marginBottom: "16px" }}>
                <div
                  style={{
                    fontSize: "12px",
                    fontWeight: "700",
                    color: "#9ca3af",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "8px",
                  }}
                >
                  Return Metrics
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "4px 12px",
                    fontSize: "12px",
                  }}
                >
                  <span style={{ color: "#9ca3af" }}>Net Profit</span>
                  <span
                    style={{
                      color:
                        result.net_profit >= 0 ? "#4ade80" : "#f87171",
                      textAlign: "right",
                      fontWeight: "700",
                    }}
                  >
                    {result.net_profit >= 0 ? "+" : ""}
                    {fmt(result.net_profit)}
                  </span>
                  <span style={{ color: "#9ca3af" }}>ROI</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {pct(result.roi)}
                  </span>
                  <span style={{ color: "#9ca3af" }}>ROE</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {pct(result.roe)}
                  </span>
                  <span style={{ color: "#9ca3af" }}>Cash-on-Cash</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {pct(result.cash_on_cash)}
                  </span>
                  <span style={{ color: "#9ca3af" }}>IRR Estimate</span>
                  <span style={{ color: "#d1d5db", textAlign: "right" }}>
                    {pct(result.irr_estimate)}
                  </span>
                  {result.breakeven_price_psf != null && (
                    <>
                      <span style={{ color: "#9ca3af" }}>Breakeven PSF</span>
                      <span
                        style={{
                          color: "#f59e0b",
                          textAlign: "right",
                          fontWeight: "600",
                        }}
                      >
                        ${result.breakeven_price_psf.toFixed(0)}/sqft
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* Viability Badge */}
              <div
                style={{
                  padding: "10px",
                  borderRadius: "6px",
                  textAlign: "center",
                  fontSize: "13px",
                  fontWeight: "700",
                  marginBottom: "16px",
                  background: result.is_viable
                    ? "rgba(34, 197, 94, 0.1)"
                    : "rgba(220, 38, 38, 0.1)",
                  color: result.is_viable ? "#4ade80" : "#f87171",
                  border: result.is_viable
                    ? "1px solid rgba(34, 197, 94, 0.25)"
                    : "1px solid rgba(220, 38, 38, 0.25)",
                }}
              >
                {result.is_viable
                  ? "DEAL IS VIABLE"
                  : "DEAL IS NOT VIABLE"}
              </div>

              {/* Scenario Tabs */}
              {result.scenarios && Object.keys(result.scenarios).length > 0 && (
                <div>
                  <div
                    style={{
                      fontSize: "12px",
                      fontWeight: "700",
                      color: "#9ca3af",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      marginBottom: "8px",
                    }}
                  >
                    Scenarios
                  </div>
                  <div
                    style={{
                      display: "flex",
                      gap: "0",
                      marginBottom: "12px",
                      borderRadius: "6px",
                      overflow: "hidden",
                      border: "1px solid #374151",
                    }}
                  >
                    {["bull", "base", "bear"].map((sc) => (
                      <button
                        key={sc}
                        onClick={() => setActiveScenario(sc)}
                        style={{
                          flex: 1,
                          padding: "8px 0",
                          background:
                            activeScenario === sc
                              ? "#1e293b"
                              : "transparent",
                          border: "none",
                          color:
                            activeScenario === sc
                              ? "#f3f4f6"
                              : "#6b7280",
                          fontSize: "11px",
                          fontWeight: "700",
                          cursor: "pointer",
                          textTransform: "uppercase",
                          fontFamily: "system-ui, sans-serif",
                          transition: "all 0.2s",
                        }}
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
