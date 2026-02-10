"use client";

import { useState } from "react";
import { createShareLink } from "@/lib/share-api";

export default function ShareButton({ pid }: { pid: string }) {
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleShare = async () => {
    setLoading(true);
    try {
      const result = await createShareLink(pid);
      await navigator.clipboard.writeText(result.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Share failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleShare}
      disabled={loading}
      style={{
        background: copied ? "#22c55e" : "#374151",
        border: "1px solid #4b5563",
        color: "#f3f4f6",
        fontSize: "11px",
        fontWeight: 600,
        padding: "6px 12px",
        borderRadius: "6px",
        cursor: loading ? "wait" : "pointer",
        transition: "all 0.2s",
      }}
    >
      {copied ? "Copied!" : loading ? "Creating..." : "Share Link"}
    </button>
  );
}
