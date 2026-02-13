import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

// ── Request / Response Interfaces ─────────────────────────────────

export interface FinancingRequest {
  acquisition_cost: number;
  equity_pct: number;
  interest_rate: number;
  hold_period_months: number;
  construction_cost: number;
  gross_revenue: number;
  soft_cost_pct?: number;
  sellable_sqft?: number;
}

export interface ScenarioResult {
  label: string;
  gross_revenue: number;
  total_project_cost: number;
  net_profit: number;
  roi: number;
  roe: number;
  is_viable: boolean;
}

export interface FinancingResult {
  equity_required: number;
  debt_amount: number;
  soft_costs: number;
  total_interest_cost: number;
  total_project_cost: number;
  net_profit: number;
  roi: number;
  roe: number;
  cash_on_cash: number;
  irr_estimate: number;
  breakeven_price_psf?: number;
  is_viable: boolean;
  scenarios: Record<string, ScenarioResult>;
}

// ── API Functions ─────────────────────────────────────────────────

export async function calculateFinancing(
  request: FinancingRequest
): Promise<FinancingResult> {
  const res = await fetch(`${API_BASE}/api/v1/financing/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Financing calculation failed: ${res.statusText}`);
  }
  return res.json();
}

export async function quickCalc(
  params: Record<string, string | number>
): Promise<FinancingResult> {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    searchParams.set(key, String(value));
  });
  const res = await fetch(
    `${API_BASE}/api/v1/financing/quick-calc?${searchParams}`
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Quick calc failed: ${res.statusText}`);
  }
  return res.json();
}
