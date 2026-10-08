/**
 * 前端散落的可调参数集中在这里，避免魔法数字埋进各组件。
 */

/* ---------------- 悬浮提示 ---------------- */
/** 顶部判定带：元素顶边高于这个值，提示向下弹出（否则向上） */
export const TIP_TOP_BAND = 96;
/** 提示与窗口左右边的最小距离 */
export const TIP_EDGE_MARGIN = 10;
/** 悬停多久后弹出 */
export const TIP_DELAY_MS = 200;
/** 小三角相对提示左右两端的最小留白 */
export const TIP_ARROW_INSET = 12;

/* ---------------- 外观偏好本地存储 ---------------- */
export const PREFS_KEY = "mh.prefs";
