"""集成测试（§13.2）：启动 fake_game 进程，端到端验证枚举→过滤→选用。

验证 12 方案中正确方案必在过滤后存活且可被选中。
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from core.filter_engine import FilterEngine
from core.matrix_enumerator import MatrixEnumerator, READ_ELEMENT_COUNT
from core.memory_reader import MemoryReader
from core.process_manager import ProcessManager
from core.projector import Projector
from core.scheme import DataType, FilterPoint, Quadrant, WorldCoord
from infra.config import AppConfig

FAKE_GAME = Path(__file__).parent / "fake_game.py"


def _spawn_fake_game() -> tuple[int, int]:
    """启动 fake_game 子进程，返回 (pid, matrix_address)。"""
    env = dict(os.environ)
    proc = subprocess.Popen(
        [sys.executable, str(FAKE_GAME)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    # 读取第一行输出: PID=xxxx  ADDR=0x...
    line = proc.stdout.readline().strip()
    # 防止进程提前退出阻塞
    if not line:
        err = proc.stderr.read()
        proc.terminate()
        pytest.skip(f"fake_game 未输出: {err}")
    parts = dict(p.split("=") for p in line.split())
    pid = int(parts["PID"])
    addr = int(parts["ADDR"], 16)
    return proc, pid, addr


@pytest.fixture(scope="module")
def fake_game():
    proc, pid, addr = _spawn_fake_game()
    time.sleep(0.3)  # 等待进程稳定
    yield pid, addr
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


class TestIntegration:
    """端到端集成测试（§13.2）。"""

    def test_enumerate_filter_select(self, fake_game):
        pid, addr = fake_game

        # 附加进程
        pm = ProcessManager()
        pm.attach(pid)
        assert pm.is_attached

        # 内存读取器
        reader = MemoryReader(pm.pymem_handle, DataType.FLOAT)

        # 枚举 12 方案
        schemes = MatrixEnumerator.enumerate(addr, DataType.FLOAT)
        assert len(schemes) == 12

        # 配置过滤引擎
        config = AppConfig()
        engine = FilterEngine(config)
        warn = engine.load_schemes(schemes)
        assert warn is None

        # 投影器：模拟 800x600 客户区
        projector = Projector(800, 600, config)

        # 已知测试点: W=(1.0, 0.5, 4.0) → TR 象限
        world = WorldCoord(1.0, 0.5, 4.0)
        fp = FilterPoint(world, Quadrant.TOP_RIGHT)

        # 批量读取矩阵数据（同地址共享）
        active = engine.active_schemes
        assert len(active) == 12
        raw_map = reader.read_floats_batch(
            [(addr, READ_ELEMENT_COUNT)]
        )
        raw = raw_map[addr]
        assert isinstance(raw, list)
        assert len(raw) == 16

        # 构建过滤输入
        points = []
        for s in active:
            matrix = s.build_matrix(raw[: s.element_count])
            points.append((s, matrix, fp))

        # 执行过滤
        outcome = engine.filter(points, projector)

        # 验证：至少有 1 个方案存活（正确的 M*v +w 方案）
        assert outcome.after_count >= 1
        assert outcome.after_count < outcome.before_count

        # 验证正确方案存活：4x4 row_major M*v +w
        correct_id = (
            f"addr_0x{addr:X}_4x4_row_major_M*v_+w_float"
        )
        survivors = {s.scheme_id for s in engine.active_schemes}
        assert correct_id in survivors, (
            f"正确方案 {correct_id} 未存活，存活: {survivors}"
        )

        # 验证可以选用该方案
        selected = engine.get_scheme(correct_id)
        assert selected is not None
        assert selected.shape.value == "4x4"
        assert selected.mul_direction.value == "M*v"
        assert selected.clip_w_sign.value == "+w"

        pm.detach()

    def test_wrong_quadrant_triggers_rollback(self, fake_game):
        """用错误象限过滤：全部方案被淘汰后自动回退（§10.1）。

        简单测试矩阵下，所有方案要么投影到 TR 要么不可见，
        用 TL 过滤会淘汰全部 → 触发自动回退 → 全部恢复。
        """
        pid, addr = fake_game

        pm = ProcessManager()
        pm.attach(pid)
        reader = MemoryReader(pm.pymem_handle, DataType.FLOAT)

        schemes = MatrixEnumerator.enumerate(addr, DataType.FLOAT)
        config = AppConfig()
        engine = FilterEngine(config)
        engine.load_schemes(schemes)
        projector = Projector(800, 600, config)

        # 错误象限：TL（实际应 TR）
        world = WorldCoord(1.0, 0.5, 4.0)
        fp = FilterPoint(world, Quadrant.TOP_LEFT)

        raw = reader.read_floats(addr, READ_ELEMENT_COUNT)
        points = [(s, s.build_matrix(raw[: s.element_count]), fp) for s in schemes]
        outcome = engine.filter(points, projector)

        # 全部淘汰后自动回退：after == before
        assert outcome.after_count == outcome.before_count
        assert engine.active_count == 12

        pm.detach()
