"""复用控件（§9.1）。

- AddressInputWidget: 地址输入文本框，校验/标红/去重
- SchemeResultTable: 方案结果表，地址/描述/状态/选用
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.scheme import MatrixScheme


def parse_hex_address(line: str) -> Optional[int]:
    """解析单行十六进制地址；非法返回 None（§2 数值约定）。"""
    line = line.strip()
    if not line:
        return None
    if line.lower().startswith("0x"):
        line = line[2:]
    if not line:
        return None
    try:
        return int(line, 16)
    except ValueError:
        return None


class AddressInputWidget(QWidget):
    """地址输入控件：文本框 + 校验 + 去重 + 状态计数。

    信号:
        sig_addresses_changed(list[int]): 合法地址列表变化（已去重，保持输入顺序）
    """

    sig_addresses_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._valid_addresses: list[int] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("地址列表（一行一个十六进制地址，可带/不带 0x）")
        layout.addWidget(self._label)

        self._text = QTextEdit()
        self._text.setPlaceholderText("0x23F28408D80\n0x23F28408E88\n...")
        self._text.textChanged.connect(self._revalidate)
        layout.addWidget(self._text)

        # 按钮行
        btn_row = QHBoxLayout()
        self._btn_paste = QPushButton("粘贴")
        self._btn_paste.clicked.connect(self._paste_from_clipboard)
        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self._clear)
        self._btn_load = QPushButton("加载文件")
        self._btn_load.clicked.connect(self._load_from_file)
        self._status = QLabel("0 个地址")
        btn_row.addWidget(self._btn_load)
        btn_row.addWidget(self._btn_paste)
        btn_row.addWidget(self._btn_clear)
        btn_row.addStretch()
        btn_row.addWidget(self._status)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    def _revalidate(self) -> None:
        """逐行校验：合法行正常显示，非法行标红忽略，自动去重。"""
        text = self._text.toPlainText()
        lines = text.split("\n")

        # 收集合法地址（去重保持顺序）
        seen: set[int] = set()
        valid: list[int] = []
        line_is_valid: list[bool] = []

        for line in lines:
            addr = parse_hex_address(line)
            if addr is not None and addr not in seen:
                seen.add(addr)
                valid.append(addr)
                line_is_valid.append(True)
            elif addr is not None and addr in seen:
                # 重复地址，行视为有效但不再加入
                line_is_valid.append(True)
            elif line.strip() == "":
                line_is_valid.append(True)  # 空行不标红
            else:
                line_is_valid.append(False)

        self._valid_addresses = valid
        self._status.setText(f"{len(valid)} 个地址")
        self._highlight_invalid(lines, line_is_valid)

        self.sig_addresses_changed.emit(valid)

    def _highlight_invalid(
        self, lines: list[str], line_is_valid: list[bool]
    ) -> None:
        """高亮非法行（标红）。阻塞 textChanged 信号避免递归。"""
        cursor = self._text.textCursor()
        self._text.blockSignals(True)
        try:
            for i, (line, ok) in enumerate(zip(lines, line_is_valid)):
                fmt = QTextCharFormat()
                if not ok:
                    fmt.setForeground(QColor(255, 80, 80))
                # 选中该行并应用格式
                block = self._text.document().findBlockByNumber(i)
                if block.isValid():
                    sel = QTextCursor(block)
                    sel.select(QTextCursor.SelectionType.LineUnderCursor)
                    sel.setCharFormat(fmt)
        finally:
            self._text.blockSignals(False)
            self._text.setTextCursor(cursor)

    # ------------------------------------------------------------------
    def get_addresses(self) -> list[int]:
        return list(self._valid_addresses)

    def set_addresses(self, addresses: list[int]) -> None:
        text = "\n".join(f"0x{a:X}" for a in addresses)
        self._text.setPlainText(text)

    def _paste_from_clipboard(self) -> None:
        from PySide6.QtWidgets import QApplication

        clip = QApplication.clipboard()
        text = clip.text()
        if text:
            current = self._text.toPlainText()
            if current and not current.endswith("\n"):
                current += "\n"
            self._text.setPlainText(current + text)

    def _clear(self) -> None:
        self._text.clear()

    def _load_from_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "选择地址文件", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._text.setPlainText(f.read())
        except OSError as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "加载失败", f"读取文件失败: {exc}")


class SchemeResultTable(QWidget):
    """方案结果表：地址 / 方案描述 / 操作（仅显示存活方案）。

    信号:
        sig_scheme_selected(str): 用户选用某 scheme_id
        sig_scheme_preview(str): 用户预览某 scheme_id
        sig_scheme_delete(str): 用户手动删除某 scheme_id
    """

    sig_scheme_selected = Signal(str)
    sig_scheme_preview = Signal(str)
    sig_scheme_delete = Signal(str)
    sig_item_copied = Signal(str)  # 右键复制内容后通知主窗口显示状态

    COLUMNS = ["地址", "方案描述", "操作"]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("结果表")
        layout.addWidget(self._label)

        self._table = QTableWidget(0, len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        header = self._table.horizontalHeader()
        # 地址、方案描述可拖动，操作列 Stretch 自动填满右侧（锁定右边）
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 140)   # 地址
        self._table.setColumnWidth(1, 300)   # 方案描述
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    def update_schemes(
        self,
        schemes: list[MatrixScheme],
        selected_id: str | None = None,
    ) -> None:
        """刷新结果表（仅存活方案）。"""
        self._table.setRowCount(len(schemes))
        for row, s in enumerate(schemes):
            # 地址
            addr_text = f"0x{s.address:X}"
            addr_item = QTableWidgetItem(addr_text)
            addr_item.setData(Qt.ItemDataRole.UserRole, s.scheme_id)
            addr_item.setToolTip(f"右键复制：{addr_text}")
            self._table.setItem(row, 0, addr_item)
            # 描述
            desc_item = QTableWidgetItem(s.description)
            desc_item.setToolTip(f"右键复制：{s.description}")
            self._table.setItem(row, 1, desc_item)
            # 操作按钮
            op_widget = QWidget()
            op_layout = QHBoxLayout(op_widget)
            op_layout.setContentsMargins(2, 2, 2, 2)
            btn_select = QPushButton("选用")
            btn_select.clicked.connect(
                lambda _=False, sid=s.scheme_id: self.sig_scheme_selected.emit(sid)
            )
            btn_preview = QPushButton("预览")
            btn_preview.clicked.connect(
                lambda _=False, sid=s.scheme_id: self.sig_scheme_preview.emit(sid)
            )
            btn_delete = QPushButton("删除")
            btn_delete.setStyleSheet("color: #c00;")
            btn_delete.clicked.connect(
                lambda _=False, sid=s.scheme_id: self.sig_scheme_delete.emit(sid)
            )
            op_layout.addWidget(btn_select)
            op_layout.addWidget(btn_preview)
            op_layout.addWidget(btn_delete)
            self._table.setCellWidget(row, 2, op_widget)

            # 高亮选中行
            if selected_id == s.scheme_id:
                for col in range(len(self.COLUMNS)):
                    item = self._table.item(row, col)
                    if item:
                        item.setBackground(QColor(200, 220, 255))
                btn_select.setText("已选用")
                btn_select.setEnabled(False)

        self._label.setText(f"存活方案（{len(schemes)}）")

    def _on_context_menu(self, pos) -> None:
        """右键菜单：复制单元格内容到剪贴板。"""
        item = self._table.itemAt(pos)
        if item is None:
            return
        text = item.text()
        if not text:
            return
        menu = QMenu(self)
        copy_action = QAction(f"复制「{text}」", self)
        copy_action.triggered.connect(lambda: self._copy_text(text))
        menu.addAction(copy_action)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.sig_item_copied.emit(text)

    def _on_double_click(self, index) -> None:
        row = index.row()
        if row < 0:
            return
        addr_item = self._table.item(row, 0)
        if addr_item:
            sid = addr_item.data(Qt.ItemDataRole.UserRole)
            if sid:
                self.sig_scheme_selected.emit(sid)
