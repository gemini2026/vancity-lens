"use client";

import { useState, useEffect } from "react";

const STORAGE_KEY = "vcl_disclaimer_dismissed";

export default function Disclaimer() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true);
    }
  }, []);

  const handleDismiss = () => {
    localStorage.setItem(STORAGE_KEY, "1");
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-16 md:bottom-0 inset-x-0 z-40 bg-[var(--color-panel)] backdrop-blur-md border-t border-[var(--color-panel-border)] px-5 py-1.5 flex items-center justify-center gap-4">
      <p className="m-0 text-[11px] leading-relaxed text-[var(--color-foreground-muted)] max-w-[900px] text-center">
        For informational purposes only — not investment advice. Verify independently before making decisions.
      </p>
      <button
        onClick={handleDismiss}
        className="shrink-0 px-3 py-1 bg-blue-500/15 border border-blue-500/30 rounded text-blue-400 text-[11px] font-semibold cursor-pointer transition-colors hover:bg-blue-500/25 hover:border-blue-500/50"
      >
        Dismiss
      </button>
    </div>
  );
}
