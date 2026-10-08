/**
 * 解析隐藏序号：
 *   - 单个数字：`3`、`7`
 *   - 区间：`1-50`、`55~70`（含两端）
 * 用逗号 / 空格 / 分号 / 换行分隔，可混用，如 `1-50, 55-70 90`。
 */
export function parseHidden(text: string): number[] {
  const out = new Set<number>();
  // 防御：误输入超大区间（如 1-999999999）时不至于把内存撑爆
  const MAX_SPAN = 100_000;
  for (const part of text.split(/[,\s;]+/)) {
    if (!part) continue;
    const range = part.match(/^(\d+)\s*[-~]\s*(\d+)$/);
    if (range) {
      let a = parseInt(range[1], 10);
      let b = parseInt(range[2], 10);
      if (a > b) [a, b] = [b, a];
      if (b - a > MAX_SPAN) b = a + MAX_SPAN;
      for (let i = a; i <= b; i++) out.add(i);
    } else {
      const n = parseInt(part, 10);
      if (Number.isFinite(n) && n >= 0) out.add(n);
    }
  }
  return [...out].sort((x, y) => x - y);
}

export function parseConns(text: string): [number, number][] {
  const out: [number, number][] = [];
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/(\d+)\s*[-:>]\s*(\d+)/);
    if (m) out.push([parseInt(m[1], 10), parseInt(m[2], 10)]);
  }
  return out;
}
