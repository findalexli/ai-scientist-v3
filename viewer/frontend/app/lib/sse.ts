import { useCallback, useEffect, useRef, useState } from "react";
import type { SSEMetrics, StepSummary } from "./types";

interface SSEState {
  isConnected: boolean;
  metrics: SSEMetrics | null;
  newEventCount: number;
}

/**
 * Hook for connecting to the SSE stream for a running job.
 * Parses `new_event` and `metrics` event types from the server.
 */
export function useSSE(
  jobId: string,
  enabled: boolean,
  onMetrics?: (metrics: SSEMetrics) => void
): SSEState {
  const [isConnected, setIsConnected] = useState(false);
  const [metrics, setMetrics] = useState<SSEMetrics | null>(null);
  const [newEventCount, setNewEventCount] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastLineRef = useRef(0);

  useEffect(() => {
    if (!enabled || !jobId) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        setIsConnected(false);
      }
      return;
    }

    const url = `/api/jobs/${encodeURIComponent(jobId)}/stream?after=${lastLineRef.current}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => setIsConnected(true);
    es.onerror = () => {
      setIsConnected(false);
      es.close();
      // Reconnect after 5s
      setTimeout(() => {
        if (eventSourceRef.current === es) {
          eventSourceRef.current = null;
        }
      }, 5000);
    };

    es.addEventListener("new_event", (e) => {
      setNewEventCount((c) => c + 1);
    });

    es.addEventListener("metrics", (e) => {
      try {
        const data: SSEMetrics = JSON.parse(e.data);
        setMetrics(data);
        if (data.total_lines) {
          lastLineRef.current = data.total_lines;
        }
        onMetrics?.(data);
      } catch {
        // ignore parse errors
      }
    });

    return () => {
      es.close();
      eventSourceRef.current = null;
      setIsConnected(false);
    };
  }, [jobId, enabled]);

  return { isConnected, metrics, newEventCount };
}
