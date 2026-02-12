"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  chatWithIntel,
  getSignalFeed,
  getSignalDocument,
  getIntelStats,
  getNeighborhoods,
} from "@/lib/intel-api";
import type {
  ChatMessage,
  IntelSignal,
  SignalDocument,
  SourceCitation,
  IntelStats,
  SignalType,
  Severity,
} from "@/lib/intel-types";
import ExportButton from "./ExportButton";

const SIGNAL_TYPE_LABELS: Record<SignalType, string> = {
  rezoning_decision: "REZONING DECISION",
  permit_approval: "PERMIT APPROVAL",
  policy_change: "POLICY CHANGE",
  community_opposition: "COMMUNITY OPPOSITION",
  density_change: "DENSITY CHANGE",
  development_proposal: "DEVELOPMENT PROPOSAL",
  infrastructure_investment: "INFRASTRUCTURE INVESTMENT",
};

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#f59e0b",
  low: "#10b981",
};

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "🔴",
  high: "🟠",
  medium: "🟡",
  low: "🟢",
};

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (date.toDateString() === today.toDateString()) return "Today";
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";

  const days = Math.floor(
    (today.getTime() - date.getTime()) / (1000 * 60 * 60 * 24)
  );
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return date.toLocaleDateString();
}

interface ChatMessageWithId extends ChatMessage {
  id: string;
}

export default function IntelPage() {
  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessageWithId[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Signal feed state
  const [signals, setSignals] = useState<IntelSignal[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [signalOffset, setSignalOffset] = useState(0);
  const [signalsHasMore, setSignalsHasMore] = useState(false);

  // Filter state
  const [neighborhoods, setNeighborhoods] = useState<string[]>([]);
  const [selectedNeighborhood, setSelectedNeighborhood] = useState<string>("");
  const [selectedSignalType, setSelectedSignalType] = useState<
    SignalType | ""
  >("");
  const [selectedDateRange, setSelectedDateRange] = useState<
    "7d" | "30d" | "90d" | "all"
  >("7d");

  // Stats state
  const [stats, setStats] = useState<IntelStats | null>(null);

  // Expanded signal document state
  const [expandedSignalId, setExpandedSignalId] = useState<string | null>(null);
  const [expandedDoc, setExpandedDoc] = useState<SignalDocument | null>(null);
  const [expandedLoading, setExpandedLoading] = useState(false);

  const handleToggleExpand = useCallback(
    async (signalId: string) => {
      if (expandedSignalId === signalId) {
        setExpandedSignalId(null);
        setExpandedDoc(null);
        return;
      }
      setExpandedSignalId(signalId);
      setExpandedDoc(null);
      setExpandedLoading(true);
      try {
        const doc = await getSignalDocument(signalId);
        setExpandedDoc(doc);
      } catch (err) {
        console.error("Failed to load document:", err);
      } finally {
        setExpandedLoading(false);
      }
    },
    [expandedSignalId]
  );

  // Auto-scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const [statsData, neighborhoodsData] = await Promise.all([
          getIntelStats(),
          getNeighborhoods(),
        ]);
        setStats(statsData);
        setNeighborhoods(neighborhoodsData);

        // Load initial signals
        const feedData = await getSignalFeed({
          limit: 20,
          date_range: "7d",
        });
        setSignals(feedData.signals);
        setSignalsHasMore(feedData.has_more);
      } catch (err) {
        console.error("Failed to load initial data:", err);
      }
    };

    loadInitialData();
  }, []);

  // Load signals when filters change
  useEffect(() => {
    const loadSignals = async () => {
      setSignalsLoading(true);
      try {
        const feedData = await getSignalFeed({
          neighborhood: selectedNeighborhood || undefined,
          signal_type: selectedSignalType || undefined,
          date_range: selectedDateRange,
          limit: 20,
          offset: 0,
        });
        setSignals(feedData.signals);
        setSignalsHasMore(feedData.has_more);
        setSignalOffset(0);
      } catch (err) {
        console.error("Failed to load signals:", err);
      } finally {
        setSignalsLoading(false);
      }
    };

    loadSignals();
  }, [selectedNeighborhood, selectedSignalType, selectedDateRange]);

  // Load more signals
  const handleLoadMoreSignals = async () => {
    const nextOffset = signalOffset + 20;
    setSignalsLoading(true);
    try {
      const feedData = await getSignalFeed({
        neighborhood: selectedNeighborhood || undefined,
        signal_type: selectedSignalType || undefined,
        date_range: selectedDateRange,
        limit: 20,
        offset: nextOffset,
      });
      setSignals((prev) => [...prev, ...feedData.signals]);
      setSignalsHasMore(feedData.has_more);
      setSignalOffset(nextOffset);
    } catch (err) {
      console.error("Failed to load more signals:", err);
    } finally {
      setSignalsLoading(false);
    }
  };

  // Handle chat submission
  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;

    const userMessage: ChatMessageWithId = {
      id: `msg-${Date.now()}`,
      role: "user",
      content: inputValue,
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setChatLoading(true);

    try {
      const response = await chatWithIntel(inputValue, {
        session_id: sessionId || undefined,
        include_signals: true,
      });

      if (!sessionId) setSessionId(response.session_id);

      const assistantMessage: ChatMessageWithId = {
        id: `msg-${Date.now()}-assistant`,
        role: "assistant",
        content: response.answer,
        citations: response.citations,
        related_signals: response.related_signals.map((s) => s.id),
      };

      setChatMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      console.error("Chat failed:", err);
      const errorMessage: ChatMessageWithId = {
        id: `msg-${Date.now()}-error`,
        role: "assistant",
        content:
          "Sorry, I encountered an error processing your question. Please try again.",
      };
      setChatMessages((prev) => [...prev, errorMessage]);
    } finally {
      setChatLoading(false);
    }
  };

  const starterQueries = [
    "What rezoning applications were approved recently?",
    "What's happening in Mount Pleasant?",
    "Show me density changes near Broadway stations",
    "Any community opposition to new developments?",
  ];

  return (
    <div
      style={{
        display: "flex",
        height: "100%",
        background: "#0a0a0a",
        fontFamily: "system-ui, sans-serif",
        color: "#f3f4f6",
      }}
    >
      {/* Left Column: Chat Panel */}
      <div
        style={{
          flex: "0 0 60%",
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid #1f2937",
          background: "#111827",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid #1f2937",
            background: "#0f172a",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span style={{ fontSize: "20px" }}>🧠</span>
          <div>
            <div style={{ fontSize: "14px", fontWeight: "600" }}>
              Ask VanCity Lens
            </div>
            <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "2px" }}>
              Intelligence for real estate development
            </div>
          </div>
        </div>

        {/* Messages List */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "16px 20px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          {chatMessages.length === 0 ? (
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: "20px",
              }}
            >
              <div style={{ fontSize: "28px" }}>💡</div>
              <div style={{ fontSize: "13px", color: "#6b7280", textAlign: "center" }}>
                Ask about rezoning decisions, permits, community feedback, and more
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  width: "100%",
                  maxWidth: "400px",
                }}
              >
                {starterQueries.map((query, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setInputValue(query);
                    }}
                    style={{
                      padding: "10px 12px",
                      background: "#1e293b",
                      border: "1px solid #374151",
                      color: "#d1d5db",
                      borderRadius: "6px",
                      fontSize: "12px",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "all 0.2s",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background =
                        "#374151";
                      (e.currentTarget as HTMLButtonElement).style.borderColor =
                        "#4b5563";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background =
                        "#1e293b";
                      (e.currentTarget as HTMLButtonElement).style.borderColor =
                        "#374151";
                    }}
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    display: "flex",
                    justifyContent:
                      msg.role === "user" ? "flex-end" : "flex-start",
                  }}
                >
                  <div
                    style={{
                      maxWidth: "85%",
                      padding: "12px 14px",
                      borderRadius: "8px",
                      background:
                        msg.role === "user" ? "#3b82f6" : "#1e293b",
                      color: msg.role === "user" ? "#ffffff" : "#d1d5db",
                      fontSize: "13px",
                      lineHeight: "1.5",
                      wordWrap: "break-word",
                    }}
                  >
                    <div>{msg.content}</div>
                    {msg.citations && msg.citations.length > 0 && (
                      <div
                        style={{
                          marginTop: "8px",
                          paddingTop: "8px",
                          borderTop:
                            msg.role === "user"
                              ? "1px solid rgba(255,255,255,0.2)"
                              : "1px solid #374151",
                          display: "flex",
                          flexWrap: "wrap",
                          gap: "6px",
                        }}
                      >
                        {msg.citations.map((citation, idx) => {
                          const citationHref = citation.document_id
                            ? `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"}/api/v1/intel/documents/${citation.document_id}/page`
                            : citation.document_url;
                          return (
                            <a
                              key={idx}
                              href={citationHref}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                display: "inline-block",
                                padding: "4px 8px",
                                background:
                                  msg.role === "user"
                                    ? "rgba(255,255,255,0.15)"
                                    : "#374151",
                                borderRadius: "4px",
                                fontSize: "11px",
                                color:
                                  msg.role === "user"
                                    ? "#f3f4f6"
                                    : "#60a5fa",
                                textDecoration: "none",
                                whiteSpace: "nowrap",
                              }}
                              title={`${citation.document_title}${citation.published_date ? ` (${citation.published_date})` : ""}`}
                            >
                              {citation.document_title.slice(0, 25)}…
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div style={{ display: "flex", justifyContent: "flex-start" }}>
                  <div
                    style={{
                      padding: "12px 14px",
                      borderRadius: "8px",
                      background: "#1e293b",
                      color: "#6b7280",
                      fontSize: "13px",
                    }}
                  >
                    <span
                      style={{
                        display: "inline-block",
                        animation: "pulse 1.5s infinite",
                      }}
                    >
                      ●●●
                    </span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input Area */}
        <div
          style={{
            padding: "16px 20px",
            borderTop: "1px solid #1f2937",
            background: "#0f172a",
            display: "flex",
            gap: "8px",
          }}
        >
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            placeholder="Ask about developments, permits, zoning..."
            style={{
              flex: 1,
              padding: "10px 12px",
              background: "#1e293b",
              border: "1px solid #374151",
              borderRadius: "6px",
              color: "#f3f4f6",
              fontSize: "13px",
              fontFamily: "inherit",
            }}
          />
          <button
            onClick={handleSendMessage}
            disabled={chatLoading || !inputValue.trim()}
            style={{
              padding: "10px 16px",
              background: chatLoading ? "#4b5563" : "#3b82f6",
              border: "none",
              borderRadius: "6px",
              color: "#ffffff",
              fontSize: "13px",
              fontWeight: "600",
              cursor: chatLoading ? "not-allowed" : "pointer",
              transition: "background 0.2s",
            }}
            onMouseEnter={(e) => {
              if (!chatLoading) {
                (e.currentTarget as HTMLButtonElement).style.background =
                  "#2563eb";
              }
            }}
            onMouseLeave={(e) => {
              if (!chatLoading) {
                (e.currentTarget as HTMLButtonElement).style.background =
                  "#3b82f6";
              }
            }}
          >
            →
          </button>
        </div>

        <style>{`
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
          }
        `}</style>
      </div>

      {/* Right Column: Signal Feed */}
      <div
        style={{
          flex: "0 0 40%",
          display: "flex",
          flexDirection: "column",
          background: "#0a0a0a",
          borderLeft: "1px solid #1f2937",
        }}
      >
        {/* Header with Stats */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #1f2937" }}>
          <div
            style={{
              display: "flex",
              gap: "16px",
              marginBottom: "14px",
              fontSize: "12px",
              color: "#9ca3af",
            }}
          >
            {stats && (
              <>
                <div>
                  <span style={{ fontWeight: "600", color: "#f3f4f6" }}>
                    {stats.total_signals}
                  </span>{" "}
                  signals
                </div>
                <div>
                  <span style={{ fontWeight: "600", color: "#f3f4f6" }}>
                    {Object.keys(stats.by_neighborhood).length}
                  </span>{" "}
                  neighborhoods
                </div>
                <div>
                  Last updated: <span style={{ color: "#6b7280" }}>2h ago</span>
                </div>
              </>
            )}
          </div>

          {/* Filters */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <select
              value={selectedNeighborhood}
              onChange={(e) => setSelectedNeighborhood(e.target.value)}
              style={{
                padding: "8px 10px",
                background: "#1e293b",
                border: "1px solid #374151",
                borderRadius: "4px",
                color: "#d1d5db",
                fontSize: "12px",
              }}
            >
              <option value="">All neighborhoods</option>
              {neighborhoods.map((neighborhood) => (
                <option key={neighborhood} value={neighborhood}>
                  {neighborhood}
                </option>
              ))}
            </select>

            <select
              value={selectedSignalType}
              onChange={(e) => setSelectedSignalType(e.target.value as SignalType | "")}
              style={{
                padding: "8px 10px",
                background: "#1e293b",
                border: "1px solid #374151",
                borderRadius: "4px",
                color: "#d1d5db",
                fontSize: "12px",
              }}
            >
              <option value="">All signal types</option>
              {Object.entries(SIGNAL_TYPE_LABELS).map(([type, label]) => (
                <option key={type} value={type}>
                  {label}
                </option>
              ))}
            </select>

            <select
              value={selectedDateRange}
              onChange={(e) =>
                setSelectedDateRange(e.target.value as "7d" | "30d" | "90d" | "all")
              }
              style={{
                padding: "8px 10px",
                background: "#1e293b",
                border: "1px solid #374151",
                borderRadius: "4px",
                color: "#d1d5db",
                fontSize: "12px",
              }}
            >
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
              <option value="all">All time</option>
            </select>
          </div>
          <ExportButton exportType="signals" filters={{
            ...(selectedNeighborhood ? { neighborhood: selectedNeighborhood } : {}),
            ...(selectedSignalType ? { signal_type: selectedSignalType } : {}),
            date_range: selectedDateRange,
          }} label="Export CSV" />
        </div>

        {/* Signals List */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "16px 20px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          {signals.length === 0 ? (
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#6b7280",
                fontSize: "13px",
              }}
            >
              No signals found
            </div>
          ) : (
            <>
              {signals.map((signal) => (
                <div
                  key={signal.id}
                  style={{
                    padding: "12px",
                    background:
                      expandedSignalId === signal.id
                        ? "#1a2744"
                        : "#1e293b",
                    borderRadius: "6px",
                    border:
                      expandedSignalId === signal.id
                        ? "1px solid #3b82f6"
                        : "1px solid #374151",
                    fontSize: "12px",
                    cursor: "pointer",
                    transition: "all 0.2s",
                  }}
                  onClick={() => handleToggleExpand(signal.id)}
                >
                  {/* Top row: Severity + Type */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      marginBottom: "6px",
                    }}
                  >
                    <span style={{ fontSize: "16px" }}>
                      {SEVERITY_DOT[signal.severity]}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: "600",
                        color: "#9ca3af",
                        background: "#374151",
                        padding: "2px 6px",
                        borderRadius: "3px",
                      }}
                    >
                      {SIGNAL_TYPE_LABELS[signal.signal_type]}
                    </span>
                    {signal.decision && (
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: "600",
                          color:
                            signal.decision.toUpperCase() === "APPROVED"
                              ? "#f3f4f6"
                              : "#f87171",
                          background:
                            signal.decision.toUpperCase() === "APPROVED"
                              ? "#10b981"
                              : "#dc2626",
                          padding: "2px 6px",
                          borderRadius: "3px",
                        }}
                      >
                        {signal.decision.toUpperCase()}
                      </span>
                    )}
                    <span
                      style={{
                        marginLeft: "auto",
                        fontSize: "10px",
                        color: "#6b7280",
                      }}
                    >
                      {expandedSignalId === signal.id ? "▲" : "▼"}
                    </span>
                  </div>

                  {/* Headline */}
                  <div
                    style={{
                      fontWeight: "600",
                      color: "#f3f4f6",
                      marginBottom: "4px",
                      lineHeight: "1.4",
                    }}
                  >
                    {signal.headline}
                  </div>

                  {/* Summary */}
                  <div
                    style={{
                      color: "#9ca3af",
                      fontSize: "11px",
                      marginBottom: "6px",
                      lineHeight: "1.4",
                      ...(expandedSignalId === signal.id
                        ? {}
                        : {
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical" as const,
                            overflow: "hidden",
                          }),
                    }}
                  >
                    {signal.summary}
                  </div>

                  {/* Addresses */}
                  {signal.addresses && signal.addresses.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "4px",
                        marginBottom: "6px",
                      }}
                    >
                      {signal.addresses.slice(0, 2).map((addr, idx) => (
                        <span
                          key={idx}
                          style={{
                            fontSize: "10px",
                            background: "#374151",
                            color: "#d1d5db",
                            padding: "2px 6px",
                            borderRadius: "3px",
                          }}
                        >
                          📍 {addr}
                        </span>
                      ))}
                      {signal.addresses.length > 2 && (
                        <span
                          style={{
                            fontSize: "10px",
                            color: "#6b7280",
                            padding: "2px 6px",
                          }}
                        >
                          +{signal.addresses.length - 2} more
                        </span>
                      )}
                    </div>
                  )}

                  {/* Date + Source */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: "10px",
                      color: "#6b7280",
                      paddingTop: "6px",
                      borderTop: "1px solid #374151",
                    }}
                  >
                    <span>{formatDate(signal.event_date)}</span>
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/intel/documents/${signal.document_id}/page`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        color: "#60a5fa",
                        cursor: "pointer",
                        textDecoration: "none",
                      }}
                    >
                      {signal.source_title} ↗
                    </a>
                  </div>

                  {/* Expanded Document View */}
                  {expandedSignalId === signal.id && (
                    <div
                      style={{
                        marginTop: "10px",
                        paddingTop: "10px",
                        borderTop: "1px solid #374151",
                      }}
                    >
                      {expandedLoading ? (
                        <div
                          style={{
                            color: "#6b7280",
                            fontSize: "11px",
                            padding: "8px 0",
                          }}
                        >
                          Loading document...
                        </div>
                      ) : expandedDoc ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                          {/* Document header */}
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "6px",
                              fontSize: "11px",
                              fontWeight: "600",
                              color: "#93c5fd",
                            }}
                          >
                            <span>📄</span>
                            <span>Source Document</span>
                          </div>

                          {/* Document title */}
                          <div style={{ fontSize: "11px", color: "#e5e7eb", fontWeight: "500" }}>
                            {expandedDoc.document.title}
                          </div>

                          {/* Document metadata row */}
                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "12px",
                              fontSize: "10px",
                              color: "#6b7280",
                              alignItems: "center",
                            }}
                          >
                            <span>
                              Type: {expandedDoc.document.source_type.replace(/_/g, " ")}
                            </span>
                            {expandedDoc.document.published_date && (
                              <span>Published: {expandedDoc.document.published_date}</span>
                            )}
                            <a
                              href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/intel/documents/${expandedDoc.document.id}/page`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ color: "#60a5fa", textDecoration: "none" }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              View full document {expandedDoc.document.url_status === "dead" ? "(cached)" : ""}
                            </a>
                          </div>

                          {/* Extracted details */}
                          {(expandedDoc.signal.zoning_from || expandedDoc.signal.zoning_to || expandedDoc.signal.unit_count) && (
                            <div
                              style={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: "6px",
                                fontSize: "10px",
                              }}
                            >
                              {expandedDoc.signal.zoning_from && expandedDoc.signal.zoning_to && (
                                <span
                                  style={{
                                    background: "#374151",
                                    color: "#d1d5db",
                                    padding: "2px 6px",
                                    borderRadius: "3px",
                                  }}
                                >
                                  Zoning: {expandedDoc.signal.zoning_from} → {expandedDoc.signal.zoning_to}
                                </span>
                              )}
                              {expandedDoc.signal.unit_count && (
                                <span
                                  style={{
                                    background: "#374151",
                                    color: "#d1d5db",
                                    padding: "2px 6px",
                                    borderRadius: "3px",
                                  }}
                                >
                                  {expandedDoc.signal.unit_count} units
                                </span>
                              )}
                              {expandedDoc.signal.vote_for != null && expandedDoc.signal.vote_against != null && (
                                <span
                                  style={{
                                    background: "#374151",
                                    color: "#d1d5db",
                                    padding: "2px 6px",
                                    borderRadius: "3px",
                                  }}
                                >
                                  Vote: {expandedDoc.signal.vote_for}-{expandedDoc.signal.vote_against}
                                </span>
                              )}
                            </div>
                          )}

                          {/* Document raw text */}
                          {expandedDoc.document.raw_text && (
                            <div
                              style={{
                                background: "#0f172a",
                                border: "1px solid #374151",
                                borderRadius: "4px",
                                padding: "8px",
                                fontSize: "11px",
                                color: "#9ca3af",
                                lineHeight: "1.5",
                                maxHeight: "200px",
                                overflowY: "auto",
                                whiteSpace: "pre-wrap",
                              }}
                            >
                              {expandedDoc.document.raw_text}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div
                          style={{
                            color: "#6b7280",
                            fontSize: "11px",
                            padding: "8px 0",
                          }}
                        >
                          Document not available
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* Load More Button */}
              {signalsHasMore && (
                <button
                  onClick={handleLoadMoreSignals}
                  disabled={signalsLoading}
                  style={{
                    padding: "10px",
                    background: "#1e293b",
                    border: "1px solid #374151",
                    borderRadius: "6px",
                    color: "#60a5fa",
                    fontSize: "12px",
                    fontWeight: "600",
                    cursor: signalsLoading ? "not-allowed" : "pointer",
                    transition: "all 0.2s",
                  }}
                  onMouseEnter={(e) => {
                    if (!signalsLoading) {
                      (e.currentTarget as HTMLButtonElement).style.background =
                        "#374151";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!signalsLoading) {
                      (e.currentTarget as HTMLButtonElement).style.background =
                        "#1e293b";
                    }
                  }}
                >
                  {signalsLoading ? "Loading..." : "Load more signals"}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
