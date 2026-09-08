"""线程安全工具（§4.2）。

- SignalBridge：子线程 → GUI 线程的信号桥接 QObject
- StoppableThread：带 stop 事件的线程基类，循环 try/except 隔离
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from infra.logger import get_logger

log = get_logger("threading")


class SignalBridge(QObject):
    """子线程与 GUI 线程之间的信号桥。

    子线程持有本对象引用并 emit 信号；
    槽函数在 GUI 线程执行（Qt 队列连接）。
    """

    # 叠加层几何对齐: screen_x, screen_y, width, height
    sig_overlay_align = Signal(int, int, int, int)
    # 叠加层显隐
    sig_overlay_visible = Signal(bool)
    # 实时绘制点更新: x, y（None 表示不可见）
    sig_realtime_point = Signal(object, object)
    # 状态/错误消息投递
    sig_status = Signal(str)
    sig_error = Signal(str)
    # 全局快捷键: "F8" | "F9" | "ESC"
    sig_hotkey = Signal(str)


class StoppableThread(threading.Thread):
    """可停止的工作线程基类。

    子类实现 tick() 完成单次工作；run() 按 interval 循环调用。
    单次 tick 异常仅记日志不终止线程；连续失败超限自动停止。
    """

    def __init__(
        self,
        interval: float,
        name: str,
        max_consecutive_failures: int = 30,
        on_failure_limit: Optional[Callable[[], None]] = None,
        daemon: bool = True,
    ):
        super().__init__(name=name, daemon=daemon)
        self._stop_event = threading.Event()
        self._interval = interval
        self._max_failures = max_consecutive_failures
        self._on_failure_limit = on_failure_limit

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def tick(self) -> None:  # pragma: no cover - 由子类实现
        raise NotImplementedError

    def run(self) -> None:
        failures = 0
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                self.tick()
                failures = 0
            except Exception:  # noqa: BLE001 - 隔离单次异常
                failures += 1
                log.exception("%s tick 失败（连续 %d 次）", self.name, failures)
                if failures >= self._max_failures:
                    log.error("%s 连续失败超限，自动停止", self.name)
                    if self._on_failure_limit is not None:
                        try:
                            self._on_failure_limit()
                        except Exception:  # noqa: BLE001
                            log.exception("failure_limit 回调异常")
                    break
            elapsed = time.monotonic() - started
            # 用 wait 代替 sleep，stop 可立即唤醒
            self._stop_event.wait(max(0.0, self._interval - elapsed))
