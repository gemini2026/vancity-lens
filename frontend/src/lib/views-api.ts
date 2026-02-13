import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

export interface SavedView {
  id: number;
  name: string;
  filters: Record<string, string>;
  created_at: string;
}

export async function listSavedViews(token: string): Promise<SavedView[]> {
  const res = await fetch(`${API_BASE}/api/v1/views`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  return res.json();
}

export async function createSavedView(token: string, name: string, filters: Record<string, string>): Promise<SavedView> {
  const res = await fetch(`${API_BASE}/api/v1/views`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name, filters }),
  });
  if (!res.ok) throw new Error("Failed to save view");
  return res.json();
}

export async function deleteSavedView(token: string, viewId: number): Promise<void> {
  await fetch(`${API_BASE}/api/v1/views/${viewId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}
