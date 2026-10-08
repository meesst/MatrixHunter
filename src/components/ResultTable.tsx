import { useEffect, useMemo, useState } from "react";
import type { SchemeView } from "../types";
import { TIPS } from "../lib/tips";

interface Props {
  schemes: SchemeView[];
  selectedId: string | null;
  previewId: string | null;
  realtimeRunning: boolean;
  onSelect: (id: string) => void;
  onPreview: (id: string) => void;
  onRealtimePreview: (id: string) => void;
  onRemove: (id: string) => void;
  onCopy: (addr: string) => void;
  onCopyAlgo: (id: string) => void;
  banner?: string | null;
  bannerKind?: "info" | "warn";
}

type FilterMode = "all" | "active" | "eliminated";

/// 单页渲染行数。候选地址可达上万（方案数万条），
/// 一次性铺进 DOM 会卡死，故只渲染当前页。
const PAGE_SIZE = 200;

export default function ResultTable({
  schemes,
  selectedId,
  previewId,
  realtimeRunning,
  onSelect,
  onPreview,
  onRealtimePreview,
  onRemove,
  onCopy,
  onCopyAlgo,
  banner,
  bannerKind = "info",
}: Props) {
  const [mode, setMode] = useState<FilterMode>("active");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    let list = schemes;
    if (mode === "active") list = list.filter((s) => s.status === "active");
    if (mode === "eliminated") list = list.filter((s) => s.status === "eliminated");
    const kw = keyword.trim().toLowerCase();
    if (kw) {
      list = list.filter(
        (s) =>
          s.address_hex.toLowerCase().includes(kw) ||
          s.description.toLowerCase().includes(kw) ||
          s.data_type.toLowerCase().includes(kw)
      );
    }
    return list;
  }, [schemes, mode, keyword]);

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  // 数据变化（过滤/删除等）后把越界的页码夹回有效范围
  const current = Math.min(page, pageCount - 1);
  useEffect(() => {
    if (page !== current) setPage(current);
  }, [page, current]);

  const pageRows = useMemo(
    () => rows.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE),
    [rows, current]
  );

  const goPage = (p: number) => setPage(Math.max(0, Math.min(pageCount - 1, p)));

  return (
    <>
      <div className="card-head">
        <span className="dot" />
        <h3>方案结果</h3>
        <span className="tag">{rows.length} 条</span>
        <div className="spacer" />
        <input
          className="table-search"
          type="text"
          placeholder="筛选地址 / 方案…"
          data-tip={TIPS.result.search}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <div className="seg">
          {(
            [
              ["active", "存活", TIPS.result.modeActive],
              ["eliminated", "淘汰", TIPS.result.modeEliminated],
              ["all", "全部", TIPS.result.modeAll],
            ] as [FilterMode, string, string][]
          ).map(([m, label, tip]) => (
            <button
              key={m}
              className={`btn sm ${mode === m ? "primary" : "ghost"}`}
              onClick={() => {
                setMode(m);
                setPage(0);
              }}
              data-tip={tip}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {banner ? <div className={`table-banner ${bannerKind}`}>{banner}</div> : null}

      <div className="table-wrap">
        {rows.length === 0 ? (
          <div className="empty">
            <div className="big">◎</div>
            <div>暂无方案</div>
            <div className="hint">
              在左侧「矩阵查找」输入地址并点击“枚举矩阵”，或直接对目标执行“过滤”。
            </div>
          </div>
        ) : (
          <table className="result">
            <thead>
              <tr>
                <th style={{ width: 134 }}>地址</th>
                <th>方案</th>
                <th style={{ width: 76 }}>类型</th>
                <th style={{ width: 74 }}>状态</th>
                <th style={{ width: 176 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((s) => (
                <tr
                  key={s.scheme_id}
                  className={`${selectedId === s.scheme_id ? "selected" : ""} ${
                    s.status === "eliminated" ? "eliminated" : ""
                  }`}
                  onClick={() => s.status === "active" && onSelect(s.scheme_id)}
                >
                  <td className="addr">{s.address_hex}</td>
                  <td>{s.description}</td>
                  <td>
                    <span className="tagx">{s.data_type}</span>
                  </td>
                  <td style={{ color: s.status === "active" ? "var(--ok)" : "var(--text-mute)" }}>
                    {s.status === "active" ? "存活" : "淘汰"}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="row" style={{ gap: 5 }}>
                      <button
                        className={`btn sm ${previewId === s.scheme_id ? "primary" : ""}`}
                        onClick={() => onPreview(s.scheme_id)}
                        data-tip={TIPS.result.preview}
                      >
                        {previewId === s.scheme_id ? "关闭预览" : "预览"}
                      </button>
                      <button
                        className={`btn sm ${
                          selectedId === s.scheme_id && realtimeRunning ? "danger" : ""
                        }`}
                        disabled={s.status !== "active"}
                        onClick={() => onRealtimePreview(s.scheme_id)}
                        data-tip={TIPS.result.realtimePreview}
                      >
                        {selectedId === s.scheme_id && realtimeRunning ? "停止实时" : "实时预览"}
                      </button>
                      <button
                        className="btn sm ghost"
                        onClick={() => onCopy(s.address_hex)}
                        data-tip={TIPS.result.copy}
                      >
                        复制
                      </button>
                      <button
                        className="btn sm ghost"
                        onClick={() => onCopyAlgo(s.scheme_id)}
                        data-tip={TIPS.result.copyAlgo}
                      >
                        复制算法
                      </button>
                      <button
                        className="btn sm danger"
                        onClick={() => onRemove(s.scheme_id)}
                        data-tip={TIPS.result.remove}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {rows.length > PAGE_SIZE ? (
        <div className="pager">
          <button className="btn sm ghost" disabled={current === 0} onClick={() => goPage(0)}>
            首页
          </button>
          <button
            className="btn sm ghost"
            disabled={current === 0}
            onClick={() => goPage(current - 1)}
          >
            上一页
          </button>
          <span className="pager-info">
            第 {current + 1} / {pageCount} 页 · 共 {rows.length} 条
          </span>
          <button
            className="btn sm ghost"
            disabled={current >= pageCount - 1}
            onClick={() => goPage(current + 1)}
          >
            下一页
          </button>
          <button
            className="btn sm ghost"
            disabled={current >= pageCount - 1}
            onClick={() => goPage(pageCount - 1)}
          >
            末页
          </button>
        </div>
      ) : null}
    </>
  );
}
