"""Dictionary manager (PRD §7.5): one tab per dictionary; medication is editable."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mimufs.core.dictionaries import KEYS, Dictionaries, DictionaryError, DictKey
from mimufs.gui import strings_pt as S
from mimufs.gui.widgets import label


class DictionaryTab(QWidget):
    def __init__(
        self, dictionaries: Dictionaries, key: DictKey, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.dictionaries = dictionaries
        self.key = key
        self.editable = key == "medicamentos"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(S.DICT_SEARCH)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.count = label("", "mono-muted")
        top.addWidget(self.count)
        lay.addLayout(top)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        if not self.editable:
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table, 1)
        self.message = label("", "small", wrap=True)
        lay.addWidget(self.message)
        if self.editable:
            buttons = QHBoxLayout()
            for text, slot in ((S.DICT_ADD, self._add), (S.DICT_DELETE, self._delete),
                               (S.DICT_IMPORT, self._import), (S.DICT_EXPORT, self._export),
                               (S.DICT_RESET, self._reset)):  # fmt: skip
                button = QPushButton(text)
                button.clicked.connect(slot)
                buttons.addWidget(button)
            buttons.addStretch(1)
            self.save = QPushButton(S.DICT_SAVE)
            self.save.setProperty("variant", "primary")
            self.save.clicked.connect(self._save)
            buttons.addWidget(self.save)
            lay.addLayout(buttons)
        else:
            self.message.setText(S.DICT_READONLY)
            export = QPushButton(S.DICT_EXPORT)
            export.clicked.connect(self._export)
            row = QHBoxLayout()
            row.addWidget(export)
            row.addStretch(1)
            lay.addLayout(row)
        self.load()

    def load(self) -> None:
        frame = self.dictionaries.table(self.key)
        self.columns = list(frame.columns)
        self.table.clear()
        self.table.setColumnCount(frame.width)
        self.table.setHorizontalHeaderLabels(frame.columns)
        self.table.setRowCount(frame.height)
        for r, row in enumerate(frame.iter_rows()):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem("" if value is None else str(value)))
        self.table.resizeColumnsToContents()
        self._filter(self.search.text())

    def frame(self) -> pl.DataFrame:
        columns = self.columns
        data: dict[str, list[str]] = {c: [] for c in columns}
        for r in range(self.table.rowCount()):
            for c, name in enumerate(columns):
                item = self.table.item(r, c)
                data[name].append(item.text() if item else "")
        return pl.DataFrame(data, schema=dict.fromkeys(columns, pl.Utf8))

    def _filter(self, text: str) -> None:
        needle = text.strip().casefold()
        shown = 0
        for r in range(self.table.rowCount()):
            cells = (self.table.item(r, c) for c in range(self.table.columnCount()))
            match = not needle or any(
                i is not None and needle in i.text().casefold() for i in cells
            )
            self.table.setRowHidden(r, not match)
            shown += match
        self.count.setText(S.DICT_ROWS.format(shown=shown, total=self.table.rowCount()))

    def _add(self) -> None:
        self.search.clear()
        row = self.table.rowCount()
        self.table.insertRow(row)
        cells = [QTableWidgetItem("") for _ in range(self.table.columnCount())]
        for c, cell in enumerate(cells):
            self.table.setItem(row, c, cell)
        self.table.scrollToBottom()
        if cells:
            self.table.editItem(cells[0])

    def _delete(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        self._filter(self.search.text())

    def _save(self) -> None:
        try:
            clean = self.dictionaries.save_medication(self.frame())
        except DictionaryError as exc:
            QMessageBox.warning(self, S.DICT_MANAGER_TITLE, str(exc))
            return
        self.load()
        self.message.setText(S.DICT_SAVED.format(n=clean.height))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, S.DICT_IMPORT, "", "CSV (*.csv)")
        if not path:
            return
        try:
            clean = self.dictionaries.import_medication(Path(path))
        except DictionaryError as exc:
            QMessageBox.warning(self, S.DICT_MANAGER_TITLE, str(exc))
            return
        self.load()
        self.message.setText(S.DICT_SAVED.format(n=clean.height))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, S.DICT_EXPORT, f"{self.key}.csv", "CSV (*.csv)")
        if path:
            self.dictionaries.export(self.key, Path(path))

    def _reset(self) -> None:
        answer = QMessageBox.question(self, S.DICT_RESET, S.DICT_RESET_CONFIRM)
        if answer == QMessageBox.StandardButton.Yes:
            self.dictionaries.reset_medication()
            self.load()
            self.message.setText("")


class DictionaryManager(QDialog):
    def __init__(self, dictionaries: Dictionaries, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.DICT_MANAGER_TITLE)
        self.resize(900, 620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        self.tabs = QTabWidget()
        self.pages: dict[DictKey, DictionaryTab] = {}
        for key in KEYS:
            page = DictionaryTab(dictionaries, key)
            self.pages[key] = page
            self.tabs.addTab(page, S.DICT_TITLES[key])
        lay.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(S.CLOSE)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
