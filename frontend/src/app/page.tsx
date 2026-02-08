"use client";

import { useState } from "react";
import MapView from "@/components/MapView";
import IntelPage from "@/components/IntelPage";
import NeighborhoodPage from "@/components/NeighborhoodPage";
import ThemeToggle from "@/components/ThemeToggle";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"map" | "intel" | "hoods">("map");

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
          <button
            onClick={() => setActiveTab("map")}
            style={tabStyle("map")}
            onMouseEnter={handleHover("map", true)}
            onMouseLeave={handleHover("map", false)}
          >
            Map
          </button>
          <button
            onClick={() => setActiveTab("intel")}
            style={tabStyle("intel")}
            onMouseEnter={handleHover("intel", true)}
            onMouseLeave={handleHover("intel", false)}
          >
            Intelligence
          </button>
          <button
            onClick={() => setActiveTab("hoods")}
            style={tabStyle("hoods")}
            onMouseEnter={handleHover("hoods", true)}
            onMouseLeave={handleHover("hoods", false)}
          >
            Neighborhoods
          </button>
        </div>

        {/* Theme Toggle */}
        <div style={{ marginLeft: "auto", paddingRight: "16px" }}>
          <ThemeToggle />
        </div>
      </nav>

      {/* Content Area */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        {/* Map Tab */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: activeTab === "map" ? "block" : "none",
          }}
        >
          <MapView />
        </div>

        {/* Intelligence Tab */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: activeTab === "intel" ? "block" : "none",
          }}
        >
          <IntelPage />
        </div>

        {/* Neighborhoods Tab */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: activeTab === "hoods" ? "block" : "none",
          }}
        >
          <NeighborhoodPage />
        </div>
      </div>
    </div>
  );
}
