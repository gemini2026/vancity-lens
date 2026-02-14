import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

// ── Interfaces ────────────────────────────────────────────────────

export interface WatchlistRule {
  type: string;
  value: string;
}

export interface Watchlist {
  id: number;
  name: string;
  rules: WatchlistRule[];
  created_at?: string;
}

export interface Alert {
  id: number;
  signal_id?: number;
  headline?: string;
  summary?: string;
  severity?: string;
  signal_type?: string;
  neighborhood?: string;
  is_read: boolean;
  created_at: string;
}

export interface AlertsResponse {
  alerts: Alert[];
  total: number;
}

// ── Helper ────────────────────────────────────────────────────────

function authHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

// ── Watchlist CRUD ────────────────────────────────────────────────

export async function getWatchlists(token: string): Promise<Watchlist[]> {
  const res = await fetch(`${API_BASE}/api/v1/intel/watchlists`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Failed to fetch watchlists: ${res.statusText}`);
  return res.json();
}

export async function createWatchlist(
  token: string,
  body: { name: string; rules: WatchlistRule[] }
): Promise<Watchlist> {
  const res = await fetch(`${API_BASE}/api/v1/intel/watchlists`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(data.detail || `Failed to create watchlist: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteWatchlist(
  token: string,
  id: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/intel/watchlists/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Failed to delete watchlist: ${res.statusText}`);
}

// ── Alerts ────────────────────────────────────────────────────────

export async function getAlerts(
  token: string,
  opts?: { unread_only?: boolean; limit?: number; offset?: number }
): Promise<AlertsResponse> {
  const params = new URLSearchParams();
  if (opts?.unread_only) params.set("unread_only", "true");
  if (opts?.limit) params.set("limit", String(opts.limit));
  if (opts?.offset) params.set("offset", String(opts.offset));

  const queryString = params.toString();
  const res = await fetch(
    `${API_BASE}/api/v1/intel/alerts${queryString ? `?${queryString}` : ""}`,
    { headers: authHeaders(token) }
  );
  if (!res.ok) throw new Error(`Failed to fetch alerts: ${res.statusText}`);
  const data = await res.json();
  // Handle both array and object responses
  if (Array.isArray(data)) {
    return { alerts: data, total: data.length };
  }
  return data;
}

export async function markAlertRead(
  token: string,
  id: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/intel/alerts/${id}/read`, {
    method: "PATCH",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Failed to mark alert as read: ${res.statusText}`);
}

export async function getUnreadCount(token: string): Promise<number> {
  const res = await fetch(`${API_BASE}/api/v1/intel/alerts/count`, {
    headers: authHeaders(token),
  });
  if (!res.ok) return 0;
  const data = await res.json();
  return typeof data === "number" ? data : data.count ?? 0;
}
