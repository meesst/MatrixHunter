import { useEffect, useRef, useState } from "react";
import { ACCENTS, LINE_COLORS, type AccentId, type ThemeMode } from "../types";
import { TIPS } from "../lib/tips";

export interface SettingsForm {
  sizeW: number;
  sizeH: number;
  /* 绘制 / 跟随频率（毫秒） */
  followMs: number;
  realtimeMs: number;
  boneMs: number;
}

interface Props {
  open: boolean;
  value: SettingsForm;
  onClose: () => void;
  onSave: (v: SettingsForm) => void;
  /* 外观（即时生效，独立于保存） */
  themeMode: ThemeMode;
  accent: AccentId;
  onTheme: (v: ThemeMode) => void;
  onAccent: (v: AccentId) => void;
  showQuadrant: boolean;
  onShowQuadrant: (v: boolean) => void;
  quadrantAlpha: number;
  onQuadrantAlpha: (v: number) => void;
  quadrantLine: string;
  onQuadrantLine: (v: string) => void;
  quadrantLineWidth: number;
  onQuadrantLineWidth: (v: number) => void;
}

const SECTIONS: { id: string; label: string }[] = [
  { id: "appearance", label: "外观" },
  { id: "overlay", label: "叠加层" },
  { id: "frame", label: "刷新频率" },
  { id: "target", label: "目标窗口" },
  { id: "storage", label: "配置存储" },
];

export default function SettingsModal({
  open,
  value,
  onClose,
  onSave,
  themeMode,
  accent,
  onTheme,
  onAccent,
  showQuadrant,
  onShowQuadrant,
  quadrantAlpha,
  onQuadrantAlpha,
  quadrantLine,
  onQuadrantLine,
  quadrantLineWidth,
  onQuadrantLineWidth,
}: Props) {
  const [form, setForm] = useState<SettingsForm>(value);
  const [active, setActive] = useState(SECTIONS[0].id);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const secRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    if (open) {
      setForm(value);
      setActive(SECTIONS[0].id);
      scrollRef.current?.scrollTo({ top: 0 });
    }
  }, [open, value]);

  if (!open) return null;

  const patch = (p: Partial<SettingsForm>) => setForm({ ...form, ...p });

  const goto = (id: string) => {
    const sc = scrollRef.current;
    const el = secRefs.current[id];
    if (!sc || !el) return;
    const delta = el.getBoundingClientRect().top - sc.getBoundingClientRect().top;
    sc.scrollTo({ top: sc.scrollTop + delta - 10, behavior: "smooth" });
  };

  const onScroll = () => {
    const sc = scrollRef.current;
    if (!sc) return;
    // 底部留白足够大，每个分组都能滚到容器顶部，所以直接按"顶边到达容器顶"判定
    const scTop = sc.getBoundingClientRect().top;
    let cur = SECTIONS[0].id;
    for (const s of SECTIONS) {
      const el = secRefs.current[s.id];
      if (el && el.getBoundingClientRect().top - scTop <= 24) cur = s.id;
    }
    setActive(cur);
  };

  const group = (id: string, title: string, children: React.ReactNode) => (
    <div
      className="settings-group"
      ref={(el) => {
        secRefs.current[id] = el;
      }}
    >
      <h4>{title}</h4>
      {children}
    </div>
  );

  return (
    <div className="overlay-mask" onClick={onClose}>
      <div className="modal settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span className="dot" style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)" }} />
          设置
        </div>

        <div className="settings-body">
          <nav className="settings-nav">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                className={`settings-nav-item ${active === s.id ? "active" : ""}`}
                onClick={() => goto(s.id)}
              >
                {s.label}
              </button>
            ))}
          </nav>

          <div className="settings-scroll" ref={scrollRef} onScroll={onScroll}>
            {group(
              "appearance",
              "外观",
              <>
                <label className="field">
                  <span>主题模式</span>
                </label>
                <div className="opt-grid">
                  <button
                    className={`opt ${themeMode === "dark" ? "active" : ""}`}
                    onClick={() => onTheme("dark")}
                    data-tip={TIPS.settings.themeDark}
                  >
                    深色
                    <small>默认</small>
                  </button>
                  <button
                    className={`opt ${themeMode === "light" ? "active" : ""}`}
                    onClick={() => onTheme("light")}
                    data-tip={TIPS.settings.themeLight}
                  >
                    浅色
                    <small>亮环境用</small>
                  </button>
                  <button
                    className={`opt ${themeMode === "system" ? "active" : ""}`}
                    onClick={() => onTheme("system")}
                    data-tip={TIPS.settings.themeSystem}
                  >
                    跟随系统
                    <small>自动切换</small>
                  </button>
                </div>

                <label className="field">
                  <span>强调色</span>
                </label>
                <div className="swatches">
                  {ACCENTS.map((a) => (
                    <div
                      key={a.id}
                      className={`swatch ${accent === a.id ? "active" : ""}`}
                      style={{ background: `linear-gradient(135deg, ${a.c1}, ${a.c2})` }}
                      data-tip={TIPS.settings.accent}
                      onClick={() => onAccent(a.id)}
                    />
                  ))}
                </div>
              </>
            )}

            {group(
              "overlay",
              "叠加层",
              <>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={showQuadrant}
                    onChange={(e) => onShowQuadrant(e.target.checked)}
                  />
                  显示象限分区参照
                  <span className="hint">（十字线 + 四个象限字母）</span>
                </label>

                {showQuadrant && (
                  <>
                    <label className="field">
                      <span>象限字母透明度 · {quadrantAlpha.toFixed(2)}</span>
                      <input
                        type="range"
                        min={0.04}
                        max={0.6}
                        step={0.02}
                        value={quadrantAlpha}
                        data-tip={TIPS.settings.quadrantAlpha}
                        onChange={(e) => onQuadrantAlpha(Number(e.target.value))}
                      />
                    </label>

                    <label className="field">
                      <span>十字线颜色</span>
                      <div className="swatches" style={{ marginTop: 4 }}>
                        {LINE_COLORS.map((c) => (
                          <div
                            key={c.id}
                            className={`swatch ${quadrantLine === c.c ? "active" : ""}`}
                            style={{ background: c.c }}
                            data-tip={TIPS.settings.quadrantLine}
                            onClick={() => onQuadrantLine(c.c)}
                          />
                        ))}
                      </div>
                    </label>

                    <label className="field">
                      <span>十字线宽度 · {quadrantLineWidth.toFixed(1)} px</span>
                      <input
                        type="range"
                        min={0.5}
                        max={6}
                        step={0.1}
                        value={quadrantLineWidth}
                        data-tip={TIPS.settings.quadrantLineWidth}
                        onChange={(e) => onQuadrantLineWidth(Number(e.target.value))}
                      />
                    </label>
                  </>
                )}
              </>
            )}

            {group(
              "frame",
              "刷新频率",
              <>
                <div className="hint">
                  数值越小越跟手，代价是 CPU 占用略高。窗口移动时的跟随迟滞主要由「窗口跟随」决定。
                </div>
                <div className="grid3">
                  <label className="field">
                    <span>窗口跟随（ms）</span>
                    <input
                      className="mono"
                      type="number"
                      min={4}
                      max={500}
                      step={2}
                      value={form.followMs}
                      data-tip={TIPS.settings.follow}
                      onChange={(e) => patch({ followMs: Number(e.target.value) })}
                    />
                  </label>
                  <label className="field">
                    <span>实时点（ms）</span>
                    <input
                      className="mono"
                      type="number"
                      min={8}
                      max={500}
                      step={1}
                      value={form.realtimeMs}
                      data-tip={TIPS.settings.realtime}
                      onChange={(e) => patch({ realtimeMs: Number(e.target.value) })}
                    />
                  </label>
                  <label className="field">
                    <span>骨骼（ms）</span>
                    <input
                      className="mono"
                      type="number"
                      min={10}
                      max={1000}
                      step={5}
                      value={form.boneMs}
                      data-tip={TIPS.settings.bone}
                      onChange={(e) => patch({ boneMs: Number(e.target.value) })}
                    />
                  </label>
                </div>
              </>
            )}

            {group(
              "target",
              "目标窗口",
              <>
                <div className="grid2">
                  <label className="field">
                    <span>客户区宽度（0 = 自动跟随）</span>
                    <input
                      className="mono"
                      type="number"
                      value={form.sizeW}
                      data-tip={TIPS.settings.sizeW}
                      onChange={(e) => patch({ sizeW: Number(e.target.value) })}
                    />
                  </label>
                  <label className="field">
                    <span>客户区高度</span>
                    <input
                      className="mono"
                      type="number"
                      value={form.sizeH}
                      data-tip={TIPS.settings.sizeH}
                      onChange={(e) => patch({ sizeH: Number(e.target.value) })}
                    />
                  </label>
                </div>
                <div className="hint">
                  默认自动读取目标窗口的客户区尺寸；当游戏为无边框窗口或独立分辨率导致坐标对不齐时，可在这里手动覆盖。
                </div>
              </>
            )}

            {group(
              "storage",
              "配置存储",
              <>
                <div className="hint">
                  <b>配置文件</b>（热键无关的后端设置：地址、象限、频率、骨骼参数等）
                  <br />
                  <code className="mono path-code">%APPDATA%\com.matrixhunter.app\settings.json</code>
                  <br />
                  <br />
                  <b>界面偏好</b>（主题、强调色、象限参照、布局等，存于 WebView 本地存储）
                  <br />
                  <code className="mono path-code">localStorage · key = mh.prefs</code>
                  <br />
                  <br />
                  界面偏好即时生效并自动写入；其余设置点击「保存」后写入配置文件。
                </div>
              </>
            )}
          </div>
        </div>

        <div className="modal-foot">
          <button className="btn ghost" onClick={onClose}>
            取消
          </button>
          <button className="btn primary" onClick={() => onSave(form)}>
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
