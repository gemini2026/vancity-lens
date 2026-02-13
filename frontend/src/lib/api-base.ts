function stripTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, "");
}

/**
 * Base URL for API requests from the browser.
 *
 * - In production builds, default to same-origin (Ingress routes `/api/*` to the API).
 * - In development, default to docker-compose host port.
 * - If NEXT_PUBLIC_API_URL is explicitly set, it always wins.
 */
export function getApiBase(): string {
  const explicit = process.env.NEXT_PUBLIC_API_URL;
  if (explicit && explicit.trim()) return stripTrailingSlashes(explicit.trim());

  // Production images should work without env-specific rebuilds by using same-origin.
  if (process.env.NODE_ENV === "production") return "";

  // Local docker-compose exposes API at http://localhost:8080 (container listens on :8000).
  return "http://localhost:8080";
}

