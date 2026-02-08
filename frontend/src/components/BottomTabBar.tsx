"use client";

import React from "react";

interface BottomTabBarProps {
  activeTab: "map" | "intel" | "hoods" | "alerts";
  onTabChange: (tab: "map" | "intel" | "hoods" | "alerts") => void;
}

export default function BottomTabBar({ activeTab, onTabChange }: BottomTabBarProps) {
  const tabs = [
    { id: "map", label: "Map", icon: "📍" },
    { id: "intel", label: "Intel", icon: "🧠" },
    { id: "hoods", label: "Neighborhoods", icon: "🏢" },
    { id: "alerts", label: "Alerts", icon: "🔔" },
  ] as const;

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 bg-slate-900 border-t border-slate-700 z-30 safe-pb"
      role="tablist"
      aria-label="Mobile navigation tabs"
    >
      <div className="flex justify-around items-center h-16 pb-safe">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id as "map" | "intel" | "hoods" | "alerts")}
            className={`flex-1 flex flex-col items-center justify-center min-h-14 transition-all duration-200 ${
              activeTab === tab.id
                ? "text-blue-500 border-t-2 border-blue-500 bg-slate-800/50"
                : "text-gray-400 hover:text-gray-300 border-t-2 border-transparent"
            }`}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-current={activeTab === tab.id ? "page" : undefined}
          >
            <span className="text-xl mb-1">{tab.icon}</span>
            <span className="text-xs font-medium">{tab.label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}
