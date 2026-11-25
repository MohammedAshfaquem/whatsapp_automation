import {useEffect, useRef, useState} from 'react';

/** Fixed-cadence, single-flight reads; returning to the page wakes it immediately. */
export function useVisibleAutoSync(sync: () => Promise<unknown>, intervalMs = 2500) {
  const callback = useRef(sync);
  callback.current = sync;
  const flight = useRef<Promise<void> | null>(null);
  const alive = useRef(false);
  const wakePending = useRef(false);
  const [syncError, setSyncError] = useState(false);
  const run = (wake = false): Promise<void> => {
    if (!alive.current) return Promise.resolve();
    if (flight.current) {
      if (wake) wakePending.current = true;
      return flight.current;
    }
    const task = Promise.resolve().then(() => callback.current()).then(
      () => { if (alive.current) setSyncError(false); },
      () => { if (alive.current) setSyncError(true); },
    ).finally(() => {
      flight.current = null;
      if (alive.current && wakePending.current && !document.hidden) {
        wakePending.current = false;
        void run();
      }
    });
    flight.current = task;
    return task;
  };
  useEffect(() => {
    alive.current = true;
    const wake = () => { if (!document.hidden) void run(true); };
    const timer = window.setInterval(() => { if (!document.hidden) void run(); }, intervalMs);
    window.addEventListener('focus', wake);
    document.addEventListener('visibilitychange', wake);
    return () => {
      alive.current = false;
      wakePending.current = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', wake);
      document.removeEventListener('visibilitychange', wake);
    };
  }, [intervalMs]);
  return {refresh: () => run(true), syncError};
}
