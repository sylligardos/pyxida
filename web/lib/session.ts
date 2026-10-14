"use client";

// useState that survives navigation within the tab. The value is read from
// sessionStorage after mount (the server render uses `initial`, so there is
// no hydration mismatch) and written back on every change. It is gone when
// the tab closes: the next visitor at the booth starts clean.

import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

const PREFIX = "pyxida.session.";

export function useSessionState<T>(
  key: string,
  initial: T,
  // Called after mount; false keeps `initial` and ignores the stored value,
  // e.g. when the URL explicitly asked for something.
  restore?: () => boolean,
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(initial);
  const [ready, setReady] = useState<string | null>(null);   // the key the value belongs to
  const init = useRef(initial); init.current = initial;
  const check = useRef(restore); check.current = restore;

  useEffect(() => {
    let v: T = init.current;
    if (!check.current || check.current()) {
      try {
        const raw = sessionStorage.getItem(PREFIX + key);
        if (raw !== null) v = JSON.parse(raw) as T;
      } catch { /* private window, or blocked */ }
    }
    setValue(v);
    setReady(key);
  }, [key]);

  useEffect(() => {
    if (ready !== key) return;
    try { sessionStorage.setItem(PREFIX + key, JSON.stringify(value)); } catch { /* full, or blocked */ }
  }, [key, value, ready]);

  return [value, setValue];
}
