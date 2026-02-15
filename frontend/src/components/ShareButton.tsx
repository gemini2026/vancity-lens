"use client";

import { useState } from "react";
import { createShareLink } from "@/lib/share-api";
import { cn } from "@/lib/utils";

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
      className={cn(
        "border border-gray-600 text-gray-100 text-[11px] font-semibold px-3 py-1.5 rounded-md transition-all",
        copied ? "bg-green-500" : "bg-gray-700",
        loading ? "cursor-wait" : "cursor-pointer"
      )}
    >
      {copied ? "Copied!" : loading ? "Creating..." : "Share Link"}
    </button>
  );
}
