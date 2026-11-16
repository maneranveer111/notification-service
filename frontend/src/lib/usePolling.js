import { useState, useEffect, useRef, useCallback } from 'react';

export function usePolling(fetchFn, { intervalMs = 5000, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const requestId = useRef(0);
  const intervalRef = useRef(null);

  const fetch_ = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const result = await fetchFn();
      if (id !== requestId.current) return;
      setData(result);
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [fetchFn]);

  const start = useCallback(() => {
    intervalRef.current = setInterval(() => {
      if (!document.hidden) fetch_();
    }, intervalMs);
  }, [fetch_, intervalMs]);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    fetch_();
    start();

    const onVisibility = () => {
      if (!document.hidden) fetch_();
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
      requestId.current++;
    };
  }, [enabled, fetch_, start, stop]);

  const refresh = useCallback(() => {
    fetch_();
  }, [fetch_]);

  return { data, error, loading, refresh, lastUpdated };
}

