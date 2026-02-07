"use client";

import { useState } from "react";
import MapView from "@/components/MapView";
import IntelPage from "@/components/IntelPage";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"map" | "intel">("map");

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
        <div
          style={{
            display: "flex",
            gap: "0",
          }}
        >
          <button
            onClick={() => setActiveTab("map")}
            style={{
              padding: "14px 20px",
              background: activeTab === "map" ? "#1e293b" : "transparent",
              border: "none",
              borderBottom:
                activeTab === "map" ? "2px solid #3b82f6" : "2px solid transparent",
              color: activeTab === "map" ? "#f3f4f6" : "#9ca3af",
              fontSize: "13px",
              fontWeight: "600",
              cursor: "pointer",
              fontFamily: "system-ui, sans-serif",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              if (activeTab !== "map") {
                (e.currentTarget as HTMLButtonElement).style.color = "#d1d5db";
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== "map") {
                (e.currentTarget as HTMLButtonElement).style.color = "#9ca3af";
              }
            }}
          >
            📍 Map
          </button>
          <button
            onClick={() => setActiveTab("intel")}
            style={{
              padding: "14px 20px",
              background: activeTab === "intel" ? "#1e293b" : "transparent",
              border: "none",
              borderBottom:
                activeTab === "intel"
                  ? "2px solid #3b82f6"
                  : "2px solid transparent",
              color: activeTab === "intel" ? "#f3f4f6" : "#9ca3af",
              fontSize: "13px",
              fontWeight: "600",
              cursor: "pointer",
              fontFamily: "system-ui, sans-serif",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              if (activeTab !== "intel") {
                (e.currentTarget as HTMLButtonElement).style.color = "#d1d5db";
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== "intel") {
                (e.currentTarget as HTMLButtonElement).style.color = "#9ca3af";
              }
            }}
          >
            🧠 Intelligence
          </button>
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
      </div>
    </div>
  );
}
