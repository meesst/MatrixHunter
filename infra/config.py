"""配置持久化（§5.6 / §12.1）。

只持久化窗口位置、最近进程名、容差等非敏感数据；
不保存地址或坐标。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

# 配置文件写到项目根目录（源码运行）；打包时写到 exe 同级目录。
if getattr(sys, "frozen", False):
    _ROOT = Path(sys.executable).resolve().parent
else:
    _ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = _ROOT / "config.json"


@dataclass
class AppConfig:
    """应用配置（§5.6）。"""

    # 过滤
    clip_w_epsilon: float = 1e-6           # clip-w 可见性阈值（低于此值判不可见）
    clip_w_max: float = 1e7                # clip-w 上限（超过此值视为矩阵数据错误，判不可见）
    quadrant_borderline_px: int = 6        # 象限判定容差带（像素），落点距中心线<=此值视为边界模糊，跳过淘汰
    # 实时绘制
    realtime_fps: int = 30                 # 实时绘制读取频率
    circle_radius_px: int = 8              # 验证圆圈半径（像素）
    circle_color: tuple[int, int, int] = (0, 255, 0)  # 绿色
    # 窗口跟踪
    window_track_interval_ms: int = 100    # 窗口跟踪轮询间隔
    # 诊断
    log_level: str = "INFO"

    # ---- 骨骼编号覆盖层 ----
    bone_mat_address: str = ""                # 视图矩阵地址
    bone_font_size: int = 14

    # ---- 非规格项：持久化的用户偏好（§12.1 允许存最近进程名等） ----
    last_process_name: str = ""
    window_geometry: bytes | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    def save(self) -> None:
        """持久化到用户目录。序列化失败静默忽略。"""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = asdict(self)
            # bytes 不可 JSON 序列化，丢弃
            data.pop("window_geometry", None)
            CONFIG_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    @classmethod
    def load(cls) -> "AppConfig":
        """从用户目录加载；文件不存在或损坏时返回默认配置。"""
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            if "circle_color" in known:
                known["circle_color"] = tuple(known["circle_color"])
            known.pop("window_geometry", None)
            return cls(**known)
        except (OSError, json.JSONDecodeError, TypeError):
            return cls()
