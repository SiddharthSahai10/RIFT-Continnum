import { useEffect, useRef, useCallback } from "react";
import { useAgentStore } from "../store/useAgentStore";
import { getWsUrl } from "../config";

/**
 * Connects to the pipeline WebSocket for a given run_id and dispatches
 * every incoming message to the Zustand store.
 */
export function useWebSocket(runId: string | null) {
  const ws = useRef<WebSocket | null>(null);
  const handleWSMessage = useAgentStore((s) => s.handleWSMessage);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (!runId) return;

    /* Determine WS URL — uses VITE_API_URL in production, Vite proxy in dev */
    const url = getWsUrl(`/ws/${runId}`);

    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => {
      console.log(`[WS] Connected — run_id=${runId}`);
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleWSMessage(msg);
      } catch {
        console.warn("[WS] Non-JSON message:", event.data);
      }
    };

    socket.onclose = (e) => {
      console.log(`[WS] Closed (${e.code})`);
      /* Auto-reconnect on abnormal close (but not if component unmounted) */
      if (e.code !== 1000 && e.code !== 1001) {
        reconnectTimeout.current = setTimeout(connect, 3000);
      }
    };

    socket.onerror = (err) => {
      console.error("[WS] Error:", err);
      socket.close();
    };
  }, [runId, handleWSMessage]);

  useEffect(() => {
    connect();

    return () => {
      clearTimeout(reconnectTimeout.current);
      if (ws.current) {
        ws.current.close(1000, "Component unmounted");
        ws.current = null;
      }
    };
  }, [connect]);

  return ws;
}
