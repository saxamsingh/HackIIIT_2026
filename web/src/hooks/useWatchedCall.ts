import { useCallback, useEffect, useRef, useState } from "react";
import { getRuns, pickRun, type RunRecord } from "../api";

export interface WatchedCall<T> {
  start: () => void;
  running: boolean;
  result: T | null;
  error: string | null;
  /** The agent run behind this call, found by polling while the call is in flight (and kept afterwards). */
  agentRun: RunRecord | null;
  reset: () => void;
}

/**
 * Runs `call` and, while it is in flight, polls /api/runs once a second for the agent run it started, so the
 * live viewer has a streaming_url to show long before the answer arrives.
 */
export function useWatchedCall<T>(call: () => Promise<T>): WatchedCall<T> {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agentRun, setAgentRun] = useState<RunRecord | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const alive = useRef(true);

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      stop();
    };
  }, []);

  const reset = useCallback(() => {
    stop();
    setResult(null);
    setError(null);
    setAgentRun(null);
    setRunning(false);
  }, []);

  const start = useCallback(() => {
    reset();
    setRunning(true);
    const since = Date.now();
    const poll = () =>
      getRuns()
        .then((runs) => alive.current && setAgentRun((prev) => pickRun(runs, since) ?? prev))
        .catch(() => undefined);
    timer.current = setInterval(poll, 1000);
    call()
      .then((r) => alive.current && setResult(r))
      .catch((e: unknown) => alive.current && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => {
        stop();
        if (!alive.current) return;
        setRunning(false);
        void poll(); // one last look, so a run that finished between polls is still shown
      });
  }, [call, reset]);

  return { start, running, result, error, agentRun, reset };
}
