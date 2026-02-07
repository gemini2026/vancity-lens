import type { ParcelEntitlement } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  return res.json();
}
