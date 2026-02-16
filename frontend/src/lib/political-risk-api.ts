import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

export interface NeighborhoodRisk {
  neighborhood: string;
  risk_score: number;
  opposition_rate: number;
  delay_score: number;
  sentiment_intensity: number;
  council_resistance: number;
}

export async function fetchNeighborhoodRiskScores(): Promise<NeighborhoodRisk[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/political-risk/neighborhoods`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}
