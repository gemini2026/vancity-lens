"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Send, Brain, Radio } from "lucide-react";
import {
  chatWithIntel, getSignalFeed, getSignalDocument, getIntelStats, getNeighborhoods,
} from "@/lib/intel-api";
import type {
  ChatMessage, IntelSignal, SignalDocument, SourceCitation, IntelStats, SignalType, Severity,
} from "@/lib/intel-types";
import ExportButton from "./ExportButton";
import { EmptyState } from "./EmptyState";
import { cn } from "@/lib/utils";
import { getApiBase } from "@/lib/api-base";

const API_BASE = getApiBase();

const SIGNAL_TYPE_LABELS: Record<SignalType, string> = {
  rezoning_decision: "REZONING DECISION", permit_approval: "PERMIT APPROVAL",
  policy_change: "POLICY CHANGE", community_opposition: "COMMUNITY OPPOSITION",
  density_change: "DENSITY CHANGE", development_proposal: "DEVELOPMENT PROPOSAL",
  infrastructure_investment: "INFRASTRUCTURE INVESTMENT",
};

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "🔴", high: "🟠", medium: "🟡", low: "🟢",
};

const SIGNAL_TYPE_BORDER_COLORS: Record<string, string> = {
  rezoning_decision: "border-l-amber-500",
  permit_approval: "border-l-blue-500",
  policy_change: "border-l-green-500",
  community_opposition: "border-l-purple-500",
  density_change: "border-l-cyan-500",
  development_proposal: "border-l-orange-500",
  infrastructure_investment: "border-l-emerald-500",
};

const LightbulbIcon = (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <path d="M9.5 2c-1.82 0-3.55.7-4.84 1.99C3.36 5.28 2.66 7.01 2.66 8.83c0 1.82.7 3.55 1.99 4.84l.01.01c.44.44.68 1.04.68 1.66v2.33c0 .92.75 1.67 1.67 1.67h6.67c.92 0 1.67-.75 1.67-1.67v-2.33c0-.62.24-1.22.68-1.66l.01-.01c1.29-1.29 1.99-3.02 1.99-4.84 0-1.82-.7-3.55-1.99-4.84C13.05 2.7 11.32 2 9.5 2z"/>
    <path d="M9.5 20v2M7 22h5"/>
  </svg>
);

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Today";
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  const days = Math.floor((today.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return date.toLocaleDateString();
}

interface ChatMessageWithId extends ChatMessage { id: string; }

export default function IntelPage() {
  const [chatMessages, setChatMessages] = useState<ChatMessageWithId[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [signals, setSignals] = useState<IntelSignal[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [signalOffset, setSignalOffset] = useState(0);
  const [signalsHasMore, setSignalsHasMore] = useState(false);

  const [neighborhoods, setNeighborhoods] = useState<string[]>([]);
  const [selectedNeighborhood, setSelectedNeighborhood] = useState("");
  const [selectedSignalType, setSelectedSignalType] = useState<SignalType | "">("");
  const [selectedDateRange, setSelectedDateRange] = useState<"7d" | "30d" | "90d" | "all">("90d");

  const [stats, setStats] = useState<IntelStats | null>(null);
  const [expandedSignalId, setExpandedSignalId] = useState<string | null>(null);
  const [expandedDoc, setExpandedDoc] = useState<SignalDocument | null>(null);
  const [expandedLoading, setExpandedLoading] = useState(false);

  // Mobile panel toggle: "chat" or "feed"
  const [mobilePanel, setMobilePanel] = useState<"chat" | "feed">("chat");

  const handleToggleExpand = useCallback(async (signalId: string) => {
    if (expandedSignalId === signalId) { setExpandedSignalId(null); setExpandedDoc(null); return; }
    setExpandedSignalId(signalId); setExpandedDoc(null); setExpandedLoading(true);
    try { setExpandedDoc(await getSignalDocument(signalId)); }
    catch (err) { console.error("Failed to load document:", err); }
    finally { setExpandedLoading(false); }
  }, [expandedSignalId]);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages]);

  useEffect(() => {
    (async () => {
      try {
        const [statsData, neighborhoodsData] = await Promise.all([getIntelStats(), getNeighborhoods()]);
        setStats(statsData); setNeighborhoods(neighborhoodsData);
        const feedData = await getSignalFeed({ limit: 20, date_range: "90d" });
        setSignals(feedData.signals); setSignalsHasMore(feedData.has_more);
      } catch (err) { console.error("Failed to load initial data:", err); }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      setSignalsLoading(true);
      try {
        const feedData = await getSignalFeed({
          neighborhood: selectedNeighborhood || undefined,
          signal_type: selectedSignalType || undefined,
          date_range: selectedDateRange, limit: 20, offset: 0,
        });
        setSignals(feedData.signals); setSignalsHasMore(feedData.has_more); setSignalOffset(0);
      } catch (err) { console.error("Failed to load signals:", err); }
      finally { setSignalsLoading(false); }
    })();
  }, [selectedNeighborhood, selectedSignalType, selectedDateRange]);

  const handleLoadMoreSignals = async () => {
    const nextOffset = signalOffset + 20;
    setSignalsLoading(true);
    try {
      const feedData = await getSignalFeed({
        neighborhood: selectedNeighborhood || undefined,
        signal_type: selectedSignalType || undefined,
        date_range: selectedDateRange, limit: 20, offset: nextOffset,
      });
      setSignals((prev) => [...prev, ...feedData.signals]);
      setSignalsHasMore(feedData.has_more); setSignalOffset(nextOffset);
    } catch (err) { console.error("Failed to load more signals:", err); }
    finally { setSignalsLoading(false); }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;
    const userMessage: ChatMessageWithId = { id: `msg-${Date.now()}`, role: "user", content: inputValue };
    setChatMessages((prev) => [...prev, userMessage]); setInputValue(""); setChatLoading(true);
    try {
      const response = await chatWithIntel(inputValue, { session_id: sessionId || undefined, include_signals: true });
      if (!sessionId) setSessionId(response.session_id);
      setChatMessages((prev) => [...prev, {
        id: `msg-${Date.now()}-assistant`, role: "assistant", content: response.answer,
        citations: response.citations, related_signals: response.related_signals.map((s) => s.id),
      }]);
    } catch {
      setChatMessages((prev) => [...prev, {
        id: `msg-${Date.now()}-error`, role: "assistant",
        content: "Sorry, I encountered an error processing your question. Please try again.",
      }]);
    } finally { setChatLoading(false); }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setInputValue(suggestion);
    inputRef.current?.focus();
  };

  const selectClasses = "w-full px-2.5 py-2 bg-[var(--color-card)] border border-[var(--color-border)] rounded text-[var(--color-foreground-secondary)] text-xs";

  return (
    <div className="flex flex-col md:flex-row h-full bg-[var(--color-surface)] text-[var(--color-foreground)]">
      {/* Mobile panel tabs */}
      <div className="md:hidden flex border-b border-[var(--color-border)]">
        <button
          onClick={() => setMobilePanel("chat")}
          className={cn("flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold transition-colors",
            mobilePanel === "chat" ? "text-blue-400 border-b-2 border-blue-400 bg-[var(--color-surface-secondary)]" : "text-[var(--color-foreground-muted)]"
          )}
        >
          <Brain className="w-4 h-4" /> Ask
        </button>
        <button
          onClick={() => setMobilePanel("feed")}
          className={cn("flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold transition-colors",
            mobilePanel === "feed" ? "text-blue-400 border-b-2 border-blue-400 bg-[var(--color-surface-secondary)]" : "text-[var(--color-foreground-muted)]"
          )}
        >
          <Radio className="w-4 h-4" /> Feed
        </button>
      </div>

      {/* Left: Chat Panel */}
      <div className={cn(
        "flex-1 md:flex-[0_0_60%] flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface-secondary)]",
        mobilePanel !== "chat" && "hidden md:flex"
      )}>
        {/* Chat header */}
        <div className="px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-secondary)] flex items-center gap-2">
          <Brain className="w-5 h-5 text-blue-400" />
          <div>
            <div className="text-sm font-semibold text-[var(--color-foreground)]">Ask VanCity Lens</div>
            <div className="text-[11px] text-[var(--color-foreground-muted)] mt-0.5">Intelligence for real estate development</div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
          {chatMessages.length === 0 ? (
            <EmptyState
              icon={LightbulbIcon}
              heading="Ask VanCity Lens"
              description="Get instant answers about Vancouver development, rezoning applications, and neighborhood trends powered by AI."
              suggestions={[
                "What rezoning applications were approved recently?",
                "What's happening in Mount Pleasant?",
                "Show me density changes near Broadway stations",
              ]}
              onSuggestionClick={handleSuggestionClick}
              className="flex-1"
            />
          ) : (
            <>
              {chatMessages.map((msg) => (
                <div key={msg.id} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                  <div className={cn(
                    "max-w-[85%] px-3.5 py-3 rounded-lg text-[13px] leading-relaxed break-words",
                    msg.role === "user" ? "bg-blue-500 text-white" : "bg-[var(--color-card)] text-[var(--color-foreground-secondary)]"
                  )}>
                    <div>{msg.content}</div>
                    {msg.citations && msg.citations.length > 0 && (
                      <div className={cn("mt-2 pt-2 flex flex-wrap gap-1.5",
                        msg.role === "user" ? "border-t border-white/20" : "border-t border-[var(--color-border)]"
                      )}>
                        {msg.citations.map((citation, idx) => (
                          <a
                            key={idx}
                            href={citation.document_id ? `${API_BASE}/api/v1/intel/documents/${citation.document_id}/page` : citation.document_url}
                            target="_blank" rel="noopener noreferrer"
                            className={cn("inline-block px-2 py-1 rounded text-[11px] no-underline whitespace-nowrap",
                              msg.role === "user" ? "bg-white/15 text-[var(--color-foreground)]" : "bg-[var(--color-surface-secondary)] text-blue-400"
                            )}
                            title={`${citation.document_title}${citation.published_date ? ` (${citation.published_date})` : ""}`}
                          >
                            {citation.document_title.slice(0, 25)}…
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="flex justify-start">
                  <div className="px-3.5 py-3 rounded-lg bg-[var(--color-card)] text-[var(--color-foreground-muted)] text-[13px] animate-pulse">●●●</div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input */}
        <div className="px-5 py-4 border-t border-[var(--color-border)] bg-[var(--color-surface-secondary)] flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSendMessage(); } }}
            placeholder="Ask about developments, permits, zoning..."
            className="flex-1 px-3 py-2.5 bg-[var(--color-card)] border border-[var(--color-border)] rounded-md text-[var(--color-foreground)] text-[13px] font-[inherit] focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleSendMessage}
            disabled={chatLoading || !inputValue.trim()}
            className={cn(
              "px-4 py-2.5 rounded-md text-white text-[13px] font-semibold transition-colors",
              chatLoading ? "bg-gray-600 cursor-not-allowed" : "bg-blue-500 cursor-pointer hover:bg-blue-600"
            )}
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Right: Signal Feed */}
      <div className={cn(
        "flex-1 md:flex-[0_0_40%] flex flex-col bg-[var(--color-surface)] border-l border-[var(--color-border)]",
        mobilePanel !== "feed" && "hidden md:flex"
      )}>
        {/* Header + filters */}
        <div className="px-5 py-4 border-b border-[var(--color-border)]">
          <div className="flex gap-4 mb-3.5 text-xs text-[var(--color-foreground-muted)]">
            {stats && (
              <>
                <div><span className="font-semibold text-[var(--color-foreground)]">{stats.total_signals}</span> signals</div>
                <div><span className="font-semibold text-[var(--color-foreground)]">{Object.keys(stats.by_neighborhood).length}</span> neighborhoods</div>
              </>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <select value={selectedNeighborhood} onChange={(e) => setSelectedNeighborhood(e.target.value)} className={selectClasses}>
              <option value="">All neighborhoods</option>
              {neighborhoods.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <select value={selectedSignalType} onChange={(e) => setSelectedSignalType(e.target.value as SignalType | "")} className={selectClasses}>
              <option value="">All signal types</option>
              {Object.entries(SIGNAL_TYPE_LABELS).map(([t, l]) => <option key={t} value={t}>{l}</option>)}
            </select>
            <select value={selectedDateRange} onChange={(e) => setSelectedDateRange(e.target.value as any)} className={selectClasses}>
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

        {/* Signal cards */}
        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-0">
          {signals.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-[var(--color-foreground-muted)] text-[13px]">No signals found</div>
          ) : (
            <>
              {signals.map((signal) => (
                <div
                  key={signal.id}
                  onClick={() => handleToggleExpand(signal.id)}
                  className={cn(
                    "p-3 rounded-md text-xs cursor-pointer transition-all border-l-[3px] mb-2",
                    SIGNAL_TYPE_BORDER_COLORS[signal.signal_type] || "border-l-gray-500",
                    expandedSignalId === signal.id
                      ? "bg-[#1a2744] border border-blue-500"
                      : "bg-[var(--color-card)] border border-[var(--color-border)] hover:border-[var(--color-foreground-muted)]"
                  )}
                >
                  {/* Severity + type */}
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-base">{SEVERITY_DOT[signal.severity]}</span>
                    <span className="text-[10px] font-semibold text-[var(--color-foreground-muted)] bg-[var(--color-surface-secondary)] px-1.5 py-0.5 rounded">{SIGNAL_TYPE_LABELS[signal.signal_type]}</span>
                    {signal.decision && (
                      <span className={cn("text-xs font-semibold px-2 py-0.5 rounded border",
                        signal.decision.toUpperCase() === "APPROVED"
                          ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                          : signal.decision.toUpperCase() === "DENIED"
                            ? "bg-red-500/20 text-red-400 border-red-500/30"
                            : "bg-amber-500/20 text-amber-400 border-amber-500/30"
                      )}>
                        {signal.decision.toUpperCase()}
                      </span>
                    )}
                    <span className="ml-auto text-[10px] text-[var(--color-foreground-muted)]">{expandedSignalId === signal.id ? "▲" : "▼"}</span>
                  </div>

                  {/* Headline */}
                  <div className="text-[13px] font-semibold text-[var(--color-foreground)] mb-1 leading-snug">{signal.headline}</div>

                  {/* Summary */}
                  <div className={cn("text-[var(--color-foreground-muted)] text-[11px] mb-1.5 leading-snug",
                    expandedSignalId !== signal.id && "line-clamp-2"
                  )}>
                    {signal.summary}
                  </div>

                  {/* Addresses */}
                  {signal.addresses?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-1.5">
                      {signal.addresses.slice(0, 2).map((addr, idx) => (
                        <span key={idx} className="text-[10px] bg-[var(--color-surface-secondary)] text-[var(--color-foreground-secondary)] px-1.5 py-0.5 rounded">📍 {addr}</span>
                      ))}
                      {signal.addresses.length > 2 && <span className="text-[10px] text-[var(--color-foreground-muted)] px-1.5">+{signal.addresses.length - 2} more</span>}
                    </div>
                  )}

                  {/* Date + source */}
                  <div className="flex justify-between items-center text-[10px] text-[var(--color-foreground-muted)] pt-1.5 border-t border-[var(--color-border)]">
                    <span>{formatDate(signal.event_date)}</span>
                    <a
                      href={`${API_BASE}/api/v1/intel/documents/${signal.document_id}/page`}
                      target="_blank" rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-blue-400 no-underline hover:underline"
                    >
                      {signal.source_title} ↗
                    </a>
                  </div>

                  {/* Expanded doc */}
                  {expandedSignalId === signal.id && (
                    <div className="mt-2.5 pt-2.5 border-t border-[var(--color-border)]">
                      {expandedLoading ? (
                        <div className="text-[var(--color-foreground-muted)] text-[11px] py-2">Loading document...</div>
                      ) : expandedDoc ? (
                        <div className="flex flex-col gap-2">
                          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-blue-300">📄 Source Document</div>
                          <div className="text-[11px] text-[var(--color-foreground)] font-medium">{expandedDoc.document.title}</div>
                          <div className="flex flex-wrap gap-3 text-[10px] text-[var(--color-foreground-muted)] items-center">
                            <span>Type: {expandedDoc.document.source_type.replace(/_/g, " ")}</span>
                            {expandedDoc.document.published_date && <span>Published: {expandedDoc.document.published_date}</span>}
                            <a
                              href={`${API_BASE}/api/v1/intel/documents/${expandedDoc.document.id}/page`}
                              target="_blank" rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-blue-400 no-underline"
                            >
                              View full document {expandedDoc.document.url_status === "dead" ? "(cached)" : ""}
                            </a>
                          </div>
                          {(expandedDoc.signal.zoning_from || expandedDoc.signal.zoning_to || expandedDoc.signal.unit_count) && (
                            <div className="flex flex-wrap gap-1.5 text-[10px]">
                              {expandedDoc.signal.zoning_from && expandedDoc.signal.zoning_to && (
                                <span className="bg-[var(--color-surface-secondary)] text-[var(--color-foreground-secondary)] px-1.5 py-0.5 rounded">Zoning: {expandedDoc.signal.zoning_from} → {expandedDoc.signal.zoning_to}</span>
                              )}
                              {expandedDoc.signal.unit_count && (
                                <span className="bg-[var(--color-surface-secondary)] text-[var(--color-foreground-secondary)] px-1.5 py-0.5 rounded">{expandedDoc.signal.unit_count} units</span>
                              )}
                              {expandedDoc.signal.vote_for != null && expandedDoc.signal.vote_against != null && (
                                <span className="bg-[var(--color-surface-secondary)] text-[var(--color-foreground-secondary)] px-1.5 py-0.5 rounded">Vote: {expandedDoc.signal.vote_for}-{expandedDoc.signal.vote_against}</span>
                              )}
                            </div>
                          )}
                          {expandedDoc.document.raw_text && (
                            <div className="bg-[var(--color-surface-secondary)] border border-[var(--color-border)] rounded p-2 text-[11px] text-[var(--color-foreground-muted)] leading-relaxed max-h-[200px] overflow-y-auto whitespace-pre-wrap">
                              {expandedDoc.document.raw_text}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-[var(--color-foreground-muted)] text-[11px] py-2">Document not available</div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {signalsHasMore && (
                <button
                  onClick={handleLoadMoreSignals}
                  disabled={signalsLoading}
                  className={cn(
                    "py-2.5 bg-[var(--color-card)] border border-[var(--color-border)] rounded-md text-blue-400 text-xs font-semibold transition-colors",
                    signalsLoading ? "cursor-not-allowed" : "cursor-pointer hover:bg-[var(--color-card-hover)]"
                  )}
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
