"use client";
import { useEffect, useRef, useState } from "react";
import { apiUrl } from "./api-client";
import type { RunStatus, RunState, RunEvent } from "./types";

export type RunEventsState = {
  logs: string[];
  events: RunEvent[];
  status: RunStatus;
  result: Record<string, unknown> | null;
  error: string | null;
  done: boolean;
};

export function useRunEvents(
  runId: string | null,
  onDone?: (state: RunEventsState) => void
): RunEventsState {
  const [state, setState] = useState<RunEventsState>({
    logs: [],
    events: [],
    status: "queued",
    result: null,
    error: null,
    done: false,
  });
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!runId) return;
    const es = new EventSource(apiUrl(`/runs/${runId}/events`));

    es.addEventListener("log", (e: MessageEvent) => {
      const { message } = JSON.parse(e.data) as { message: string };
      setState((prev) => ({
        ...prev,
        status: "running",
        logs: [...prev.logs, message],
      }));
    });

    es.addEventListener("structured", (e: MessageEvent) => {
      const event = JSON.parse(e.data) as RunEvent;
      setState((prev) => ({
        ...prev,
        status: "running",
        events: [...prev.events, event],
      }));
    });

    es.addEventListener("done", (e: MessageEvent) => {
      const run = JSON.parse(e.data) as RunState;
      setState((prev) => {
        const next: RunEventsState = {
          ...prev,
          status: run.status,
          events: run.events ?? prev.events,
          result: run.result ?? null,
          error: run.error ?? null,
          done: true,
        };
        setTimeout(() => onDoneRef.current?.(next), 0);
        return next;
      });
      es.close();
    });

    es.addEventListener("error", () => es.close());

    return () => es.close();
  }, [runId]);

  return state;
}
