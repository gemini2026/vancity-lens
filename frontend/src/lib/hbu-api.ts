import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

function getAuthHeaders(): HeadersInit {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export interface HBUAnalysis {
  pid: string;
  address: string;
  current_zoning: string;
  highest_best_use: {
    recommended_use: string;
    zoning_basis: string;
    max_height_storeys: number | null;
    max_fsr: number | null;
    estimated_units: number | null;
    unit_mix: Record<string, number> | null;
    buildable_sqft: number | null;
    key_constraints: string[];
    feasibility_verdict: string;
    narrative: string | null;
    cited_sources: Array<{ title: string; section: string; relevance: string }>;
  };
  confidence_score: number | null;
  sources: Array<{ title: string; url: string; score: number }>;
  llm_model: string | null;
  analysis_duration_ms: number;
  cached_at: string | null;
  expires_at: string | null;
}

export async function getHBUAnalysis(pid: string): Promise<HBUAnalysis | null> {
  const res = await fetch(`${API_BASE}/api/v1/intel/parcels/${pid}/hbu`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (data.detail) return null; // no cached result
  return data;
}

export async function runHBUAnalysis(
  pid: string,
  forceRefresh = false
): Promise<HBUAnalysis> {
  const url = `${API_BASE}/api/v1/intel/parcels/${pid}/hbu${forceRefresh ? "?force_refresh=true" : ""}`;
  const res = await fetch(url, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`HBU analysis failed: ${res.status}`);
  return res.json();
}
