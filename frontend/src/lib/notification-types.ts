export type NotificationType = "info" | "warning" | "alert" | "success";

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  createdAt: string;
  readAt?: string | null;
  parcelId?: string | null;
  link?: string | null;
}

export interface NotificationFilter {
  type?: NotificationType;
  unreadOnly?: boolean;
  limit?: number;
  offset?: number;
}

export interface NotificationResponse {
  notifications: Notification[];
  total: number;
  limit: number;
  offset: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}
