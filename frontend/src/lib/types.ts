/** Bill 47 API response types — mirrors Pydantic models (V3) */

export type EntitlementSignal = "high_alpha" | "moderate" | "low" | "already_zoned" | "none";

export interface StationEntitlement {
  station_name: string;
  distance_m: string;
  tier: number;
  bill47_storeys: number;
  bill47_fsr: string;
  entitled_storeys: number;
  entitled_fsr: string;
  current_storeys: number | null;
  current_fsr: string | null;
  storey_uplift: number;
  fsr_uplift: string;
  zoning_already_exceeds: boolean;
}

export interface ValueEstimate {
  lot_area_sqm: string;
  entitled_fsr: string;
  buildable_sqft: string;
  estimated_land_value: number;
  current_assessed: number | null;
  asking_price: number | null;
  value_delta: number;
  price_per_sqft_assumption: string;
  estimated_units: number | null;
  nla_sqft: number | null;
}

export interface DataSource {
  field: string;
  label: string;
  value: string;
  origin: string;
  confidence: "verified" | "estimated" | "calculated";
  url: string | null;
  note: string | null;
}

export interface SourceAttribution {
  sources: DataSource[];
  last_updated: string | null;
  disclaimer: string;
}

export interface RiskFlag {
  code: string;
  severity: "red" | "yellow" | "green";
  label: string;
  detail: string;
  cost_impact: string | null;
  verify_url: string | null;
}

export interface DeveloperProForma {
  buildable_sqft: string;
  revenue_per_sqft: string;
  gross_revenue: number;
  construction_type: string;
  hard_cost_per_sqft: string;
  hard_cost_total: number;
  soft_cost_pct: string;
  soft_cost_total: number;
  cac_dcl_total: number;
  developer_profit_pct: string;
  developer_profit: number;
  residual_land_value: number;
  asking_price: number | null;
  assessed_value: number | null;
  true_alpha: number;
  // V2: Neighborhood adjustment
  neighborhood: string | null;
  neighborhood_multiplier: string | null;
  // V2: Holding cost
  holding_cost: number | null;
  holding_months: number | null;
}

export interface DueDiligenceItem {
  item: string;
  description: string;
  url: string | null;
  priority: "critical" | "high" | "medium";
}

// V3: Scenario Pro Forma
export interface ScenarioProForma {
  scenario: "bull" | "base" | "bear";
  buildable_sqft: string;
  sellable_sqft: string;
  revenue_per_sqft: string;
  absorption_discount: string;
  gross_revenue: number;
  net_revenue: number;
  construction_type: string;
  hard_cost_per_sqft: string;
  hard_cost_inflation: string;
  hard_cost_total: number;
  soft_cost_total: number;
  contingency_total: number;
  marketing_total: number;
  cac_dcl_total: number;
  hidden_costs_total: number;
  holding_cost: number;
  holding_months: number;
  developer_profit: number;
  total_costs: number;
  residual_land_value: number;
  true_alpha: number;
  is_viable: boolean;
}

export interface HiddenCostItem {
  category: string;
  cost: number;
  explanation: string;
}

export interface ThreeScenarioProForma {
  bull: ScenarioProForma;
  base: ScenarioProForma;
  bear: ScenarioProForma;
  hidden_costs: HiddenCostItem[];
  hidden_costs_total: number;
  grade_scenario: string;
}

export interface DealValidation {
  deal_grade: string;
  deal_score: number;
  confidence_level: "high" | "medium" | "low";
  // V2: Multi-axis grading
  confidence_stars: number;
  friction_level: "low" | "medium" | "high";
  friction_score: number;
  neighborhood: string | null;
  // Key metrics
  price_per_buildable_sqft: string | null;
  assessed_ratio: string | null;
  land_to_total_ratio: string | null;
  lot_adequate: boolean;
  lot_adequacy_note: string | null;
  min_lot_sqm_required: string | null;
  competing_parcels: number;
  supply_saturation: "low" | "moderate" | "high";
  risk_flags: RiskFlag[];
  red_flag_count: number;
  yellow_flag_count: number;
  green_flag_count: number;
  pro_forma: DeveloperProForma | null;
  // V3: Three-scenario pro forma
  three_scenario_proforma: ThreeScenarioProForma | null;
  // V3: Gap analysis
  gap_analysis: string | null;
  // V3: Execution difficulty
  execution_difficulty_score: number;
  execution_difficulty_factors: string[];
  // V2: Due diligence
  due_diligence_checklist: DueDiligenceItem[];
  one_liner: string;
}

export interface ParcelEntitlement {
  pid: string;
  civic_address: string | null;
  current_zoning: string | null;
  in_toa: boolean;
  entitlements: StationEntitlement[];
  best_entitlement: StationEntitlement | null;
  value_estimate: ValueEstimate | null;
  sources: SourceAttribution | null;
  validation: DealValidation | null;
  signal: EntitlementSignal;
  headline: string;
}
