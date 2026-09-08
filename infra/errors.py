"""MatrixHunter 统一异常层级（§6.1 / §16.2）。"""


class MatrixHunterError(Exception):
    """所有 MatrixHunter 异常的基类。"""


class ProcessListError(MatrixHunterError):
    """枚举进程失败。"""


class AttachError(MatrixHunterError):
    """附加进程失败（进程不存在或 OpenProcess 失败）。"""


class MemoryReadError(MatrixHunterError):
    """ReadProcessMemory 失败（跨页/未分配/权限不足/进程退出）。"""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        # code 可用于区分典型场景，如 "PROCESS_EXITED"
        self.code = code


class InvalidAddressError(MatrixHunterError):
    """地址非法（非十六进制 / 为 0 / 超出范围）。"""


class EnumerationError(MatrixHunterError):
    """矩阵方案枚举失败。"""
