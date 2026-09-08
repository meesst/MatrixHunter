"""进程与窗口管理（§6.1）。

进程检测、附加、目标窗口定位、客户区屏幕坐标。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

import psutil
import pymem

from infra.errors import AttachError, ProcessListError
from infra.logger import get_logger

log = get_logger("process")

# Win32 常量
WS_VISIBLE = 0x10000000
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def _is_process_64bit(pid: int) -> bool:
    """判断进程是否为 64 位。

    64 位系统上 is_wow64()=True 即 32 位(WoW64)进程。
    psutil 标准库无 is_wow64()，改用 ctypes 调 IsWow64Process。
    """
    try:
        proc_h = kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
        if not proc_h:
            return True  # 默认按 64 位
        try:
            is_wow64 = wintypes.BOOL(False)
            if not kernel32.IsWow64Process(proc_h, ctypes.byref(is_wow64)):
                return True
            # is_wow64=True 表示 32 位进程
            return not bool(is_wow64.value)
        finally:
            kernel32.CloseHandle(proc_h)
    except OSError:
        return True


# 枚举窗口回调类型
EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)


class _WindowInfo:
    __slots__ = ("hwnd", "area")

    def __init__(self):
        self.hwnd: int = 0
        self.area: int = 0


class ProcessManager:
    """进程检测、附加、目标窗口定位。"""

    def __init__(self):
        self._pm: Optional[pymem.Pymem] = None
        self._pid: int = 0

    @property
    def attached_pid(self) -> int:
        return self._pid

    @property
    def is_attached(self) -> bool:
        return self._pm is not None

    def list_processes(self) -> list[tuple[int, str, bool]]:
        """枚举进程。

        Returns: [(pid, process_name, is_64bit), ...]
        is_64bit: True=64位进程, False=32位(WoW64)进程。
        Raises: ProcessListError
        """
        result: list[tuple[int, str, bool]] = []
        try:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    name = p.info["name"] or ""
                    pid = p.info["pid"]
                    result.append((pid, name, _is_process_64bit(pid)))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as exc:  # noqa: BLE001
            raise ProcessListError(f"枚举进程失败: {exc}") from exc
        return result

    def attach(self, pid: int) -> None:
        """附加到目标进程。

        Raises: AttachError - 进程不存在或 OpenProcess 失败
        """
        if not psutil.pid_exists(pid):
            raise AttachError(f"进程不存在: pid={pid}")
        try:
            self._pm = pymem.Pymem()
            self._pm.open_process_from_id(pid)
        except Exception as exc:  # noqa: BLE001
            self._pm = None
            raise AttachError(f"OpenProcess failed (pid={pid}): {exc}") from exc
        self._pid = pid
        log.info("已附加进程 pid=%d", pid)

    @property
    def pymem_handle(self) -> Optional[pymem.Pymem]:
        """返回已附加的 Pymem 实例，供 MemoryReader 使用。"""
        return self._pm

    def find_main_window(self, pid: int) -> int | None:
        """查找目标进程的主窗口句柄 hwnd。

        实现: EnumWindows + GetWindowThreadProcessId 匹配 pid，
              取具有 WS_VISIBLE 且无父窗口的最大客户区窗口。
        Returns: hwnd 或 None(未找到)
        """
        best = _WindowInfo()

        def _callback(hwnd: int, lparam: int) -> bool:
            # 必须可见
            if not user32.IsWindowVisible(hwnd):
                return True
            # 必须无父窗口（顶层窗口）
            if user32.GetParent(hwnd):
                return True
            # 进程匹配
            proc_id = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value != pid:
                return True
            # 取客户区面积作为排序依据
            rect = wintypes.RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(rect)):
                area = (rect.right - rect.left) * (rect.bottom - rect.top)
                if area > best.area:
                    best.hwnd = hwnd
                    best.area = area
            return True

        user32.EnumWindows(EnumWindowsProc(_callback), 0)
        return best.hwnd if best.hwnd else None

    def get_client_rect_on_screen(
        self, hwnd: int
    ) -> tuple[int, int, int, int] | None:
        """获取客户区在屏幕坐标系中的位置与大小。

        Returns: (screen_x, screen_y, width, height) 或 None(窗口无效)
        实现: GetClientRect + ClientToScreen(左上角)
        注意: 需在 DPI 感知后调用，返回物理像素。
        """
        if not hwnd or not user32.IsWindow(hwnd):
            return None

        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        point = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
            return None

        return (point.x, point.y, width, height)

    def is_window_visible(self, hwnd: int) -> bool:
        """窗口是否可见（含最小化判定，供叠加层使用）。"""
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        if not user32.IsWindowVisible(hwnd):
            return False
        # 最小化判定
        if user32.IsIconic(hwnd):
            return False
        return True

    def detach(self) -> None:
        """断开附加，关闭句柄。"""
        if self._pm is not None:
            try:
                # pymem 无显式 close，依赖 __del__；显式清空引用
                self._pm.close_process()
            except Exception:  # noqa: BLE001
                pass
            self._pm = None
            log.info("已断开进程 pid=%d", self._pid)
        self._pid = 0
