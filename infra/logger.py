"""日志封装（§12.1）。

仅记录地址、方案 ID、过滤统计、异常栈；
不记录矩阵数值等可能敏感的数据。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 日志写到项目根目录（源码运行时即 infra 的父目录），
# 便于开发调试时直接查看；打包 exe 时回退到可执行文件同级目录。
if getattr(sys, "frozen", False):
    LOG_DIR = Path(sys.executable).resolve().parent
else:
    LOG_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = LOG_DIR / "matrixhunter.log"

_initialized = False


def setup_logger(level: str = "INFO") -> logging.Logger:
    """初始化全局 logger（幂等）。文件 + 控制台双输出。"""
    global _initialized
    logger = logging.getLogger("matrixhunter")
    if _initialized:
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        # 无权限写日志文件时仅控制台输出
        pass

    _initialized = True
    return logger


def get_logger(name: str = "matrixhunter") -> logging.Logger:
    """获取子 logger；若未初始化则使用默认级别初始化。"""
    if not _initialized:
        setup_logger()
    return logging.getLogger(f"matrixhunter.{name}" if name != "matrixhunter" else name)
