"""核心数据结构定义（§5）。

所有 core 模块共享的枚举与 dataclass。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


# ----------------------------------------------------------------------
# §5.1 枚举类型
# ----------------------------------------------------------------------
class MatrixShape(Enum):
    """矩阵形状"""

    FULL_4x4 = "4x4"   # 16 个数，完整 4x4
    ROW3x4 = "3x4"     # 12 个数，行主序，补第 4 行 [0,0,0,1]


class MemoryLayout(Enum):
    """内存布局"""

    ROW_MAJOR = "row_major"  # 行主序: M[i][j] = d[i*4 + j]
    COL_MAJOR = "col_major"  # 列主序: M[i][j] = d[j*4 + i]


class MulDirection(Enum):
    """向量乘法方向"""

    VEC_MUL_M = "v*M"  # 行向量: t = v @ M
    M_MUL_VEC = "M*v"  # 列向量: t = M @ v


class ClipWSign(Enum):
    """clip-w 符号"""

    POSITIVE = "+w"  # clip_w = t[3]
    NEGATIVE = "-w"  # clip_w = -t[3]


class DataType(Enum):
    """数据类型"""

    FLOAT = "float"    # 32 位单精度，4 字节
    DOUBLE = "double"  # 64 位双精度，8 字节

    @property
    def elem_bytes(self) -> int:
        return 4 if self is DataType.FLOAT else 8

    @property
    def struct_fmt(self) -> str:
        """struct 小端格式符（x86/x64 标准）。"""
        return "<f" if self is DataType.FLOAT else "<d"


class Quadrant(Enum):
    """屏幕象限（以客户区中心为原点）"""

    TOP_LEFT = "TL"
    TOP_RIGHT = "TR"
    BOTTOM_LEFT = "BL"
    BOTTOM_RIGHT = "BR"


class SchemeStatus(Enum):
    """方案状态"""

    ACTIVE = "active"          # 在候选池中
    ELIMINATED = "eliminated"  # 已淘汰


# ----------------------------------------------------------------------
# §5.2 矩阵方案
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class MatrixScheme:
    """一个地址的一种完整矩阵解释方案。不可变。"""

    scheme_id: str        # 唯一 ID，如 "addr_0x23F..._4x4_row_v*M_+w"
    address: int          # 矩阵头地址（十进制整数）
    data_type: DataType
    shape: MatrixShape
    layout: MemoryLayout  # 对 ROW3x4 固定为 ROW_MAJOR
    mul_direction: MulDirection
    clip_w_sign: ClipWSign

    @property
    def element_count(self) -> int:
        """需读取的浮点数个数"""
        return 16 if self.shape is MatrixShape.FULL_4x4 else 12

    @property
    def byte_size(self) -> int:
        """需读取的字节数"""
        return self.element_count * self.data_type.elem_bytes

    @property
    def description(self) -> str:
        """人类可读描述，用于结果表展示"""
        shape_str = self.shape.value  # "4x4" 或 "3x4"
        layout_str = "行主序" if self.layout is MemoryLayout.ROW_MAJOR else "列主序"
        mul_str = "向量×矩阵" if self.mul_direction is MulDirection.VEC_MUL_M else "矩阵×向量"
        sign_str = "+w" if self.clip_w_sign is ClipWSign.POSITIVE else "-w"
        return f"{shape_str} {layout_str} {mul_str} {sign_str} {self.data_type.value}"

    def build_matrix(self, raw: list[float]) -> np.ndarray:
        """将原始浮点数列表构建为 4x4 numpy 矩阵（§7.1）。

        raw 长度必须 >= element_count（允许传入统一读取的 16 元素，截断使用）。
        Raises: ValueError - raw 长度不足
        """
        if len(raw) < self.element_count:
            raise ValueError(
                f"raw 长度 {len(raw)} 不足 {self.element_count}"
            )
        if self.shape is MatrixShape.FULL_4x4:
            d = raw[:16]
            if self.layout is MemoryLayout.ROW_MAJOR:
                # M[i][j] = d[i*4+j]
                return np.array(d, dtype=np.float64).reshape(4, 4)
            # COL_MAJOR: M[i][j] = d[j*4+i]
            return np.array(d, dtype=np.float64).reshape(4, 4, order="F")
        # ROW3x4，layout 固定 ROW_MAJOR，补第 4 行 [0,0,0,1]
        rows = [raw[i * 4:(i + 1) * 4] for i in range(3)]
        rows.append([0.0, 0.0, 0.0, 1.0])
        return np.array(rows, dtype=np.float64)


# ----------------------------------------------------------------------
# §5.3 测试点
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class WorldCoord:
    """世界坐标 W（用户提供的静态目标三维坐标）。"""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class FilterPoint:
    """一次过滤的输入：世界坐标 + 用户判断的象限。

    象限模式不需要屏幕像素坐标，仅需象限归属。
    """

    world: WorldCoord
    quadrant: Quadrant


# ----------------------------------------------------------------------
# §5.4 投影结果
# ----------------------------------------------------------------------
@dataclass
class ProjectionResult:
    """一次投影的输出"""

    visible: bool            # 是否可见（clip_w > epsilon 且落点在客户区内）
    screen_x: float = 0.0    # 客户区像素 X（visible=False 时无意义）
    screen_y: float = 0.0    # 客户区像素 Y
    quadrant: Quadrant | None = None  # 落点所属象限（visible=False 时无意义）
    clip_w: float = 0.0      # clip-w 原值（诊断用）
    reason: str = "ok"       # "ok"|"clip_w_le_zero"|"clip_w_too_large"|"nan_or_inf"|"out_of_client"|"borderline"
    borderline: bool = False  # 落点距中心线过近，象限归属模糊（不应淘汰）


# ----------------------------------------------------------------------
# §5.5 过滤结果
# ----------------------------------------------------------------------
@dataclass
class FilterOutcome:
    """一次过滤的统计"""

    before_count: int              # 过滤前候选数
    after_count: int               # 过滤后候选数
    eliminated_ids: list[str]      # 被淘汰的 scheme_id 列表
    skipped_ids: list[str] = None  # 因边界模糊跳过的 scheme_id 列表（未淘汰也未确认）

    def __post_init__(self):
        if self.skipped_ids is None:
            self.skipped_ids = []
