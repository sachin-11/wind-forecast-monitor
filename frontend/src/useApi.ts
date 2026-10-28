import { useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** Fetch on dependency change, cancel stale requests, keep previous data while reloading. */
export function useApi<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true });

  useEffect(() => {
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fn(ctrl.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((err: Error) => {
        if (ctrl.signal.aborted) return;
        setState((s) => ({ ...s, error: err.message, loading: false }));
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
