"use client";
// The colour theme. "dark" is the default; "light" is set as data-theme on <html>
// and remembered in localStorage. A script in layout.tsx applies it before paint.
import { useEffect, useState } from "react";

export type Theme = "dark" | "light";
const KEY = "pyxida.theme";

export function readTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function setTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem(KEY, t); } catch { /* private window */ }
}

/** The current theme, updated when data-theme changes on <html>. */
export function useTheme(): Theme {
  const [t, setT] = useState<Theme>("dark");
  useEffect(() => {
    setT(readTheme());
    const o = new MutationObserver(() => setT(readTheme()));
    o.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => o.disconnect();
  }, []);
  return t;
}

/** Inline, runs before paint: localStorage first, then the OS preference, then dark. */
export const THEME_BOOT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(KEY)});if(t!=="light"&&t!=="dark"){var q=new URLSearchParams(location.search).get("theme");t=q==="light"||q==="dark"?q:(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");}document.documentElement.dataset.theme=t;}catch(e){}})();`;
