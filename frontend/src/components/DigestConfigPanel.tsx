"use client";

import React, { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DigestSubscription {
  id: number;
  frequency: "daily" | "weekly";
  neighborhoods: string[];
  signal_types: string[];
  is_active: boolean;
  severity_min?: string;
  max_signals_per_digest?: number;
}

const VANCOUVER_NEIGHBORHOODS = [
  "Arbutus Ridge", "Downtown", "Dunbar-Southlands", "Fairview",
  "Grandview-Woodland", "Hastings-Sunrise", "Kensington-Cedar Cottage",
  "Kerrisdale", "Killarney", "Kitsilano", "Marpole", "Mount Pleasant",
  "Oakridge", "Renfrew-Collingwood", "Riley Park", "Shaughnessy",
  "South Cambie", "Strathcona", "Sunset", "Victoria-Fraserview",
  "West End", "West Point Grey",
];

const SIGNAL_TYPES = [
  "rezoning", "development_permit", "building_permit", "policy_change",
  "council_decision", "public_hearing", "infrastructure", "bylaw_amendment",
];

const SEVERITY_LEVELS = ["info", "low", "medium", "high", "critical"];

interface DigestConfigPanelProps {
  token: string;
}

export default function DigestConfigPanel({ token }: DigestConfigPanelProps) {
  const [subscriptions, setSubscriptions] = useState<DigestSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [frequency, setFrequency] = useState<"daily" | "weekly">("weekly");
  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<string[]>([]);
  const [selectedSignalTypes, setSelectedSignalTypes] = useState<string[]>([]);
  const [severityMin, setSeverityMin] = useState("info");
  const [editing, setEditing] = useState<number | null>(null);

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  const fetchSubscriptions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/intel/digests/subscriptions`, { headers });
      if (res.ok) {
        const data = await res.json();
        setSubscriptions(data.subscriptions || data || []);
      }
    } catch (e) {
      setError("Failed to load subscriptions");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchSubscriptions();
  }, [fetchSubscriptions]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const body = {
      frequency,
      neighborhoods: selectedNeighborhoods,
      signal_types: selectedSignalTypes,
      severity_min: severityMin,
    };

    try {
      if (editing !== null) {
        await fetch(`${API_BASE}/api/v1/intel/digests/subscriptions/${editing}`, {
          method: "PUT",
          headers,
          body: JSON.stringify(body),
        });
      } else {
        await fetch(`${API_BASE}/api/v1/intel/digests/subscribe`, {
          method: "POST",
          headers,
          body: JSON.stringify(body),
        });
      }
      setEditing(null);
      resetForm();
      fetchSubscriptions();
    } catch (e) {
      setError("Failed to save subscription");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await fetch(`${API_BASE}/api/v1/intel/digests/subscriptions/${id}`, {
        method: "DELETE",
        headers,
      });
      fetchSubscriptions();
    } catch (e) {
      setError("Failed to delete subscription");
    }
  };

  const handleEdit = (sub: DigestSubscription) => {
    setEditing(sub.id);
    setFrequency(sub.frequency);
    setSelectedNeighborhoods(sub.neighborhoods || []);
    setSelectedSignalTypes(sub.signal_types || []);
    setSeverityMin(sub.severity_min || "info");
  };

  const resetForm = () => {
    setFrequency("weekly");
    setSelectedNeighborhoods([]);
    setSelectedSignalTypes([]);
    setSeverityMin("info");
    setEditing(null);
  };

  const toggleItem = (list: string[], item: string, setter: (v: string[]) => void) => {
    setter(list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);
  };

  if (loading) return <div className="p-4 text-gray-400">Loading digest settings...</div>;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-2">
          Intelligence Brief Configuration
        </h3>
        <p className="text-sm text-gray-400">
          Configure personalized intelligence digests delivered to your inbox.
        </p>
      </div>

      {error && (
        <div className="p-3 bg-red-900/30 border border-red-700 rounded text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Existing Subscriptions */}
      {subscriptions.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-gray-300">Active Subscriptions</h4>
          {subscriptions.map((sub) => (
            <div
              key={sub.id}
              className="flex items-center justify-between p-3 bg-gray-800 rounded-lg border border-gray-700"
            >
              <div>
                <span className="text-white font-medium capitalize">{sub.frequency}</span>
                <span className="text-gray-400 text-sm ml-2">
                  {sub.neighborhoods?.length
                    ? `${sub.neighborhoods.length} neighborhoods`
                    : "All neighborhoods"}
                  {" | "}
                  {sub.signal_types?.length
                    ? `${sub.signal_types.length} types`
                    : "All types"}
                </span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => handleEdit(sub)}
                  className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(sub.id)}
                  className="px-3 py-1 text-sm bg-red-600 hover:bg-red-700 text-white rounded"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Subscription Form */}
      <form onSubmit={handleSubmit} className="space-y-4 p-4 bg-gray-800 rounded-lg border border-gray-700">
        <h4 className="text-sm font-medium text-gray-300">
          {editing !== null ? "Edit Subscription" : "New Subscription"}
        </h4>

        {/* Frequency */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">Frequency</label>
          <div className="flex gap-4">
            {(["daily", "weekly"] as const).map((f) => (
              <label key={f} className="flex items-center gap-2 text-white cursor-pointer">
                <input
                  type="radio"
                  name="frequency"
                  value={f}
                  checked={frequency === f}
                  onChange={() => setFrequency(f)}
                  className="accent-blue-500"
                />
                <span className="capitalize">{f}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Minimum Severity */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">Minimum Severity</label>
          <select
            value={severityMin}
            onChange={(e) => setSeverityMin(e.target.value)}
            className="w-full p-2 bg-gray-700 border border-gray-600 rounded text-white text-sm"
          >
            {SEVERITY_LEVELS.map((s) => (
              <option key={s} value={s} className="capitalize">
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* Neighborhoods */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Neighborhoods{" "}
            <span className="text-gray-500">(empty = all)</span>
          </label>
          <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
            {VANCOUVER_NEIGHBORHOODS.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => toggleItem(selectedNeighborhoods, n, setSelectedNeighborhoods)}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                  selectedNeighborhoods.includes(n)
                    ? "bg-blue-600 border-blue-500 text-white"
                    : "bg-gray-700 border-gray-600 text-gray-300 hover:border-gray-500"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        {/* Signal Types */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Signal Types{" "}
            <span className="text-gray-500">(empty = all)</span>
          </label>
          <div className="flex flex-wrap gap-1.5">
            {SIGNAL_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => toggleItem(selectedSignalTypes, t, setSelectedSignalTypes)}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                  selectedSignalTypes.includes(t)
                    ? "bg-green-600 border-green-500 text-white"
                    : "bg-gray-700 border-gray-600 text-gray-300 hover:border-gray-500"
                }`}
              >
                {t.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
          >
            {editing !== null ? "Update" : "Subscribe"}
          </button>
          {editing !== null && (
            <button
              type="button"
              onClick={resetForm}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-white text-sm rounded"
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
