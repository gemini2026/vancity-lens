import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

function getAuthHeaders(): HeadersInit {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function saveParcel(
  pid: string,
  notes = ""
): Promise<{ saved: boolean }> {
  const res = await fetch(`${API_BASE}/api/v1/parcels/${pid}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ notes }),
  });
  if (!res.ok) throw new Error(`Save failed: ${res.status}`);
  return res.json();
}

export async function unsaveParcel(
  pid: string
): Promise<{ saved: boolean }> {
  const res = await fetch(`${API_BASE}/api/v1/parcels/${pid}/save`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Unsave failed: ${res.status}`);
  return res.json();
}

export async function checkParcelSaved(
  pid: string
): Promise<{ saved: boolean }> {
  const res = await fetch(`${API_BASE}/api/v1/parcels/${pid}/saved`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return { saved: false };
  return res.json();
}

export interface SavedParcelItem {
  id: number;
  pid: string;
  notes: string;
  created_at: string;
  civic_address: string | null;
  current_zoning: string | null;
}

export async function listSavedParcels(): Promise<SavedParcelItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/saved-parcels`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) return [];
  return res.json();
}
