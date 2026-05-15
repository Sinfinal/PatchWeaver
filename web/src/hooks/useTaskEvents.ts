import { useEffect, useMemo, useRef, useState } from "react";
import { getApiBase } from "../services/http";

type TaskEventStatus = "idle" | "connecting" | "connected" | "reconnecting" | "error";

type TaskEventSnapshot = {
  event: string;
  task_id: string;
  fingerprint?: string;
};

export function useTaskEvents(taskId: string, onTaskChanged: () => void): TaskEventStatus {
  const [status, setStatus] = useState<TaskEventStatus>("idle");
  const eventsUrl = useMemo(() => buildTaskEventsUrl(taskId), [taskId]);
  const onTaskChangedRef = useRef(onTaskChanged);

  useEffect(() => {
    onTaskChangedRef.current = onTaskChanged;
  }, [onTaskChanged]);

  useEffect(() => {
    if (!taskId || !eventsUrl) {
      setStatus("idle");
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let closedByEffect = false;
    let lastFingerprint = "";

    const connect = () => {
      setStatus((current) => (current === "connected" ? "connected" : current === "idle" ? "connecting" : "reconnecting"));
      socket = new WebSocket(eventsUrl);
      socket.onopen = () => {
        setStatus("connected");
      };
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as TaskEventSnapshot;
          if (payload.event !== "task_snapshot" || !payload.fingerprint || payload.fingerprint === lastFingerprint) {
            return;
          }
          lastFingerprint = payload.fingerprint;
          onTaskChangedRef.current();
        } catch {
          setStatus("error");
        }
      };
      socket.onerror = () => {
        setStatus("error");
      };
      socket.onclose = () => {
        if (closedByEffect) {
          return;
        }
        setStatus("reconnecting");
        reconnectTimer = window.setTimeout(connect, 2500);
      };
    };

    connect();

    return () => {
      closedByEffect = true;
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [eventsUrl, taskId]);

  return status;
}

function buildTaskEventsUrl(taskId: string): string | null {
  if (!taskId) {
    return null;
  }
  const apiBase = getApiBase();
  const httpUrl = new URL(`${apiBase}/tasks/${encodeURIComponent(taskId)}/events`, window.location.origin);
  httpUrl.protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
  return httpUrl.toString();
}
