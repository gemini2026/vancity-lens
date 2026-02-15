"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Bell } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getAlerts,
  markAlertRead,
  getUnreadCount,
  type Alert,
} from "@/lib/watchlist-api";

interface AlertsFeedProps {
  token: string | null;
}

const SEVERITY_BG: Record<string, string> = {
  critical: "bg-red-600",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "bg-emerald-500",
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
    if (!token) { setUnreadCount(0); return; }
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

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  useEffect(() => {
    if (isOpen && token) fetchAlerts();
  }, [isOpen, token, fetchAlerts]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
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
    <div ref={dropdownRef} className="relative inline-flex">
      {/* Bell */}
      <button
        onClick={() => token && setIsOpen(!isOpen)}
        className={cn(
          "relative p-1.5 text-gray-400 transition-colors",
          token ? "cursor-pointer hover:text-gray-100" : "cursor-default"
        )}
        title={token ? "Alerts" : "Login to view alerts"}
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute top-0.5 right-0 bg-red-600 text-white text-[9px] font-bold min-w-[16px] h-4 rounded-full flex items-center justify-center px-1">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && token && (
        <div className="absolute top-full right-0 mt-2 w-[360px] max-h-[420px] overflow-y-auto bg-gray-900 border border-gray-800 rounded-lg shadow-2xl z-[1000]">
          {/* Header */}
          <div className="px-4 py-3 border-b border-gray-800 flex justify-between items-center">
            <span className="text-[13px] font-bold text-gray-100">Alerts</span>
            {unreadCount > 0 && (
              <span className="text-[10px] text-blue-400 font-semibold">
                {unreadCount} unread
              </span>
            )}
          </div>

          {/* List */}
          {loading ? (
            <div className="p-6 text-center text-gray-500 text-xs">Loading alerts...</div>
          ) : alerts.length === 0 ? (
            <div className="p-6 text-center text-gray-500 text-xs">No alerts yet</div>
          ) : (
            alerts.map((alert) => (
              <div
                key={alert.id}
                className={cn(
                  "px-4 py-2.5 border-b border-gray-800 transition-colors",
                  !alert.is_read && "bg-blue-500/5"
                )}
              >
                <div className="flex items-start gap-2">
                  <div
                    className={cn(
                      "w-2 h-2 rounded-full mt-1 shrink-0",
                      SEVERITY_BG[alert.severity || "low"] || "bg-gray-500"
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div
                      className={cn(
                        "text-xs leading-snug truncate",
                        alert.is_read ? "font-normal text-gray-400" : "font-semibold text-gray-100"
                      )}
                    >
                      {alert.headline || alert.summary || "New alert"}
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500">
                      {alert.signal_type && (
                        <span className="bg-gray-700 px-1.5 py-px rounded">
                          {alert.signal_type.replace(/_/g, " ")}
                        </span>
                      )}
                      {alert.neighborhood && <span>{alert.neighborhood}</span>}
                      <span>{formatTimeAgo(alert.created_at)}</span>
                    </div>
                  </div>
                  {!alert.is_read && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleMarkRead(alert.id); }}
                      className="shrink-0 text-[10px] text-blue-400 px-1.5 py-0.5 hover:text-blue-300"
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
