"""叠加层窗口（§6.7 / §9.3）。

透明置顶无边框窗口，覆盖目标窗口客户区。
- 全程显示白色半透明十字线（四等分客户区，辅助象限判断）
- 实时绘制开启时叠加绿色验证圆圈
- 骨骼编号覆盖层：数字标注 + 连线
- 鼠标穿透（WS_EX_TRANSPARENT | WS_EX_LAYERED）
- 跟随目标窗口移动/缩放
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QFontMetrics,
)
from PySide6.QtWidgets import QWidget

from infra.logger import get_logger

log = get_logger("overlay")

# Win32 扩展样式（§16.3）
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

user32 = ctypes.windll.user32


class OverlayWindow(QWidget):
    """透明置顶无边框窗口，覆盖目标客户区。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Qt 窗口属性：无边框、置顶、工具窗口、透明背景
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # 绘制状态
        self._crosshair_visible = False
        self._realtime_x: float | None = None
        self._realtime_y: float | None = None
        self._circle_radius = 8
        self._circle_color = QColor(0, 255, 0)
        # 预览点（黄色，区别于绿色实时点）
        self._preview_x: float | None = None
        self._preview_y: float | None = None
        self._preview_color = QColor(255, 200, 0)

        # ---- 骨骼编号覆盖层 ----
        self._bone_points: list[tuple[int, float, float]] = []  # [(index, x, y), ...]
        self._bone_hidden: set[int] = set()                     # 不绘制的骨骼编号
        self._bone_connections: list[tuple[int, int]] = []      # [(from, to), ...]
        self._bone_font_size: int = 14
        self._bone_font_color: QColor = QColor(255, 255, 255)   # 白色
        self._bone_bg_color: QColor = QColor(0, 0, 0, 140)      # 半透明黑底
        self._line_color: QColor = QColor(0, 200, 255, 180)     # 青蓝色连线

        # 初始隐藏，等待对齐后再显示
        self.resize(1, 1)
        self.hide()

    # ------------------------------------------------------------------
    # 配置（原有）
    # ------------------------------------------------------------------
    def set_circle_style(self, radius: int, color: tuple[int, int, int]) -> None:
        """设置验证圆圈半径与颜色（§5.6）。"""
        self._circle_radius = radius
        self._circle_color = QColor(*color)
        self.update()

    def set_crosshair_visible(self, visible: bool) -> None:
        self._crosshair_visible = visible
        self.update()

    def set_realtime_point(
        self, x: float | None, y: float | None
    ) -> None:
        """设置实时绘制点；x/y 为 None 表示不可见。"""
        self._realtime_x = x
        self._realtime_y = y
        self.update()

    def set_preview_point(self, x: float | None, y: float | None) -> None:
        """设置预览点（黄色，用于"预览"按钮）；x/y 为 None 表示清除。"""
        self._preview_x = x
        self._preview_y = y
        self.update()

    # ------------------------------------------------------------------
    # 骨骼编号覆盖层
    # ------------------------------------------------------------------
    def set_bone_data(
        self,
        points: list[tuple[int, float, float]],
        hidden: set[int] | None = None,
    ) -> None:
        """设置骨骼屏幕坐标点。

        points: [(index, screen_x, screen_y), ...]
        hidden: 不绘制的骨骼编号集合
        """
        self._bone_points = list(points)
        if hidden is not None:
            self._bone_hidden = set(hidden)
        self.update()

    def set_bone_hidden(self, hidden: set[int]) -> None:
        self._bone_hidden = set(hidden)
        self.update()

    def set_bone_connections(self, conns: list[tuple[int, int]]) -> None:
        self._bone_connections = list(conns)
        self.update()

    def set_bone_font_size(self, size: int) -> None:
        self._bone_font_size = max(6, min(72, size))
        self.update()

    # ------------------------------------------------------------------
    # 对齐
    # ------------------------------------------------------------------
    def align_to_client(
        self, screen_x: int, screen_y: int, w: int, h: int
    ) -> None:
        """移动并缩放到目标客户区屏幕坐标（由窗口跟踪线程调用）。"""
        if w <= 0 or h <= 0:
            self.hide()
            return
        self.setGeometry(screen_x, screen_y, w, h)
        self.show()
        self._apply_click_through()

    def _apply_click_through(self) -> None:
        """设置 WS_EX_TRANSPARENT | WS_EX_LAYERED 实现鼠标穿透。"""
        try:
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT,
            )
        except Exception:  # noqa: BLE001
            log.exception("设置鼠标穿透失败")

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()

        # 十字线（白色半透明，四等分客户区）
        if self._crosshair_visible:
            pen = QPen(QColor(255, 255, 255, 160), 1)
            painter.setPen(pen)
            cx = w / 2.0
            cy = h / 2.0
            painter.drawLine(0, int(cy), w, int(cy))
            painter.drawLine(int(cx), 0, int(cx), h)

        # ---- 骨骼连线（先画线，再画数字，避免遮挡） ----
        if self._bone_connections and self._bone_points:
            pt_map = {idx: (x, y) for idx, x, y in self._bone_points}
            pen = QPen(self._line_color, 2)
            painter.setPen(pen)
            for a, b in self._bone_connections:
                if a in pt_map and b in pt_map:
                    x1, y1 = pt_map[a]
                    x2, y2 = pt_map[b]
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ---- 骨骼编号 ----
        if self._bone_points:
            font = QFont("Consolas", self._bone_font_size)
            painter.setFont(font)
            fm = QFontMetrics(font)

            for idx, sx, sy in self._bone_points:
                if idx in self._bone_hidden:
                    continue
                # 限制在窗口范围内
                if not (0.0 <= sx <= w and 0.0 <= sy <= h):
                    continue

                text = str(idx)
                # 纯文字，无背景
                painter.setPen(QPen(self._bone_font_color))
                painter.drawText(int(sx), int(sy), text)

        # 实时圆圈（绿色）
        if (
            self._realtime_x is not None
            and self._realtime_y is not None
        ):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._circle_color))
            painter.drawEllipse(
                QRectF(
                    self._realtime_x - self._circle_radius,
                    self._realtime_y - self._circle_radius,
                    self._circle_radius * 2,
                    self._circle_radius * 2,
                )
            )

        # 预览圆圈（黄色，带深色边框，区别于实时点）
        if (
            self._preview_x is not None
            and self._preview_y is not None
        ):
            r = self._circle_radius + 2
            painter.setBrush(QBrush(self._preview_color))
            painter.setPen(QPen(QColor(120, 80, 0), 2))
            painter.drawEllipse(
                QRectF(
                    self._preview_x - r,
                    self._preview_y - r,
                    r * 2,
                    r * 2,
                )
            )

        painter.end()
