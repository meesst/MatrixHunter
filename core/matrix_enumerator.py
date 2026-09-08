"""矩阵方案枚举（§6.3 / §7.1）。

枚举维度：
  shape ∈ {FULL_4x4, ROW3x4}
  layout: FULL_4x4 → {ROW_MAJOR, COL_MAJOR}; ROW3x4 → ROW_MAJOR 固定
  mul_direction ∈ {VEC_MUL_M, M_MUL_VEC}
  clip_w_sign ∈ {POSITIVE, NEGATIVE}
合计 12 种/地址。
"""
from __future__ import annotations

from core.scheme import (
    ClipWSign,
    DataType,
    MatrixScheme,
    MatrixShape,
    MemoryLayout,
    MulDirection,
)
from infra.errors import InvalidAddressError

# 每地址统一读取的元素数（覆盖 4x4=16 与 3x4=12，§7.1 读取长度策略）
READ_ELEMENT_COUNT = 16


def _make_scheme_id(
    address: int,
    data_type: DataType,
    shape: MatrixShape,
    layout: MemoryLayout,
    mul_direction: MulDirection,
    clip_w_sign: ClipWSign,
) -> str:
    return (
        f"addr_0x{address:X}_{shape.value}_{layout.value}_"
        f"{mul_direction.value}_{clip_w_sign.value}_{data_type.value}"
    )


class MatrixEnumerator:
    """根据地址 + 数据类型生成所有候选矩阵方案。"""

    @staticmethod
    def enumerate(address: int, data_type: DataType) -> list[MatrixScheme]:
        """对单个地址生成全部 12 种候选方案。

        Raises: InvalidAddressError - address 非法（<=0）
        """
        if not isinstance(address, int) or address <= 0:
            raise InvalidAddressError(f"address is 0 or invalid: {address!r}")

        schemes: list[MatrixScheme] = []
        # (shape, layout) 组合：4x4 两种布局 + 3x4 固定行主序（§7.1）
        shape_layouts = [
            (MatrixShape.FULL_4x4, MemoryLayout.ROW_MAJOR),
            (MatrixShape.FULL_4x4, MemoryLayout.COL_MAJOR),
            (MatrixShape.ROW3x4, MemoryLayout.ROW_MAJOR),
        ]
        for shape, layout in shape_layouts:
            for mul in (MulDirection.VEC_MUL_M, MulDirection.M_MUL_VEC):
                for sign in (ClipWSign.POSITIVE, ClipWSign.NEGATIVE):
                    schemes.append(
                        MatrixScheme(
                            scheme_id=_make_scheme_id(
                                address, data_type, shape, layout, mul, sign
                            ),
                            address=address,
                            data_type=data_type,
                            shape=shape,
                            layout=layout,
                            mul_direction=mul,
                            clip_w_sign=sign,
                        )
                    )
        return schemes

    @staticmethod
    def enumerate_batch(
        addresses: list[int], data_type: DataType
    ) -> list[MatrixScheme]:
        """对一批地址批量枚举。非法地址跳过。"""
        result: list[MatrixScheme] = []
        for addr in addresses:
            try:
                result.extend(MatrixEnumerator.enumerate(addr, data_type))
            except InvalidAddressError:
                continue
        return result
