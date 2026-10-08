import { PREFS_KEY } from "./constants";

export function readPref(key: string, fallback: string): string {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return fallback;
    return (JSON.parse(raw)?.[key] as string) ?? fallback;
  } catch {
    return fallback;
  }
}

export function writePref(key: string, value: string) {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    const obj = raw ? JSON.parse(raw) : {};
    obj[key] = value;
    localStorage.setItem(PREFS_KEY, JSON.stringify(obj));
  } catch {
    /* ignore */
  }
}

/** URL 参数临时覆盖（截图 / 对比）。 */
export function urlOverride(key: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(key);
  } catch {
    return null;
  }
}
