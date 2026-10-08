import { useEffect, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { api } from "../lib/api";
import type { PerfSnapshot } from "../types";
import { isTauri } from "../lib/env";
import { TIPS } from "../lib/tips";

interface Props {
  version?: string;
  attached: boolean;
  attachLabel?: string;
  onOpenSettings: () => void;
}

export default function TitleBar({ version, attached, attachLabel, onOpenSettings }: Props) {
  const [maximized, setMaximized] = useState(false);
  const [perf, setPerf] = useState<PerfSnapshot | null>(null);

  // 全局性能监测：每 1.5s 采集一次硬件 / 本进程占用
  useEffect(() => {
    if (!isTauri) return;
    let alive = true;
    const tick = () => {
      api
        .perfSnapshot()
        .then((p) => {
          if (alive) setPerf(p);
        })
        .catch(() => {});
    };
    tick();
    const id = window.setInterval(tick, 1500);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!isTauri) return;
    const win = getCurrentWindow();
    let un: (() => void) | undefined;
    win.isMaximized().then(setMaximized).catch(() => {});
    win
      .onResized(() => {
        win.isMaximized().then(setMaximized).catch(() => {});
      })
      .then((f) => {
        un = f;
      })
      .catch(() => {});
    return () => un?.();
  }, []);

  const minimize = () => isTauri && getCurrentWindow().minimize().catch(() => {});
  const toggleMax = () => isTauri && getCurrentWindow().toggleMaximize().catch(() => {});
  const close = () => isTauri && getCurrentWindow().close().catch(() => {});

  return (
    <header className="titlebar" data-tauri-drag-region>
      <div className="tb-brand" data-tauri-drag-region>
        <div className="tb-logo">MH</div>
        <div className="tb-titles" data-tauri-drag-region>
          <span className="tb-name">MatrixHunter</span>
          <span className="tb-ver">v{version ?? "1.0.0"}</span>
        </div>
      </div>

      <div className="tb-drag" data-tauri-drag-region>
        <span className="tb-sub">内存矩阵发现与验证工具</span>
        {perf && (
          <span className="tb-perf" data-tip={TIPS.title.perf}>
            <span className="pf">
              本程序 CPU <b>{perf.cpu_percent.toFixed(1)}%</b>
            </span>
            <span className="pf">
              内存 <b>{perf.mem_mb}</b> MB（<b>{perf.mem_percent.toFixed(2)}%</b>）
            </span>
          </span>
        )}
      </div>

      <div className="tb-actions">
        <span
          className={`status-pill ${attached ? "on" : ""}`}
          data-tip={attached ? TIPS.title.attachOn : TIPS.title.attachOff}
        >
          <span className="led" />
          {attached ? attachLabel ?? "已附加" : "未附加"}
        </span>
        <button className="btn icon" data-tip={TIPS.title.settings} onClick={onOpenSettings}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="3.2" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.9 19.3a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.7 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.7 8.9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.7a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15 4.7a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9v.09A1.7 1.7 0 0 0 21 10.09H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1.03z" />
          </svg>
        </button>
      </div>

      <div className="tb-win">
        <button className="win-btn" data-tip={TIPS.title.minimize} onClick={minimize}>
          <svg viewBox="0 0 12 12" width="11" height="11">
            <path d="M1 6h10" stroke="currentColor" strokeWidth="1.2" />
          </svg>
        </button>
        <button
          className="win-btn"
          data-tip={maximized ? TIPS.title.restore : TIPS.title.maximize}
          onClick={toggleMax}
        >
          {maximized ? (
            <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.2">
              <rect x="1.2" y="3.2" width="7" height="7" rx="0.6" />
              <path d="M3.6 3.2V1.4h7v7H8.8" />
            </svg>
          ) : (
            <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.2">
              <rect x="1.4" y="1.4" width="9.2" height="9.2" rx="0.6" />
            </svg>
          )}
        </button>
        <button className="win-btn close" data-tip={TIPS.title.close} onClick={close}>
          <svg viewBox="0 0 12 12" width="11" height="11" stroke="currentColor" strokeWidth="1.2">
            <path d="M2 2l8 8M10 2l-8 8" />
          </svg>
        </button>
      </div>
    </header>
  );
}
