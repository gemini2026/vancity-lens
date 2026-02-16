import type { ParcelEntitlement } from "./types";
import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

export async function fetchEntitlement(pid: string): Promise<ParcelEntitlement> {
  const res = await fetch(`${API_BASE}/api/v1/parcels/${pid}/entitlement`);
  if (!res.ok) throw new Error(`Parcel ${pid} not found`);
  return res.json();
}

export async function fetchTOAGeoJSON(): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(`${API_BASE}/api/v1/toa/geojson`);
  if (!res.ok) throw new Error("Failed to load TOA zones");
  return res.json();
}

export async function fetchNearestParcel(lng: number, lat: number, radiusM = 100) {
  const res = await fetch(
    `${API_BASE}/api/v1/parcels/nearest?lng=${lng}&lat=${lat}&radius_m=${radiusM}`
  );
  if (!res.ok) return null;
  return res.json();
}

export async function fetchOpportunities(limit = 50) {
  const res = await fetch(`${API_BASE}/api/v1/opportunities?limit=${limit}`);
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data) ? data : data.items || [];
}

export interface TopOpportunity {
  pid: string;
  civic_address: string | null;
  current_zoning: string | null;
  tier: number;
  station_name: string;
  storey_uplift: number;
  ilr: number | null;
  signal_count: number;
  composite_score: number;
  asking_price: number | null;
  est_value: number | null;
  lng: number;
  lat: number;
}

export async function fetchTopOpportunities(limit = 10): Promise<TopOpportunity[]> {
  const res = await fetch(`${API_BASE}/api/v1/opportunities/top?limit=${limit}`);
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}

export async function downloadReport(pid: string, token?: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/v1/parcels/${pid}/report.pdf`, { headers });
  if (!res.ok) throw new Error("Failed to download report");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `parcel-${pid}-report.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadMemo(pid: string, token?: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/v1/parcels/${pid}/memo.pdf`, { headers });
  if (!res.ok) throw new Error("Failed to download memo");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `parcel-${pid}-investor-memo.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function fetchComparables(pid: string, token?: string) {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/v1/parcels/${pid}/comparables`, { headers });
  if (!res.ok) return [];
  return res.json();
}
