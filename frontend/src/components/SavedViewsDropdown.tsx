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
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="bg-slate-800 border border-gray-700 rounded text-gray-300 text-xs px-2.5 py-2 cursor-pointer w-full text-left"
      >
        Saved Views ({views.length}) {open ? "\u25B2" : "\u25BC"}
      </button>

      {open && (
        <div className="absolute top-full left-0 right-0 bg-slate-800 border border-gray-700 rounded-b-md z-50 max-h-[300px] overflow-y-auto">
          {/* Save current */}
          <div className="p-2 border-b border-gray-700 flex gap-1">
            <input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Save current filters as..."
              className="flex-1 bg-slate-900 border border-gray-700 rounded text-gray-100 text-[11px] px-2 py-1"
            />
            <button
              onClick={handleSave}
              disabled={saving || !saveName.trim()}
              className="bg-blue-500 border-none rounded text-white text-[11px] px-2 py-1 cursor-pointer"
            >
              Save
            </button>
          </div>

          {views.length === 0 ? (
            <div className="p-3 text-center text-gray-500 text-[11px]">
              No saved views yet
            </div>
          ) : (
            views.map((v) => (
              <div
                key={v.id}
                className="p-2 border-b border-gray-700 flex items-center gap-2 cursor-pointer hover:bg-gray-700"
                onClick={() => {
                  onLoadView(v.filters);
                  setOpen(false);
                }}
              >
                <span className="flex-1 text-xs text-gray-300">{v.name}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(v.id);
                  }}
                  className="bg-transparent border-none text-gray-500 cursor-pointer text-[11px] hover:text-gray-300"
                >
                  &#10005;
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
