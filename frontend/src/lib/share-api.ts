import { getApiBase } from "./api-base";

const API_BASE = getApiBase();

export async function createShareLink(pid: string, token?: string, label?: string): Promise<{ token: string; url: string; expires_at: string }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/v1/share`, {
    method: "POST",
    headers,
    body: JSON.stringify({ pid, label }),
  });
  if (!res.ok) throw new Error("Failed to create share link");
  return res.json();
}
