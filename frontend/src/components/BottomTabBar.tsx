"use client";

import { Map, Brain, Building2, Bell } from "lucide-react";
import { cn } from "@/lib/utils";

export type Tab = "map" | "intel" | "hoods";

interface BottomTabBarProps {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
}

const tabs = [
  { id: "map" as Tab, label: "Map", icon: Map },
  { id: "intel" as Tab, label: "Intel", icon: Brain },
  { id: "hoods" as Tab, label: "Hoods", icon: Building2 },
];

export default function BottomTabBar({ activeTab, onTabChange }: BottomTabBarProps) {
  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-surface/95 backdrop-blur-md border-t border-border safe-area-bottom"
      role="tablist"
      aria-label="Navigation"
    >
      <div className="flex items-stretch h-16">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                "flex-1 flex flex-col items-center justify-center gap-0.5 transition-colors",
                isActive
                  ? "text-brand"
                  : "text-foreground-muted hover:text-foreground-secondary"
              )}
              role="tab"
              aria-selected={isActive}
            >
              <Icon className="w-5 h-5" />
              <span className="text-[10px] font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
