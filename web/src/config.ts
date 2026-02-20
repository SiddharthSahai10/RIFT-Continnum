/**
 * Runtime configuration — reads VITE_API_URL at build time.
 *
 * Local dev:  leave VITE_API_URL unset → relative paths + Vite proxy
 * Production: set VITE_API_URL=https://your-railway-backend.up.railway.app
 */

const raw = import.meta.env.VITE_API_URL ?? "";

/** Base URL for REST API calls. Empty string for same-origin (dev). */
export const API_BASE: string = raw.replace(/\/+$/, "");

/**
 * Build a full WebSocket URL for a given path (e.g. `/ws/{runId}`).
 *
 * When VITE_API_URL is set the WS connects directly to the backend host.
 * Otherwise it derives the URL from the browser's current location (dev proxy).
 */
export function getWsUrl(path: string): string {
  if (raw) {
    try {
      const url = new URL(raw);
      const proto = url.protocol === "https:" ? "wss" : "ws";
      return `${proto}://${url.host}${path}`;
    } catch {
      // fall through to same-origin logic
    }
  }
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${path}`;
}
