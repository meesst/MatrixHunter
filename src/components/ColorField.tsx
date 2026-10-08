import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface Props {
  value: string;
  onChange: (v: string) => void;
  tip?: string;
}

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

function hexToRgb(hex: string): [number, number, number] {
  let h = (hex || "").replace(/^#/, "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt((h.slice(0, 6) || "000000").padEnd(6, "0"), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(r: number, g: number, b: number): string {
  const f = (x: number) =>
    Math.round(Math.max(0, Math.min(255, x)))
      .toString(16)
      .padStart(2, "0")
      .toUpperCase();
  return `#${f(r)}${f(g)}${f(b)}`;
}

function rgbToHsv(r: number, g: number, b: number): [number, number, number] {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return [h, max === 0 ? 0 : d / max, max];
}

function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r = 0;
  let g = 0;
  let b = 0;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

/** 解析 `#RGB` / `#RRGGBB` / `#RRGGBBAA`。 */
function parseColor(v: string): { hex6: string; alpha: number } {
  let h = (v || "").trim().replace(/^#/, "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (h.length !== 6 && h.length !== 8) return { hex6: "#35E0FF", alpha: 1 };
  const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
  return { hex6: "#" + h.slice(0, 6), alpha: Number.isFinite(a) ? a : 1 };
}

/** 组合成 8 位 `#RRGGBBAA`。 */
function toHex8(hex6: string, alpha: number): string {
  const a = Math.round(clamp01(alpha) * 255)
    .toString(16)
    .padStart(2, "0")
    .toUpperCase();
  return `${hex6}${a}`;
}

/**
 * 取色控件：点击色块弹出取色面板（SV 区 + 色相条 + 透明度条），
 * 透明度就在同一面板里，不再单独占一个滑块。对外统一 8 位 `#RRGGBBAA`。
 */
export default function ColorField({ value, onChange, tip }: Props) {
  const { hex6, alpha } = parseColor(value);
  const [r, g, b] = hexToRgb(hex6);
  const [h, s, v] = rgbToHsv(r, g, b);

  const [open, setOpen] = useState(false);
  const [text, setText] = useState(value);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const popRef = useRef<HTMLDivElement | null>(null);
  const swatchRef = useRef<HTMLButtonElement | null>(null);
  const svRef = useRef<HTMLDivElement | null>(null);
  const hueRef = useRef<HTMLDivElement | null>(null);
  const alphaRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setText(value);
  }, [value]);

  // 点击面板外关闭
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t)) return;
      if (popRef.current?.contains(t)) return;
      setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  const emit = (hh: number, ss: number, vv: number, aa: number) => {
    const [rr, gg, bb] = hsvToRgb(hh, ss, vv);
    onChange(toHex8(rgbToHex(rr, gg, bb), aa));
  };

  const startDrag =
    (
      elRef: React.RefObject<HTMLDivElement | null>,
      onMove: (px: number, py: number) => void
    ) =>
    (e: React.PointerEvent) => {
      e.preventDefault();
      const rectOf = () => elRef.current?.getBoundingClientRect();
      const apply = (cx: number, cy: number) => {
        const rect = rectOf();
        if (!rect) return;
        onMove((cx - rect.left) / rect.width, (cy - rect.top) / rect.height);
      };
      apply(e.clientX, e.clientY);
      const move = (ev: PointerEvent) => apply(ev.clientX, ev.clientY);
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    };

  const pureHue = `hsl(${Math.round(h)}, 100%, 50%)`;
  const cur = `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`;

  return (
    <div className="color-field" data-tip={tip} ref={rootRef}>
      <button
        ref={swatchRef}
        type="button"
        className="cf-swatch"
        aria-label="选择颜色"
        onClick={() => {
          if (!open && swatchRef.current) {
            const r = swatchRef.current.getBoundingClientRect();
            setPos({
              left: Math.min(r.left, Math.max(8, window.innerWidth - 224)),
              top: Math.min(r.bottom + 6, Math.max(8, window.innerHeight - 214)),
            });
          }
          setOpen((o) => !o);
        }}
      >
        <span className="cf-checker" />
        <span className="cf-fill" style={{ background: value }} />
      </button>

      <input
        className="mono cf-hex"
        type="text"
        value={text}
        placeholder="#RRGGBBAA"
        onChange={(e) => {
          const raw = e.target.value;
          setText(raw);
          const hh = raw.trim().replace(/^#/, "");
          if (/^([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(hh)) {
            onChange("#" + hh.toUpperCase());
          }
        }}
        onBlur={() => setText(value)}
      />

      <span className="cf-alpha-val">{Math.round(alpha * 100)}%</span>

      {open &&
        createPortal(
          <div
            ref={popRef}
            className="cf-pop"
            style={pos ? { position: "fixed", left: pos.left, top: pos.top } : undefined}
            onMouseDown={(e) => e.stopPropagation()}
          >
          <div
            ref={svRef}
            className="cf-sv"
            style={{
              background: `linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, ${pureHue})`,
            }}
            onPointerDown={startDrag(svRef, (px, py) => emit(h, clamp01(px), clamp01(1 - py)))}
          >
            <span
              className="cf-dot"
              style={{ left: `${s * 100}%`, top: `${(1 - v) * 100}%`, background: cur }}
            />
          </div>

          <div
            ref={hueRef}
            className="cf-hue"
            onPointerDown={startDrag(hueRef, (px) => emit(clamp01(px) * 360, s, v))}
          >
            <span className="cf-handle" style={{ left: `${(h / 360) * 100}%` }} />
          </div>

          <div
            ref={alphaRef}
            className="cf-alpha-bar"
            style={{ ["--cf-base" as string]: hex6 }}
            onPointerDown={startDrag(alphaRef, (px) => emit(h, s, v, clamp01(px)))}
          >
            <span className="cf-handle" style={{ left: `${alpha * 100}%` }} />
          </div>
          </div>,
          document.body
        )}
    </div>
  );
}
