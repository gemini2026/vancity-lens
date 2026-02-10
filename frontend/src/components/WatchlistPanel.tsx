"use client";

import { useState, useEffect, useCallback } from "react";
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

  // New watchlist form state
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

  const selectStyle: React.CSSProperties = {
    padding: "6px 8px",
    background: "#1e293b",
    border: "1px solid #374151",
    borderRadius: "4px",
    color: "#d1d5db",
    fontSize: "12px",
    fontFamily: "system-ui, sans-serif",
  };

  const inputStyle: React.CSSProperties = {
    flex: 1,
    padding: "6px 8px",
    background: "#1e293b",
    border: "1px solid #374151",
    borderRadius: "4px",
    color: "#f3f4f6",
    fontSize: "12px",
    fontFamily: "system-ui, sans-serif",
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.4)",
            zIndex: 998,
          }}
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width: "400px",
          maxWidth: "100vw",
          background: "#111827",
          borderLeft: "1px solid #1f2937",
          zIndex: 999,
          transform: isOpen ? "translateX(0)" : "translateX(100%)",
          transition: "transform 0.3s ease-in-out",
          display: "flex",
          flexDirection: "column",
          fontFamily: "system-ui, sans-serif",
          color: "#f3f4f6",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "16px 20px",
            borderBottom: "1px solid #1f2937",
            background: "#0f172a",
          }}
        >
          <div style={{ fontSize: "15px", fontWeight: "700" }}>
            Watchlists
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#6b7280",
              fontSize: "20px",
              cursor: "pointer",
              padding: "4px 8px",
              lineHeight: "1",
            }}
          >
            x
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {!token ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "200px",
                color: "#6b7280",
                fontSize: "13px",
                textAlign: "center",
                gap: "8px",
              }}
            >
              <span style={{ fontSize: "28px" }}>&#128274;</span>
              <span>Login required to manage watchlists</span>
            </div>
          ) : loading ? (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100px",
                color: "#6b7280",
                fontSize: "13px",
              }}
            >
              Loading watchlists...
            </div>
          ) : (
            <>
              {/* Existing Watchlists */}
              {watchlists.length === 0 && !showNewForm && (
                <div
                  style={{
                    textAlign: "center",
                    color: "#6b7280",
                    fontSize: "13px",
                    padding: "24px 0",
                  }}
                >
                  No watchlists yet. Create one to get started.
                </div>
              )}

              {watchlists.map((wl) => (
                <div
                  key={wl.id}
                  style={{
                    padding: "12px",
                    background: "#1e293b",
                    borderRadius: "6px",
                    border: "1px solid #374151",
                    marginBottom: "10px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "8px",
                    }}
                  >
                    <div style={{ fontSize: "13px", fontWeight: "600" }}>
                      {wl.name}
                    </div>
                    <button
                      onClick={() => handleDeleteWatchlist(wl.id)}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#f87171",
                        fontSize: "11px",
                        cursor: "pointer",
                        padding: "2px 6px",
                      }}
                    >
                      Delete
                    </button>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "4px",
                    }}
                  >
                    {wl.rules.map((rule, idx) => (
                      <span
                        key={idx}
                        style={{
                          fontSize: "10px",
                          background: "#374151",
                          color: "#d1d5db",
                          padding: "2px 8px",
                          borderRadius: "3px",
                        }}
                      >
                        {rule.type}: {rule.value}
                      </span>
                    ))}
                  </div>
                  {wl.created_at && (
                    <div
                      style={{
                        fontSize: "10px",
                        color: "#6b7280",
                        marginTop: "6px",
                      }}
                    >
                      Created: {new Date(wl.created_at).toLocaleDateString()}
                    </div>
                  )}
                </div>
              ))}

              {/* New Watchlist Form */}
              {showNewForm ? (
                <div
                  style={{
                    padding: "14px",
                    background: "#0f172a",
                    borderRadius: "6px",
                    border: "1px solid #374151",
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  <div
                    style={{
                      fontSize: "12px",
                      fontWeight: "700",
                      color: "#9ca3af",
                      textTransform: "uppercase",
                    }}
                  >
                    New Watchlist
                  </div>

                  <div>
                    <label
                      style={{
                        display: "block",
                        fontSize: "11px",
                        color: "#9ca3af",
                        marginBottom: "4px",
                      }}
                    >
                      Name
                    </label>
                    <input
                      type="text"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="My Watchlist"
                      style={{
                        ...inputStyle,
                        width: "100%",
                        flex: "unset" as any,
                      }}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: "block",
                        fontSize: "11px",
                        color: "#9ca3af",
                        marginBottom: "4px",
                      }}
                    >
                      Rules
                    </label>
                    {newRules.map((rule, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          gap: "6px",
                          marginBottom: "6px",
                          alignItems: "center",
                        }}
                      >
                        <select
                          value={rule.type}
                          onChange={(e) =>
                            updateRule(idx, "type", e.target.value)
                          }
                          style={selectStyle}
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
                          style={inputStyle}
                        />
                        {newRules.length > 1 && (
                          <button
                            onClick={() => removeRule(idx)}
                            style={{
                              background: "none",
                              border: "none",
                              color: "#f87171",
                              fontSize: "14px",
                              cursor: "pointer",
                              padding: "0 4px",
                              flexShrink: 0,
                            }}
                          >
                            x
                          </button>
                        )}
                      </div>
                    ))}
                    <button
                      onClick={addRule}
                      style={{
                        background: "none",
                        border: "1px dashed #374151",
                        color: "#60a5fa",
                        fontSize: "11px",
                        cursor: "pointer",
                        padding: "4px 10px",
                        borderRadius: "4px",
                        fontFamily: "system-ui, sans-serif",
                      }}
                    >
                      + Add Rule
                    </button>
                  </div>

                  {formError && (
                    <div
                      style={{
                        fontSize: "11px",
                        color: "#f87171",
                        padding: "6px 8px",
                        background: "rgba(220, 38, 38, 0.1)",
                        borderRadius: "4px",
                      }}
                    >
                      {formError}
                    </div>
                  )}

                  <div style={{ display: "flex", gap: "8px" }}>
                    <button
                      onClick={handleCreateWatchlist}
                      disabled={saving}
                      style={{
                        flex: 1,
                        padding: "8px",
                        background: saving ? "#374151" : "#3b82f6",
                        border: "none",
                        borderRadius: "4px",
                        color: "#fff",
                        fontSize: "12px",
                        fontWeight: "600",
                        cursor: saving ? "not-allowed" : "pointer",
                        fontFamily: "system-ui, sans-serif",
                      }}
                    >
                      {saving ? "Saving..." : "Create"}
                    </button>
                    <button
                      onClick={() => {
                        setShowNewForm(false);
                        setFormError(null);
                      }}
                      style={{
                        padding: "8px 14px",
                        background: "transparent",
                        border: "1px solid #374151",
                        borderRadius: "4px",
                        color: "#9ca3af",
                        fontSize: "12px",
                        cursor: "pointer",
                        fontFamily: "system-ui, sans-serif",
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowNewForm(true)}
                  style={{
                    width: "100%",
                    padding: "10px",
                    background: "#1e293b",
                    border: "1px dashed #374151",
                    borderRadius: "6px",
                    color: "#60a5fa",
                    fontSize: "12px",
                    fontWeight: "600",
                    cursor: "pointer",
                    fontFamily: "system-ui, sans-serif",
                    transition: "all 0.2s",
                    marginTop: "8px",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "#374151";
                    e.currentTarget.style.borderColor = "#4b5563";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "#1e293b";
                    e.currentTarget.style.borderColor = "#374151";
                  }}
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
