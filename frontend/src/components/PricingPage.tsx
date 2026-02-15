"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
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
    <div className="min-h-screen bg-gray-900 text-gray-100 px-6 py-12">
      {/* Header */}
      <div className="text-center mb-12">
        <h1 className="text-[32px] font-extrabold mb-2 text-gray-100">
          Choose Your Plan
        </h1>
        <p className="text-[15px] text-gray-400 max-w-[500px] mx-auto">
          Unlock the full power of VanCity Lens for your real estate investment
          decisions.
        </p>
        {subscription && subscription.is_active && (
          <div className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-blue-500/10 border border-blue-500/20 rounded-md text-[13px]">
            <span className="text-blue-400 font-semibold">
              Current plan: {subscription.tier}
            </span>
            <button
              onClick={handleManage}
              className="bg-transparent border-none text-blue-400 text-xs cursor-pointer underline"
            >
              Manage billing
            </button>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="max-w-[600px] mx-auto mb-6 px-4 py-2.5 bg-red-600/10 border border-red-600/20 rounded-md text-red-400 text-[13px] text-center">
          {error}
        </div>
      )}

      {/* Pricing Cards */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-5 max-w-[1200px] mx-auto">
        {TIERS.map((tier) => {
          const isCurrent = isCurrentTier(tier.name);
          const isLoading = checkoutLoading === tier.priceId;

          return (
            <div
              key={tier.name}
              className={cn(
                "rounded-xl p-7 flex flex-col relative transition-all duration-200",
                tier.highlighted
                  ? "bg-slate-800 border-2 border-blue-500"
                  : "bg-slate-900 border border-gray-800"
              )}
            >
              {tier.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-500 text-white text-[10px] font-bold px-3 py-1 rounded-[10px] uppercase tracking-wide">
                  Most Popular
                </div>
              )}

              <div className="text-sm font-bold text-gray-100 mb-1">
                {tier.name}
              </div>

              <div className="text-[11px] text-gray-500 mb-4">
                {tier.description}
              </div>

              <div className="text-[28px] font-extrabold text-gray-100 mb-5">
                {tier.price}
              </div>

              {/* Features */}
              <div className="flex-1 flex flex-col gap-2 mb-6">
                {tier.features.map((feature, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-2 text-xs text-gray-300"
                  >
                    <span className="text-blue-500 font-bold shrink-0 mt-px">
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
                  className="block p-3 bg-transparent border border-gray-700 rounded-md text-gray-300 text-[13px] font-semibold cursor-pointer text-center no-underline transition-all duration-200 hover:bg-gray-700 hover:text-white"
                >
                  Contact Sales
                </a>
              ) : isCurrent ? (
                <button
                  disabled
                  className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-md text-blue-400 text-[13px] font-semibold cursor-default"
                >
                  Current Plan
                </button>
              ) : tier.priceId ? (
                <button
                  onClick={() => handleSubscribe(tier.priceId!)}
                  disabled={isLoading}
                  className={cn(
                    "p-3 rounded-md text-white text-[13px] font-semibold transition-colors duration-200",
                    isLoading
                      ? "bg-gray-700 cursor-not-allowed"
                      : tier.highlighted
                        ? "bg-blue-500 cursor-pointer hover:bg-blue-600 border-none"
                        : "bg-slate-800 cursor-pointer hover:bg-gray-700 border border-gray-700"
                  )}
                >
                  {isLoading ? "Redirecting..." : tier.cta}
                </button>
              ) : (
                <button
                  disabled
                  className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-md text-blue-400 text-[13px] font-semibold cursor-default"
                >
                  {isCurrent ? "Current Plan" : "Free Forever"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer note */}
      <div className="text-center text-xs text-gray-500 max-w-[600px] mx-auto mt-10">
        All plans include access to the VanCity Lens platform. Pricing is in CAD.
        Cancel anytime from your billing portal. Enterprise plans require annual
        commitment.
      </div>
    </div>
  );
}
