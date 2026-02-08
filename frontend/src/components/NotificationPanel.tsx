import React, { useState } from "react";
import { Notification, NotificationType } from "@/lib/notification-types";

interface NotificationPanelProps {
  notifications: Notification[];
  onMarkRead: (id: string) => Promise<void>;
  onDismiss: (id: string) => Promise<void>;
}

export const NotificationPanel: React.FC<NotificationPanelProps> = ({
  notifications,
  onMarkRead,
  onDismiss,
}) => {
  const [filterType, setFilterType] = useState<NotificationType | "all">("all");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [selectedNotifications, setSelectedNotifications] = useState<Set<string>>(
    new Set()
  );
  const [currentPage, setCurrentPage] = useState(0);
  const itemsPerPage = 20;

  const filteredNotifications = notifications.filter(
    (n) => filterType === "all" || n.type === filterType
  );

  const sortedNotifications = [...filteredNotifications].sort((a, b) => {
    const timeA = new Date(a.createdAt).getTime();
    const timeB = new Date(b.createdAt).getTime();
    return sortOrder === "newest" ? timeB - timeA : timeA - timeB;
  });

  const paginatedNotifications = sortedNotifications.slice(
    currentPage * itemsPerPage,
    (currentPage + 1) * itemsPerPage
  );

  const totalPages = Math.ceil(sortedNotifications.length / itemsPerPage);

  const toggleNotificationSelection = (id: string) => {
    const newSelected = new Set(selectedNotifications);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedNotifications(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedNotifications.size === paginatedNotifications.length) {
      setSelectedNotifications(new Set());
    } else {
      setSelectedNotifications(
        new Set(paginatedNotifications.map((n) => n.id))
      );
    }
  };

  const markSelectedAsRead = async () => {
    for (const id of selectedNotifications) {
      try {
        await onMarkRead(id);
      } catch (error) {
        console.error(`Failed to mark ${id} as read:`, error);
      }
    }
    setSelectedNotifications(new Set());
  };

  const dismissSelected = async () => {
    for (const id of selectedNotifications) {
      try {
        await onDismiss(id);
      } catch (error) {
        console.error(`Failed to dismiss ${id}:`, error);
      }
    }
    setSelectedNotifications(new Set());
  };

  const getTypeColor = (type: NotificationType) => {
    switch (type) {
      case "alert":
        return "text-red-400";
      case "warning":
        return "text-yellow-400";
      case "success":
        return "text-green-400";
      default:
        return "text-blue-400";
    }
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
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="w-full max-w-4xl mx-auto p-6 bg-gray-900 rounded-lg">
      <h1 className="text-2xl font-bold text-white mb-6">Notifications</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div>
          <label className="block text-sm text-gray-400 mb-2">
            Filter by type
          </label>
          <select
            value={filterType}
            onChange={(e) => {
              setFilterType(e.target.value as NotificationType | "all");
              setCurrentPage(0);
            }}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm"
            aria-label="Filter notifications by type"
          >
            <option value="all">All Types</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="alert">Alert</option>
            <option value="success">Success</option>
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-2">
            Sort by
          </label>
          <select
            value={sortOrder}
            onChange={(e) =>
              setSortOrder(e.target.value as "newest" | "oldest")
            }
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm"
            aria-label="Sort notifications"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>
        </div>

        <div className="flex items-end">
          <div className="text-sm text-gray-400">
            {filteredNotifications.length} notification
            {filteredNotifications.length !== 1 ? "s" : ""}
          </div>
        </div>
      </div>

      {selectedNotifications.size > 0 && (
        <div className="mb-4 p-4 bg-gray-800 border border-gray-700 rounded flex justify-between items-center">
          <span className="text-white text-sm">
            {selectedNotifications.size} selected
          </span>
          <div className="flex gap-2">
            <button
              onClick={markSelectedAsRead}
              className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
            >
              Mark as read
            </button>
            <button
              onClick={dismissSelected}
              className="px-3 py-1 text-sm bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {sortedNotifications.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-400 text-lg">
            No notifications found
          </p>
        </div>
      ) : (
        <>
          <div className="mb-4 flex items-center gap-2">
            <input
              type="checkbox"
              checked={
                selectedNotifications.size === paginatedNotifications.length &&
                paginatedNotifications.length > 0
              }
              onChange={toggleSelectAll}
              className="w-4 h-4 cursor-pointer"
              aria-label="Select all notifications on this page"
            />
            <label className="text-sm text-gray-400">
              Select all on page
            </label>
          </div>

          <div className="space-y-2 mb-6">
            {paginatedNotifications.map((notif) => (
              <div
                key={notif.id}
                className={`p-4 border border-gray-700 rounded transition-colors ${
                  notif.readAt ? "bg-gray-800" : "bg-gray-750"
                }`}
              >
                <div className="flex gap-3">
                  <input
                    type="checkbox"
                    checked={selectedNotifications.has(notif.id)}
                    onChange={() => toggleNotificationSelection(notif.id)}
                    className="w-4 h-4 mt-1 cursor-pointer"
                    aria-label={`Select notification: ${notif.title}`}
                  />

                  <span className="text-lg flex-shrink-0 mt-0.5">
                    {getNotificationIcon(notif.type)}
                  </span>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="text-white font-semibold text-sm">
                          {notif.title}
                        </h3>
                        <p className="text-gray-300 text-sm mt-1">
                          {notif.message}
                        </p>
                      </div>
                      {!notif.readAt && (
                        <div className="w-2 h-2 bg-blue-400 rounded-full flex-shrink-0 mt-1" />
                      )}
                    </div>

                    <div className="flex justify-between items-center mt-3">
                      <p className="text-gray-500 text-xs">
                        {formatTime(notif.createdAt)}
                      </p>
                      <span
                        className={`text-xs font-semibold ${getTypeColor(
                          notif.type
                        )}`}
                      >
                        {notif.type.charAt(0).toUpperCase() +
                          notif.type.slice(1)}
                      </span>
                    </div>

                    {notif.link && (
                      <a
                        href={notif.link}
                        className="inline-block mt-2 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                      >
                        View details
                      </a>
                    )}
                  </div>

                  <button
                    onClick={() => onDismiss(notif.id)}
                    className="text-gray-400 hover:text-gray-300 transition-colors flex-shrink-0"
                    aria-label={`Dismiss: ${notif.title}`}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex justify-between items-center pt-4 border-t border-gray-700">
              <button
                onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                disabled={currentPage === 0}
                className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded transition-colors"
              >
                Previous
              </button>

              <span className="text-sm text-gray-400">
                Page {currentPage + 1} of {totalPages}
              </span>

              <button
                onClick={() =>
                  setCurrentPage(Math.min(totalPages - 1, currentPage + 1))
                }
                disabled={currentPage === totalPages - 1}
                className="px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default NotificationPanel;
