import type {
  ChatResponse,
  SignalFeedResponse,
  IntelSignal,
  IntelStats,
  SignalType,
  Severity,
  GeoJSON,
  NeighborhoodSummary,
  NeighborhoodScorecard,
  NeighborhoodComparison,
} from "./intel-types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ChatOptions {
  session_id?: string;
  include_signals?: boolean;
}

export interface SignalFilters {
  neighborhood?: string;
  signal_type?: SignalType;
  severity?: Severity;
  date_range?: "7d" | "30d" | "90d" | "all";
  limit?: number;
  offset?: number;
}

export async function chatWithIntel(
  query: string,
  options?: ChatOptions
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/v1/intel/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      session_id: options?.session_id,
      include_signals: options?.include_signals !== false,
    }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.statusText}`);
  return res.json();
}

export async function getSignalFeed(
  filters?: SignalFilters
): Promise<SignalFeedResponse> {
  const params = new URLSearchParams();
  if (filters?.neighborhood) params.set("neighborhood", filters.neighborhood);
  if (filters?.signal_type) params.set("signal_type", filters.signal_type);
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.date_range) params.set("date_range", filters.date_range);
  if (filters?.limit) params.set("limit", String(filters.limit));
  if (filters?.offset) params.set("offset", String(filters.offset));

  const res = await fetch(`${API_BASE}/api/v1/intel/signals?${params}`);
  if (!res.ok) throw new Error("Failed to fetch signal feed");
  return res.json();
}

export async function getSignalById(id: string): Promise<IntelSignal> {
  const res = await fetch(`${API_BASE}/api/v1/intel/signals/${id}`);
  if (!res.ok) throw new Error(`Signal ${id} not found`);
  return res.json();
}

export async function getSignalsForParcel(
  pid: string,
  radius?: number
): Promise<IntelSignal[]> {
  const params = new URLSearchParams();
  if (radius) params.set("radius", String(radius));

  const url = `${API_BASE}/api/v1/intel/signals/parcel/${encodeURIComponent(pid)}${params.toString() ? '?' + params : ''}`;
  const res = await fetch(url);
  if (!res.ok) return [];
  return res.json();
}

export async function getIntelStats(): Promise<IntelStats> {
  const res = await fetch(`${API_BASE}/api/v1/intel/stats`);
  if (!res.ok) throw new Error("Failed to fetch intel stats");
  return res.json();
}

export async function getNeighborhoods(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/v1/intel/neighborhoods`);
  if (!res.ok) return [];
  return res.json();
}

// ── Neighborhood Scorecard API ─────────────────────

export async function getNeighborhoodScorecards(): Promise<NeighborhoodSummary[]> {
  const res = await fetch(`${API_BASE}/api/v1/intel/neighborhoods/scorecards`);
  if (!res.ok) return [];
  return res.json();
}

export async function getNeighborhoodScorecard(slug: string): Promise<NeighborhoodScorecard | null> {
  const res = await fetch(`${API_BASE}/api/v1/intel/neighborhoods/${encodeURIComponent(slug)}/scorecard`);
  if (!res.ok) return null;
  return res.json();
}

export async function compareNeighborhoods(slugs: string[]): Promise<NeighborhoodComparison | null> {
  const params = new URLSearchParams({ slugs: slugs.join(",") });
  const res = await fetch(`${API_BASE}/api/v1/intel/neighborhoods/compare?${params}`);
  if (!res.ok) return null;
  return res.json();
}

export async function getSignalsGeoJSON(
  limit: number = 200,
  days: number = 90
): Promise<GeoJSON.FeatureCollection> {
  const params = new URLSearchParams({
    limit: String(limit),
    days: String(days),
  });
  const res = await fetch(`${API_BASE}/api/v1/intel/signals/geojson?${params}`);
  if (!res.ok) return { type: "FeatureCollection", features: [] };
  return res.json();
}
