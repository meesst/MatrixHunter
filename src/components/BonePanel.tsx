import { useEffect, useState } from "react";
import { TIPS } from "../lib/tips";
import ColorField from "./ColorField";

export interface BoneForm {
  base: string;
  count: number;
  stride: number;
  addr: string;
  hidden: string;
  conn: string;
  fontSize: number;
  fontColor: string;
  lineColor: string;
  lineWidth: number;
  pointRadius: number;
  pointOutlineWidth: number;
  pointColor: string;
  showLabels: boolean;
  showLines: boolean;
  showJoints: boolean;
  /** 点位筛选方式：label = 按显示序号；links = 按连接关系 */
  pointMode: "label" | "links";
  enabled: boolean;
}

/** 人体模板的关键部位（只需填填对应的骨骼序号）。 */
const BODY_SLOTS: [string, string][] = [
  ["head", "头"],
  ["neck", "颈"],
  ["chest", "胸"],
  ["pelvis", "腰"],
  ["l_shoulder", "左肩"],
  ["l_elbow", "左肘"],
  ["l_hand", "左手"],
  ["r_shoulder", "右肩"],
  ["r_elbow", "右肘"],
  ["r_hand", "右手"],
  ["l_hip", "左髋"],
  ["l_knee", "左膝"],
  ["l_foot", "左脚"],
  ["r_hip", "右髋"],
  ["r_knee", "右膝"],
  ["r_foot", "右脚"],
];

/** 人体骨架的大关系（关节连线）；只连接两端都填了的点。 */
const BODY_LINKS: [string, string][] = [
  ["head", "neck"],
  ["neck", "chest"],
  ["chest", "pelvis"],
  ["neck", "l_shoulder"],
  ["l_shoulder", "l_elbow"],
  ["l_elbow", "l_hand"],
  ["neck", "r_shoulder"],
  ["r_shoulder", "r_elbow"],
  ["r_elbow", "r_hand"],
  ["pelvis", "l_hip"],
  ["l_hip", "l_knee"],
  ["l_knee", "l_foot"],
  ["pelvis", "r_hip"],
  ["r_hip", "r_knee"],
  ["r_knee", "r_foot"],
];

interface Props {
  value: BoneForm;
  onChange: (patch: Partial<BoneForm>) => void;
  liveCount: number;
  /** 是否已在结果列表中选中一条方案（未选中则不允许启用骨骼）。 */
  hasSelection: boolean;
  /** 当前选中方案的矩阵地址（只读展示，不可自定义）。 */
  schemeAddress: string;
}

export default function BonePanel({
  value,
  onChange,
  liveCount,
  hasSelection,
  schemeAddress,
}: Props) {
  const [styleOpen, setStyleOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [body, setBody] = useState<Record<string, number | "">>({});

  const setSlot = (key: string, v: string) => {
    setBody((b) => ({ ...b, [key]: v === "" ? "" : Math.max(0, Math.floor(Number(v))) }));
  };

  const applyBodyTemplate = () => {
    const idx: Record<string, number> = {};
    for (const [key] of BODY_SLOTS) {
      const v = body[key];
      if (typeof v === "number" && Number.isFinite(v)) idx[key] = v;
    }
    const lines: string[] = [];
    for (const [a, b] of BODY_LINKS) {
      if (idx[a] !== undefined && idx[b] !== undefined) lines.push(`${idx[a]}-${idx[b]}`);
    }
    onChange({ conn: lines.join("\n") });
  };

  /** 把当前模板整理成可粘贴的文本。 */
  const buildTemplateText = () => {
    const lines: string[] = ["MatrixHunter 人体模板（部位 = 骨骼序号）"];
    const idx: Record<string, number> = {};
    for (const [key, label] of BODY_SLOTS) {
      const v = body[key];
      if (typeof v === "number" && Number.isFinite(v)) {
        idx[key] = v;
        lines.push(`${label} = ${v}`);
      }
    }
    lines.push("", "连接关系：");
    for (const [a, b] of BODY_LINKS) {
      if (idx[a] !== undefined && idx[b] !== undefined) lines.push(`${idx[a]}-${idx[b]}`);
    }
    return lines.join("\n");
  };

  const copyTemplate = () => {
    navigator.clipboard?.writeText(buildTemplateText());
  };

  // 强制要求：没有选中方案时自动关闭「启用」。
  useEffect(() => {
    if (!hasSelection && value.enabled) onChange({ enabled: false });
  }, [hasSelection, value.enabled, onChange]);

  return (
    <div className="card">
      <div className="card-head">
        <span className="dot" style={{ background: "var(--gold)", boxShadow: "0 0 10px var(--gold)" }} />
        <h3>骨骼编号</h3>
        <span className="tag">
          可见 <span className="bone-count">{liveCount}</span>
        </span>
        <div className="spacer" />
        <label
          className="switch"
          data-tip={hasSelection ? TIPS.bone.enabled : TIPS.bone.enabledNeedScheme}
        >
          <input
            type="checkbox"
            checked={value.enabled}
            disabled={!hasSelection}
            onChange={(e) => onChange({ enabled: e.target.checked })}
          />
          启用
        </label>
      </div>
      <div className="card-body">
        {!hasSelection && (
          <div className="hint" style={{ color: "var(--warn)" }}>
            未选中方案：骨骼编号已停用。请先在右侧「方案结果」选中一条存活方案（先在「矩阵查找」枚举 +
            过滤确定方案），再启用骨骼。
          </div>
        )}
        <div className="grid2">
          <label className="field">
            <span>骨骼基址</span>
            <input
              className="mono"
              type="text"
              placeholder="0x..."
              value={value.base}
              data-tip={TIPS.bone.base}
              onChange={(e) => onChange({ base: e.target.value })}
            />
          </label>
          <label className="field">
            <span>矩阵地址（来自选中方案）</span>
            <input
              className="mono"
              type="text"
              readOnly
              value={schemeAddress}
              placeholder="未选中方案"
              data-tip={TIPS.bone.addr}
            />
          </label>
        </div>

        <div className="hint">
          矩阵地址与「解释方式」都取自右侧选中的方案（同一地址有 8 种可能）。若已知矩阵地址，请先在
          「矩阵查找」填入该地址 → 枚举矩阵 → 过滤，选中唯一方案后再来这里启用骨骼。
        </div>

        <div className="grid2">
          <label className="field">
            <span>骨骼数量</span>
            <input
              className="mono"
              type="number"
              min={0}
              value={value.count}
              data-tip={TIPS.bone.count}
              onChange={(e) => onChange({ count: Math.max(0, Number(e.target.value)) })}
            />
          </label>
          <label className="field">
            <span>步长（字节）</span>
            <input
              className="mono"
              type="number"
              min={1}
              value={value.stride}
              data-tip={TIPS.bone.stride}
              onChange={(e) => onChange({ stride: Math.max(1, Number(e.target.value)) })}
            />
          </label>
        </div>

        <div className="field">
          <span>点位筛选方式（控制哪些点与序号被绘制）</span>
          <div className="seg">
            <button
              type="button"
              className={`btn sm ${value.pointMode === "label" ? "primary" : "ghost"}`}
              onClick={() => onChange({ pointMode: "label" })}
              data-tip={TIPS.bone.modeLabel}
            >
              按显示序号
            </button>
            <button
              type="button"
              className={`btn sm ${value.pointMode === "links" ? "primary" : "ghost"}`}
              onClick={() => onChange({ pointMode: "links" })}
              data-tip={TIPS.bone.modeLinks}
            >
              按连接关系
            </button>
          </div>
        </div>

        {value.pointMode === "label" ? (
          <label className="field">
            <span>显示序号（留空 = 全部；支持 1,3,5 或 1-3）</span>
            <div className="row">
              <input
                className="mono"
                type="text"
                value={value.hidden}
                placeholder="留空表示显示全部序号"
                data-tip={TIPS.bone.labelOnly}
                onChange={(e) => onChange({ hidden: e.target.value })}
              />
              <button
                type="button"
                className="btn"
                onClick={(e) => {
                  e.preventDefault();
                  onChange({ hidden: "" });
                }}
              >
                清空
              </button>
            </div>
          </label>
        ) : (
          <div className="hint">
            当前按「连接关系」筛选：只绘制连接关系里出现过的点与序号，连线仍由「显示连线」开关控制。
          </div>
        )}

        <label className="field">
          <span>连接关系（每行 "a-b"，如 0-1）</span>
          <textarea
            className="mono"
            style={{ minHeight: 52 }}
            value={value.conn}
            placeholder={"0-1\n1-2\n2-3"}
            data-tip={TIPS.bone.conn}
            onChange={(e) => onChange({ conn: e.target.value })}
          />
        </label>

        <div className="row">
          <button
            type="button"
            className="btn"
            onClick={() => setTemplateOpen((v) => !v)}
          >
            {templateOpen ? "收起人体模板" : "展开人体模板"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setStyleOpen((v) => !v)}
          >
            {styleOpen ? "收起绘制样式" : "展开绘制样式"}
          </button>
        </div>

        {templateOpen && (
          <div className="style-block">
            <div className="hint">
              填入各部位对应的骨骼序号，点「生成连接关系」即可自动连成人体骨架（只连接两端都填了的点）。
            </div>
            <div className="grid3">
              {BODY_SLOTS.map(([key, label]) => (
                <label className="field" key={key}>
                  <span>{label}</span>
                  <input
                    className="mono"
                    type="number"
                    min={0}
                    value={body[key] ?? ""}
                    placeholder="—"
                    onChange={(e) => setSlot(key, e.target.value)}
                  />
                </label>
              ))}
            </div>
            <div className="row wrap">
              <button type="button" className="btn primary" onClick={applyBodyTemplate}>
                生成连接关系
              </button>
              <button type="button" className="btn" onClick={copyTemplate}>
                复制模板
              </button>
              <button type="button" className="btn ghost" onClick={() => setBody({})}>
                清空模板
              </button>
            </div>
          </div>
        )}

        {styleOpen && (
        <div className="style-block">
        <div className="grid2">
          <label className="field">
            <span>字号</span>
            <div className="row">
              <input
                className="mono"
                type="number"
                min={6}
                value={value.fontSize}
                data-tip={TIPS.bone.fontSize}
                onChange={(e) => onChange({ fontSize: Number(e.target.value) })}
              />
              <button
                type="button"
                className={`mini-toggle ${value.showLabels ? "on" : ""}`}
                data-tip={TIPS.bone.showLabels}
                onClick={(e) => {
                  e.preventDefault();
                  onChange({ showLabels: !value.showLabels });
                }}
              >
                {value.showLabels ? "显示" : "隐藏"}
              </button>
            </div>
          </label>
          <label className="field">
            <span>连线粗细</span>
            <div className="row">
              <input
                className="mono"
                type="number"
                min={0}
                max={8}
                step={0.1}
                value={value.lineWidth}
                data-tip={TIPS.bone.lineWidth}
                onChange={(e) => onChange({ lineWidth: Math.max(0, Number(e.target.value)) })}
              />
              <button
                type="button"
                className={`mini-toggle ${value.showLines ? "on" : ""}`}
                data-tip={TIPS.bone.showLines}
                onClick={(e) => {
                  e.preventDefault();
                  onChange({ showLines: !value.showLines });
                }}
              >
                {value.showLines ? "显示" : "隐藏"}
              </button>
            </div>
          </label>
        </div>
        <div className="grid2">
          <label className="field">
            <span>关节大小</span>
            <div className="row">
              <input
                className="mono"
                type="number"
                min={0}
                max={20}
                step={0.5}
                value={value.pointRadius}
                data-tip={TIPS.bone.pointRadius}
                onChange={(e) => onChange({ pointRadius: Math.max(0, Number(e.target.value)) })}
              />
              <button
                type="button"
                className={`mini-toggle ${value.showJoints ? "on" : ""}`}
                data-tip={TIPS.bone.showJoints}
                onClick={(e) => {
                  e.preventDefault();
                  onChange({ showJoints: !value.showJoints });
                }}
              >
                {value.showJoints ? "显示" : "隐藏"}
              </button>
            </div>
          </label>
          <label className="field">
            <span>关节轮廓粗细</span>
            <input
              className="mono"
              type="number"
              min={0}
              max={8}
              step={0.1}
              value={value.pointOutlineWidth}
              data-tip={TIPS.bone.pointOutlineWidth}
              onChange={(e) =>
                onChange({ pointOutlineWidth: Math.max(0, Number(e.target.value)) })
              }
            />
          </label>
        </div>
        <label className="field">
          <span>关节颜色</span>
          <ColorField
            value={value.pointColor}
            tip={TIPS.bone.pointColor}
            onChange={(v) => onChange({ pointColor: v })}
          />
        </label>

        <label className="field">
          <span data-tip={TIPS.bone.fontColor}>序号颜色</span>
          <ColorField
            value={value.fontColor}
            tip={TIPS.bone.fontColor}
            onChange={(v) => onChange({ fontColor: v })}
          />
        </label>
        <label className="field">
          <span data-tip={TIPS.bone.lineColor}>连线颜色</span>
          <ColorField
            value={value.lineColor}
            tip={TIPS.bone.lineColor}
            onChange={(v) => onChange({ lineColor: v })}
          />
        </label>
        </div>
        )}

        <div className="hint">
          骨骼投影基于右侧选中的方案矩阵；未选中方案时无法启用。本页只负责读取并绘制骨骼，不参与矩阵过滤。
        </div>
      </div>
    </div>
  );
}
