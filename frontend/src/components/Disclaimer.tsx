"use client";

import { useState, useEffect } from "react";

const STORAGE_KEY = "vcl_disclaimer_dismissed";

export default function Disclaimer() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const dismissed = localStorage.getItem(STORAGE_KEY);
    if (!dismissed) {
      setVisible(true);
    }
  }, []);

  const handleDismiss = () => {
    localStorage.setItem(STORAGE_KEY, "1");
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        background: "rgba(17, 24, 39, 0.92)",
        backdropFilter: "blur(8px)",
        borderTop: "1px solid rgba(255, 255, 255, 0.1)",
        padding: "12px 20px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "16px",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "12px",
          lineHeight: "1.5",
          color: "#9ca3af",
          maxWidth: "900px",
          textAlign: "center",
        }}
      >
        VanCity Lens is for informational purposes only. Not investment advice.
        All estimates are derived from public data and may contain inaccuracies.
        Verify independently before making any decisions.
      </p>
      <button
        onClick={handleDismiss}
        style={{
          flexShrink: 0,
          padding: "6px 14px",
          background: "rgba(59, 130, 246, 0.15)",
          border: "1px solid rgba(59, 130, 246, 0.3)",
          borderRadius: "4px",
          color: "#60a5fa",
          fontSize: "11px",
          fontWeight: "600",
          cursor: "pointer",
          fontFamily: "system-ui, sans-serif",
          transition: "all 0.2s",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "rgba(59, 130, 246, 0.25)";
          e.currentTarget.style.borderColor = "rgba(59, 130, 246, 0.5)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "rgba(59, 130, 246, 0.15)";
          e.currentTarget.style.borderColor = "rgba(59, 130, 246, 0.3)";
        }}
      >
        Dismiss
      </button>
    </div>
  );
}
