"use client";

import { useState, useEffect } from "react";
import {
  ChecklistItem,
  ChecklistCategory,
  DEFAULT_CHECKLIST_ITEMS,
  CATEGORY_LABELS,
} from "@/lib/checklist-types";

interface DueDiligenceChecklistProps {
  parcelId: string;
  initialItems?: ChecklistItem[];
}

export const DueDiligenceChecklist = ({
  parcelId,
  initialItems,
}: DueDiligenceChecklistProps) => {
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [expandedCategories, setExpandedCategories] = useState<
    Set<ChecklistCategory>
  >(new Set(["title_legal", "zoning_planning", "physical", "financial", "municipal"]));
  const [customItemInput, setCustomItemInput] = useState("");

  useEffect(() => {
    if (initialItems && initialItems.length > 0) {
      setItems(initialItems);
    } else {
      const defaultItems: ChecklistItem[] = DEFAULT_CHECKLIST_ITEMS.map(
        (item, index) => ({
          ...item,
          id: `default-${index}`,
          createdAt: new Date().toISOString(),
        })
      );
      setItems(defaultItems);
    }
  }, [initialItems]);

  const categories: ChecklistCategory[] = [
    "title_legal",
    "zoning_planning",
    "physical",
    "financial",
    "municipal",
  ];

  const getItemsByCategory = (category: ChecklistCategory): ChecklistItem[] =>
    items.filter((item) => item.category === category);

  const toggleCategory = (category: ChecklistCategory) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  const toggleItem = (id: string) => {
    setItems(
      items.map((item) =>
        item.id === id ? { ...item, checked: !item.checked } : item
      )
    );
  };

  const updateNotes = (id: string, notes: string) => {
    setItems(
      items.map((item) =>
        item.id === id ? { ...item, notes } : item
      )
    );
  };

  const addCustomItem = () => {
    if (customItemInput.trim()) {
      const newItem: ChecklistItem = {
        id: `custom-${Date.now()}`,
        label: customItemInput,
        category: "title_legal",
        checked: false,
        createdAt: new Date().toISOString(),
      };
      setItems([...items, newItem]);
      setCustomItemInput("");
    }
  };

  const removeItem = (id: string) => {
    setItems(items.filter((item) => item.id !== id));
  };

  const exportChecklist = () => {
    const exportData = {
      parcelId,
      exportedAt: new Date().toISOString(),
      items,
      progress: calculateProgress(),
    };
    const dataStr = JSON.stringify(exportData, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `checklist-${parcelId}-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const calculateProgress = (): number => {
    if (items.length === 0) return 0;
    const checked = items.filter((item) => item.checked).length;
    return Math.round((checked / items.length) * 100);
  };

  const progress = calculateProgress();

  return (
    <div className="w-full max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-md">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">
          Due Diligence Checklist
        </h1>

        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700">Progress</span>
            <span className="text-sm font-semibold text-gray-900">
              {progress}%
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="space-y-4 mb-6">
        {categories.map((category) => {
          const categoryItems = getItemsByCategory(category);
          const isExpanded = expandedCategories.has(category);
          const categoryChecked = categoryItems.filter((i) => i.checked).length;

          return (
            <div key={category} className="border rounded-lg overflow-hidden">
              <button
                onClick={() => toggleCategory(category)}
                className="w-full px-4 py-3 bg-gray-50 hover:bg-gray-100 flex items-center justify-between font-medium text-gray-900 transition-colors"
                aria-expanded={isExpanded}
              >
                <span className="flex items-center gap-2">
                  <span className="text-lg">
                    {isExpanded ? "▼" : "▶"}
                  </span>
                  {CATEGORY_LABELS[category]}
                  <span className="text-sm text-gray-500">
                    ({categoryChecked}/{categoryItems.length})
                  </span>
                </span>
              </button>

              {isExpanded && (
                <div className="p-4 space-y-3">
                  {categoryItems.map((item) => (
                    <div key={item.id} className="space-y-2">
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          id={item.id}
                          checked={item.checked}
                          onChange={() => toggleItem(item.id)}
                          className="mt-1 w-4 h-4 accent-blue-600 cursor-pointer"
                          aria-label={item.label}
                          role="checkbox"
                        />
                        <label
                          htmlFor={item.id}
                          className="flex-1 text-gray-700 cursor-pointer"
                        >
                          {item.label}
                        </label>
                        {item.id.startsWith("custom-") && (
                          <button
                            onClick={() => removeItem(item.id)}
                            className="text-xs text-red-600 hover:text-red-800 font-medium"
                            aria-label={`Remove ${item.label}`}
                          >
                            Remove
                          </button>
                        )}
                      </div>

                      {item.checked && (
                        <textarea
                          value={item.notes || ""}
                          onChange={(e) => updateNotes(item.id, e.target.value)}
                          placeholder="Add notes..."
                          className="ml-7 w-full px-3 py-2 text-sm border border-gray-300 rounded bg-gray-50 text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          rows={2}
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="space-y-4">
        <div className="bg-gray-50 p-4 rounded-lg">
          <label htmlFor="custom-item" className="block text-sm font-medium text-gray-700 mb-2">
            Add Custom Item
          </label>
          <div className="flex gap-2">
            <input
              id="custom-item"
              type="text"
              value={customItemInput}
              onChange={(e) => setCustomItemInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  addCustomItem();
                }
              }}
              placeholder="Enter custom checklist item..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={addCustomItem}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded transition-colors"
              aria-label="Add custom item"
            >
              Add
            </button>
          </div>
        </div>

        <button
          onClick={exportChecklist}
          className="w-full px-4 py-3 bg-green-600 hover:bg-green-700 text-white font-medium rounded transition-colors"
          aria-label="Export checklist as JSON"
        >
          Export as JSON
        </button>
      </div>
    </div>
  );
};
