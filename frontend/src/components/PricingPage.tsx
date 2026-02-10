"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  createCheckoutSession,
  getSubscriptionStatus,
  openCustomerPortal,
  type SubscriptionStatus,
} from "@/lib/stripe-api";

interface PricingTier {
  name: string;
  price: string;
  priceId: string | null;
  description: string;
  features: string[];
  highlighted?: boolean;
  cta: string;
}

const TIERS: PricingTier[] = [
  {
    name: "Free",
    price: "$0",
    priceId: null,
    description: "Get started with basic access",
    cta: "Current Plan",
    features: [
      "Map view with TOA zones",
      "5 parcel lookups / day",
      "Basic signal feed",
      "Community data",
    ],
  },
  {
    name: "Starter",
    price: "$49/mo",
    priceId: "price_starter_monthly",
    description: "For individual investors",
    cta: "Subscribe",
    features: [
      "Everything in Free",
      "Unlimited parcel lookups",
      "Full signal feed + filters",
      "Neighborhood scorecards",
      "CSV exports",
      "Email alerts (5 watchlists)",
    ],
  },
  {
    name: "Pro",
    price: "$149/mo",
    priceId: "price_pro_monthly",
    description: "For active developers",
    cta: "Subscribe",
    highlighted: true,
    features: [
      "Everything in Starter",
      "AI chat intelligence",
      "Deal modeling calculator",
      "Pro forma analysis",
      "PDF reports",
      "Unlimited watchlists",
      "Priority support",
      "API access",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    priceId: null,
    description: "For teams and brokerages",
    cta: "Contact Sales",
    features: [
      "Everything in Pro",
      "Team accounts (up to 25 seats)",
      "Custom data integrations",
      "White-label reports",
      "Dedicated account manager",
      "SLA guarantee",
      "Custom pipeline feeds",
    ],
  },
];

export default function PricingPage() {
  const { token, user } = useAuth();
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(
    null
  );
  const [loadingSub, setLoadingSub] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoadingSub(true);
    getSubscriptionStatus(token)
      .then(setSubscription)
      .catch(() => setSubscription(null))
      .finally(() => setLoadingSub(false));
  }, [token]);

  const handleSubscribe = async (priceId: string) => {
    if (!token) {
      setError("Please log in to subscribe");
      return;
    }
    setCheckoutLoading(priceId);
    setError(null);
    try {
      const session = await createCheckoutSession(token, priceId);
      window.location.href = session.checkout_url;
    } catch (err: any) {
      setError(err.message || "Failed to start checkout");
    } finally {
      setCheckoutLoading(null);
    }
  };

  const handleManage = async () => {
    if (!token) return;
    try {
      const portal = await openCustomerPortal(token);
      window.location.href = portal.portal_url;
    } catch (err: any) {
      setError(err.message || "Failed to open billing portal");
    }
  };

  const isCurrentTier = (tierName: string): boolean => {
    if (!subscription) return tierName === "Free";
    return (
      subscription.tier.toLowerCase() === tierName.toLowerCase() &&
      subscription.is_active
    );
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#111827",
        fontFamily: "system-ui, sans-serif",
        color: "#f3f4f6",
        padding: "48px 24px",
      }}
    >
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: "48px" }}>
        <h1
          style={{
            fontSize: "32px",
            fontWeight: "800",
            margin: "0 0 8px",
            color: "#f3f4f6",
          }}
        >
          Choose Your Plan
        </h1>
        <p
          style={{
            fontSize: "15px",
            color: "#9ca3af",
            margin: 0,
            maxWidth: "500px",
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          Unlock the full power of VanCity Lens for your real estate investment
          decisions.
        </p>
        {subscription && subscription.is_active && (
          <div
            style={{
              marginTop: "16px",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 16px",
              background: "rgba(59, 130, 246, 0.1)",
              border: "1px solid rgba(59, 130, 246, 0.2)",
              borderRadius: "6px",
              fontSize: "13px",
            }}
          >
            <span style={{ color: "#60a5fa", fontWeight: "600" }}>
              Current plan: {subscription.tier}
            </span>
            <button
              onClick={handleManage}
              style={{
                background: "none",
                border: "none",
                color: "#60a5fa",
                fontSize: "12px",
                cursor: "pointer",
                textDecoration: "underline",
                fontFamily: "system-ui, sans-serif",
              }}
            >
              Manage billing
            </button>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            maxWidth: "600px",
            margin: "0 auto 24px",
            padding: "10px 16px",
            background: "rgba(220, 38, 38, 0.1)",
            border: "1px solid rgba(220, 38, 38, 0.2)",
            borderRadius: "6px",
            color: "#f87171",
            fontSize: "13px",
            textAlign: "center",
          }}
        >
          {error}
        </div>
      )}

      {/* Pricing Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "20px",
          maxWidth: "1200px",
          margin: "0 auto",
        }}
      >
        {TIERS.map((tier) => {
          const isCurrent = isCurrentTier(tier.name);
          const isLoading = checkoutLoading === tier.priceId;

          return (
            <div
              key={tier.name}
              style={{
                background: tier.highlighted
                  ? "#1e293b"
                  : "#0f172a",
                borderRadius: "12px",
                border: tier.highlighted
                  ? "2px solid #3b82f6"
                  : "1px solid #1f2937",
                padding: "28px 24px",
                display: "flex",
                flexDirection: "column",
                position: "relative",
                transition: "transform 0.2s, box-shadow 0.2s",
              }}
            >
              {tier.highlighted && (
                <div
                  style={{
                    position: "absolute",
                    top: "-12px",
                    left: "50%",
                    transform: "translateX(-50%)",
                    background: "#3b82f6",
                    color: "#fff",
                    fontSize: "10px",
                    fontWeight: "700",
                    padding: "4px 12px",
                    borderRadius: "10px",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  Most Popular
                </div>
              )}

              <div
                style={{
                  fontSize: "14px",
                  fontWeight: "700",
                  color: "#f3f4f6",
                  marginBottom: "4px",
                }}
              >
                {tier.name}
              </div>

              <div
                style={{
                  fontSize: "11px",
                  color: "#6b7280",
                  marginBottom: "16px",
                }}
              >
                {tier.description}
              </div>

              <div
                style={{
                  fontSize: "28px",
                  fontWeight: "800",
                  color: "#f3f4f6",
                  marginBottom: "20px",
                }}
              >
                {tier.price}
              </div>

              {/* Features */}
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  marginBottom: "24px",
                }}
              >
                {tier.features.map((feature, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "8px",
                      fontSize: "12px",
                      color: "#d1d5db",
                    }}
                  >
                    <span
                      style={{
                        color: "#3b82f6",
                        fontWeight: "700",
                        flexShrink: 0,
                        marginTop: "1px",
                      }}
                    >
                      &#10003;
                    </span>
                    <span>{feature}</span>
                  </div>
                ))}
              </div>

              {/* CTA Button */}
              {tier.name === "Enterprise" ? (
                <a
                  href="mailto:sales@vancitylens.com?subject=Enterprise%20Inquiry"
                  style={{
                    display: "block",
                    padding: "12px",
                    background: "transparent",
                    border: "1px solid #374151",
                    borderRadius: "6px",
                    color: "#d1d5db",
                    fontSize: "13px",
                    fontWeight: "600",
                    cursor: "pointer",
                    textAlign: "center",
                    textDecoration: "none",
                    fontFamily: "system-ui, sans-serif",
                    transition: "all 0.2s",
                  }}
                >
                  Contact Sales
                </a>
              ) : isCurrent ? (
                <button
                  disabled
                  style={{
                    padding: "12px",
                    background: "rgba(59, 130, 246, 0.1)",
                    border: "1px solid rgba(59, 130, 246, 0.2)",
                    borderRadius: "6px",
                    color: "#60a5fa",
                    fontSize: "13px",
                    fontWeight: "600",
                    cursor: "default",
                    fontFamily: "system-ui, sans-serif",
                  }}
                >
                  Current Plan
                </button>
              ) : tier.priceId ? (
                <button
                  onClick={() => handleSubscribe(tier.priceId!)}
                  disabled={isLoading}
                  style={{
                    padding: "12px",
                    background: isLoading
                      ? "#374151"
                      : tier.highlighted
                        ? "#3b82f6"
                        : "#1e293b",
                    border: tier.highlighted
                      ? "none"
                      : "1px solid #374151",
                    borderRadius: "6px",
                    color: "#fff",
                    fontSize: "13px",
                    fontWeight: "600",
                    cursor: isLoading ? "not-allowed" : "pointer",
                    fontFamily: "system-ui, sans-serif",
                    transition: "background 0.2s",
                  }}
                  onMouseEnter={(e) => {
                    if (!isLoading) {
                      e.currentTarget.style.background = tier.highlighted
                        ? "#2563eb"
                        : "#374151";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isLoading) {
                      e.currentTarget.style.background = tier.highlighted
                        ? "#3b82f6"
                        : "#1e293b";
                    }
                  }}
                >
                  {isLoading ? "Redirecting..." : tier.cta}
                </button>
              ) : (
                <button
                  disabled
                  style={{
                    padding: "12px",
                    background: "rgba(59, 130, 246, 0.1)",
                    border: "1px solid rgba(59, 130, 246, 0.2)",
                    borderRadius: "6px",
                    color: "#60a5fa",
                    fontSize: "13px",
                    fontWeight: "600",
                    cursor: "default",
                    fontFamily: "system-ui, sans-serif",
                  }}
                >
                  {isCurrent ? "Current Plan" : "Free Forever"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer note */}
      <div
        style={{
          textAlign: "center",
          marginTop: "40px",
          fontSize: "12px",
          color: "#6b7280",
          maxWidth: "600px",
          margin: "40px auto 0",
        }}
      >
        All plans include access to the VanCity Lens platform. Pricing is in CAD.
        Cancel anytime from your billing portal. Enterprise plans require annual
        commitment.
      </div>
    </div>
  );
}
