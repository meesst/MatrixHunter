import { useEffect, useRef, useState } from "react";
import type { DataType, Quadrant, WorldCoord } from "../types";
import { QUADRANTS } from "../types";
import { TIPS } from "../lib/tips";

/**
 * 数字输入框：用文本输入以便中途输入负号 / 小数点，
 * 仅当内容可解析为有限数时才回传数值。
 */
function WorldNumInput({
  value,
  onChange,
  tip,
}: {
  value: number;
  onChange: (n: number) => void;
  tip?: string;
}) {
  const [text, setText] = useState(() => String(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(String(value));
  }, [value, focused]);

  return (
    <input
      className="mono"
      type="text"
      inputMode="decimal"
      value={text}
      data-tip={tip}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onChange={(e) => {
        const v = e.target.value;
        setText(v);
        const n = Number(v);
        if (v.trim() !== "" && Number.isFinite(n)) onChange(n);
      }}
    />
  );
}

interface Props {
  addresses: string;
  setAddresses: (v: string | ((prev: string) => string)) => void;
  dataType: DataType;
  setDataType: (v: DataType) => void;
  quadrant: Quadrant;
  setQuadrant: (q: Quadrant) => void;
  world: WorldCoord;
  setWorld: (w: WorldCoord) => void;
  onEnumerate: () => void;
  onFilter: () => void;
  onUndo: () => void;
  onReset: () => void;
  onLoadFileText: (text: string) => void;
  canUndo: boolean;
  busy: boolean;
  attached: boolean;
  schemeCount: number;
}

export default function FindPanel(props: Props) {
  const {
    addresses,
    setAddresses,
    dataType,
    setDataType,
    quadrant,
    setQuadrant,
    world,
    setWorld,
    onEnumerate,
    onFilter,
    onUndo,
    onReset,
    onLoadFileText,
    canUndo,
    busy,
    attached,
    schemeCount,
  } = props;

  const [dragHot, setDragHot] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const readFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => onLoadFileText(String(reader.result ?? ""));
    reader.readAsText(file);
  };

  return (
    <div className="card">
      <div className="card-head">
        <span className="dot" />
        <h3>矩阵查找</h3>
        <span className="tag">{schemeCount} 方案</span>
      </div>
      <div className="card-body">
        <div className="grid2">
          <label className="field">
            <span>数据类型</span>
            <select
              value={dataType}
              data-tip={TIPS.find.dataType}
              onChange={(e) => setDataType(e.target.value as DataType)}
            >
              <option value="float">float（4 字节）</option>
              <option value="double">double（8 字节）</option>
            </select>
          </label>
          <label className="field">
            <span>目标象限</span>
            <select
              value={quadrant}
              data-tip={TIPS.find.quadrant}
              onChange={(e) => setQuadrant(e.target.value as Quadrant)}
            >
              {QUADRANTS.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.label}（{q.hint}）
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="quad-grid">
          {QUADRANTS.map((q) => (
            <div
              key={q.id}
              className={`quad ${quadrant === q.id ? "active" : ""}`}
              onClick={() => setQuadrant(q.id)}
              data-tip={TIPS.find.quadCell(q.label, q.hint)}
            >
              {q.label}
              <small>{q.hint}</small>
            </div>
          ))}
        </div>

        <label className="field">
          <span>候选地址（每行一个，支持 0x 十六进制）</span>
          <textarea
            className="mono"
            value={addresses}
            onChange={(e) => setAddresses(e.target.value)}
            placeholder={"0x1A2B3C40\n0x1A2B3D80\n1A2B3E00"}
            spellCheck={false}
            data-tip={TIPS.find.addresses}
          />
        </label>

        <div className="hint">
          提示：已知矩阵地址时，直接把它填进来 → 点「枚举矩阵」→ 点「过滤」，即可从 8
          种方案里筛出唯一正确的那个；骨骼 / 实时都基于选中的方案，所以这是最可靠的用法。
        </div>

        <div
          className={`dropzone ${dragHot ? "hot" : ""}`}
          data-tip={TIPS.find.dropzone}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragHot(true);
          }}
          onDragLeave={() => setDragHot(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragHot(false);
            const f = e.dataTransfer.files?.[0];
            if (f) readFile(f);
          }}
        >
          拖拽文本文件到此处导入地址 · 或点击选择文件
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.csv,.log,text/plain"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) readFile(f);
            e.target.value = "";
          }}
        />

        <div className="divider" />

        <div className="grid3">
          <label className="field">
            <span>世界 X</span>
            <WorldNumInput
              value={world.x}
              tip={TIPS.find.worldX}
              onChange={(n) => setWorld({ ...world, x: n })}
            />
          </label>
          <label className="field">
            <span>世界 Y</span>
            <WorldNumInput
              value={world.y}
              tip={TIPS.find.worldY}
              onChange={(n) => setWorld({ ...world, y: n })}
            />
          </label>
          <label className="field">
            <span>世界 Z</span>
            <WorldNumInput
              value={world.z}
              tip={TIPS.find.worldZ}
              onChange={(n) => setWorld({ ...world, z: n })}
            />
          </label>
        </div>

        <div className="btn-row">
          <button
            className="btn"
            onClick={onEnumerate}
            disabled={busy || !attached}
            data-tip={TIPS.find.enumerate}
          >
            枚举矩阵
          </button>
          <button
            className="btn"
            onClick={onFilter}
            disabled={busy || !attached}
            data-tip={TIPS.find.filter}
          >
            过滤（象限）
          </button>
          <button
            className="btn"
            onClick={onUndo}
            disabled={busy || !canUndo}
            data-tip={TIPS.find.undo}
          >
            撤销
          </button>
          <button
            className="btn"
            onClick={onReset}
            disabled={busy}
            data-tip={TIPS.find.reset}
          >
            清空
          </button>
        </div>

        <div className="hint">
          过滤会读取每个地址的矩阵并把投影点落在「目标象限」之外的方案淘汰；若全部被淘汰会自动回滚。
          实时投影请用右侧「方案结果」里每条方案后的「实时预览」按钮（选中并开启，再点一次停止）。
        </div>
      </div>
    </div>
  );
}
