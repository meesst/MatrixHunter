"""filter_engine 单元测试（§13.1）。

- 单点过滤淘汰率符合预期
- active=0 时自动回退
- 读取失败方案被淘汰
- 多方案共存
- 撤销栈
"""
import numpy as np
import pytest

from core.filter_engine import FilterEngine
from core.projector import Projector
from core.scheme import (
    ClipWSign,
    DataType,
    FilterPoint,
    MatrixScheme,
    MatrixShape,
    MemoryLayout,
    MulDirection,
    Quadrant,
    WorldCoord,
)
from infra.config import AppConfig

W_C, H_C = 800, 600


def make_scheme(
    sid: str,
    mul: MulDirection = MulDirection.M_MUL_VEC,
    sign: ClipWSign = ClipWSign.POSITIVE,
) -> MatrixScheme:
    return MatrixScheme(
        scheme_id=sid,
        address=0x1000,
        data_type=DataType.FLOAT,
        shape=MatrixShape.FULL_4x4,
        layout=MemoryLayout.ROW_MAJOR,
        mul_direction=mul,
        clip_w_sign=sign,
    )


# 投影到 (x=0.25*W, y=0.125*H) 的矩阵 → TR 象限
# M*v, t = [x, y, z, z] → ndc=(x/z, y/z)
MATRIX_TR = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ]
)
WORLD = WorldCoord(1.0, 0.5, 4.0)  # → TR


@pytest.fixture
def engine() -> FilterEngine:
    return FilterEngine(AppConfig())


@pytest.fixture
def projector() -> Projector:
    return Projector(W_C, H_C, AppConfig())


class TestPoolManagement:
    def test_load_and_active_count(self, engine):
        schemes = [make_scheme(f"s{i}") for i in range(5)]
        engine.load_schemes(schemes)
        assert engine.active_count == 5
        assert engine.total_count == 5

    def test_reset(self, engine):
        engine.load_schemes([make_scheme("s1")])
        engine.reset()
        assert engine.active_count == 0
        assert engine.total_count == 0

    def test_active_schemes_sorted(self, engine):
        s1 = make_scheme("s1")
        s1.__dict__  # frozen dataclass，直接构造不同地址
        s_high = MatrixScheme(
            scheme_id="s_high",
            address=0x2000,
            data_type=DataType.FLOAT,
            shape=MatrixShape.FULL_4x4,
            layout=MemoryLayout.ROW_MAJOR,
            mul_direction=MulDirection.M_MUL_VEC,
            clip_w_sign=ClipWSign.POSITIVE,
        )
        s_low = MatrixScheme(
            scheme_id="s_low",
            address=0x1000,
            data_type=DataType.FLOAT,
            shape=MatrixShape.FULL_4x4,
            layout=MemoryLayout.ROW_MAJOR,
            mul_direction=MulDirection.M_MUL_VEC,
            clip_w_sign=ClipWSign.POSITIVE,
        )
        engine.load_schemes([s_high, s_low])
        active = engine.active_schemes
        assert active[0].address == 0x1000
        assert active[1].address == 0x2000


class TestFilter:
    def test_match_kept_mismatch_eliminated(self, engine, projector):
        """TR 象限匹配保留，TL 象限不匹配淘汰。"""
        engine.load_schemes([make_scheme("match"), make_scheme("mismatch")])
        fp_match = FilterPoint(WORLD, Quadrant.TOP_RIGHT)
        fp_mismatch = FilterPoint(WORLD, Quadrant.TOP_LEFT)

        outcome = engine.filter(
            [
                (make_scheme("match"), MATRIX_TR, fp_match),
                (make_scheme("mismatch"), MATRIX_TR, fp_mismatch),
            ],
            projector,
        )
        assert outcome.before_count == 2
        assert outcome.after_count == 1
        assert "mismatch" in outcome.eliminated_ids
        assert "match" not in outcome.eliminated_ids

    def test_read_failed_eliminated(self, engine, projector):
        """matrix=None 表示读取失败 → 淘汰。"""
        engine.load_schemes([make_scheme("ok"), make_scheme("bad")])
        fp = FilterPoint(WORLD, Quadrant.TOP_RIGHT)
        outcome = engine.filter(
            [
                (make_scheme("ok"), MATRIX_TR, fp),
                (make_scheme("bad"), None, fp),
            ],
            projector,
        )
        assert outcome.after_count == 1
        assert "bad" in outcome.eliminated_ids

    def test_invisible_eliminated(self, engine, projector):
        """clip_w<=0 → 不可见 → 淘汰（需保留至少 1 个，否则触发自动回退）。"""
        m_zero = np.zeros((4, 4))  # t[3]=0 → clip_w=0 → 不可见
        engine.load_schemes([make_scheme("inv"), make_scheme("ok")])
        fp = FilterPoint(WORLD, Quadrant.TOP_RIGHT)
        outcome = engine.filter(
            [
                (make_scheme("inv"), m_zero, fp),
                (make_scheme("ok"), MATRIX_TR, fp),
            ],
            projector,
        )
        assert outcome.after_count == 1
        assert "inv" in outcome.eliminated_ids
        assert "ok" not in outcome.eliminated_ids

    def test_multiple_schemes_coexist(self, engine, projector):
        """多个匹配方案共存。"""
        schemes = [make_scheme(f"s{i}") for i in range(10)]
        engine.load_schemes(schemes)
        fp = FilterPoint(WORLD, Quadrant.TOP_RIGHT)
        points = [(s, MATRIX_TR, fp) for s in schemes]
        outcome = engine.filter(points, projector)
        assert outcome.after_count == 10
        assert len(outcome.eliminated_ids) == 0

    def test_borderline_skipped_not_eliminated(self, engine, projector):
        """落点贴近中心线（容差带）的方案被跳过，不淘汰。"""
        # 投影到客户区中心 (400, 300) → borderline
        MATRIX_CENTER = np.array(
            [
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 4.0, 0.0],
            ]
        )
        engine.load_schemes([make_scheme("bl"), make_scheme("tr")])
        fp = FilterPoint(WORLD, Quadrant.TOP_RIGHT)
        outcome = engine.filter(
            [
                (make_scheme("bl"), MATRIX_CENTER, fp),
                (make_scheme("tr"), MATRIX_TR, fp),
            ],
            projector,
        )
        # 两个都未淘汰：bl 边界跳过，tr 匹配保留
        assert outcome.after_count == 2
        assert outcome.eliminated_ids == []
        assert "bl" in outcome.skipped_ids
        assert "tr" not in outcome.skipped_ids


class TestAutoRollback:
    def test_all_eliminated_auto_rollback(self, engine, projector):
        """§10.1: 一轮过滤后 active=0 → 自动回退。"""
        engine.load_schemes([make_scheme("a"), make_scheme("b")])
        # 全部不匹配（TL，但实际是 TR）
        fp = FilterPoint(WORLD, Quadrant.TOP_LEFT)
        outcome = engine.filter(
            [
                (make_scheme("a"), MATRIX_TR, fp),
                (make_scheme("b"), MATRIX_TR, fp),
            ],
            projector,
        )
        # 自动回退后应恢复到 2
        assert outcome.after_count == 2
        assert engine.active_count == 2


class TestUndo:
    def test_undo_restores(self, engine, projector):
        engine.load_schemes([make_scheme("keep"), make_scheme("drop")])
        fp_match = FilterPoint(WORLD, Quadrant.TOP_RIGHT)
        fp_drop = FilterPoint(WORLD, Quadrant.TOP_LEFT)
        engine.filter(
            [
                (make_scheme("keep"), MATRIX_TR, fp_match),
                (make_scheme("drop"), MATRIX_TR, fp_drop),
            ],
            projector,
        )
        assert engine.active_count == 1
        assert engine.can_undo

        restored = engine.undo_last()
        assert restored is not None
        assert "drop" in restored
        assert engine.active_count == 2

    def test_undo_empty_returns_none(self, engine):
        engine.load_schemes([make_scheme("s1")])
        assert engine.undo_last() is None
        assert not engine.can_undo

    def test_undo_max_one_round(self, engine, projector):
        """撤销栈最多保留 1 轮（§9.2）。"""
        engine.load_schemes(
            [make_scheme("a"), make_scheme("b"), make_scheme("c")]
        )
        # 第一轮淘汰 a
        engine.filter(
            [
                (make_scheme("a"), None, FilterPoint(WORLD, Quadrant.TOP_RIGHT)),
                (make_scheme("b"), MATRIX_TR, FilterPoint(WORLD, Quadrant.TOP_RIGHT)),
                (make_scheme("c"), MATRIX_TR, FilterPoint(WORLD, Quadrant.TOP_RIGHT)),
            ],
            projector,
        )
        assert engine.active_count == 2
        # 第二轮淘汰 b（撤销栈被覆盖，只剩第二轮）
        engine.filter(
            [
                (make_scheme("b"), None, FilterPoint(WORLD, Quadrant.TOP_RIGHT)),
                (make_scheme("c"), MATRIX_TR, FilterPoint(WORLD, Quadrant.TOP_RIGHT)),
            ],
            projector,
        )
        assert engine.active_count == 1
        restored = engine.undo_last()
        # 只恢复 b，不恢复 a
        assert restored == {"b"}
        assert engine.active_count == 2
