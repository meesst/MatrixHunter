import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AttachInfo, WindowDetail } from "../types";

interface Props {
  attachInfo: AttachInfo | null;
}

/**
 * 窗口信息面板：显示当前选定窗口的类名、标题、进程路径、客户区、样式等。
 * 全部为只读输入框，可选中复制。
 */
export default function WindowInfoPanel({ attachInfo }: Props) {
  const [detail, setDetail] = useState<WindowDetail | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDetail(await api.windowDetail());
    } catch {
      setDetail(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [attachInfo, load]);

  const copy = (label: string, val: string) => {
    navigator.clipboard?.writeText(val).then(() => {
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1200);
    });
  };

  const fields: [string, string][] = detail
    ? [
        ["窗口句柄", detail.hwnd],
        ["窗口标题", detail.title],
        ["窗口类名", detail.class_name],
        ["进程名", detail.name],
        ["进程 PID", String(detail.pid)],
        ["进程位数", detail.is_64bit ? "64 位" : "32 位"],
        ["进程路径", detail.path],
        ["窗口位置", `${detail.win_x}, ${detail.win_y}`],
        ["窗口尺寸", `${detail.win_w} × ${detail.win_h}`],
        ["客户区位置", `${detail.client_x}, ${detail.client_y}`],
        ["客户区尺寸", `${detail.client_w} × ${detail.client_h}`],
        ["窗口样式", detail.style],
        ["扩展样式", detail.ex_style],
      ]
    : [];

  return (
    <div className="card" style={{ flex: 1, minHeight: 0 }}>
      <div className="card-head">
        <span className="dot" />
        <h3>窗口信息</h3>
        <div className="spacer" />
        <button className="btn sm" onClick={load} disabled={!attachInfo}>
          刷新
        </button>
      </div>
      <div className="card-body">
        {!attachInfo ? (
          <div className="empty">
            <div className="big">◇</div>
            <div>未选定窗口</div>
            <div className="hint">
              在左侧「目标进程」里双击进程附加，或用「拖拽选窗」拖到目标窗口上松开，
              这里会显示该窗口的类名、标题、进程路径、客户区尺寸、样式等完整信息。
            </div>
          </div>
        ) : !detail ? (
          <div className="hint">窗口信息不可用（窗口可能已关闭或不可见），可点右上「刷新」重试。</div>
        ) : (
          <>
            <div className="hint">以下内容只读，可选中复制。</div>
            {fields.map(([label, val]) => (
              <label className="field" key={label}>
                <span className="info-label">
                  {label}
                  <button
                    type="button"
                    className="mini-copy"
                    onClick={(e) => {
                      e.preventDefault();
                      copy(label, val);
                    }}
                  >
                    {copied === label ? "已复制" : "复制"}
                  </button>
                </span>
                <input className="mono" type="text" readOnly value={val} />
              </label>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
