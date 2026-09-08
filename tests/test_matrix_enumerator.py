"""matrix_enumerator 单元测试（§13.1）。

- 单地址生成恰好 12 方案
- ROW3x4 的 layout 恒为 ROW_MAJOR
- scheme_id 唯一
- build_matrix 行/列主序互为转置；3x4 补第 4 行；长度不符抛异常
"""
import numpy as np
import pytest

from core.matrix_enumerator import MatrixEnumerator
from core.scheme import (
    DataType,
    MatrixShape,
    MemoryLayout,
)
from infra.errors import InvalidAddressError

ADDR = 0x23F28408D80


class TestEnumerate:
    def test_exactly_12_schemes_per_address(self):
        schemes = MatrixEnumerator.enumerate(ADDR, DataType.FLOAT)
        assert len(schemes) == 12

    def test_row3x4_layout_always_row_major(self):
        schemes = MatrixEnumerator.enumerate(ADDR, DataType.FLOAT)
        for s in schemes:
            if s.shape is MatrixShape.ROW3x4:
                assert s.layout is MemoryLayout.ROW_MAJOR

    def test_scheme_ids_unique(self):
        schemes = MatrixEnumerator.enumerate(ADDR, DataType.FLOAT)
        ids = [s.scheme_id for s in schemes]
        assert len(ids) == len(set(ids))

    def test_scheme_composition(self):
        """8 个 4x4 + 4 个 3x4（§7.1 枚举表）。"""
        schemes = MatrixEnumerator.enumerate(ADDR, DataType.FLOAT)
        n4x4 = sum(1 for s in schemes if s.shape is MatrixShape.FULL_4x4)
        n3x4 = sum(1 for s in schemes if s.shape is MatrixShape.ROW3x4)
        assert n4x4 == 8
        assert n3x4 == 4

    def test_element_count(self):
        schemes = MatrixEnumerator.enumerate(ADDR, DataType.FLOAT)
        for s in schemes:
            expected = 16 if s.shape is MatrixShape.FULL_4x4 else 12
            assert s.element_count == expected

    def test_byte_size_float_double(self):
        f = MatrixEnumerator.enumerate(ADDR, DataType.FLOAT)[0]
        d = MatrixEnumerator.enumerate(ADDR, DataType.DOUBLE)[0]
        assert f.byte_size == 64
        assert d.byte_size == 128

    def test_batch_enumerate(self):
        addrs = [ADDR, ADDR + 0x40, ADDR + 0x80]
        schemes = MatrixEnumerator.enumerate_batch(addrs, DataType.DOUBLE)
        assert len(schemes) == 36

    def test_invalid_address_zero(self):
        with pytest.raises(InvalidAddressError):
            MatrixEnumerator.enumerate(0, DataType.FLOAT)

    def test_invalid_address_negative(self):
        with pytest.raises(InvalidAddressError):
            MatrixEnumerator.enumerate(-1, DataType.FLOAT)

    def test_batch_skips_invalid(self):
        schemes = MatrixEnumerator.enumerate_batch([0, ADDR], DataType.FLOAT)
        assert len(schemes) == 12


class TestBuildMatrix:
    def _scheme(self, shape, layout):
        return next(
            s
            for s in MatrixEnumerator.enumerate(ADDR, DataType.FLOAT)
            if s.shape is shape and s.layout is layout
        )

    def test_row_col_major_transpose(self):
        """行主序与列主序对同一组数据互为转置（§13.1）。"""
        raw = [float(i) for i in range(16)]
        row_s = self._scheme(MatrixShape.FULL_4x4, MemoryLayout.ROW_MAJOR)
        col_s = self._scheme(MatrixShape.FULL_4x4, MemoryLayout.COL_MAJOR)
        m_row = row_s.build_matrix(raw)
        m_col = col_s.build_matrix(raw)
        np.testing.assert_array_equal(m_row, m_col.T)

    def test_row_major_indexing(self):
        """M[i][j] = d[i*4+j]"""
        raw = [float(i) for i in range(16)]
        s = self._scheme(MatrixShape.FULL_4x4, MemoryLayout.ROW_MAJOR)
        m = s.build_matrix(raw)
        assert m[1][2] == 6.0
        assert m[3][3] == 15.0

    def test_col_major_indexing(self):
        """M[i][j] = d[j*4+i]"""
        raw = [float(i) for i in range(16)]
        s = self._scheme(MatrixShape.FULL_4x4, MemoryLayout.COL_MAJOR)
        m = s.build_matrix(raw)
        assert m[1][2] == 9.0
        assert m[2][1] == 6.0

    def test_row3x4_appends_last_row(self):
        """3x4 补第 4 行 [0,0,0,1]（§7.1）。"""
        raw = [float(i) for i in range(12)]
        s = self._scheme(MatrixShape.ROW3x4, MemoryLayout.ROW_MAJOR)
        m = s.build_matrix(raw)
        assert m.shape == (4, 4)
        np.testing.assert_array_equal(m[3], [0.0, 0.0, 0.0, 1.0])
        assert m[0][3] == 3.0
        assert m[2][0] == 8.0

    def test_build_matrix_accepts_16_raw_for_3x4(self):
        """统一读取 16 元素时，3x4 方案用前 12 个（§7.1 读取长度策略）。"""
        raw = [float(i) for i in range(16)]
        s = self._scheme(MatrixShape.ROW3x4, MemoryLayout.ROW_MAJOR)
        m = s.build_matrix(raw)
        assert m[2][3] == 11.0

    def test_build_matrix_length_mismatch_raises(self):
        s = self._scheme(MatrixShape.FULL_4x4, MemoryLayout.ROW_MAJOR)
        with pytest.raises(ValueError):
            s.build_matrix([1.0] * 15)

    def test_dtype_is_float64(self):
        raw = [float(i) for i in range(16)]
        s = self._scheme(MatrixShape.FULL_4x4, MemoryLayout.ROW_MAJOR)
        assert s.build_matrix(raw).dtype == np.float64
