"use client";

import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  getWatchlists,
  createWatchlist,
  deleteWatchlist,
  type Watchlist,
  type WatchlistRule,
} from "@/lib/watchlist-api";

interface WatchlistPanelProps {
  isOpen: boolean;
  onClose: () => void;
  token: string | null;
}

const RULE_TYPES = [
  "NEIGHBORHOOD",
  "ADDRESS",
  "ZONING",
  "SIGNAL_TYPE",
  "KEYWORD",
  "SEVERITY",
];

export default function WatchlistPanel({
  isOpen,
  onClose,
  token,
}: WatchlistPanelProps) {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [loading, setLoading] = useState(false);
  const [showNewForm, setShowNewForm] = useState(false);

  const [newName, setNewName] = useState("");
  const [newRules, setNewRules] = useState<WatchlistRule[]>([
    { type: "NEIGHBORHOOD", value: "" },
  ]);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadWatchlists = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await getWatchlists(token);
      setWatchlists(data);
    } catch (err) {
      console.error("Failed to load watchlists:", err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (isOpen && token) {
      loadWatchlists();
    }
  }, [isOpen, token, loadWatchlists]);

  const handleCreateWatchlist = async () => {
    if (!token) return;
    if (!newName.trim()) {
      setFormError("Name is required");
      return;
    }
    const validRules = newRules.filter((r) => r.value.trim());
    if (validRules.length === 0) {
      setFormError("At least one rule with a value is required");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      await createWatchlist(token, { name: newName.trim(), rules: validRules });
      setNewName("");
      setNewRules([{ type: "NEIGHBORHOOD", value: "" }]);
      setShowNewForm(false);
      await loadWatchlists();
    } catch (err: any) {
      setFormError(err.message || "Failed to create watchlist");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteWatchlist = async (id: number) => {
    if (!token) return;
    try {
      await deleteWatchlist(token, id);
      setWatchlists((prev) => prev.filter((w) => w.id !== id));
    } catch (err) {
      console.error("Failed to delete watchlist:", err);
    }
  };

  const addRule = () => {
    setNewRules((prev) => [...prev, { type: "NEIGHBORHOOD", value: "" }]);
  };

  const removeRule = (idx: number) => {
    setNewRules((prev) => prev.filter((_, i) => i !== idx));
  };

  const updateRule = (idx: number, field: "type" | "value", val: string) => {
    setNewRules((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, [field]: val } : r))
    );
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-[998]"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        className={cn(
          "fixed top-0 right-0 bottom-0 w-[400px] max-w-[100vw]",
          "bg-gray-900 border-l border-gray-800 z-[999]",
          "flex flex-col text-gray-100",
          "transition-transform duration-300 ease-in-out",
          isOpen ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex justify-between items-center px-5 py-4 border-b border-gray-800 bg-slate-900">
          <div className="text-[15px] font-bold">Watchlists</div>
          <button
            onClick={onClose}
            className="bg-transparent border-none text-gray-500 text-xl cursor-pointer px-2 py-1 leading-none"
          >
            x
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!token ? (
            <div className="flex flex-col items-center justify-center h-[200px] text-gray-500 text-[13px] text-center gap-2">
              <span className="text-[28px]">&#128274;</span>
              <span>Login required to manage watchlists</span>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center h-[100px] text-gray-500 text-[13px]">
              Loading watchlists...
            </div>
          ) : (
            <>
              {/* Existing Watchlists */}
              {watchlists.length === 0 && !showNewForm && (
                <div className="text-center text-gray-500 text-[13px] py-6">
                  No watchlists yet. Create one to get started.
                </div>
              )}

              {watchlists.map((wl) => (
                <div
                  key={wl.id}
                  className="p-3 bg-slate-800 rounded-md border border-gray-700 mb-2.5"
                >
                  <div className="flex justify-between items-center mb-2">
                    <div className="text-[13px] font-semibold">{wl.name}</div>
                    <button
                      onClick={() => handleDeleteWatchlist(wl.id)}
                      className="bg-transparent border-none text-red-400 text-[11px] cursor-pointer px-1.5 py-0.5"
                    >
                      Delete
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {wl.rules.map((rule, idx) => (
                      <span
                        key={idx}
                        className="text-[10px] bg-gray-700 text-gray-300 px-2 py-0.5 rounded-sm"
                      >
                        {rule.type}: {rule.value}
                      </span>
                    ))}
                  </div>
                  {wl.created_at && (
                    <div className="text-[10px] text-gray-500 mt-1.5">
                      Created: {new Date(wl.created_at).toLocaleDateString()}
                    </div>
                  )}
                </div>
              ))}

              {/* New Watchlist Form */}
              {showNewForm ? (
                <div className="p-3.5 bg-slate-900 rounded-md border border-gray-700 flex flex-col gap-3">
                  <div className="text-xs font-bold text-gray-400 uppercase">
                    New Watchlist
                  </div>

                  <div>
                    <label className="block text-[11px] text-gray-400 mb-1">
                      Name
                    </label>
                    <input
                      type="text"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="My Watchlist"
                      className="w-full px-2 py-1.5 bg-slate-800 border border-gray-700 rounded text-gray-100 text-xs"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] text-gray-400 mb-1">
                      Rules
                    </label>
                    {newRules.map((rule, idx) => (
                      <div
                        key={idx}
                        className="flex gap-1.5 mb-1.5 items-center"
                      >
                        <select
                          value={rule.type}
                          onChange={(e) =>
                            updateRule(idx, "type", e.target.value)
                          }
                          className="px-2 py-1.5 bg-slate-800 border border-gray-700 rounded text-gray-300 text-xs"
                        >
                          {RULE_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </select>
                        <input
                          type="text"
                          value={rule.value}
                          onChange={(e) =>
                            updateRule(idx, "value", e.target.value)
                          }
                          placeholder="Value"
                          className="flex-1 px-2 py-1.5 bg-slate-800 border border-gray-700 rounded text-gray-100 text-xs"
                        />
                        {newRules.length > 1 && (
                          <button
                            onClick={() => removeRule(idx)}
                            className="bg-transparent border-none text-red-400 text-sm cursor-pointer px-1 shrink-0"
                          >
                            x
                          </button>
                        )}
                      </div>
                    ))}
                    <button
                      onClick={addRule}
                      className="bg-transparent border border-dashed border-gray-700 text-blue-400 text-[11px] cursor-pointer px-2.5 py-1 rounded"
                    >
                      + Add Rule
                    </button>
                  </div>

                  {formError && (
                    <div className="text-[11px] text-red-400 px-2 py-1.5 bg-red-900/10 rounded">
                      {formError}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button
                      onClick={handleCreateWatchlist}
                      disabled={saving}
                      className={cn(
                        "flex-1 p-2 border-none rounded text-white text-xs font-semibold",
                        saving
                          ? "bg-gray-700 cursor-not-allowed"
                          : "bg-blue-500 cursor-pointer"
                      )}
                    >
                      {saving ? "Saving..." : "Create"}
                    </button>
                    <button
                      onClick={() => {
                        setShowNewForm(false);
                        setFormError(null);
                      }}
                      className="px-3.5 py-2 bg-transparent border border-gray-700 rounded text-gray-400 text-xs cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowNewForm(true)}
                  className="w-full p-2.5 bg-slate-800 border border-dashed border-gray-700 rounded-md text-blue-400 text-xs font-semibold cursor-pointer transition-all duration-200 mt-2 hover:bg-gray-700 hover:border-gray-600"
                >
                  + New Watchlist
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
