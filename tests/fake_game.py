"""假游戏进程（§13.2 集成测试辅助）。

写入一个已知 ViewProj 矩阵到固定地址并保持运行，
供 MatrixHunter 枚举 → 过滤 → 选出正确方案 → 实时绘制验证。

用法:
    python tests/fake_game.py
输出:
    PID=xxxx  ADDR=0x...  （将地址粘贴到 MatrixHunter）
然后按 Ctrl+C 退出。
"""
from __future__ import annotations

import ctypes
import struct
import time


def main() -> None:
    # 分配一块可读内存，写入一个已知的 4x4 ViewProj 矩阵（行主序）
    # 该矩阵将世界点 (1.0, 0.5, 4.0) 投影到客户区右上区域（TR 象限）
    # M*v: t = [x, y, z, z]  → ndc=(x/z, y/z)=(0.25, 0.125)
    matrix = [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
    ]
    # 再补 4 个 float 凑足 16 个（4x4 尾部），便于测试 3x4 读取
    matrix_full = matrix + [0.0, 0.0, 0.0, 0.0]

    raw = struct.pack(f"<{len(matrix_full)}f", *matrix_full)
    size = len(raw)

    # VirtualAlloc 分配可读内存
    buf = ctypes.create_string_buffer(raw, size)
    addr = ctypes.addressof(buf)

    pid = ctypes.windll.kernel32.GetCurrentProcessId()
    print(f"PID={pid}  ADDR=0x{addr:X}")
    print(f"矩阵: 4x4 行主序, M*v, clip_w=+w (z)")
    print(f"测试点 W=(1.0, 0.5, 4.0) → TR 象限")
    print("保持运行中... Ctrl+C 退出")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n退出")


if __name__ == "__main__":
    main()
