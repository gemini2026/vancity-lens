"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  getAlerts,
  markAlertRead,
  getUnreadCount,
  type Alert,
} from "@/lib/watchlist-api";

interface AlertsFeedProps {
  token: string | null;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#f59e0b",
  low: "#10b981",
};

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export default function AlertsFeed({ token }: AlertsFeedProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = useCallback(async () => {
    if (!token) {
      setUnreadCount(0);
      return;
    }
    try {
      const count = await getUnreadCount(token);
      setUnreadCount(count);
    } catch {
      setUnreadCount(0);
    }
  }, [token]);

  const fetchAlerts = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await getAlerts(token, { limit: 20 });
      setAlerts(data.alerts);
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  // Poll unread count every 30s
  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  // Load alerts when dropdown opens
  useEffect(() => {
    if (isOpen && token) {
      fetchAlerts();
    }
  }, [isOpen, token, fetchAlerts]);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkRead = async (alertId: number) => {
    if (!token) return;
    try {
      await markAlertRead(token, alertId);
      setAlerts((prev) =>
        prev.map((a) => (a.id === alertId ? { ...a, is_read: true } : a))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch (err) {
      console.error("Failed to mark alert as read:", err);
    }
  };

  return (
    <div
      ref={dropdownRef}
      style={{
        position: "relative",
        display: "inline-flex",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      {/* Bell Button */}
      <button
        onClick={() => {
          if (token) setIsOpen(!isOpen);
        }}
        style={{
          position: "relative",
          background: "none",
          border: "none",
          cursor: token ? "pointer" : "default",
          padding: "6px",
          fontSize: "18px",
          lineHeight: "1",
          color: "#9ca3af",
          transition: "color 0.2s",
        }}
        onMouseEnter={(e) => {
          if (token) e.currentTarget.style.color = "#f3f4f6";
        }}
        onMouseLeave={(e) => {
          if (token) e.currentTarget.style.color = "#9ca3af";
        }}
        title={token ? "Alerts" : "Login to view alerts"}
      >
        &#128276;
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: "2px",
              right: "0px",
              background: "#dc2626",
              color: "#fff",
              fontSize: "9px",
              fontWeight: "700",
              minWidth: "16px",
              height: "16px",
              borderRadius: "8px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 4px",
              lineHeight: "1",
            }}
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && token && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            marginTop: "8px",
            width: "360px",
            maxHeight: "420px",
            overflowY: "auto",
            background: "#111827",
            border: "1px solid #1f2937",
            borderRadius: "8px",
            boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5)",
            zIndex: 1000,
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid #1f2937",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ fontSize: "13px", fontWeight: "700", color: "#f3f4f6" }}>
              Alerts
            </div>
            {unreadCount > 0 && (
              <span
                style={{
                  fontSize: "10px",
                  color: "#60a5fa",
                  fontWeight: "600",
                }}
              >
                {unreadCount} unread
              </span>
            )}
          </div>

          {/* Alert List */}
          {loading ? (
            <div
              style={{
                padding: "24px",
                textAlign: "center",
                color: "#6b7280",
                fontSize: "12px",
              }}
            >
              Loading alerts...
            </div>
          ) : alerts.length === 0 ? (
            <div
              style={{
                padding: "24px",
                textAlign: "center",
                color: "#6b7280",
                fontSize: "12px",
              }}
            >
              No alerts yet
            </div>
          ) : (
            alerts.map((alert) => (
              <div
                key={alert.id}
                style={{
                  padding: "10px 16px",
                  borderBottom: "1px solid #1f2937",
                  background: alert.is_read ? "transparent" : "rgba(59, 130, 246, 0.05)",
                  transition: "background 0.2s",
                  cursor: "default",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "8px",
                  }}
                >
                  {/* Severity dot */}
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background:
                        SEVERITY_COLORS[alert.severity || "low"] || "#6b7280",
                      marginTop: "4px",
                      flexShrink: 0,
                    }}
                  />

                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "12px",
                        fontWeight: alert.is_read ? "400" : "600",
                        color: alert.is_read ? "#9ca3af" : "#f3f4f6",
                        lineHeight: "1.4",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {alert.headline || alert.summary || "New alert"}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        marginTop: "4px",
                        fontSize: "10px",
                        color: "#6b7280",
                      }}
                    >
                      {alert.signal_type && (
                        <span
                          style={{
                            background: "#374151",
                            padding: "1px 5px",
                            borderRadius: "3px",
                          }}
                        >
                          {alert.signal_type.replace(/_/g, " ")}
                        </span>
                      )}
                      {alert.neighborhood && (
                        <span>{alert.neighborhood}</span>
                      )}
                      <span>{formatTimeAgo(alert.created_at)}</span>
                    </div>
                  </div>

                  {/* Mark as read */}
                  {!alert.is_read && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleMarkRead(alert.id);
                      }}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#60a5fa",
                        fontSize: "10px",
                        cursor: "pointer",
                        padding: "2px 6px",
                        flexShrink: 0,
                        fontFamily: "system-ui, sans-serif",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Mark read
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
