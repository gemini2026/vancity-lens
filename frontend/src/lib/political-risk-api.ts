import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

export interface NeighborhoodRisk {
  neighborhood: string;
  /** Composite risk score, range 1-10 */
  risk_score: number;
  /** Percentage of applications with opposition, range 0-100 */
  opposition_rate: number;
  /** Delay attribution score, range 0-10 */
  delay_score: number;
  /** Sentiment intensity score, range 0-10 */
  sentiment_intensity: number;
  /** Council voting resistance score, range 0-10 */
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
