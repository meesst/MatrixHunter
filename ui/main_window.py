"""主窗口（§6.6 / §9.1 / §9.2 / §9.4）。

聚合 ProcessManager / MemoryReader / FilterEngine / Projector / OverlayWindow，
提供完整的进程附加 → 枚举 → 过滤 → 选用 → 实时绘制 交互流程。
"""
from __future__ import annotations

from typing import Optional

import ctypes
from ctypes import wintypes

import numpy as np
import psutil

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QMetaObject, Q_ARG
from PySide6.QtGui import QColor, QDoubleValidator, QCursor, QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.filter_engine import FilterEngine
from core.matrix_enumerator import MatrixEnumerator, READ_ELEMENT_COUNT
from core.memory_reader import MemoryReader
from core.process_manager import ProcessManager, _is_process_64bit
from core.projector import Projector
from core.scheme import (
    DataType,
    FilterPoint,
    MatrixScheme,
    MulDirection,
    Quadrant,
    SchemeStatus,
    WorldCoord,
)
from infra.config import AppConfig
from infra.errors import (
    AttachError,
    InvalidAddressError,
    MatrixHunterError,
    ProcessListError,
)
from infra.logger import get_logger
from infra.threading_helpers import SignalBridge, StoppableThread
from ui.overlay import OverlayWindow
from ui.widgets import AddressInputWidget, SchemeResultTable

log = get_logger("main")

# 象限中文显示名
_QUADRANT_CN = {
    Quadrant.TOP_LEFT: "左上",
    Quadrant.TOP_RIGHT: "右上",
    Quadrant.BOTTOM_LEFT: "左下",
    Quadrant.BOTTOM_RIGHT: "右下",
}

# Win32 API（窗口拖拽选择用）
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


# ----------------------------------------------------------------------
# 工作线程
# ----------------------------------------------------------------------
class WindowTrackThread(StoppableThread):
    """窗口跟踪线程（§4.2, 10Hz）。"""

    def __init__(self, pm: ProcessManager, pid: int, bridge: SignalBridge,
                 interval_ms: int):
        super().__init__(interval_ms / 1000.0, "WindowTrack")
        self._pm = pm
        self._pid = pid
        self._bridge = bridge
        self._last_rect: Optional[tuple[int, int, int, int]] = None

    def tick(self) -> None:
        hwnd = self._pm.find_main_window(self._pid)
        if not hwnd or not self._pm.is_window_visible(hwnd):
            if self._last_rect is not None:
                self._last_rect = None
                self._bridge.sig_overlay_visible.emit(False)
            return
        rect = self._pm.get_client_rect_on_screen(hwnd)
        if rect is None:
            return
        if rect != self._last_rect:
            self._last_rect = rect
            self._bridge.sig_overlay_align.emit(*rect)


class RealtimeDrawThread(StoppableThread):
    """实时绘制线程（§4.2, 30Hz, §7.4）。"""

    def __init__(
        self,
        reader_getter,
        projector_getter,
        scheme_getter,
        world_getter,
        bridge: SignalBridge,
        interval_ms: int,
        on_failure_limit=None,
    ):
        super().__init__(
            interval_ms / 1000.0,
            "RealtimeDraw",
            max_consecutive_failures=30,
            on_failure_limit=on_failure_limit,
        )
        self._reader_getter = reader_getter
        self._projector_getter = projector_getter
        self._scheme_getter = scheme_getter
        self._world_getter = world_getter
        self._bridge = bridge

    def tick(self) -> None:
        reader = self._reader_getter()
        projector = self._projector_getter()
        scheme = self._scheme_getter()
        world = self._world_getter()
        if reader is None or projector is None or scheme is None or world is None:
            return

        raw = reader.read_floats(scheme.address, READ_ELEMENT_COUNT)
        matrix = scheme.build_matrix(raw[: scheme.element_count])
        result = projector.project(scheme, matrix, world)
        if result.visible:
            self._bridge.sig_realtime_point.emit(
                float(result.screen_x), float(result.screen_y)
            )
        else:
            self._bridge.sig_realtime_point.emit(None, None)


# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    """MatrixHunter 主窗口。"""

    # §6.6 信号
    sig_filter_triggered = Signal(object, object)  # WorldCoord, Quadrant
    sig_realtime_toggled = Signal(bool)
    sig_scheme_selected = Signal(str)
    sig_process_attached = Signal(int, bool)

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config
        self._pm = ProcessManager()
        self._reader: Optional[MemoryReader] = None
        self._filter = FilterEngine(config)
        self._projector = Projector(0, 0, config)
        self._overlay = OverlayWindow()
        self._data_type = DataType.FLOAT
        self._selected_scheme: Optional[MatrixScheme] = None
        self._current_world: Optional[WorldCoord] = None

        # 窗口拖拽选择状态
        self._drag_picking = False
        self._drag_timer: Optional[QTimer] = None
        self._drag_last_down = False

        # 骨骼编号
        self._bone_timer: Optional[QTimer] = None

        # 线程
        self._bridge = SignalBridge()
        self._track_thread: Optional[WindowTrackThread] = None
        self._realtime_thread: Optional[RealtimeDrawThread] = None

        self.setWindowTitle("MatrixHunter")
        self.resize(1000, 700)
        self._build_ui()
        self._connect_signals()
        self._refresh_process_list()
        self._update_ui_state()

    # ==================================================================
    # UI 构建
    # ==================================================================
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        # ================================================================
        # 全局顶部：进程选择 + 操作按钮（始终可见）
        # ================================================================
        top = QHBoxLayout()
        top.addWidget(QLabel("进程:"))
        self._combo_process = QComboBox()
        self._combo_process.setMinimumWidth(280)
        top.addWidget(self._combo_process)
        self._btn_refresh = QPushButton("刷新")
        top.addWidget(self._btn_refresh)
        self._btn_attach = QPushButton("附加")
        top.addWidget(self._btn_attach)
        self._btn_drag = QPushButton("🎯")
        self._btn_drag.setToolTip("按住拖拽到目标窗口以选择并附加（松开后弹窗确认）")
        self._btn_drag.setFixedWidth(32)
        top.addWidget(self._btn_drag)
        top.addSpacing(12)
        top.addWidget(QLabel("数据类型:"))
        self._rb_float = QRadioButton("float")
        self._rb_double = QRadioButton("double")
        self._rb_float.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._rb_float)
        grp.addButton(self._rb_double)
        top.addWidget(self._rb_float)
        top.addWidget(self._rb_double)
        top.addStretch()
        root.addLayout(top)

        # 当前进程状态
        self._lbl_process_info = QLabel("当前进程：未附加")
        self._lbl_process_info.setStyleSheet("color: #888; padding: 2px 0 4px 0;")
        root.addWidget(self._lbl_process_info)

        # ================================================================
        # QTabWidget 功能切换
        # ================================================================
        self._tab_widget = QTabWidget()

        # ---- Tab 1: 矩阵查找 ----
        matrix_tab = QWidget()
        matrix_layout = QVBoxLayout(matrix_tab)

        # 地址列表 + 过滤区（水平等分）
        hbox = QHBoxLayout()

        # 左：地址表
        left_box = QGroupBox("地址列表")
        left_layout = QVBoxLayout(left_box)
        self._address_widget = AddressInputWidget()
        left_layout.addWidget(self._address_widget)
        self._btn_enumerate = QPushButton("枚举候选方案")
        left_layout.addWidget(self._btn_enumerate)
        hbox.addWidget(left_box, 1)

        # 右：过滤区
        right_box = QGroupBox("过滤区")
        right_layout = QVBoxLayout(right_box)

        # 世界坐标
        form = QFormLayout()
        self._spin_x = QDoubleSpinBox()
        self._spin_y = QDoubleSpinBox()
        self._spin_z = QDoubleSpinBox()
        for sp in (self._spin_x, self._spin_y, self._spin_z):
            sp.setRange(-1e12, 1e12)
            sp.setDecimals(6)
            sp.setValue(0.0)
        form.addRow("W.X:", self._spin_x)
        form.addRow("W.Y:", self._spin_y)
        form.addRow("W.Z:", self._spin_z)
        right_layout.addLayout(form)

        # 象限按钮
        quad_label = QLabel("目标象限（点击触发过滤）:")
        right_layout.addWidget(quad_label)
        quad_grid = QGridLayout()
        self._btn_tl = QPushButton("左上 (TL)")
        self._btn_tr = QPushButton("右上 (TR)")
        self._btn_bl = QPushButton("左下 (BL)")
        self._btn_br = QPushButton("右下 (BR)")
        quad_grid.addWidget(self._btn_tl, 0, 0)
        quad_grid.addWidget(self._btn_tr, 0, 1)
        quad_grid.addWidget(self._btn_bl, 1, 0)
        quad_grid.addWidget(self._btn_br, 1, 1)
        right_layout.addLayout(quad_grid)

        # 撤销/重置
        action_row = QHBoxLayout()
        self._btn_undo = QPushButton("撤销最近一轮")
        self._btn_reset_pool = QPushButton("重置候选池")
        action_row.addWidget(self._btn_undo)
        action_row.addWidget(self._btn_reset_pool)
        right_layout.addLayout(action_row)

        right_layout.addStretch()
        self._lbl_count = QLabel("存活方案: 0 / 总 0")
        right_layout.addWidget(self._lbl_count)
        hbox.addWidget(right_box, 1)

        matrix_layout.addLayout(hbox)

        # 结果表 + 实时绘制
        bottom_box = QGroupBox("结果表")
        bottom_layout = QVBoxLayout(bottom_box)
        self._result_table = SchemeResultTable()
        bottom_layout.addWidget(self._result_table)
        realtime_row = QHBoxLayout()
        self._chk_realtime = QCheckBox("实时绘制(基于选中方案)")
        realtime_row.addWidget(self._chk_realtime)
        self._chk_crosshair = QCheckBox("十字线")
        self._chk_crosshair.setChecked(False)
        realtime_row.addWidget(self._chk_crosshair)
        realtime_row.addStretch()
        bottom_layout.addLayout(realtime_row)
        matrix_layout.addWidget(bottom_box)

        self._tab_widget.addTab(matrix_tab, "矩阵查找")

        # ---- Tab 2: 骨骼编号（实时读取） ----
        skeleton_tab = QWidget()
        sk_layout = QVBoxLayout(skeleton_tab)

        # ---- 骨骼配置 ----
        cfg_box = QGroupBox("骨骼配置")
        cfg_grid = QVBoxLayout(cfg_box)
        self._bone_base_addr = QLineEdit()
        self._bone_base_addr.setPlaceholderText("0x23FDABAA030")
        cfg_grid.addWidget(self._bone_base_addr)
        rc_row = QHBoxLayout()
        rc_row.addWidget(QLabel("数量:")); self._bone_count = QSpinBox(); self._bone_count.setRange(1, 256); self._bone_count.setValue(24)
        rc_row.addWidget(self._bone_count)
        rc_row.addSpacing(10)
        rc_row.addWidget(QLabel("步长:")); self._bone_stride = QSpinBox(); self._bone_stride.setRange(1, 512); self._bone_stride.setValue(96); self._bone_stride.setSuffix(" 字节")
        rc_row.addWidget(self._bone_stride)
        rc_row.addStretch()
        cfg_grid.addLayout(rc_row)
        self._bone_mat_addr = QLineEdit()
        self._bone_mat_addr.setPlaceholderText("0x... 视图投影矩阵（可选，填了则投影）")
        cfg_grid.addWidget(self._bone_mat_addr)
        ctrl_row = QHBoxLayout()
        self._btn_bone_start = QPushButton("▶ 开始绘制")
        ctrl_row.addWidget(self._btn_bone_start)
        self._btn_bone_stop = QPushButton("■ 停止绘制")
        self._btn_bone_stop.setEnabled(False)
        ctrl_row.addWidget(self._btn_bone_stop)
        ctrl_row.addStretch()
        self._lbl_bone_status = QLabel("就绪")
        ctrl_row.addWidget(self._lbl_bone_status)
        cfg_grid.addLayout(ctrl_row)
        sk_layout.addWidget(cfg_box)

        # ---- 显示设置 ----
        disp_box = QGroupBox("显示设置")
        disp_grid = QVBoxLayout(disp_box)

        chk_row = QHBoxLayout()
        self._chk_bone_visible = QCheckBox("绘制编号")
        self._chk_bone_visible.setChecked(True)
        chk_row.addWidget(self._chk_bone_visible)
        chk_row.addStretch()
        disp_grid.addLayout(chk_row)

        # 字体+编号颜色一行
        fc_row = QHBoxLayout()
        fc_row.addWidget(QLabel("字体大小:"))
        self._bone_font_size = QSpinBox(); self._bone_font_size.setRange(6, 72); self._bone_font_size.setValue(14)
        fc_row.addWidget(self._bone_font_size)
        self._lbl_bone_font_preview = QLabel("14")
        self._lbl_bone_font_preview.setStyleSheet("font-size:14px;font-family:Consolas;background:#333;color:#fff;padding:2px 6px;border-radius:3px;")
        fc_row.addWidget(self._lbl_bone_font_preview)
        fc_row.addSpacing(16)
        fc_row.addWidget(QLabel("编号颜色:"))
        self._btn_bone_num_color = QPushButton()
        self._btn_bone_num_color.setFixedSize(28, 22)
        self._bone_num_color = QColor(255, 255, 255)
        self._btn_bone_num_color.setStyleSheet(f"background:{self._bone_num_color.name()};border:1px solid #888;")
        fc_row.addWidget(self._btn_bone_num_color)
        fc_row.addStretch()
        disp_grid.addLayout(fc_row)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("过滤编号:"))
        self._bone_filter_input = QLineEdit()
        self._bone_filter_input.setPlaceholderText("如: 0,3,7-10,15")
        filter_row.addWidget(self._bone_filter_input, 1)
        self._btn_bone_apply_filter = QPushButton("应用")
        filter_row.addWidget(self._btn_bone_apply_filter)
        self._btn_bone_clear_filter = QPushButton("清除")
        filter_row.addWidget(self._btn_bone_clear_filter)
        disp_grid.addLayout(filter_row)
        sk_layout.addWidget(disp_box)

        # ---- 连线配置 ----
        conn_box = QGroupBox("连线配置")
        conn_layout = QVBoxLayout(conn_box)
        # 第一行：绘制开关 + 颜色
        conn_top = QHBoxLayout()
        self._chk_bone_lines = QCheckBox("绘制连线")
        self._chk_bone_lines.setChecked(True)
        conn_top.addWidget(self._chk_bone_lines)
        conn_top.addSpacing(12)
        conn_top.addWidget(QLabel("颜色:"))
        self._btn_bone_line_color = QPushButton()
        self._btn_bone_line_color.setFixedSize(28, 22)
        self._bone_line_color = QColor(0, 200, 255, 180)
        self._btn_bone_line_color.setStyleSheet(f"background:{self._bone_line_color.name()};border:1px solid #888;")
        conn_top.addWidget(self._btn_bone_line_color)
        conn_top.addStretch()
        conn_layout.addLayout(conn_top)
        # 第二行：添加连线
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("起点:"))
        self._bone_conn_from = QSpinBox(); self._bone_conn_from.setRange(0, 255)
        add_row.addWidget(self._bone_conn_from)
        add_row.addWidget(QLabel("→"))
        self._bone_conn_to = QSpinBox(); self._bone_conn_to.setRange(0, 255); self._bone_conn_to.setValue(1)
        add_row.addWidget(self._bone_conn_to)
        self._btn_bone_add_conn = QPushButton("添加")
        add_row.addWidget(self._btn_bone_add_conn)
        add_row.addStretch()
        conn_layout.addLayout(add_row)
        # 第三行：文本显示连线
        self._bone_conn_text = QLineEdit()
        self._bone_conn_text.setPlaceholderText("1→2, 5→6, 10→15")
        conn_layout.addWidget(self._bone_conn_text)
        conn_btn_row = QHBoxLayout()
        self._btn_bone_apply_conn = QPushButton("应用连线")
        conn_btn_row.addWidget(self._btn_bone_apply_conn)
        conn_btn_row.addStretch()
        conn_layout.addLayout(conn_btn_row)
        sk_layout.addWidget(conn_box)

        sk_layout.addStretch()
        self._tab_widget.addTab(skeleton_tab, "骨骼编号")
        self._tab_widget.setTabEnabled(1, True)

        root.addWidget(self._tab_widget, 1)

        # ---- 状态栏 ----
        self.setStatusBar(QStatusBar())
        self._lbl_status = QLabel("就绪")
        self.statusBar().addWidget(self._lbl_status, 1)

    # ==================================================================
    # 信号连接
    # ==================================================================
    def _connect_signals(self) -> None:
        self._btn_refresh.clicked.connect(self._refresh_process_list)
        self._btn_attach.clicked.connect(self._on_attach)
        self._btn_drag.pressed.connect(self._on_drag_start)
        self._btn_enumerate.clicked.connect(self._on_enumerate)
        self._btn_undo.clicked.connect(self._on_undo)
        self._btn_reset_pool.clicked.connect(self._on_reset_pool)

        self._rb_float.toggled.connect(self._on_data_type_changed)
        self._rb_double.toggled.connect(self._on_data_type_changed)

        # 象限按钮直接触发过滤
        self._btn_tl.clicked.connect(lambda: self._do_filter(Quadrant.TOP_LEFT))
        self._btn_tr.clicked.connect(lambda: self._do_filter(Quadrant.TOP_RIGHT))
        self._btn_bl.clicked.connect(lambda: self._do_filter(Quadrant.BOTTOM_LEFT))
        self._btn_br.clicked.connect(lambda: self._do_filter(Quadrant.BOTTOM_RIGHT))

        self._result_table.sig_scheme_selected.connect(self._on_scheme_selected)
        self._result_table.sig_scheme_preview.connect(self._on_scheme_preview)
        self._result_table.sig_scheme_delete.connect(self._on_scheme_delete)
        self._result_table.sig_item_copied.connect(
            lambda text: self._set_status(f"已复制: {text}")
        )
        self._chk_realtime.toggled.connect(self._on_realtime_toggled)
        self._chk_crosshair.toggled.connect(self._overlay.set_crosshair_visible)

        # 桥接信号
        # ---- 骨骼编号信号 ----
        self._btn_bone_start.clicked.connect(self._on_bone_start)
        self._btn_bone_stop.clicked.connect(self._on_bone_stop)
        self._bone_font_size.valueChanged.connect(self._on_bone_font_size_changed)
        self._chk_bone_visible.toggled.connect(lambda: None)  # 下次 tick 自动处理
        self._chk_bone_lines.toggled.connect(self._on_bone_lines_toggled)
        self._btn_bone_num_color.clicked.connect(lambda: self._pick_color("num"))
        self._btn_bone_line_color.clicked.connect(lambda: self._pick_color("line"))
        self._btn_bone_apply_filter.clicked.connect(self._on_bone_apply_filter)
        self._btn_bone_clear_filter.clicked.connect(self._on_bone_clear_filter)
        self._btn_bone_add_conn.clicked.connect(self._on_bone_add_connection)
        self._btn_bone_apply_conn.clicked.connect(self._on_bone_apply_conn_text)

        # 桥接信号
        self._bridge.sig_overlay_align.connect(self._overlay.align_to_client)
        self._bridge.sig_overlay_align.connect(self._on_client_rect_updated)
        self._bridge.sig_overlay_visible.connect(self._on_overlay_visible)
        self._bridge.sig_realtime_point.connect(self._on_realtime_point)
        self._bridge.sig_status.connect(self._lbl_status.setText)
        self._bridge.sig_error.connect(self._on_thread_error)
        self._bridge.sig_hotkey.connect(self._on_hotkey)

    # ==================================================================
    # 进程管理
    # ==================================================================
    def _refresh_process_list(self) -> None:
        self._combo_process.clear()
        try:
            procs = self._pm.list_processes()
        except ProcessListError as exc:
            QMessageBox.warning(self, "错误", f"枚举进程失败: {exc}")
            return
        for pid, name, is64 in procs:
            bit = "64" if is64 else "32"
            label = f"[{bit}] {name} (pid={pid})"
            self._combo_process.addItem(label, (pid, name, is64))

    def _on_attach(self) -> None:
        idx = self._combo_process.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "提示", "请先选择进程")
            return
        pid, name, is64 = self._combo_process.itemData(idx)
        try:
            self._pm.attach(pid)
        except AttachError as exc:
            QMessageBox.critical(self, "附加失败", str(exc))
            return
        self._reader = MemoryReader(self._pm.pymem_handle, self._data_type)
        self._config.last_process_name = name
        self.sig_process_attached.emit(pid, is64)
        # 立即查找主窗口并同步客户区尺寸
        hwnd = self._pm.find_main_window(pid)
        if hwnd:
            rect = self._pm.get_client_rect_on_screen(hwnd)
            log.debug(
                "attached pid=%d name=%s hwnd=0x%X client_rect=%s",
                pid, name, hwnd, rect,
            )
            if rect:
                self._projector.set_client_size(rect[2], rect[3])
        else:
            log.warning("attached pid=%d name=%s but no main window found", pid, name)
        bit_str = "64 位" if is64 else "32 位"
        self._lbl_process_info.setText(
            f"当前进程：{name}  |  PID: {pid}  |  {bit_str}"
        )
        self._lbl_process_info.setStyleSheet("color: #080; padding: 2px 0 4px 0;")
        self._set_status(f"已附加: {name} (pid={pid}, {'64' if is64 else '32'}位)")
        self._update_ui_state()
        # 启动窗口跟踪
        self._start_window_tracking(pid)

    # ==================================================================
    # 窗口拖拽选择
    # ==================================================================
    def _on_drag_start(self) -> None:
        """按下拖拽按钮 → 进入拖拽选择模式。

        鼠标按钮当前为按下状态（pressed 信号），
        用户保持按住→拖动到目标窗口→松开→选择该窗口。
        """
        if self._drag_picking:
            return
        self._drag_picking = True
        self._drag_last_down = True  # 当前鼠标是按下状态
        self._update_ui_state()
        self._set_status("按住鼠标拖动到目标窗口，松开以选择（按 ESC 取消）...")
        QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)

        # 隐藏主窗口让用户能看到目标窗口
        self.hide()

        # 开始轮询鼠标按键状态
        self._drag_timer = QTimer(self)
        self._drag_timer.timeout.connect(self._drag_poll)
        self._drag_timer.start(80)

    def _drag_cancel(self) -> None:
        """取消拖拽选择。"""
        if not self._drag_picking:
            return
        self._drag_picking = False
        if self._drag_timer:
            self._drag_timer.stop()
            self._drag_timer = None
        QApplication.restoreOverrideCursor()
        self._set_status("已取消窗口选择")
        # 恢复窗口，并刷新 UI 状态让按钮重新可用
        self._restore_after_drag()
        self._update_ui_state()

    def _drag_poll(self) -> None:
        """轮询检测鼠标按键状态。

        初始时按钮是按下状态（_drag_last_down=True），
        检测到按钮从按下→释放，即为拖拽完成。
        """
        if not self._drag_picking:
            return
        # 检测 ESC 取消
        if _user32.GetAsyncKeyState(0x1B) & 0x8000:  # VK_ESCAPE
            self._drag_cancel()
            return
        down = bool(_user32.GetAsyncKeyState(0x01) & 0x8000)  # VK_LBUTTON
        if self._drag_last_down and not down:
            # 按钮从按下→释放 → 拖拽完成，识别目标窗口
            self._drag_last_down = False
            self._handle_drag_drop()

    def _handle_drag_drop(self) -> None:
        """在目标窗口上松开鼠标 → 获取窗口信息。"""
        if not self._drag_picking:
            return
        self._drag_picking = False
        if self._drag_timer:
            self._drag_timer.stop()
            self._drag_timer = None
        QApplication.restoreOverrideCursor()

        # 获取鼠标松开时的窗口位置
        pt = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        hwnd = _user32.WindowFromPoint(pt)

        # 先恢复窗口和 UI 状态（确保按钮可点击）
        self._restore_after_drag()
        self._update_ui_state()

        if not hwnd or not _user32.IsWindow(hwnd):
            self._set_status("未找到目标窗口")
            return

        self._show_window_info_dialog(hwnd)

    def _show_window_info_dialog(self, hwnd: int) -> None:
        """弹窗显示目标窗口信息，让用户决定是否附加。"""
        # 获取窗口标题
        title_buf = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, title_buf, 512)
        title = title_buf.value or "(无标题)"

        # 获取窗口类名
        class_buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, class_buf, 256)
        cls_name = class_buf.value or "(未知)"

        # 获取进程 PID
        proc_id = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        pid = proc_id.value

        # 获取进程名
        proc_name = f"(pid={pid})"
        bit_str = "未知"
        try:
            if pid:
                p = psutil.Process(pid)
                proc_name = p.name()
                bit_str = "64 位" if _is_process_64bit(pid) else "32 位"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            proc_name = f"(pid={pid})"

        # 构建对话框
        dlg = QDialog(self)
        dlg.setWindowTitle("窗口信息")
        dlg.setMinimumWidth(400)

        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        form.addRow("窗口标题:", QLabel(title))
        form.addRow("窗口类名:", QLabel(cls_name))
        form.addRow("进程名称:", QLabel(proc_name))
        form.addRow("进程 PID:", QLabel(str(pid)))
        form.addRow("位数:", QLabel(bit_str))
        layout.addLayout(form)

        layout.addSpacing(10)
        btn_box = QDialogButtonBox()
        btn_box.addButton("附加到此进程", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(btn_box)

        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)

        # 显示对话框（模态）
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._drag_attach_to_process(pid, proc_name)
        # 取消后刷新 UI 状态，确保按钮恢复
        self._update_ui_state()

    def _drag_attach_to_process(self, pid: int, name: str) -> None:
        """从拖拽选择结果附加到进程。"""
        try:
            self._pm.attach(pid)
        except AttachError as exc:
            QMessageBox.critical(self, "附加失败", str(exc))
            self._update_ui_state()
            return
        # 检查位数
        is64 = _is_process_64bit(pid)
        self._reader = MemoryReader(self._pm.pymem_handle, self._data_type)
        self._config.last_process_name = name
        self.sig_process_attached.emit(pid, is64)
        # 同步客户区
        hwnd = self._pm.find_main_window(pid)
        if hwnd:
            rect = self._pm.get_client_rect_on_screen(hwnd)
            if rect:
                self._projector.set_client_size(rect[2], rect[3])
        # 更新下拉选中
        for i in range(self._combo_process.count()):
            _, pn, _ = self._combo_process.itemData(i)
            if pn == name:
                self._combo_process.setCurrentIndex(i)
                break
        bit_str = "64 位" if is64 else "32 位"
        self._lbl_process_info.setText(
            f"当前进程：{name}  |  PID: {pid}  |  {bit_str}"
        )
        self._lbl_process_info.setStyleSheet("color: #080; padding: 2px 0 4px 0;")
        self._set_status(f"已附加（拖拽）: {name} (pid={pid}, {'64' if is64 else '32'}位)")
        self._update_ui_state()
        self._start_window_tracking(pid)

    def _restore_after_drag(self) -> None:
        """拖拽结束后恢复主窗口。"""
        self.show()
        self.raise_()
        self.activateWindow()

    # ==================================================================
    # 数据类型
    # ==================================================================
    def _on_data_type_changed(self) -> None:
        new_type = DataType.FLOAT if self._rb_float.isChecked() else DataType.DOUBLE
        if new_type is self._data_type:
            return
        self._data_type = new_type
        # §9.2: 切换数据类型清空候选池
        self._filter.reset()
        self._selected_scheme = None
        self._overlay.set_preview_point(None, None)
        if self._reader is not None:
            self._reader = MemoryReader(self._pm.pymem_handle, self._data_type)
        self._refresh_result_table()
        self._update_ui_state()
        self._set_status(f"数据类型切换为 {new_type.value}，候选池已清空")

    # ==================================================================
    # 枚举
    # ==================================================================
    def _on_enumerate(self) -> None:
        if not self._pm.is_attached:
            QMessageBox.warning(self, "提示", "请先附加进程")
            return
        addresses = self._address_widget.get_addresses()
        if not addresses:
            QMessageBox.warning(self, "提示", "请输入至少一个地址")
            return

        self._set_status(f"正在枚举候选方案（{len(addresses)} 地址）...")
        self._set_buttons_busy(True)

        progress = QProgressDialog(
            f"正在枚举 {len(addresses)} 个地址的候选方案...", None, 0, 100, self
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setWindowTitle("枚举")
        progress.setValue(10)
        QApplication.processEvents()

        try:
            schemes = MatrixEnumerator.enumerate_batch(addresses, self._data_type)
            progress.setValue(60)
            QApplication.processEvents()
            warn = self._filter.load_schemes(schemes)
        finally:
            progress.setValue(100)
            progress.close()
            self._set_buttons_busy(False)

        if warn:
            QMessageBox.warning(self, "警告", warn)
        self._selected_scheme = None
        self._overlay.set_preview_point(None, None)
        self._refresh_result_table()
        self._update_ui_state()
        self._set_status(f"枚举完成：{len(schemes)} 方案（{len(addresses)} 地址），请转动视角后点击象限按钮过滤")

    # ==================================================================
    # 过滤
    # ==================================================================
    def _do_filter(self, quadrant: Quadrant) -> None:
        if not self._pm.is_attached:
            QMessageBox.warning(self, "提示", "请先附加进程")
            return
        if self._filter.active_count == 0:
            QMessageBox.warning(self, "提示", "候选池为空，请先枚举")
            return
        # 校验 W
        wx = self._spin_x.value()
        wy = self._spin_y.value()
        wz = self._spin_z.value()
        import math
        if any(math.isnan(v) or math.isinf(v) for v in (wx, wy, wz)):
            QMessageBox.warning(self, "提示", "请输入有效的世界坐标")
            return
        world = WorldCoord(wx, wy, wz)
        self._current_world = world
        fp = FilterPoint(world, quadrant)

        quad_cn = _QUADRANT_CN.get(quadrant, quadrant.value)
        self._set_status(f"正在过滤（{quad_cn}）...")
        self._set_buttons_busy(True)

        # 同步客户区尺寸
        self._sync_client_size()
        cw, ch = self._projector.client_size
        if cw <= 0 or ch <= 0:
            self._set_buttons_busy(False)
            self._update_ui_state()
            QMessageBox.warning(self, "提示", "窗口客户区无效，请确认目标窗口可见")
            return

        progress = QProgressDialog(f"正在过滤（{quad_cn}）...", None, 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setWindowTitle("过滤")
        progress.setValue(10)
        QApplication.processEvents()

        try:
            # §7.3/§11.2: 批量读取所有 active 方案数据（同地址共享）
            active = self._filter.active_schemes
            unique_addrs = list({s.address for s in active})
            addr_count = [(a, READ_ELEMENT_COUNT) for a in unique_addrs]
            raw_map = self._reader.read_floats_batch(addr_count)
            progress.setValue(40)
            QApplication.processEvents()

            # 构建 (scheme, matrix_or_None, fp)
            points = []
            for s in active:
                raw = raw_map.get(s.address)
                if isinstance(raw, Exception):
                    points.append((s, None, fp))
                else:
                    try:
                        matrix = s.build_matrix(raw[: s.element_count])
                        points.append((s, matrix, fp))
                    except Exception:  # noqa: BLE001
                        points.append((s, None, fp))
            progress.setValue(70)
            QApplication.processEvents()

            outcome = self._filter.filter(points, self._projector)
        finally:
            progress.setValue(100)
            progress.close()
            self._set_buttons_busy(False)

        self.sig_filter_triggered.emit(world, quadrant)
        # 过滤后清除预览点（视角/矩阵已变）
        self._overlay.set_preview_point(None, None)
        self._refresh_result_table()
        self._update_ui_state()

        skipped = len(outcome.skipped_ids) if outcome.skipped_ids else 0
        self._show_filter_result(outcome, quad_cn, skipped)

    def _show_filter_result(
        self, outcome, quad_cn: str, skipped: int
    ) -> None:
        """过滤完成后给出状态栏 + 弹窗反馈。"""
        if outcome.after_count == 0 and outcome.before_count > 0:
            QMessageBox.information(
                self,
                "过滤结果",
                f"【{quad_cn}】无方案满足，已自动回退该轮。\n"
                f"可重新判断象限或重置候选池。",
            )
            self._set_status(f"过滤（{quad_cn}）：无方案，已自动回退")
            return

        parts = [f"{outcome.before_count} → {outcome.after_count}"]
        if skipped:
            parts.append(f"边界模糊跳过 {skipped}")
        msg = "，".join(parts)
        self._set_status(f"过滤完成（{quad_cn}）：{msg}")

        if outcome.after_count == 1:
            QMessageBox.information(
                self,
                "过滤完成",
                f"【{quad_cn}】已收敛到唯一存活方案！\n"
                f"请在结果表点「选用」并开启实时绘制验证。",
            )
        elif skipped > 0 and outcome.after_count == outcome.before_count:
            QMessageBox.information(
                self,
                "过滤提示",
                f"【{quad_cn}】本轮 {skipped} 个方案因落点贴近中心十字线被跳过，\n"
                f"未淘汰任何方案。建议调整视角让目标远离十字线后再过滤。",
            )

    def _sync_client_size(self) -> None:
        """从目标窗口同步客户区尺寸到投影器。"""
        if self._pm.attached_pid:
            hwnd = self._pm.find_main_window(self._pm.attached_pid)
            if hwnd:
                rect = self._pm.get_client_rect_on_screen(hwnd)
                if rect:
                    self._projector.set_client_size(rect[2], rect[3])

    def _set_buttons_busy(self, busy: bool) -> None:
        """处理数据时禁用/恢复操作按钮，给用户明确反馈。"""
        for btn in (
            self._btn_enumerate, self._btn_tl, self._btn_tr,
            self._btn_bl, self._btn_br, self._btn_undo,
            self._btn_reset_pool, self._btn_attach, self._btn_refresh,
            self._btn_drag,
        ):
            btn.setEnabled(not busy)

    def _on_undo(self) -> None:
        if not self._filter.can_undo:
            self._set_status("无可撤销")
            return
        self._filter.undo_last()
        self._refresh_result_table()
        self._update_ui_state()
        self._set_status("已撤销最近一轮过滤")

    def _on_reset_pool(self) -> None:
        self._filter.reset()
        self._selected_scheme = None
        self._overlay.set_preview_point(None, None)
        self._refresh_result_table()
        self._update_ui_state()
        self._set_status("候选池已重置，可重新枚举")

    # ==================================================================
    # 方案选用
    # ==================================================================
    def _on_scheme_selected(self, scheme_id: str) -> None:
        scheme = self._filter.get_scheme(scheme_id)
        if scheme is None:
            return
        self._selected_scheme = scheme
        self.sig_scheme_selected.emit(scheme_id)
        self._overlay.set_preview_point(None, None)
        self._refresh_result_table()
        self._set_status(f"已选用方案: {scheme.description}，可开启实时绘制验证")
        self._update_ui_state()

    def _on_scheme_delete(self, scheme_id: str) -> None:
        """手动删除某个方案。"""
        scheme = self._filter.get_scheme(scheme_id)
        name = scheme.description if scheme else scheme_id
        if self._selected_scheme and self._selected_scheme.scheme_id == scheme_id:
            self._selected_scheme = None
            self._overlay.set_preview_point(None, None)
            self._chk_realtime.setChecked(False)
        self._filter.remove_scheme(scheme_id)
        self._refresh_result_table()
        self._update_ui_state()
        self._set_status(f"已删除方案: {name}")

    # ==================================================================
    # 预览
    # ==================================================================
    def _on_scheme_preview(self, scheme_id: str) -> None:
        """预览某方案：读取内存 → 投影 → 在叠加层画黄色预览点。

        预览不修改候选池，仅临时可视化该方案的投影位置，
        帮助用户判断哪个方案是正确的。
        """
        scheme = self._filter.get_scheme(scheme_id)
        if scheme is None:
            return
        if self._reader is None:
            QMessageBox.warning(self, "提示", "请先附加进程")
            return
        if self._current_world is None:
            QMessageBox.warning(
                self, "提示", "请先填写世界坐标并执行至少一次过滤"
            )
            return
        self._sync_client_size()
        cw, ch = self._projector.client_size
        if cw <= 0 or ch <= 0:
            QMessageBox.warning(self, "提示", "窗口客户区无效")
            return

        self._set_status("正在预览方案...")
        QApplication.processEvents()
        try:
            raw = self._reader.read_floats(scheme.address, READ_ELEMENT_COUNT)
            matrix = scheme.build_matrix(raw[: scheme.element_count])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "预览失败", f"读取内存失败: {exc}")
            return
        result = self._projector.project(scheme, matrix, self._current_world)
        if result.visible:
            self._overlay.show()
            self._overlay.set_preview_point(
                float(result.screen_x), float(result.screen_y)
            )
            border = "（边界模糊）" if result.borderline else ""
            self._set_status(
                f"预览：{scheme.description} → "
                f"({result.screen_x:.0f}, {result.screen_y:.0f}){border}"
            )
        else:
            self._overlay.set_preview_point(None, None)
            QMessageBox.information(
                self,
                "预览",
                f"该方案投影不可见（{result.reason}）\n"
                f"可能是矩阵方案错误或目标不在视野内。",
            )

    # ==================================================================
    # 实时绘制
    # ==================================================================
    def _on_realtime_toggled(self, checked: bool) -> None:
        self.sig_realtime_toggled.emit(checked)
        if checked:
            if self._selected_scheme is None:
                QMessageBox.warning(self, "提示", "请先选用一个方案")
                self._chk_realtime.setChecked(False)
                return
            if self._current_world is None:
                QMessageBox.warning(self, "提示", "请先执行一次过滤以设置世界坐标")
                self._chk_realtime.setChecked(False)
                return
            # 开启实时绘制前确保客户区尺寸最新
            self._sync_client_size()
            cw, ch = self._projector.client_size
            log.debug(
                "realtime start: scheme=%s world=%s client=%dx%d",
                self._selected_scheme.scheme_id,
                (self._current_world.x, self._current_world.y, self._current_world.z),
                cw, ch,
            )
            if cw <= 0 or ch <= 0:
                QMessageBox.warning(self, "提示", "窗口客户区无效，无法实时绘制")
                self._chk_realtime.setChecked(False)
                return
            self._start_realtime()
        else:
            self._stop_realtime()
            self._overlay.set_realtime_point(None, None)

    def _start_realtime(self) -> None:
        self._stop_realtime()
        interval = max(1, 1000 // max(1, self._config.realtime_fps))
        self._realtime_thread = RealtimeDrawThread(
            reader_getter=lambda: self._reader,
            projector_getter=lambda: self._projector,
            scheme_getter=lambda: self._selected_scheme,
            world_getter=lambda: self._current_world,
            bridge=self._bridge,
            interval_ms=interval,
            on_failure_limit=self._on_realtime_failure,
        )
        self._overlay.show()
        self._realtime_thread.start()
        self._set_status("实时绘制已启动")

    def _stop_realtime(self) -> None:
        if self._realtime_thread is not None:
            self._realtime_thread.stop()
            self._realtime_thread.join(timeout=2.0)
            self._realtime_thread = None

    def _on_realtime_failure(self) -> None:
        QMetaObject.invokeMethod(
            self, "_on_realtime_failure_slot", Qt.ConnectionType.QueuedConnection
        )

    # ==================================================================
    # 窗口跟踪
    # ==================================================================
    def _start_window_tracking(self, pid: int) -> None:
        self._stop_window_tracking()
        self._track_thread = WindowTrackThread(
            self._pm, pid, self._bridge, self._config.window_track_interval_ms
        )
        self._track_thread.start()

    def _stop_window_tracking(self) -> None:
        if self._track_thread is not None:
            self._track_thread.stop()
            self._track_thread.join(timeout=2.0)
            self._track_thread = None

    # ==================================================================
    # 桥接槽
    # ==================================================================
    def _on_client_rect_updated(
        self, screen_x: int, screen_y: int, w: int, h: int
    ) -> None:
        """窗口跟踪拿到的客户区尺寸同步到投影器（实时绘制依赖）。"""
        self._projector.set_client_size(w, h)
        log.debug("client_rect updated: pos=(%d,%d) size=%dx%d", screen_x, screen_y, w, h)

    def _on_overlay_visible(self, visible: bool) -> None:
        if visible:
            self._overlay.show()
        else:
            self._overlay.hide()
            # 暂停实时绘制（§10.1: 窗口最小化/隐藏）
            if self._chk_realtime.isChecked():
                self._chk_realtime.setChecked(False)

    def _on_realtime_point(self, x, y) -> None:
        self._overlay.set_realtime_point(x, y)

    def _on_thread_error(self, msg: str) -> None:
        QMessageBox.critical(self, "错误", msg)
        self._set_status(f"错误: {msg}")

    def _on_hotkey(self, key: str) -> None:
        if key == "F8":
            self._overlay.setVisible(not self._overlay.isVisible())
        elif key == "F9":
            self._chk_realtime.setChecked(not self._chk_realtime.isChecked())
        elif key == "ESC":
            if self._chk_realtime.isChecked():
                self._chk_realtime.setChecked(False)

    # ==================================================================
    # 骨骼编号
    # ==================================================================
    def _on_bone_format_changed(self) -> None:
        """骨骼格式切换时同步 QStackedWidget。"""
        self._bone_fmt_stack.setCurrentIndex(self._bone_format_combo.currentIndex())
        # 父索引只在 FTransform 和 Matrix 模式下需要
        needs_parent = self._bone_format_combo.currentIndex() < 2
        self._bone_parent_group.setVisible(needs_parent)

    # ==================================================================
    # 骨骼编号（简化版）
    # ==================================================================
    # ==================================================================
    # 骨骼编号（实时读取）
    # ==================================================================
    def _on_bone_start(self) -> None:
        """开始实时绘制骨骼。"""
        if self._reader is None:
            QMessageBox.warning(self, "提示", "请先附加进程")
            return
        if not self._bone_base_addr.text().strip():
            QMessageBox.warning(self, "提示", "请填写骨骼基地址")
            return
        try:
            int(self._bone_base_addr.text().strip(), 16)
        except ValueError:
            QMessageBox.warning(self, "提示", "基地址格式错误")
            return

        self._btn_bone_start.setEnabled(False)
        self._btn_bone_stop.setEnabled(True)
        self._lbl_bone_status.setText("运行中...")
        self._bone_timer = QTimer(self)
        self._bone_timer.timeout.connect(self._bone_tick)
        self._bone_timer.start(100)
        self._bone_tick()

    def _on_bone_stop(self) -> None:
        """停止实时绘制。"""
        if self._bone_timer is not None:
            self._bone_timer.stop()
            self._bone_timer = None
        self._overlay.set_bone_data([])
        self._overlay.set_bone_connections([])
        self._btn_bone_start.setEnabled(True)
        self._btn_bone_stop.setEnabled(False)
        self._lbl_bone_status.setText("已停止")

    def _bone_tick(self) -> None:
        """定时读取骨骼数据并更新叠加层。"""
        if self._reader is None:
            self._on_bone_stop()
            return
        try:
            base = int(self._bone_base_addr.text().strip(), 16)
        except ValueError:
            self._on_bone_stop()
            return

        count = self._bone_count.value()
        stride = self._bone_stride.value()

        # 视图矩阵
        view_mat = None
        mat_str = self._bone_mat_addr.text().strip()
        if mat_str:
            try:
                raw = self._reader.read_floats(int(mat_str, 16), 16)
                if any(abs(v) > 1e10 for v in raw):
                    self._on_bone_stop()
                    QMessageBox.warning(self, "提示", "视图矩阵数据异常，已停止")
                    return
                view_mat = np.array(raw, dtype=np.float64).reshape(4, 4)
            except Exception:
                return

        # 读取坐标
        points_data = []
        for idx in range(count):
            try:
                raw = self._reader.read_floats(base + idx * stride, 3)
                points_data.append({"index": idx, "x": float(raw[0]), "y": float(raw[1]), "z": float(raw[2])})
            except Exception:
                continue
        if not points_data:
            return

        from core.bone_reader import project_points
        proj = project_points(points_data, view_mat, MulDirection.VEC_MUL_M, self._projector)
        visible = [p for p in proj if p["visible"]]
        pts = [(p["index"], float(p["screen_x"]), float(p["screen_y"])) for p in visible]

        # 编号（受单独开关控制）
        if self._chk_bone_visible.isChecked():
            self._overlay.set_bone_data(pts, self._parse_hidden_indices())
        else:
            self._overlay.set_bone_data([])

        # 连线（受单独开关控制）
        if self._chk_bone_lines.isChecked():
            self._sync_connections_to_overlay()
        else:
            self._overlay.set_bone_connections([])

        self._lbl_bone_status.setText(f"骨骼: {len(pts)}/{count} 可见")

    def _on_bone_lines_toggled(self, checked: bool) -> None:
        """连线开关：显示或隐藏连线。"""
        if checked:
            self._sync_connections_to_overlay()
        else:
            self._overlay.set_bone_connections([])

    def _sync_connections_to_overlay(self) -> None:
        """将文本中的连线同步到叠加层。"""
        conns = self._parse_conn_text()
        self._overlay.set_bone_connections(conns)

    def _parse_conn_text(self) -> list[tuple[int, int]]:
        """解析连线文本如 '1→2, 5→6, 10→15'。"""
        text = self._bone_conn_text.text().strip().replace("，", ",")
        if not text:
            return []
        conns = []
        for part in text.split(","):
            part = part.strip()
            if "→" in part:
                parts = part.split("→")
            elif "-" in part:
                parts = part.split("-")
            else:
                continue
            if len(parts) == 2:
                try:
                    a, b = int(parts[0].strip()), int(parts[1].strip())
                    conns.append((a, b))
                except ValueError:
                    continue
        return conns

    def _on_bone_apply_conn_text(self) -> None:
        """应用文本框中的连线。"""
        if self._chk_bone_lines.isChecked():
            self._sync_connections_to_overlay()

    def _on_bone_add_connection(self) -> None:
        """通过 SpinBox 添加连线。"""
        a, b = self._bone_conn_from.value(), self._bone_conn_to.value()
        if a == b:
            QMessageBox.warning(self, "提示", "起点和终点不能相同")
            return
        existing = set()
        for pair in self._parse_conn_text():
            existing.add((pair[0], pair[1]))
        if (a, b) in existing or (b, a) in existing:
            QMessageBox.warning(self, "提示", "该连线已存在")
            return
        text = self._bone_conn_text.text().strip()
        suffix = f"{a}→{b}"
        if text:
            text += ", " + suffix
        else:
            text = suffix
        self._bone_conn_text.setText(text)
        self._on_bone_apply_conn_text()

    def _on_bone_font_size_changed(self, size: int) -> None:
        self._lbl_bone_font_preview.setStyleSheet(
            f"font-size:{size}px;font-family:Consolas;background:#333;color:#fff;padding:2px 6px;border-radius:3px;"
        )
        self._lbl_bone_font_preview.setText(str(size))
        self._overlay.set_bone_font_size(size)

    def _pick_color(self, target: str) -> None:
        """弹出颜色选择器。"""
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        if target == "num":
            self._bone_num_color = color
            self._btn_bone_num_color.setStyleSheet(f"background:{color.name()};border:1px solid #888;")
            self._overlay._bone_font_color = color
            self._overlay.update()
        else:
            self._bone_line_color = color
            self._btn_bone_line_color.setStyleSheet(f"background:{color.name()};border:1px solid #888;")
            self._overlay._line_color = color
            self._overlay.update()

    def _parse_hidden_indices(self) -> set[int]:
        text = self._bone_filter_input.text().strip()
        if not text:
            return set()
        hidden = set()
        for part in text.replace("，", ",").split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    start, end = int(a.strip()), int(b.strip())
                    hidden.update(range(min(start, end), max(start, end) + 1))
                except ValueError:
                    continue
            else:
                try:
                    hidden.add(int(part))
                except ValueError:
                    continue
        return hidden

    def _on_bone_apply_filter(self) -> None:
        self._overlay.set_bone_hidden(self._parse_hidden_indices())

    def _on_bone_clear_filter(self) -> None:
        self._bone_filter_input.clear()
        self._overlay.set_bone_hidden(set())

    # ==================================================================
    # UI 状态更新
    # ==================================================================
    def _update_ui_state(self) -> None:
        attached = self._pm.is_attached
        has_active = self._filter.active_count > 0
        self._btn_enumerate.setEnabled(attached)
        self._btn_undo.setEnabled(self._filter.can_undo)
        self._btn_reset_pool.setEnabled(has_active)
        self._btn_tl.setEnabled(attached and has_active)
        self._btn_tr.setEnabled(attached and has_active)
        self._btn_bl.setEnabled(attached and has_active)
        self._btn_br.setEnabled(attached and has_active)
        self._chk_realtime.setEnabled(self._selected_scheme is not None)
        self._btn_drag.setEnabled(not self._drag_picking)  # 拖拽中禁用

        self._lbl_count.setText(
            f"存活方案: {self._filter.active_count} / 总 {self._filter.total_count}"
        )

    def _refresh_result_table(self) -> None:
        schemes = self._filter.active_schemes
        selected_id = self._selected_scheme.scheme_id if self._selected_scheme else None
        self._result_table.update_schemes(schemes, selected_id)

    def _set_status(self, msg: str) -> None:
        self._lbl_status.setText(msg)
        log.info(msg)

    # ==================================================================
    # 清理
    # ==================================================================
    def closeEvent(self, event) -> None:  # noqa: N802
        self._on_bone_stop()
        self._stop_realtime()
        self._stop_window_tracking()
        self._overlay.close()
        try:
            self._pm.detach()
        except Exception:  # noqa: BLE001
            pass
        self._config.save()
        super().closeEvent(event)
