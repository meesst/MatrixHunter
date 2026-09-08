"""projector 单元测试（§13.1）。

- 已知正确矩阵投影误差 < 1px
- clip_w<=0 / NaN / Inf / 界外 → 不可见
- 象限边界归右/下
- Y 轴翻转正确
"""
import numpy as np
import pytest

from core.projector import Projector
from core.scheme import (
    ClipWSign,
    DataType,
    MatrixScheme,
    MatrixShape,
    MemoryLayout,
    MulDirection,
    Quadrant,
    WorldCoord,
)
from infra.config import AppConfig

W_C, H_C = 1920, 1080


def make_scheme(
    mul: MulDirection = MulDirection.M_MUL_VEC,
    sign: ClipWSign = ClipWSign.POSITIVE,
) -> MatrixScheme:
    return MatrixScheme(
        scheme_id="test",
        address=0x1000,
        data_type=DataType.FLOAT,
        shape=MatrixShape.FULL_4x4,
        layout=MemoryLayout.ROW_MAJOR,
        mul_direction=mul,
        clip_w_sign=sign,
    )


@pytest.fixture
def projector() -> Projector:
    return Projector(W_C, H_C, AppConfig())


class TestKnownMatrix:
    """构造一个简单的透视投影矩阵，验证像素落点。

    设计：世界点 (1, 0.5, 4)，期望 NDC=(0.25, 0.125)。
    M*v 下取矩阵：
      t = [x*1, y*1, z, z]  →  ndc = (x/z, y/z) = (0.25, 0.125)
    screen_x = (0.25*0.5+0.5)*1920 = 1200
    screen_y = (1-(0.125*0.5+0.5))*1080 = 472.5
    """

    M = np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
    )
    WORLD = WorldCoord(1.0, 0.5, 4.0)

    def test_m_mul_vec_pixel(self, projector):
        r = projector.project(make_scheme(MulDirection.M_MUL_VEC), self.M, self.WORLD)
        assert r.visible
        assert r.reason == "ok"
        assert abs(r.screen_x - 1200.0) < 1.0
        assert abs(r.screen_y - 472.5) < 1.0
        assert r.quadrant is Quadrant.TOP_RIGHT
        assert r.clip_w == pytest.approx(4.0)

    def test_v_mul_m_equivalent(self, projector):
        """v*M 与 M*M.T 等价：同一矩阵转置后 v*M 结果应一致。"""
        r = projector.project(
            make_scheme(MulDirection.VEC_MUL_M), self.M.T, self.WORLD
        )
        assert r.visible
        assert abs(r.screen_x - 1200.0) < 1.0
        assert abs(r.screen_y - 472.5) < 1.0

    def test_negative_clip_w_sign(self, projector):
        """clip_w 符号翻转：t[3] 为负时取 -w 可见。"""
        m = self.M.copy()
        m[3] = [0.0, 0.0, -1.0, 0.0]  # t[3] = -z = -4
        r = projector.project(
            make_scheme(MulDirection.M_MUL_VEC, ClipWSign.NEGATIVE), m, self.WORLD
        )
        assert r.visible
        assert r.clip_w == pytest.approx(4.0)


class TestVisibility:
    def test_clip_w_zero(self, projector):
        m = np.zeros((4, 4))
        r = projector.project(make_scheme(), m, WorldCoord(0, 0, 0))
        assert not r.visible
        assert r.reason == "clip_w_le_zero"

    def test_clip_w_negative(self, projector):
        m = np.diag([1.0, 1.0, 1.0, -1.0])
        r = projector.project(make_scheme(), m, WorldCoord(0, 0, 0))
        assert not r.visible
        assert r.reason == "clip_w_le_zero"
        assert r.clip_w == pytest.approx(-1.0)

    def test_clip_w_tiny_positive(self, projector):
        """clip_w <= epsilon 视为不可见（§10.2）。"""
        m = np.diag([1.0, 1.0, 1.0, 1e-8])
        r = projector.project(make_scheme(), m, WorldCoord(0, 0, 0))
        assert not r.visible
        assert r.reason == "clip_w_le_zero"

    def test_nan_in_matrix(self, projector):
        m = np.full((4, 4), np.nan)
        r = projector.project(make_scheme(), m, WorldCoord(1, 2, 3))
        assert not r.visible
        assert r.reason == "nan_or_inf"

    def test_inf_in_matrix(self, projector):
        m = np.full((4, 4), np.inf)
        m[3][3] = 1.0  # 避免 0*inf 产生 NaN，纯粹测试 Inf 路径
        r = projector.project(make_scheme(), m, WorldCoord(1, 2, 3))
        assert not r.visible
        assert r.reason == "nan_or_inf"

    def test_nan_world_coord(self, projector):
        r = projector.project(make_scheme(), np.eye(4), WorldCoord(np.nan, 0, 0))
        assert not r.visible
        assert r.reason == "nan_or_inf"

    def test_out_of_client(self, projector):
        """NDC 超出 [-1,1] → 落点在客户区外。"""
        m = np.array(
            [
                [10.0, 0.0, 0.0, 0.0],  # ndc_x = 10 → screen 远大于宽度
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        r = projector.project(make_scheme(), m, WorldCoord(1, 0, 1))
        assert not r.visible
        assert r.reason == "out_of_client"


class TestQuadrant:
    @pytest.mark.parametrize(
        "x,y,expected,borderline",
        [
            (0, 0, Quadrant.TOP_LEFT, False),
            (W_C - 1, 0, Quadrant.TOP_RIGHT, False),
            (0, H_C - 1, Quadrant.BOTTOM_LEFT, False),
            (W_C - 1, H_C - 1, Quadrant.BOTTOM_RIGHT, False),
            # 边界规则：center_x 归右，center_y 归下（§7.2）
            # 贴近中心线（容差带内）→ borderline=True
            (W_C / 2, 0, Quadrant.TOP_RIGHT, True),
            (0, H_C / 2, Quadrant.BOTTOM_LEFT, True),
            (W_C / 2, H_C / 2, Quadrant.BOTTOM_RIGHT, True),
            (W_C / 2 - 1, H_C / 2 - 1, Quadrant.TOP_LEFT, True),
        ],
    )
    def test_quadrant_boundaries(self, projector, x, y, expected, borderline):
        quad, bl = projector.quadrant_of(x, y)
        assert quad is expected
        assert bl is borderline

    def test_borderline_project_reason(self, projector):
        """落点贴近中心线时 project 返回 reason='borderline'。"""
        # 构造投影到客户区中心附近的矩阵
        cx = 1920 / 2.0
        m = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [cx, 540.0, 0.0, 1.0],  # 平移到中心
            ]
        )
        r = projector.project(make_scheme(), m, WorldCoord(0, 0, 1))
        assert r.visible
        assert r.reason == "borderline"
        assert r.borderline is True

    def test_far_from_axis_not_borderline(self, projector):
        """远离中心线时 borderline=False。"""
        # 左上角附近，距中心线远超容差
        quad, bl = projector.quadrant_of(10, 10)
        assert bl is False
        assert quad is Quadrant.TOP_LEFT
        # 右下角附近
        quad, bl = projector.quadrant_of(1900, 1070)
        assert bl is False
        assert quad is Quadrant.BOTTOM_RIGHT


class TestYFlip:
    def test_ndc_up_maps_to_screen_top(self, projector):
        """NDC y=+1（上方）应映射到屏幕 y=0（顶部）（§7.2 Y 轴翻转）。"""
        m = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],  # ndc_y = y/z
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],  # t[3] = z
            ]
        )
        # 世界点 y=z → ndc_y=1 → screen_y=0（顶部）
        r = projector.project(make_scheme(), m, WorldCoord(0.0, 2.0, 2.0))
        assert r.visible
        assert abs(r.screen_y - 0.0) < 1.0

        # y=-z → ndc_y=-1 → screen_y=H（底部）
        r2 = projector.project(make_scheme(), m, WorldCoord(0.0, -2.0, 2.0))
        assert r2.visible
        assert abs(r2.screen_y - H_C) < 1.0


class TestClientSize:
    def test_set_client_size_updates_projection(self, projector):
        projector.set_client_size(800, 600)
        assert projector.client_size == (800, 600)
        m = np.eye(4)
        r = projector.project(make_scheme(), m, WorldCoord(0, 0, 1))
        # ndc=(0,0) → 中心点
        assert abs(r.screen_x - 400.0) < 1.0
        assert abs(r.screen_y - 300.0) < 1.0

    def test_zero_size_degenerate(self, projector):
        """客户区为 0×0 时投影退化（§10.1 在更高层暂停过滤/绘制，
        projector 仅返回几何结果，原点 0<=0<=0 视为 in-bounds）。"""
        projector.set_client_size(0, 0)
        r = projector.project(make_scheme(), np.eye(4), WorldCoord(0, 0, 1))
        # 几何上 0<=0<=0 成立，故 visible=True；上层应拦截零尺寸场景
        assert r.visible
        assert r.screen_x == 0.0
        assert r.screen_y == 0.0
