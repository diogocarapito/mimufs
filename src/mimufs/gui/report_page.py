"""One report sub-step of phase 02 (PRD §6.3, mockup docs/ui/mimufs-ui-v2-dark.png, centre)."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from mimufs.core.project import ReportState
from mimufs.core.specs.loader import load_icpc_batches
from mimufs.core.specs.models import IcpcSetsSlots, MimufReportSpec
from mimufs.core.validation.result import Status
from mimufs.gui import strings_pt as S
from mimufs.gui.iconset import icon
from mimufs.gui.status import color, look, status_pixmap
from mimufs.gui.widgets import DropZone, StatusLine, clear, label, restyle

TILE_COLUMNS = 6


class SlotTile(QFrame):
    def __init__(self, title: str, status: Status, tooltip: str = "") -> None:
        super().__init__()
        self.setObjectName("SlotTile")
        self.setMinimumWidth(96)
        lk = look(status)
        self.setProperty("state", lk.state)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        ic = QLabel()
        ic.setPixmap(status_pixmap(status, 16))
        layout.addWidget(ic)
        layout.addWidget(label(title, name="SlotTileLabel"))
        state = label(lk.label, name="SlotTileState")
        state.setProperty("state", lk.state)
        layout.addWidget(state)
        if tooltip:
            self.setToolTip(tooltip)
        restyle(self)


class ReportPage(QWidget):
    import_requested = Signal(list, str)  # paths, expected report code
    remove_requested = Signal(int)
    skip_requested = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.code = ""
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 20, 24, 24)
        self.layout_.setSpacing(10)
        self.drop = DropZone(S.DROP_TITLE, S.DROP_SUBTITLE)
        self.drop.paths_dropped.connect(lambda paths: self.import_requested.emit(paths, self.code))
        self.copy_buttons: list[QPushButton] = []

    def show_report(self, state: ReportState, unit: str, years: tuple[int, ...]) -> None:
        self.code = state.code
        spec = state.spec
        self.drop.setParent(None)
        clear(self.layout_)
        self.copy_buttons = []
        lay = self.layout_
        source = S.SOURCE_MIMUF if isinstance(spec, MimufReportSpec) else S.SOURCE_SCLINICO
        lay.addWidget(label(S.REPORT_CODE_LINE.format(code=spec.code, source=source,
                                                     level=S.LEVELS.get(spec.level, spec.level)),
                            "code"))  # fmt: skip
        lay.addWidget(label(spec.title, "title", wrap=True))
        lay.addWidget(label(spec.purpose, "muted", wrap=True))
        if not state.available:
            lay.addWidget(StatusLine(Status.PENDING, S.NOT_AVAILABLE))
        if not spec.required:
            row = QHBoxLayout()
            row.addWidget(label(S.OPTIONAL_REPORT, "small"))
            skip = QPushButton(S.UNSKIP_REPORT if state.skipped else S.SKIP_REPORT)
            skip.setProperty("variant", "link")
            skip.clicked.connect(lambda: self.skip_requested.emit(spec.code, not state.skipped))
            skip.setEnabled(not state.files)
            row.addWidget(skip)
            row.addStretch(1)
            lay.addLayout(row)

        lay.addSpacing(8)
        lay.addWidget(label(S.REQUIRED_SLOTS.format(filled=state.filled, total=len(state.slots)),
                            "section"))  # fmt: skip
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for n, slot in enumerate(state.slots):
            tile = SlotTile(slot.slot.label, slot.status, slot.slot.detail)
            grid.addWidget(tile, n // TILE_COLUMNS, n % TILE_COLUMNS)
        grid.setColumnStretch(TILE_COLUMNS, 1)
        lay.addLayout(grid)

        lay.addSpacing(8)
        steps = QFrame()
        steps.setObjectName("StepsCard")
        steps_layout = QVBoxLayout(steps)
        steps_layout.setContentsMargins(16, 14, 16, 14)
        steps_layout.setSpacing(10)
        how = S.HOW_TO_EXTRACT if isinstance(spec, MimufReportSpec) else S.HOW_TO_EXTRACT_SCLINICO
        steps_layout.addWidget(label(how, "section"))
        year_text = " e ".join(str(y) for y in years)
        for n, line in enumerate(spec.render_instructions(ano=year_text, unidade=unit), start=1):
            row = QHBoxLayout()
            row.setSpacing(14)
            row.addWidget(label(str(n), name="StepNumber"))
            row.addWidget(label(line, "body", wrap=True), 1)
            steps_layout.addLayout(row)
        lay.addWidget(steps)

        if isinstance(spec, MimufReportSpec) and isinstance(spec.slots, IcpcSetsSlots):
            lay.addWidget(self._icpc_helper(spec.slots.sets_file))

        lay.addSpacing(6)
        lay.addWidget(self.drop)
        self.drop.refresh_theme()

        if state.files:
            lay.addSpacing(6)
            lay.addWidget(label(S.FILES_HEADER.format(n=len(state.files)), "section"))
            labels = {s.slot.key: s.slot.label for s in state.slots}
            for f in state.files:
                row = QHBoxLayout()
                slots = ", ".join(labels.get(k, k) for k in f.slot_keys) or f.period or "—"
                text = f"{f.original_name} · " + S.FILE_LINE.format(slots=slots, rows=f.n_rows)
                row.addWidget(StatusLine(f.status, text), 1)
                remove = QPushButton(S.REMOVE_FILE)
                remove.setIcon(icon("trash", color("muted"), 14))
                remove.clicked.connect(
                    lambda _=False, f=f: self._confirm_remove(f.file_id, f.original_name)
                )
                row.addWidget(remove)
                lay.addLayout(row)
        lay.addStretch(1)

    def _icpc_helper(self, sets_file: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("StepsCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(label(S.ICPC_HELPER, "section"))
        for batch in load_icpc_batches(sets_file).batches:
            row = QHBoxLayout()
            text = S.ICPC_BATCH.format(
                n=batch.n, first=batch.first, last=batch.last, count=batch.unique
            )
            texts = QVBoxLayout()
            texts.setSpacing(0)
            texts.addWidget(label(text, "body"))
            preview = ", ".join(batch.codes[:12]) + ", …"
            texts.addWidget(label(preview, "mono-muted"))
            row.addLayout(texts, 1)
            button = QPushButton(S.COPY_CODES)
            button.setIcon(icon("copy", color("text"), 14))
            paste = batch.paste_text()
            button.clicked.connect(lambda _=False, b=button, p=paste: self._copy(b, p))
            self.copy_buttons.append(button)
            row.addWidget(button)
            layout.addLayout(row)
        return frame

    def _copy(self, button: QPushButton, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        button.setText(S.COPIED)
        QTimer.singleShot(1800, lambda: self._restore(button))

    @staticmethod
    def _restore(button: QPushButton) -> None:
        if isValid(button):  # the page may have been rebuilt meanwhile
            button.setText(S.COPY_CODES)

    def _confirm_remove(self, file_id: int, name: str) -> None:
        answer = QMessageBox.question(self, S.REMOVE_FILE, S.REMOVE_CONFIRM.format(name=name))
        if answer == QMessageBox.StandardButton.Yes:
            self.remove_requested.emit(file_id)

    def set_busy(self, text: str | None) -> None:
        self.drop.set_busy(text)
