import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { TIP_ARROW_INSET, TIP_DELAY_MS, TIP_EDGE_MARGIN, TIP_TOP_BAND } from "../lib/constants";

interface RawTip {
  text: string;
  below: boolean;
  x: number;
  y: number;
}

/**
 * 自绘悬浮提示层。
 *
 * 不用原生 title 的原因：原生提示是 Windows 系统样式，与界面风格不符，
 * 而且在 overflow:hidden 的卡片里会被裁切。
 *
 * 定位策略：
 *  - 靠顶部的元素向下弹出（否则会飞出窗口上沿）
 *  - 水平方向做边界收拢，超出左右边界的会被夹回窗口内
 *  - 小三角独立成元素，收拢后仍指向原元素的中心
 */
export default function TooltipLayer() {
  const [tip, setTip] = useState<RawTip | null>(null);
  const [placed, setPlaced] = useState<{ left: number; arrowX: number } | null>(null);
  const timer = useRef<number | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const clear = () => {
      if (timer.current) {
        window.clearTimeout(timer.current);
        timer.current = null;
      }
    };

    const onOver = (e: Event) => {
      const target = e.target as HTMLElement | null;
      const el = target?.closest?.("[data-tip]") as HTMLElement | null;
      clear();
      const text = el?.getAttribute("data-tip") || "";
      if (!el || !text) {
        setTip(null);
        return;
      }
      timer.current = window.setTimeout(() => {
        const r = el.getBoundingClientRect();
        // 只有窗口顶部这一条带（标题栏 / 工具条 / 标签栏）的元素向下弹，
        // 从元素【底边】出发，避免遮住元素自身；其余元素维持向上弹出。
        const below = r.top < TIP_TOP_BAND;
        setPlaced(null); // 先隐藏，等测量完再显示，避免旧位置闪一下
        setTip({
          text,
          below,
          x: r.left + r.width / 2,
          y: below ? r.bottom : r.top,
        });
      }, TIP_DELAY_MS);
    };

    const onOut = () => {
      clear();
      setTip(null);
    };

    document.addEventListener("mouseover", onOver, true);
    document.addEventListener("mouseout", onOut, true);
    document.addEventListener("scroll", onOut, true);
    window.addEventListener("blur", onOut);
    return () => {
      clear();
      document.removeEventListener("mouseover", onOver, true);
      document.removeEventListener("mouseout", onOut, true);
      document.removeEventListener("scroll", onOut, true);
      window.removeEventListener("blur", onOut);
    };
  }, []);

  // 渲染后在绘制前测量实际宽度并做边界收拢
  useLayoutEffect(() => {
    const el = ref.current;
    if (!tip || !el) return;
    const w = el.offsetWidth;
    const minLeft = TIP_EDGE_MARGIN + w / 2;
    const maxLeft = window.innerWidth - TIP_EDGE_MARGIN - w / 2;
    const left = Math.min(Math.max(tip.x, minLeft), maxLeft);
    // 收拢后让三角仍然指向原元素中心
    const arrowX = Math.min(
      Math.max(tip.x - (left - w / 2), TIP_ARROW_INSET),
      w - TIP_ARROW_INSET
    );
    setPlaced({ left, arrowX });
  }, [tip]);

  if (!tip) return null;

  return (
    <div
      ref={ref}
      className={`tooltip${tip.below ? " below" : ""}`}
      style={{
        left: placed ? placed.left : tip.x,
        top: tip.y,
        visibility: placed ? "visible" : "hidden",
      }}
    >
      <span className="tooltip-arrow" style={{ left: placed ? placed.arrowX : "50%" }} />
      {tip.text}
    </div>
  );
}
