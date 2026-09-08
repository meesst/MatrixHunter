"""世界 → 屏幕投影（§6.4 / §7.2）。

算法步骤严格按 §7.2：
  1. v = [x, y, z, 1.0]
  2. t = v @ M 或 M @ v
  3. NaN/Inf 检查 → 不可见
  4. clip_w = ±t[3]
  5. clip_w <= epsilon → 不可见
  6. NDC 透视除法 → 客户区像素（Y 轴翻转）
  7. 客户区内判定
  8. 象限判定（边界归右/下）
"""
from __future__ import annotations

import numpy as np

from core.scheme import (
    ClipWSign,
    MatrixScheme,
    MulDirection,
    ProjectionResult,
    Quadrant,
    WorldCoord,
)
from infra.config import AppConfig
from infra.logger import get_logger

log = get_logger("projector")


class Projector:
    """世界坐标 → 客户区屏幕坐标 → 象限。"""

    def __init__(self, client_width: int, client_height: int, config: AppConfig):
        self._w = max(0, client_width)
        self._h = max(0, client_height)
        self._config = config

    @property
    def client_size(self) -> tuple[int, int]:
        return self._w, self._h

    def set_client_size(self, width: int, height: int) -> None:
        """客户区尺寸变更时调用（窗口跟踪触发）。"""
        self._w = max(0, width)
        self._h = max(0, height)

    def project(
        self, scheme: MatrixScheme, matrix: np.ndarray, world: WorldCoord
    ) -> ProjectionResult:
        """执行投影。

        matrix: 已由 scheme.build_matrix 构建的 4x4 矩阵。
        """
        # 1. 齐次向量
        v = np.array([world.x, world.y, world.z, 1.0], dtype=np.float64)

        # 2. 变换
        if scheme.mul_direction is MulDirection.VEC_MUL_M:
            t = v @ matrix
        else:
            t = matrix @ v
        t = np.asarray(t, dtype=np.float64).reshape(4)

        # 3. NaN/Inf 检查（含 W 本身非法的情况）
        if not np.isfinite(t).all():
            log.debug(
                "project NaN/Inf: world=%s t=%s client=%dx%d",
                (world.x, world.y, world.z), t.tolist(), self._w, self._h,
            )
            return ProjectionResult(visible=False, reason="nan_or_inf")

        # 4. clip-w 符号
        wc_raw = float(t[3])
        clip_w = wc_raw if scheme.clip_w_sign is ClipWSign.POSITIVE else -wc_raw

        # 5. 可见性（含 <=0 与极小正数）
        if clip_w <= self._config.clip_w_epsilon:
            log.debug(
                "project clip_w<=0: clip_w=%g t=%s client=%dx%d",
                clip_w, t.tolist(), self._w, self._h,
            )
            return ProjectionResult(
                visible=False, clip_w=clip_w, reason="clip_w_le_zero"
            )

        # 5b. clip_w 过大 → 矩阵数据错误/方案不匹配（如 t[3] 高达 42 亿）
        if clip_w > self._config.clip_w_max:
            log.debug(
                "project clip_w>max: clip_w=%g (max=%g) t=%s client=%dx%d",
                clip_w, self._config.clip_w_max, t.tolist(), self._w, self._h,
            )
            return ProjectionResult(
                visible=False, clip_w=clip_w, reason="clip_w_too_large"
            )

        # 6. 透视除法 (NDC) → 客户区像素
        ndc_x = float(t[0]) / clip_w
        ndc_y = float(t[1]) / clip_w
        screen_x = (ndc_x * 0.5 + 0.5) * self._w
        screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * self._h  # Y 轴翻转

        # 7. 客户区内判定
        if not (0.0 <= screen_x <= self._w and 0.0 <= screen_y <= self._h):
            log.debug(
                "project out_of_client: t=%s clip_w=%g ndc=(%.4f,%.4f) screen=(%.1f,%.1f) client=%dx%d",
                t.tolist(), clip_w, ndc_x, ndc_y, screen_x, screen_y,
                self._w, self._h,
            )
            return ProjectionResult(
                visible=False,
                screen_x=screen_x,
                screen_y=screen_y,
                clip_w=clip_w,
                reason="out_of_client",
            )

        # 8. 象限（含边界容差带判定）
        quad, borderline = self.quadrant_of(screen_x, screen_y)
        if borderline:
            log.debug(
                "project visible(borderline): t=%s clip_w=%g screen=(%.1f,%.1f) client=%dx%d",
                t.tolist(), clip_w, screen_x, screen_y,
                self._w, self._h,
            )
            return ProjectionResult(
                visible=True,
                screen_x=screen_x,
                screen_y=screen_y,
                quadrant=quad,
                clip_w=clip_w,
                reason="borderline",
                borderline=True,
            )

        # 9. 可见 + 象限明确
        log.debug(
            "project visible: t=%s clip_w=%g screen=(%.1f,%.1f) quad=%s client=%dx%d",
            t.tolist(), clip_w, screen_x, screen_y,
            quad.value, self._w, self._h,
        )
        return ProjectionResult(
            visible=True,
            screen_x=screen_x,
            screen_y=screen_y,
            quadrant=quad,
            clip_w=clip_w,
            reason="ok",
        )

    def quadrant_of(self, screen_x: float, screen_y: float) -> tuple[Quadrant, bool]:
        """判定像素坐标所属象限（以客户区中心为界）。

        边界容差带（§7.2 增强）：参考目标不会精确落在中心十字线上，
        当 |screen_x - cx| 或 |screen_y - cy| <= 容差时，象限归属模糊，
        返回 borderline=True，调用方应跳过对该方案的淘汰判定。

        边界规则（非模糊区）: screen_x == center_x 归右(TR/BR);
                              screen_y == center_y 归下(BL/BR)。
        Returns: (Quadrant, borderline)
        """
        cx = self._w / 2.0
        cy = self._h / 2.0
        tol = self._config.quadrant_borderline_px
        dx = screen_x - cx
        dy = screen_y - cy
        borderline = (abs(dx) <= tol) or (abs(dy) <= tol)
        right = dx >= 0
        bottom = dy >= 0
        if right and bottom:
            quad = Quadrant.BOTTOM_RIGHT
        elif right:
            quad = Quadrant.TOP_RIGHT
        elif bottom:
            quad = Quadrant.BOTTOM_LEFT
        else:
            quad = Quadrant.TOP_LEFT
        return quad, borderline
