"use client";

import { useState, useEffect, useCallback } from "react";
import MapView from "@/components/MapView";
import IntelPage from "@/components/IntelPage";
import NeighborhoodPage from "@/components/NeighborhoodPage";
import ThemeToggle from "@/components/ThemeToggle";
import AlertsFeed from "@/components/AlertsFeed";
import Disclaimer from "@/components/Disclaimer";
import { AuthProvider, useAuth } from "@/lib/auth-context";

type Tab = "map" | "intel" | "hoods";

const VALID_TABS: Tab[] = ["map", "intel", "hoods"];

function getTabFromHash(): Tab {
  if (typeof window === "undefined") return "map";
  const hash = window.location.hash.replace("#", "");
  return VALID_TABS.includes(hash as Tab) ? (hash as Tab) : "map";
}

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

  const tabStyle = (tab: string) => ({
    padding: "14px 20px",
    background: activeTab === tab ? "#1e293b" : "transparent",
    border: "none",
    borderBottom:
      activeTab === tab ? "2px solid #3b82f6" : "2px solid transparent",
    color: activeTab === tab ? "#f3f4f6" : "#9ca3af",
    fontSize: "13px",
    fontWeight: "600" as const,
    cursor: "pointer" as const,
    fontFamily: "system-ui, sans-serif",
    transition: "all 0.2s",
  });

  const handleHover = (tab: string, entering: boolean) => (
    e: React.MouseEvent<HTMLButtonElement>
  ) => {
    if (activeTab !== tab) {
      e.currentTarget.style.color = entering ? "#d1d5db" : "#9ca3af";
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "map", label: "Map" },
    { key: "intel", label: "Intelligence" },
    { key: "hoods", label: "Neighborhoods" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Navigation Bar */}
      <nav
        style={{
          display: "flex",
          alignItems: "center",
          background: "rgba(15, 23, 42, 0.95)",
          borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
          backdropFilter: "blur(8px)",
          zIndex: 50,
          padding: "0 16px",
        }}
      >
        {/* Logo */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginRight: "auto",
            paddingRight: "32px",
          }}
        >
          <div
            style={{
              fontSize: "20px",
              fontWeight: "700",
              color: "#f3f4f6",
              fontFamily: "system-ui, sans-serif",
            }}
          >
            VanCity Lens
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "#6b7280",
              fontFamily: "system-ui, sans-serif",
            }}
          >
            V2
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: "flex", gap: "0" }}>
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => handleSetTab(t.key)}
              style={tabStyle(t.key)}
              onMouseEnter={handleHover(t.key, true)}
              onMouseLeave={handleHover(t.key, false)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Right side: Theme Toggle */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "12px", paddingRight: "16px" }}>
          <AlertsFeed token={token} />
          <ThemeToggle />
        </div>
      </nav>

      {/* Content Area */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            top: 0, left: 0, right: 0, bottom: 0,
            display: activeTab === "map" ? "block" : "none",
          }}
        >
          <MapView />
        </div>

        <div
          style={{
            position: "absolute",
            top: 0, left: 0, right: 0, bottom: 0,
            display: activeTab === "intel" ? "block" : "none",
          }}
        >
          <IntelPage />
        </div>

        <div
          style={{
            position: "absolute",
            top: 0, left: 0, right: 0, bottom: 0,
            display: activeTab === "hoods" ? "block" : "none",
          }}
        >
          <NeighborhoodPage />
        </div>

      </div>

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
