"""MatrixHunter 入口（§11.3 DPI 感知 / §10.3 异常钩子 / §9.3 全局快捷键）。

启动顺序：
1. Win32 DPI 感知（PER_MONITOR_AWARE_V2）— 必须在 QApplication 之前
2. 日志初始化
3. 全局异常钩子
4. QApplication + 主窗口
5. 全局快捷键注册（F8/F9/ESC）
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from infra.config import AppConfig
from infra.logger import setup_logger, get_logger
from ui.main_window import MainWindow

# Win32 常量
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_F8 = 0x77
VK_F9 = 0x78
VK_ESCAPE = 0x1B

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def setup_dpi_awareness() -> None:
    """§11.3: 启用 Per-Monitor V2 DPI 感知，必须在 QApplication 之前调用。"""
    try:
        # SetProcessDpiAwarenessContext 返回 BOOL
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        ok = user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        )
        if ok:
            return
    except (AttributeError, OSError):
        pass
    # 回退到较旧的 SetProcessDpiAwareness
    try:
        user32.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def setup_excepthook(logger) -> None:
    """§10.3: 全局异常钩子，写日志、弹错但不退出。"""

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _hook


class HotkeyManager:
    """全局快捷键管理（§9.3）。

    使用 RegisterHotKey + QTimer 轮询 PeekMessage 检测 WM_HOTKEY。
    F8: 显示/隐藏叠加层
    F9: 切换实时绘制
    ESC: 取消实时绘制
    """

    def __init__(self, main_window: MainWindow):
        self._mw = main_window
        self._bridge = main_window._bridge
        self._registered: list[int] = []
        self._timer = QTimer()
        self._timer.setInterval(30)  # ~33Hz 检测
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        hotkeys = [
            (1, MOD_NOREPEAT, VK_F8, "F8"),
            (2, MOD_NOREPEAT, VK_F9, "F9"),
            (3, MOD_NOREPEAT, VK_ESCAPE, "ESC"),
        ]
        for hid, mod, vk, name in hotkeys:
            ok = user32.RegisterHotKey(0, hid, mod, vk)
            if ok:
                self._registered.append(hid)
            else:
                log = get_logger("hotkey")
                log.warning("注册快捷键 %s 失败", name)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        for hid in self._registered:
            user32.UnregisterHotKey(0, hid)
        self._registered.clear()

    def _poll(self) -> None:
        msg = wintypes.MSG()
        # PeekMessage 取出 WM_HOTKEY
        while user32.PeekMessageW(
            ctypes.byref(msg), 0, WM_HOTKEY, WM_HOTKEY, 1  # PM_REMOVE
        ):
            hid = msg.wParam
            if hid == 1:
                self._bridge.sig_hotkey.emit("F8")
            elif hid == 2:
                self._bridge.sig_hotkey.emit("F9")
            elif hid == 3:
                self._bridge.sig_hotkey.emit("ESC")


def main() -> int:
    # 1. DPI 感知（必须在 QApplication 之前）
    setup_dpi_awareness()

    # 2. 日志 + 配置（--debug 开启详细日志，便于排查读取/投影数据）
    config = AppConfig.load()
    debug = "--debug" in sys.argv
    logger = setup_logger("DEBUG" if debug else config.log_level)
    logger.info("MatrixHunter 启动 (debug=%s)", debug)

    # 3. 异常钩子
    setup_excepthook(logger)

    # 4. Qt 应用
    app = QApplication(sys.argv)
    app.setApplicationName("MatrixHunter")
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow(config)
    window.show()

    # 5. 全局快捷键
    hotkey_mgr = HotkeyManager(window)
    hotkey_mgr.start()

    exit_code = app.exec()
    hotkey_mgr.stop()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
