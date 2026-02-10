"use client";

import { useState, useEffect } from "react";
import { listSavedViews, createSavedView, deleteSavedView } from "@/lib/views-api";
import type { SavedView } from "@/lib/views-api";

export default function SavedViewsDropdown({
  currentFilters,
  onLoadView,
  token,
}: {
  currentFilters: Record<string, string>;
  onLoadView: (filters: Record<string, string>) => void;
  token?: string;
}) {
  const [views, setViews] = useState<SavedView[]>([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState("");

  useEffect(() => {
    if (token) {
      listSavedViews(token).then(setViews).catch(() => {});
    }
  }, [token]);

  const handleSave = async () => {
    if (!token || !saveName.trim()) return;
    setSaving(true);
    try {
      const view = await createSavedView(token, saveName.trim(), currentFilters);
      setViews((prev) => [view, ...prev]);
      setSaveName("");
    } catch (err) {
      console.error("Save view failed:", err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!token) return;
    await deleteSavedView(token, id);
    setViews((prev) => prev.filter((v) => v.id !== id));
  };

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: "#1e293b",
          border: "1px solid #374151",
          borderRadius: "4px",
          color: "#d1d5db",
          fontSize: "12px",
          padding: "8px 10px",
          cursor: "pointer",
          width: "100%",
          textAlign: "left",
        }}
      >
        Saved Views ({views.length}) {open ? "▲" : "▼"}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            background: "#1e293b",
            border: "1px solid #374151",
            borderRadius: "0 0 6px 6px",
            zIndex: 50,
            maxHeight: "300px",
            overflowY: "auto",
          }}
        >
          {/* Save current */}
          <div style={{ padding: "8px", borderBottom: "1px solid #374151", display: "flex", gap: "4px" }}>
            <input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Save current filters as..."
              style={{
                flex: 1,
                background: "#0f172a",
                border: "1px solid #374151",
                borderRadius: "4px",
                color: "#f3f4f6",
                fontSize: "11px",
                padding: "4px 8px",
              }}
            />
            <button
              onClick={handleSave}
              disabled={saving || !saveName.trim()}
              style={{
                background: "#3b82f6",
                border: "none",
                borderRadius: "4px",
                color: "#fff",
                fontSize: "11px",
                padding: "4px 8px",
                cursor: "pointer",
              }}
            >
              Save
            </button>
          </div>

          {views.length === 0 ? (
            <div style={{ padding: "12px", textAlign: "center", color: "#6b7280", fontSize: "11px" }}>
              No saved views yet
            </div>
          ) : (
            views.map((v) => (
              <div
                key={v.id}
                style={{
                  padding: "8px",
                  borderBottom: "1px solid #374151",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  cursor: "pointer",
                }}
                onClick={() => {
                  onLoadView(v.filters);
                  setOpen(false);
                }}
              >
                <span style={{ flex: 1, fontSize: "12px", color: "#d1d5db" }}>
                  {v.name}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(v.id);
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#6b7280",
                    cursor: "pointer",
                    fontSize: "11px",
                  }}
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
