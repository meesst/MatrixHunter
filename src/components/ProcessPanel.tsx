import { useMemo, useState } from "react";
import type { AttachInfo, ProcessInfo } from "../types";
import { TIPS } from "../lib/tips";

interface Props {
  processes: ProcessInfo[];
  attached: AttachInfo | null;
  loading: boolean;
  onRefresh: () => void;
  onAttach: (pid: number) => void;
  onDetach: () => void;
  onPickWindow: () => void;
}

export default function ProcessPanel({
  processes,
  attached,
  loading,
  onRefresh,
  onAttach,
  onDetach,
  onPickWindow,
}: Props) {
  const [keyword, setKeyword] = useState("");
  const [selectedPid, setSelectedPid] = useState<number | null>(null);

  const list = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    let arr = processes;
    if (kw) {
      arr = arr.filter(
        (p) => p.name.toLowerCase().includes(kw) || String(p.pid).includes(kw)
      );
    }
    return [...arr].sort((a, b) => a.name.localeCompare(b.name));
  }, [processes, keyword]);

  const isAttached = !!attached;

  return (
    <div className="card">
      <div className="card-head">
        <span className="dot" />
        <h3>目标进程</h3>
        <span className="tag">{processes.length} 个</span>
        <div className="spacer" />
        <button
          className="btn sm"
          onClick={onRefresh}
          disabled={loading}
          data-tip={TIPS.proc.refresh}
        >
          {loading ? "刷新中…" : "刷新"}
        </button>
      </div>
      <div className="card-body">
        <div className="row">
          <div
            className={`status-pill ${isAttached ? "on" : ""}`}
            data-tip={isAttached ? TIPS.toolbar.attachOn : TIPS.toolbar.attachOff}
          >
            <span className="led" />
            {isAttached
              ? `pid ${attached!.pid} · ${attached!.name}`
              : "未附加进程"}
          </div>
          <div className="spacer" />
          {isAttached && (
            <button
              className="btn sm danger"
              onClick={onDetach}
              data-tip={TIPS.proc.detach}
            >
              断开
            </button>
          )}
        </div>

        <div className="row">
          <input
            type="text"
            placeholder="搜索进程名或 PID…"
            value={keyword}
            data-tip={TIPS.proc.search}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <button
            className="btn"
            onMouseDown={onPickWindow}
            data-tip={TIPS.proc.dragPick}
          >
            拖拽选窗
          </button>
        </div>

        <div className="proc-list">
          {list.length === 0 ? (
            <div className="hint" style={{ padding: 14, textAlign: "center" }}>
              没有匹配的进程
            </div>
          ) : (
            list.slice(0, 400).map((p) => (
              <div
                key={p.pid}
                className={`proc-item ${selectedPid === p.pid ? "selected" : ""}`}
                onClick={() => setSelectedPid(p.pid)}
                onDoubleClick={() => onAttach(p.pid)}
                data-tip={TIPS.proc.listItem}
              >
                <span className="proc-badge">{p.is_64bit ? "64 位" : "32 位"}</span>
                <span className="proc-name">{p.name}</span>
                <span className="proc-pid mono">{p.pid}</span>
              </div>
            ))
          )}
        </div>

        <button
          className="btn primary"
          disabled={selectedPid == null || isAttached}
          onClick={() => selectedPid != null && onAttach(selectedPid)}
          data-tip={TIPS.proc.attachBtn}
        >
          附加到选中进程
        </button>
        <div className="hint">
          双击列表项可直接附加；按住「拖拽选窗」拖到目标窗口上，松开左键即自动识别并附加。
        </div>
      </div>
    </div>
  );
}
