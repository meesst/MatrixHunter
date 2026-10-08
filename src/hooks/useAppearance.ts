import { useEffect, useState } from "react";
import type { AccentId, ThemeMode } from "../types";
import { readPref, urlOverride, writePref } from "../lib/prefs";

const MODES: ThemeMode[] = ["dark", "light", "system"];

export function useAppearance() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    const v = (urlOverride("mode") ?? readPref("mode", "dark")) as ThemeMode;
    return MODES.includes(v) ? v : "dark";
  });
  const [accent, setAccent] = useState<AccentId>(
    () => (urlOverride("accent") ?? readPref("accent", "blue")) as AccentId
  );
  const [showQuadrant, setShowQuadrant] = useState(() => readPref("quadrant", "1") !== "0");
  const [quadrantAlpha, setQuadrantAlpha] = useState(() => {
    const v = Number(readPref("qalpha", "0.22"));
    return Number.isFinite(v) && v > 0 ? v : 0.22;
  });
  const [quadrantLine, setQuadrantLine] = useState(() => readPref("qline", "#35E0FF"));
  const [quadrantLineWidth, setQuadrantLineWidth] = useState(() => {
    const v = Number(readPref("qlinew", "1.5"));
    return Number.isFinite(v) && v >= 0.5 ? v : 1.5;
  });
  const [leadW, setLeadW] = useState(() => {
    const v = Number(readPref("leadW", "424"));
    return Number.isFinite(v) ? Math.min(560, Math.max(280, v)) : 424;
  });

  useEffect(() => {
    const root = document.documentElement;
    const resolve = () =>
      themeMode === "system"
        ? window.matchMedia?.("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : themeMode;
    root.setAttribute("data-mode", resolve());
    if (themeMode !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => root.setAttribute("data-mode", resolve());
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [themeMode]);

  useEffect(() => {
    document.documentElement.setAttribute("data-accent", accent);
    writePref("accent", accent);
  }, [accent]);

  useEffect(() => {
    writePref("mode", themeMode);
  }, [themeMode]);

  useEffect(() => {
    writePref("quadrant", showQuadrant ? "1" : "0");
  }, [showQuadrant]);

  useEffect(() => {
    writePref("qalpha", String(quadrantAlpha));
  }, [quadrantAlpha]);

  useEffect(() => {
    writePref("qline", quadrantLine);
  }, [quadrantLine]);

  useEffect(() => {
    writePref("qlinew", String(quadrantLineWidth));
  }, [quadrantLineWidth]);

  useEffect(() => {
    writePref("leadW", String(leadW));
    document.documentElement.style.setProperty("--lead-w", `${leadW}px`);
  }, [leadW]);

  return {
    themeMode,
    setThemeMode,
    accent,
    setAccent,
    showQuadrant,
    setShowQuadrant,
    quadrantAlpha,
    setQuadrantAlpha,
    quadrantLine,
    setQuadrantLine,
    quadrantLineWidth,
    setQuadrantLineWidth,
    leadW,
    setLeadW,
  };
}
