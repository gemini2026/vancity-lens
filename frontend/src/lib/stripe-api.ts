const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Interfaces ────────────────────────────────────────────────────

export interface CheckoutSession {
  checkout_url: string;
}

export interface SubscriptionStatus {
  tier: string;
  is_active: boolean;
  current_period_end: string;
}

export interface PortalSession {
  portal_url: string;
}

// ── Helper ────────────────────────────────────────────────────────

function authHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

// ── API Functions ─────────────────────────────────────────────────

export async function createCheckoutSession(
  token: string,
  priceId: string
): Promise<CheckoutSession> {
  const res = await fetch(`${API_BASE}/api/v1/stripe/checkout`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ price_id: priceId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Checkout failed: ${res.statusText}`);
  }
  return res.json();
}

export async function getSubscriptionStatus(
  token: string
): Promise<SubscriptionStatus> {
  const res = await fetch(`${API_BASE}/api/v1/subscriptions/status`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Failed to get subscription: ${res.statusText}`);
  }
  return res.json();
}

export async function openCustomerPortal(
  token: string
): Promise<PortalSession> {
  const res = await fetch(`${API_BASE}/api/v1/stripe/portal`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Portal failed: ${res.statusText}`);
  }
  return res.json();
}
