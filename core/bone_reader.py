"""骨骼数据读取——简化版。

用户从外部处理好骨骼坐标，粘贴文本到文本框，
格式: [编号] (x, y, z)

如果提供了视图矩阵，将 (x,y,z) 投影到屏幕；
否则直接当屏幕坐标绘制。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import numpy as np
import re

from core.scheme import WorldCoord, MulDirection
from infra.logger import get_logger

if TYPE_CHECKING:
    from core.projector import Projector

log = get_logger("bone")

# 匹配格式: [0] (1.23, 4.56, 7.89)  或  [0] (1.23, 4.56)
_PATTERN = re.compile(
    r"\[\s*(\d+)\s*\]\s*"
    r"\(\s*([\d.eE+-]+)\s*,\s*([\d.eE+-]+)\s*(?:,\s*([\d.eE+-]+)\s*)?\)"
)


def parse_bone_text(text: str) -> list[dict]:
    """解析用户粘贴的骨骼坐标文本。

    支持格式:
        [0] (x, y, z)
        [0] (x, y)
    返回 [{index, x, y, z}, ...]
    """
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _PATTERN.match(line)
        if not m:
            continue
        idx = int(m.group(1))
        x = float(m.group(2))
        y = float(m.group(3))
        z = float(m.group(4)) if m.group(4) else 0.0
        results.append({"index": idx, "x": x, "y": y, "z": z})
    return results


def project_points(
    points: list[dict],
    view_matrix: Optional[np.ndarray],
    mul_direction: MulDirection,
    proj: "Projector",
) -> list[dict]:
    """将坐标列表投影到屏幕。

    每个 points 元素: {index, x, y, z}
    如果 view_matrix 为 None，直接把 (x,y) 当屏幕坐标。
    返回: [{index, screen_x, screen_y, visible, reason}, ...]
    """
    results = []
    cw, ch = proj.client_size

    for p in points:
        idx = p["index"]
        if view_matrix is not None:
            v = np.array([p["x"], p["y"], p["z"], 1.0], dtype=np.float64)
            if mul_direction is MulDirection.M_MUL_VEC:
                t = view_matrix @ v
            else:
                t = v @ view_matrix
            t = np.asarray(t, dtype=np.float64).reshape(4)

            if not np.isfinite(t).all():
                results.append({"index": idx, "screen_x": 0.0, "screen_y": 0.0, "visible": False, "reason": "nan"})
                continue

            clip_w = float(t[3])
            if clip_w <= 1e-6:
                results.append({"index": idx, "screen_x": 0.0, "screen_y": 0.0, "visible": False, "reason": "clip_w"})

            ndc_x = float(t[0]) / clip_w
            ndc_y = float(t[1]) / clip_w
            sx = (ndc_x * 0.5 + 0.5) * cw
            sy = (1.0 - (ndc_y * 0.5 + 0.5)) * ch

            if not (0.0 <= sx <= cw and 0.0 <= sy <= ch):
                results.append({"index": idx, "screen_x": sx, "screen_y": sy, "visible": False, "reason": "out"})
                continue

            results.append({"index": idx, "screen_x": sx, "screen_y": sy, "visible": True, "reason": "ok"})
        else:
            # 无视图矩阵，直接当屏幕坐标
            results.append({"index": idx, "screen_x": float(p["x"]), "screen_y": float(p["y"]), "visible": True, "reason": "ok"})

    return results
