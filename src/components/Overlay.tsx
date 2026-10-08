import { useEffect, useRef } from "react";
import { emit, listen } from "@tauri-apps/api/event";
import { events } from "../lib/api";
import type { AlignPayload, BoneFrame, PointPayload, PreviewResult, Quadrant } from "../types";

interface QuadrantPayload {
  quadrant: Quadrant;
  visible?: boolean;
  alpha?: number;
  line?: string;
  lineWidth?: number;
}

/** #RRGGBB → rgba(...)，用于给线颜色叠加上固定透明度。 */
function hexToRgba(hex: string, a: number): string {
  const h = (hex || "").replace("#", "");
  if (h.length !== 6) return `rgba(53,224,255,${a})`;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  if ([r, g, b].some((v) => Number.isNaN(v))) return `rgba(53,224,255,${a})`;
  return `rgba(${r},${g},${b},${a})`;
}
/**
 * 透明叠加层：全屏 canvas，绘制象限高亮、实时点、预览点、骨骼点与连线。
 * 通过 Tauri 事件接收数据；窗口本身由 Rust 设为鼠标穿透 + 置顶。
 */
export default function Overlay() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<{
    align: AlignPayload | null;
    realtime: PointPayload | null;
    preview: PreviewResult | null;
    bone: BoneFrame | null;
    quadrant: Quadrant;
    quadrantVisible: boolean;
    quadrantAlpha: number;
    quadrantLine: string;
    quadrantLineWidth: number;
  }>({
    align: null,
    realtime: null,
    preview: null,
    bone: null,
    quadrant: "TL",
    quadrantVisible: true,
    quadrantAlpha: 0.22,
    quadrantLine: "#35E0FF",
    quadrantLineWidth: 1.5,
  });
  const rafRef = useRef<number>(0);

  useEffect(() => {
    document.body.classList.add("overlay-body");
    return () => document.body.classList.remove("overlay-body");
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const schedule = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(draw);
    };

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      schedule();
    };

    const draw = () => {
      const s = stateRef.current;
      const dpr = window.devicePixelRatio || 1;
      const W = window.innerWidth;
      const H = window.innerHeight;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      // 物理像素 -> CSS 像素 比例
      const sx = s.align && s.align.w > 0 ? W / s.align.w : 1;
      const sy = s.align && s.align.h > 0 ? H / s.align.h : 1;

      // ------- 象限分区参照（可关闭）：十字实线 + 象限字母，纯线条不遮挡 -------
      if (s.quadrantVisible) {
        ctx.save();

        // 十字实线：颜色可在设置中调整
        ctx.strokeStyle = hexToRgba(s.quadrantLine, 0.72);
        ctx.lineWidth = Math.max(0.5, s.quadrantLineWidth || 1.5);
        ctx.beginPath();
        ctx.moveTo(Math.round(W / 2) + 0.5, 0);
        ctx.lineTo(Math.round(W / 2) + 0.5, H);
        ctx.moveTo(0, Math.round(H / 2) + 0.5);
        ctx.lineTo(W, Math.round(H / 2) + 0.5);
        ctx.stroke();

        // 象限字母：统一颜色，透明度可在设置中调整
        const size = Math.round(Math.min(W, H) * 0.17);
        ctx.font = `800 ${size}px "Segoe UI", "Microsoft YaHei UI", sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = `rgba(150,180,240,${s.quadrantAlpha})`;
        const labels: [string, number, number][] = [
          ["TL", W * 0.25, H * 0.25],
          ["TR", W * 0.75, H * 0.25],
          ["BL", W * 0.25, H * 0.75],
          ["BR", W * 0.75, H * 0.75],
        ];
        for (const [t, x, y] of labels) ctx.fillText(t, x, y);
        ctx.restore();
      }

      // ------- 骨骼连线 -------
      if (s.bone && s.bone.points.length > 0) {
        const lw = s.bone.line_width ?? 1.6;
        const pr = s.bone.point_radius ?? 3.2;
        const fs = s.bone.font_size ?? 13;
        const ow = s.bone.point_outline_width ?? 1.5;
        const pColor = s.bone.point_color || s.bone.line_color || "#35E0FF";
        const map = new Map<number, { x: number; y: number }>();
        for (const p of s.bone.points) map.set(p.index, { x: p.x * sx, y: p.y * sy });

        // 连线：由「显示连线」开关控制（透明度由颜色自带 alpha 决定）
        if (s.bone.show_lines && lw > 0) {
          ctx.strokeStyle = s.bone.line_color || "#35E0FF";
          ctx.lineWidth = lw;
          for (const [a, b] of s.bone.connections) {
            const pa = map.get(a);
            const pb = map.get(b);
            if (!pa || !pb) continue;
            ctx.beginPath();
            ctx.moveTo(pa.x, pa.y);
            ctx.lineTo(pb.x, pb.y);
            ctx.stroke();
          }
        }

        // 关节 + 序号
        // 优先级：样式总开关（显示关节 / 显示序号 / 显示连线）最高。
        // 点位筛选方式二选一：
        //   - label：以「显示序号」白名单为准（留空 = 全部）；
        //   - links：以「连接关系」为准（只画连线里出现的点）。
        const only = s.bone.label_only ?? [];
        const linked = new Set<number>();
        for (const [a, b] of s.bone.connections) {
          linked.add(a);
          linked.add(b);
        }
        const byLinks = s.bone.point_mode === "links";
        const inScope = (idx: number) =>
          byLinks ? linked.has(idx) : only.length === 0 || only.includes(idx);
        const showText = s.bone.show_labels && fs > 0;
        if (showText) {
          ctx.font = `600 ${fs}px "Consolas", monospace`;
          ctx.textBaseline = "middle";
        }
        for (const p of s.bone.points) {
          if (!inScope(p.index)) continue;
          const px = p.x * sx;
          const py = p.y * sy;
          if (s.bone.show_joints && pr > 0) {
            ctx.fillStyle = "rgba(5,12,24,0.85)";
            ctx.beginPath();
            ctx.arc(px, py, pr + Math.max(ow, 0), 0, Math.PI * 2);
            ctx.fill();
            if (ow > 0) {
              ctx.strokeStyle = pColor;
              ctx.lineWidth = ow;
              ctx.beginPath();
              ctx.arc(px, py, pr, 0, Math.PI * 2);
              ctx.stroke();
            }
          }
          if (showText) {
            ctx.fillStyle = s.bone.font_color || "#FFD54A";
            ctx.fillText(String(p.index), px + pr + 3, py - pr - 3);
          }
        }
      }

      // ------- 预览点（金色准星标记） -------
      if (s.preview && s.preview.visible) {
        const x = s.preview.x * sx;
        const y = s.preview.y * sy;
        const gold = "#FFD54A";
        ctx.save();
        ctx.shadowColor = gold;
        ctx.shadowBlur = 14;
        ctx.strokeStyle = gold;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(x, y, 11, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
        // 外圈淡环
        ctx.strokeStyle = "rgba(255,213,74,0.5)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(x, y, 15, 0, Math.PI * 2);
        ctx.stroke();
        // 四向刻度
        ctx.strokeStyle = gold;
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        for (const [dx, dy] of [
          [0, -1],
          [0, 1],
          [-1, 0],
          [1, 0],
        ] as [number, number][]) {
          ctx.beginPath();
          ctx.moveTo(x + dx * 16, y + dy * 16);
          ctx.lineTo(x + dx * 21, y + dy * 21);
          ctx.stroke();
        }
        ctx.lineCap = "butt";
        // 中心实心点
        ctx.fillStyle = gold;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      }

      // ------- 实时点（绿 / 橙） -------
      if (s.realtime && s.realtime.visible) {
        const x = s.realtime.x * sx;
        const y = s.realtime.y * sy;
        const color = s.realtime.borderline ? "#FFB545" : "#35E07A";
        ctx.save();
        ctx.shadowColor = color;
        ctx.shadowBlur = 12;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        ctx.strokeStyle = "rgba(255,255,255,0.9)";
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.stroke();
      }

      // ------- 左上角：图标使用说明 -------
      {
        const items: [string, string][] = [
          [hexToRgba(s.quadrantLine, 0.9), "象限参照：十字线 + TL/TR/BL/BR"],
          ["#35E07A", "实时点：选中方案的实时投影"],
          ["#FFD54A", "预览点：单次试算落点"],
          ["#35E0FF", "骨骼：连线 + 关节序号"],
        ];
        const pad = 10;
        const lh = 17;
        const boxW = 252;
        const boxH = pad * 2 + 22 + items.length * lh;
        const bx = 14;
        const by = 14;
        ctx.save();
        ctx.fillStyle = "rgba(8,14,26,0.62)";
        ctx.strokeStyle = "rgba(120,150,200,0.35)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(bx, by, boxW, boxH, 8);
        ctx.fill();
        ctx.stroke();
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "rgba(205,222,248,0.95)";
        ctx.font = '700 12px "Segoe UI", "Microsoft YaHei UI", sans-serif';
        ctx.fillText("MatrixHunter · 叠加层图例", bx + pad, by + pad + 7);
        let ly = by + pad + 30;
        for (const [c, text] of items) {
          ctx.fillStyle = c;
          ctx.beginPath();
          ctx.arc(bx + pad + 4, ly, 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = "rgba(220,232,250,0.9)";
          ctx.font = '500 12px "Segoe UI", "Microsoft YaHei UI", sans-serif';
          ctx.fillText(text, bx + pad + 15, ly);
          ly += lh;
        }
        ctx.restore();
      }
    };

    const unlisteners: Array<() => void> = [];
    (async () => {
      unlisteners.push(await events.onOverlayAlign((a) => {
        stateRef.current.align = a;
        resize();
      }));
      unlisteners.push(await events.onRealtimePoint((p) => {
        stateRef.current.realtime = p.visible ? p : null;
        schedule();
      }));
      unlisteners.push(await events.onOverlayPreview((p) => {
        stateRef.current.preview = p.visible ? p : null;
        schedule();
      }));
      unlisteners.push(await events.onBoneFrame((f) => {
        stateRef.current.bone = f.points.length ? f : null;
        schedule();
      }));
      unlisteners.push(
        await listen<QuadrantPayload>("overlay:quadrant", (e) => {
          stateRef.current.quadrant = e.payload.quadrant;
          if (e.payload.visible !== undefined) {
            stateRef.current.quadrantVisible = e.payload.visible;
          }
          if (e.payload.alpha !== undefined) {
            stateRef.current.quadrantAlpha = e.payload.alpha;
          }
          if (e.payload.line) {
            stateRef.current.quadrantLine = e.payload.line;
          }
          if (e.payload.lineWidth !== undefined) {
            stateRef.current.quadrantLineWidth = e.payload.lineWidth;
          }
          schedule();
        })
      );
      // 监听就绪后通知主窗口补发当前叠加层配置（修复首帧颜色不同步）。
      await emit("overlay:ready").catch(() => {});
    })();
    resize();
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(rafRef.current);
      for (const u of unlisteners) u();
    };
  }, []);

  return (
    <div className="overlay-root">
      <canvas ref={canvasRef} />
    </div>
  );
}
