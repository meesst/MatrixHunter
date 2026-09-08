"""过滤引擎（§6.5 / §7.3）。

候选池管理 + 象限过滤。所有方法在 GUI 线程调用。

规则（§7.3）：
  - 对每个 active 方案，用 FilterPoint 投影并比对象限
  - 读取失败 → 淘汰 (read_failed)
  - 不可见 → 淘汰
  - 象限不匹配 → 淘汰
  - 一票否决（单点逐轮过滤）

撤销栈（§9.2/§10.1）：
  - 最多保留 1 轮淘汰快照
  - 一轮过滤后 active=0 → 自动回退该轮
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from core.projector import Projector
from core.scheme import (
    FilterOutcome,
    FilterPoint,
    MatrixScheme,
    ProjectionResult,
    Quadrant,
    SchemeStatus,
)
from infra.config import AppConfig
from infra.logger import get_logger

log = get_logger("filter")

# 候选池规模上限（§11.1）
MAX_SCHEMES = 10000


class FilterEngine:
    """候选池管理 + 象限过滤。所有方法在 GUI 线程调用。"""

    def __init__(self, config: AppConfig):
        self._config = config
        # scheme_id -> (MatrixScheme, status)
        self._pool: dict[str, tuple[MatrixScheme, SchemeStatus]] = {}
        # 撤销栈：上一轮被淘汰的 scheme_id 集合（最多 1 轮）
        self._undo_stack: list[set[str]] = []
        self._total_enumerated: int = 0

    # ------------------------------------------------------------------
    # 候选池管理
    # ------------------------------------------------------------------
    def load_schemes(self, schemes: list[MatrixScheme]) -> Optional[str]:
        """重置候选池为给定方案列表（清空已有）。

        Returns: 警告字符串（超上限时），None 表示正常。
        """
        if len(schemes) > MAX_SCHEMES:
            warn = (
                f"候选方案数 {len(schemes)} 超过上限 {MAX_SCHEMES}，"
                f"请减少地址数量"
            )
            log.warning(warn)
            return warn

        self._pool = {s.scheme_id: (s, SchemeStatus.ACTIVE) for s in schemes}
        self._undo_stack.clear()
        self._total_enumerated = len(schemes)
        log.info("候选池已载入 %d 方案", len(schemes))
        return None

    def reset(self) -> None:
        """清空候选池。"""
        self._pool.clear()
        self._undo_stack.clear()
        self._total_enumerated = 0
        log.info("候选池已清空")

    @property
    def active_schemes(self) -> list[MatrixScheme]:
        """当前存活方案（只读视图，按地址排序便于展示）。"""
        items = [
            (s, st) for s, st in self._pool.values() if st is SchemeStatus.ACTIVE
        ]
        items.sort(key=lambda x: (x[0].address, x[0].scheme_id))
        return [s for s, _ in items]

    @property
    def all_schemes(self) -> list[MatrixScheme]:
        """全部方案（含已淘汰），用于结果表展示。"""
        items = sorted(
            self._pool.values(), key=lambda x: (x[0].address, x[0].scheme_id)
        )
        return [s for s, _ in items]

    def remove_scheme(self, scheme_id: str) -> bool:
        """手动从候选池移除指定方案（彻底删除，不可撤销）。"""
        if scheme_id in self._pool:
            del self._pool[scheme_id]
            log.info("手动移除方案: %s", scheme_id)
            return True
        return False

    def get_scheme(self, scheme_id: str) -> Optional[MatrixScheme]:
        entry = self._pool.get(scheme_id)
        return entry[0] if entry else None

    def get_status(self, scheme_id: str) -> Optional[SchemeStatus]:
        entry = self._pool.get(scheme_id)
        return entry[1] if entry else None

    @property
    def active_count(self) -> int:
        return sum(1 for _, st in self._pool.values() if st is SchemeStatus.ACTIVE)

    @property
    def total_count(self) -> int:
        return self._total_enumerated

    @property
    def can_undo(self) -> bool:
        """撤销栈非空时可撤销。"""
        return bool(self._undo_stack)

    # ------------------------------------------------------------------
    # 过滤
    # ------------------------------------------------------------------
    def filter(
        self,
        points: list[tuple[MatrixScheme, Optional[np.ndarray], FilterPoint]],
        projector: Projector,
    ) -> FilterOutcome:
        """执行一轮过滤。

        points: [(scheme, matrix_or_None, filter_point), ...]
                matrix 为 None 表示读取失败。
        规则: 对每个方案，用 FilterPoint 投影并比对象限；
              读取失败/不可见/象限不匹配 → 淘汰（一票否决）。
        Returns: FilterOutcome
        """
        before = self.active_count
        eliminated: list[str] = []
        skipped: list[str] = []

        for scheme, matrix, fp in points:
            sid = scheme.scheme_id
            # 仅处理当前 active 方案（防御性）
            entry = self._pool.get(sid)
            if entry is None or entry[1] is not SchemeStatus.ACTIVE:
                continue

            result = self._judge(scheme, matrix, fp, projector)
            # result 为 None 表示边界模糊，跳过本轮淘汰判定
            if result is None:
                skipped.append(sid)
                continue
            if result:  # True = 应淘汰
                self._pool[sid] = (scheme, SchemeStatus.ELIMINATED)
                eliminated.append(sid)

        after = self.active_count

        # §10.1: 一轮过滤后 active=0 → 自动回退该轮
        auto_rolled_back = False
        if after == 0 and before > 0 and eliminated:
            self._undo(eliminated)
            after = self.active_count
            auto_rolled_back = True
            log.warning(
                "过滤后候选池为空，已自动回退该轮（淘汰 %d 方案）",
                len(eliminated),
            )
        else:
            # 压入撤销栈（最多保留 1 轮）
            self._undo_stack = [set(eliminated)] if eliminated else []

        log.info(
            "过滤完成: %d → %d (淘汰 %d，跳过边界 %d%s)",
            before,
            after,
            len(eliminated),
            len(skipped),
            "，已自动回退" if auto_rolled_back else "",
        )
        return FilterOutcome(
            before_count=before,
            after_count=after,
            eliminated_ids=eliminated,
            skipped_ids=skipped,
        )

    def _judge(
        self,
        scheme: MatrixScheme,
        matrix: Optional[np.ndarray],
        fp: FilterPoint,
        projector: Projector,
    ) -> Optional[bool]:
        """判定单个方案是否应淘汰。

        Returns:
            True  - 淘汰（读取失败/不可见/象限不匹配）
            False - 保留（象限匹配）
            None  - 边界模糊，跳过本轮判定（不淘汰也不确认）
        """
        # 读取失败 → 淘汰
        if matrix is None:
            return True
        try:
            result = projector.project(scheme, matrix, fp.world)
        except Exception:  # noqa: BLE001
            log.exception("投影异常 scheme=%s", scheme.scheme_id)
            return True
        # 不可见 → 淘汰（§7.3: 不可见即不满足"目标在该象限"的前提）
        if not result.visible:
            return True
        # 边界模糊 → 跳过（§7.2 容差带：参考目标贴近中心线，无法可靠判定象限）
        if result.borderline:
            return None
        # 象限不匹配 → 淘汰
        if result.quadrant is not fp.quadrant:
            return True
        return False

    # ------------------------------------------------------------------
    # 撤销
    # ------------------------------------------------------------------
    def undo_last(self) -> Optional[set[str]]:
        """撤销最近一轮过滤（恢复被淘汰的方案）。

        Returns: 被恢复的 scheme_id 集合，None 表示无可撤销。
        """
        if not self._undo_stack:
            return None
        eliminated = self._undo_stack.pop()
        self._undo(eliminated)
        log.info("已撤销最近一轮，恢复 %d 方案", len(eliminated))
        return eliminated

    def _undo(self, eliminated_ids: list[str] | set[str]) -> None:
        """内部恢复实现。"""
        id_set = set(eliminated_ids)
        for sid in id_set:
            entry = self._pool.get(sid)
            if entry and entry[1] is SchemeStatus.ELIMINATED:
                self._pool[sid] = (entry[0], SchemeStatus.ACTIVE)
