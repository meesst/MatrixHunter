"""内存读取封装（§6.2）。

封装 pymem 的 ReadProcessMemory，批量读取浮点数。
生命周期与 ProcessManager.attach 绑定。
"""
from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from core.scheme import DataType
from infra.errors import InvalidAddressError, MemoryReadError
from infra.logger import get_logger

if TYPE_CHECKING:
    import pymem

log = get_logger("memory")


class MemoryReader:
    """批量读取浮点数。"""

    def __init__(self, pm: "pymem.Pymem", data_type: DataType):
        """pm 为已附加的 Pymem 实例；data_type 决定单元素字节数。"""
        self._pm = pm
        self._data_type = data_type
        self._elem_bytes = data_type.elem_bytes
        self._fmt = data_type.struct_fmt

    @property
    def data_type(self) -> DataType:
        return self._data_type

    def read_floats(self, address: int, count: int) -> list[float]:
        """从 address 读取 count 个浮点数。

        Raises:
            InvalidAddressError - address 非法或为 0
            MemoryReadError - ReadProcessMemory 失败
        返回长度恒等于 count。
        """
        if not isinstance(address, int) or address <= 0:
            raise InvalidAddressError(f"address is 0 or invalid: {address!r}")
        if count <= 0:
            return []

        size = count * self._elem_bytes
        try:
            raw = self._pm.read_bytes(address, size)
        except Exception as exc:  # pymem 抛多种异常，统一封装
            msg = str(exc).lower()
            if "process" in msg and ("exit" in msg or "close" in msg):
                raise MemoryReadError(
                    f"process exited: {exc}", code="PROCESS_EXITED"
                ) from exc
            raise MemoryReadError(
                f"ReadProcessMemory failed at 0x{address:X} ({count}x{self._data_type.value}): {exc}"
            ) from exc

        if raw is None or len(raw) != size:
            raise MemoryReadError(
                f"short read at 0x{address:X}: got {0 if raw is None else len(raw)} bytes, expected {size}"
            )

        # struct 小端解包（§6.2）
        vals = list(struct.unpack(f"<{count}{self._fmt[-1]}", raw))
        preview = [round(v, 6) for v in vals[: min(count, 16)]]
        log.debug(
            "read 0x%X x%d (%s) = %s%s",
            address, count, self._data_type.value, preview,
            " ..." if count > 16 else "",
        )
        return vals

    def read_floats_batch(
        self, addresses: list[tuple[int, int]]
    ) -> dict[int, list[float] | Exception]:
        """批量读取多个 (address, count)。

        单个地址失败不影响其他地址（异常作为值返回，不抛出）。
        用途: 过滤前批量刷新所有候选方案的数据。
        """
        result: dict[int, list[float] | Exception] = {}
        for addr, count in addresses:
            try:
                result[addr] = self.read_floats(addr, count)
            except Exception as exc:  # noqa: BLE001
                result[addr] = exc
                log.debug("batch read failed at 0x%X: %s", addr, exc)
        return result
