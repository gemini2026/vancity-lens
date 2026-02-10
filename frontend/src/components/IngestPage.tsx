"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { ingestUrl, getDocumentStatus } from "@/lib/intel-api";
import type { IngestResult, DocumentStatus } from "@/lib/intel-types";

interface HistoryEntry {
  url: string;
  result: IngestResult;
  timestamp: Date;
  processingStatus?: DocumentStatus | null;
}

export default function IngestPage() {
  const [urlValue, setUrlValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const pollTimers = useRef<Record<number, ReturnType<typeof setInterval>>>({});

  // Poll processing status for a document
  const pollStatus = useCallback((docId: number) => {
    if (pollTimers.current[docId]) return; // already polling
    pollTimers.current[docId] = setInterval(async () => {
      const status = await getDocumentStatus(docId);
      if (!status) return;
      setHistory((prev) =>
        prev.map((e) =>
          e.result.document_id === docId ? { ...e, processingStatus: status } : e
        )
      );
      if (status.status === "completed" || status.status === "failed") {
        clearInterval(pollTimers.current[docId]);
        delete pollTimers.current[docId];
      }
    }, 3000);
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval);
    };
  }, []);

  const handleIngest = async () => {
    const url = urlValue.trim();
    if (!url) return;

    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const res = await ingestUrl(url);
      setResult(res);
      setUrlValue("");
      setHistory((prev) => [{ url, result: res, timestamp: new Date() }, ...prev]);
      if (res.processing) {
        pollStatus(res.document_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        height: "100%",
        background: "#0a0a0a",
        fontFamily: "system-ui, sans-serif",
        color: "#f3f4f6",
        overflowY: "auto",
      }}
    >
      <div style={{ maxWidth: "720px", margin: "0 auto", padding: "32px 24px" }}>
        {/* Header */}
        <div style={{ marginBottom: "28px" }}>
          <h1 style={{ fontSize: "22px", fontWeight: "700", margin: "0 0 6px 0" }}>
            Document Ingestion
          </h1>
          <p style={{ fontSize: "13px", color: "#9ca3af", margin: 0 }}>
            Paste a URL to scrape, parse, and extract intelligence signals from public documents.
          </p>
        </div>

        {/* URL Input */}
        <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
          <input
            type="text"
            value={urlValue}
            onChange={(e) => {
              setUrlValue(e.target.value);
              setError(null);
              setResult(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleIngest();
              }
            }}
            placeholder="https://example.com/council-minutes.pdf"
            style={{
              flex: 1,
              padding: "10px 12px",
              background: "#1e293b",
              border: `1px solid ${error ? "#dc2626" : "#374151"}`,
              borderRadius: "6px",
              color: "#d1d5db",
              fontSize: "13px",
              fontFamily: "inherit",
            }}
          />
          <button
            onClick={handleIngest}
            disabled={loading || !urlValue.trim()}
            style={{
              padding: "10px 20px",
              background: loading ? "#4b5563" : "#8b5cf6",
              border: "none",
              borderRadius: "6px",
              color: "#ffffff",
              fontSize: "13px",
              fontWeight: "600",
              cursor: loading ? "not-allowed" : "pointer",
              whiteSpace: "nowrap",
              transition: "background 0.2s",
            }}
            onMouseEnter={(e) => {
              if (!loading)
                (e.currentTarget as HTMLButtonElement).style.background = "#7c3aed";
            }}
            onMouseLeave={(e) => {
              if (!loading)
                (e.currentTarget as HTMLButtonElement).style.background = "#8b5cf6";
            }}
          >
            {loading ? "Ingesting..." : "Ingest"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              fontSize: "12px",
              color: "#f87171",
              padding: "8px 10px",
              background: "rgba(220,38,38,0.1)",
              borderRadius: "6px",
              marginBottom: "12px",
            }}
          >
            {error}
          </div>
        )}

        {/* Success */}
        {result && (
          <div
            style={{
              fontSize: "12px",
              color: result.status === "new" ? "#34d399" : "#fbbf24",
              padding: "8px 10px",
              background:
                result.status === "new"
                  ? "rgba(52,211,153,0.1)"
                  : "rgba(251,191,36,0.1)",
              borderRadius: "6px",
              marginBottom: "12px",
            }}
          >
            {result.status === "new" ? (
              <>
                Ingested: <strong>{result.title}</strong> (
                {result.text_length.toLocaleString()} chars, {result.page_count}{" "}
                pages)
                {result.processing && " — Processing signals..."}
              </>
            ) : (
              <>
                Already ingested: <strong>{result.title}</strong> (doc #
                {result.document_id})
              </>
            )}
          </div>
        )}

        {/* Session History */}
        {history.length > 0 && (
          <div style={{ marginTop: "32px" }}>
            <h2
              style={{
                fontSize: "14px",
                fontWeight: "600",
                color: "#d1d5db",
                marginBottom: "12px",
              }}
            >
              Session History
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {history.map((entry, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "10px 12px",
                    background: "#111827",
                    border: "1px solid #1f2937",
                    borderRadius: "6px",
                    fontSize: "12px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "4px",
                    }}
                  >
                    <span style={{ fontWeight: "600", color: "#f3f4f6" }}>
                      {entry.result.title || "Untitled"}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        color:
                          entry.result.status === "new" ? "#34d399" : "#fbbf24",
                        background:
                          entry.result.status === "new"
                            ? "rgba(52,211,153,0.15)"
                            : "rgba(251,191,36,0.15)",
                        padding: "2px 6px",
                        borderRadius: "3px",
                        fontWeight: "600",
                      }}
                    >
                      {entry.result.status === "new" ? "NEW" : "EXISTS"}
                    </span>
                  </div>
                  <div style={{ color: "#6b7280", fontSize: "11px" }}>
                    <span style={{ wordBreak: "break-all" }}>{entry.url}</span>
                    <span style={{ margin: "0 6px" }}>·</span>
                    <span>
                      {entry.result.text_length.toLocaleString()} chars
                    </span>
                    <span style={{ margin: "0 6px" }}>·</span>
                    <span>
                      {entry.timestamp.toLocaleTimeString()}
                    </span>
                  </div>
                  {entry.processingStatus && (
                    <div style={{ marginTop: "6px", fontSize: "11px" }}>
                      <span
                        style={{
                          color:
                            entry.processingStatus.status === "completed"
                              ? "#34d399"
                              : entry.processingStatus.status === "failed"
                              ? "#f87171"
                              : "#60a5fa",
                        }}
                      >
                        {entry.processingStatus.status === "completed"
                          ? `Done: ${entry.processingStatus.chunk_count} chunks, ${entry.processingStatus.signal_count} signals`
                          : entry.processingStatus.status === "failed"
                          ? "Processing failed"
                          : `Processing... ${entry.processingStatus.chunk_count} chunks so far`}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
