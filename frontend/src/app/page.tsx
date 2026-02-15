"use client";

import { useState, useEffect, useCallback } from "react";
import { Map, Brain, Building2, Sun, Moon, Monitor } from "lucide-react";
import MapView from "@/components/MapView";
import IntelPage from "@/components/IntelPage";
import NeighborhoodPage from "@/components/NeighborhoodPage";
import ThemeToggle from "@/components/ThemeToggle";
import AlertsFeed from "@/components/AlertsFeed";
import BottomTabBar, { type Tab } from "@/components/BottomTabBar";
import Disclaimer from "@/components/Disclaimer";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

const VALID_TABS: Tab[] = ["map", "intel", "hoods"];

function getTabFromHash(): Tab {
  if (typeof window === "undefined") return "map";
  const hash = window.location.hash.replace("#", "");
  return VALID_TABS.includes(hash as Tab) ? (hash as Tab) : "map";
}

const desktopTabs = [
  { id: "map" as Tab, label: "Map", icon: Map },
  { id: "intel" as Tab, label: "Intelligence", icon: Brain },
  { id: "hoods" as Tab, label: "Neighborhoods", icon: Building2 },
];

function AppContent() {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>(getTabFromHash);

  const handleSetTab = useCallback((tab: Tab) => {
    setActiveTab(tab);
    window.location.hash = tab;
  }, []);

  useEffect(() => {
    const onHashChange = () => setActiveTab(getTabFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return (
    <div className="flex flex-col h-dvh">
      {/* Desktop top nav — hidden on mobile */}
      <nav className="hidden md:flex items-center bg-gray-900/95 backdrop-blur-md border-b border-white/10 z-50 px-4">
        {/* Logo */}
        <div className="flex items-center gap-2 mr-auto pr-8">
          <span className="text-xl font-bold text-gray-100 font-sans">
            VanCity Lens
          </span>
          <span className="text-[11px] text-gray-500">V2</span>
        </div>

        {/* Desktop tabs */}
        <div className="flex">
          {desktopTabs.map((t) => {
            const Icon = t.icon;
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => handleSetTab(t.id)}
                className={cn(
                  "flex items-center gap-2 px-5 py-3.5 text-[13px] font-semibold border-b-2 transition-colors",
                  isActive
                    ? "bg-gray-800 border-blue-500 text-gray-100"
                    : "border-transparent text-gray-400 hover:text-gray-200"
                )}
              >
                <Icon className="w-4 h-4" />
                {t.label}
              </button>
            );
          })}
        </div>

        {/* Right side */}
        <div className="ml-auto flex items-center gap-3 pr-4">
          <AlertsFeed token={token} />
          <ThemeToggle />
        </div>
      </nav>

      {/* Content area */}
      <main className="relative flex-1 overflow-hidden mb-16 md:mb-0">
        {/* Map — always rendered, shown/hidden to preserve GL state */}
        <div
          className={cn(
            "absolute inset-0",
            activeTab === "map" ? "block" : "hidden"
          )}
        >
          <MapView />
        </div>

        <div
          className={cn(
            "absolute inset-0",
            activeTab === "intel" ? "block" : "hidden"
          )}
        >
          <IntelPage />
        </div>

        <div
          className={cn(
            "absolute inset-0",
            activeTab === "hoods" ? "block" : "hidden"
          )}
        >
          <NeighborhoodPage />
        </div>
      </main>

      {/* Mobile bottom tab bar */}
      <BottomTabBar activeTab={activeTab} onTabChange={handleSetTab} />

      {/* Disclaimer banner */}
      <Disclaimer />
    </div>
  );
}

export default function Home() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
