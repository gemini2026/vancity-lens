"use client";

import React, { useState, useEffect } from "react";
import { Notification, UnreadCountResponse } from "@/lib/notification-types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const NotificationBadge: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchNotifications();
    }
  }, [isOpen]);

  const fetchUnreadCount = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/notifications/unread-count`
      );
      if (res.ok) {
        const data: UnreadCountResponse = await res.json();
        setUnreadCount(data.unread_count);
      }
    } catch (error) {
      console.error("Failed to fetch unread count:", error);
    }
  };

  const fetchNotifications = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/notifications?limit=10&offset=0`
      );
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.notifications || []);
      }
    } catch (error) {
      console.error("Failed to fetch notifications:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const markAsRead = async (notificationId: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/notifications/${notificationId}/read`,
        { method: "PUT" }
      );
      if (res.ok) {
        setNotifications(
          notifications.map((n) =>
            n.id === notificationId
              ? { ...n, readAt: new Date().toISOString() }
              : n
          )
        );
        fetchUnreadCount();
      }
    } catch (error) {
      console.error("Failed to mark notification as read:", error);
    }
  };

  const markAllAsRead = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/notifications/read-all`, {
        method: "PUT",
      });
      if (res.ok) {
        setNotifications(
          notifications.map((n) => ({
            ...n,
            readAt: new Date().toISOString(),
          }))
        );
        setUnreadCount(0);
      }
    } catch (error) {
      console.error("Failed to mark all as read:", error);
    }
  };

  const getBadgeDisplay = () => {
    if (unreadCount === 0) return null;
    if (unreadCount > 99) return "99+";
    return unreadCount.toString();
  };

  const getNotificationIcon = (type: string) => {
    switch (type) {
      case "alert":
        return "⚠️";
      case "warning":
        return "⚡";
      case "success":
        return "✓";
      default:
        return "ℹ️";
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`relative p-2 rounded-lg transition-colors ${
          isOpen
            ? "bg-gray-700 text-white"
            : "hover:bg-gray-700 text-gray-300"
        }`}
        aria-label="Notifications"
        aria-live="polite"
      >
        <span className="text-xl">🔔</span>
        {unreadCount > 0 && (
          <span
            className={`absolute top-0 right-0 inline-flex items-center justify-center h-5 w-5 text-xs font-bold text-white bg-red-500 rounded-full ${
              unreadCount > 0 ? "animate-pulse" : ""
            }`}
            role="status"
            aria-live="assertive"
          >
            {getBadgeDisplay()}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50">
          <div className="p-4 border-b border-gray-700 flex justify-between items-center">
            <h3 className="text-white font-semibold text-sm">Notifications</h3>
            {unreadCount > 0 && (
              <button
                onClick={markAllAsRead}
                className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
              >
                Mark all as read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {isLoading ? (
              <div className="p-4 text-center text-gray-400 text-sm">
                Loading...
              </div>
            ) : notifications.length === 0 ? (
              <div className="p-4 text-center text-gray-400 text-sm">
                No notifications yet
              </div>
            ) : (
              notifications.map((notif) => (
                <button
                  key={notif.id}
                  onClick={() => markAsRead(notif.id)}
                  className={`w-full text-left p-3 border-b border-gray-700 transition-colors ${
                    notif.readAt
                      ? "bg-gray-800 hover:bg-gray-750"
                      : "bg-gray-750 hover:bg-gray-700"
                  }`}
                >
                  <div className="flex gap-2">
                    <span className="text-lg flex-shrink-0">
                      {getNotificationIcon(notif.type)}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-white text-xs font-semibold line-clamp-1">
                        {notif.title}
                      </p>
                      <p className="text-gray-300 text-xs line-clamp-2 mt-0.5">
                        {notif.message}
                      </p>
                      <p className="text-gray-500 text-xs mt-1">
                        {formatTime(notif.createdAt)}
                      </p>
                    </div>
                    {!notif.readAt && (
                      <div className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0 mt-1" />
                    )}
                  </div>
                </button>
              ))
            )}
          </div>

          <div className="p-3 border-t border-gray-700">
            <a
              href="/alerts"
              className="text-blue-400 hover:text-blue-300 text-xs font-semibold transition-colors"
            >
              View all alerts
            </a>
          </div>
        </div>
      )}

      {isOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}
    </div>
  );
};

export default NotificationBadge;
