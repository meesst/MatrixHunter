import type { PoolSummary } from "../types";

export type StatusKind = "info" | "ok" | "warn" | "error";

interface Props {
  message: string;
  kind: StatusKind;
  summary: PoolSummary;
  realtimeRunning: boolean;
  attached: boolean;
}

export default function StatusBar({ message, kind, summary, realtimeRunning, attached }: Props) {
  return (
    <div className="statusbar">
      <span className={`msg ${kind === "info" ? "" : kind}`}>{message || "就绪"}</span>
      {realtimeRunning && (
        <span className="stat" style={{ color: "var(--ok)" }}>
          ● 实时追踪
        </span>
      )}
      <span className="stat">
        目标 <b>{attached ? "已附加" : "未附加"}</b>
      </span>
      <span className="stat">
        方案 <b>{summary.total}</b>
      </span>
      <span className="stat">
        存活 <b style={{ color: "var(--ok)" }}>{summary.active}</b>
      </span>
      <span className="stat">
        淘汰 <b style={{ color: "var(--text-mute)" }}>{summary.eliminated}</b>
      </span>
      <span className="stat">
        撤销层 <b>{summary.undo_depth}</b>
      </span>
    </div>
  );
}
