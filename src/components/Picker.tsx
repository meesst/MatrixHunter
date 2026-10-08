import { useEffect, useRef } from "react";
import { events } from "../lib/api";
import type { PickHover } from "../types";

/**
 * 拖拽选取层：全屏透明窗口，跟随鼠标高亮当前指向的顶层窗口，
 * 松开左键由 Rust 侧结束选取。这里只负责绘制。
 */
export default function Picker() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const hoverRef = useRef<PickHover | null>(null);

  useEffect(() => {
    document.body.classList.add("overlay-body");
    return () => document.body.classList.remove("overlay-body");
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    const dpr = window.devicePixelRatio || 1;

    const resize = () => {
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
    };

    const roundRect = (
      x: number,
      y: number,
      w: number,
      h: number,
      r: number
    ) => {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r);
      ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r);
      ctx.closePath();
    };

    const draw = () => {
      const W = canvas.width;
      const H = canvas.height;
      const h = hoverRef.current;

      ctx.clearRect(0, 0, W, H);

      if (h) {
        // 目标窗口之外压暗，目标区域保持原样露出
        ctx.fillStyle = "rgba(5,9,18,0.42)";
        ctx.fillRect(0, 0, W, H);
        ctx.clearRect(h.x, h.y, h.w, h.h);

        // 高亮描边 + 外发光
        ctx.save();
        ctx.shadowColor = "rgba(91,140,255,0.95)";
        ctx.shadowBlur = 20;
        ctx.strokeStyle = "#5b8cff";
        ctx.lineWidth = 3 * dpr;
        ctx.strokeRect(
          h.x + 1.5 * dpr,
          h.y + 1.5 * dpr,
          h.w - 3 * dpr,
          h.h - 3 * dpr
        );
        ctx.restore();

        // 内侧细白线，增强"取景框"观感
        ctx.strokeStyle = "rgba(255,255,255,0.85)";
        ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(
          h.x + 5 * dpr,
          h.y + 5 * dpr,
          h.w - 10 * dpr,
          h.h - 10 * dpr
        );

        // 四角标记
        const c = 16 * dpr;
        const t = 3 * dpr;
        ctx.strokeStyle = "#5b8cff";
        ctx.lineWidth = t;
        const corners: [number, number, number, number][] = [
          [h.x, h.y, 1, 1],
          [h.x + h.w, h.y, -1, 1],
          [h.x, h.y + h.h, 1, -1],
          [h.x + h.w, h.y + h.h, -1, -1],
        ];
        for (const [cx, cy, sx, sy] of corners) {
          ctx.beginPath();
          ctx.moveTo(cx + sx * c, cy);
          ctx.lineTo(cx, cy);
          ctx.lineTo(cx, cy + sy * c);
          ctx.stroke();
        }

        // 名称标签
        const label = `${h.name || "未知进程"}   ·   pid ${h.pid}`;
        ctx.font = `600 ${14 * dpr}px "Segoe UI", "Microsoft YaHei UI", sans-serif`;
        const tw = ctx.measureText(label).width;
        const bw = tw + 22 * dpr;
        const bh = 28 * dpr;
        const bx = Math.min(Math.max(h.x + 2 * dpr, 6 * dpr), W - bw - 6 * dpr);
        const by = h.y - bh - 8 * dpr > 6 * dpr ? h.y - bh - 8 * dpr : h.y + 8 * dpr;

        ctx.fillStyle = "rgba(91,140,255,0.96)";
        roundRect(bx, by, bw, bh, 7 * dpr);
        ctx.fill();
        ctx.fillStyle = "#fff";
        ctx.textBaseline = "middle";
        ctx.fillText(label, bx + 11 * dpr, by + bh / 2);

        // 尺寸提示
        const sizeLabel = `${h.w} × ${h.h}`;
        ctx.font = `500 ${12 * dpr}px "Consolas", monospace`;
        const sw2 = ctx.measureText(sizeLabel).width;
        ctx.fillStyle = "rgba(5,9,18,0.7)";
        roundRect(
          h.x + h.w - sw2 - 20 * dpr,
          h.y + h.h + 8 * dpr,
          sw2 + 16 * dpr,
          22 * dpr,
          6 * dpr
        );
        ctx.fill();
        ctx.fillStyle = "#9fb6e8";
        ctx.fillText(
          sizeLabel,
          h.x + h.w - sw2 - 12 * dpr,
          h.y + h.h + 19 * dpr
        );
      } else {
        // 未指向任何窗口时整体压暗
        ctx.fillStyle = "rgba(5,9,18,0.42)";
        ctx.fillRect(0, 0, W, H);
      }

      // 顶部操作提示
      const tip = "拖动鼠标到目标窗口  ·  松开左键选中";
      ctx.font = `600 ${14 * dpr}px "Segoe UI", "Microsoft YaHei UI", sans-serif`;
      const tipW = ctx.measureText(tip).width;
      const tipX = (W - tipW - 40 * dpr) / 2;
      const tipY = 22 * dpr;
      ctx.fillStyle = "rgba(10,14,26,0.86)";
      roundRect(tipX, tipY, tipW + 40 * dpr, 38 * dpr, 10 * dpr);
      ctx.fill();
      ctx.strokeStyle = "rgba(91,140,255,0.55)";
      ctx.lineWidth = 1 * dpr;
      ctx.stroke();
      ctx.fillStyle = "#e8eefc";
      ctx.textBaseline = "middle";
      ctx.fillText(tip, tipX + 20 * dpr, tipY + 19 * dpr);

      raf = requestAnimationFrame(draw);
    };

    resize();
    window.addEventListener("resize", resize);

    const un = events.onPickHover((p) => {
      hoverRef.current = p;
    });

    raf = requestAnimationFrame(draw);

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(raf);
      un.then((f) => f());
    };
  }, []);

  return (
    <div className="overlay-root">
      <canvas ref={canvasRef} />
    </div>
  );
}
