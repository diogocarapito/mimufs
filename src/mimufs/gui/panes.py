"""Right-hand validation pane, the "Rever e continuar" gate, phase 01 and locked phases."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mimufs.core.project import ImportOutcome, ProjectInfo, ReportState
from mimufs.core.validation.info import InfoCard
from mimufs.core.validation.result import Issue, Status
from mimufs.gui import strings_pt as S
from mimufs.gui.iconset import pixmap
from mimufs.gui.status import color, look, severity_label, status_pixmap
from mimufs.gui.widgets import DropZone, StatusLine, clear, label


class IssueCard(QFrame):
    """What (bold), where (mono), how to fix it (→ hint)."""

    def __init__(self, issue: Issue) -> None:
        super().__init__()
        self.setObjectName("IssueCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(status_pixmap(issue.severity, 16))
        layout.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(label(issue.message, wrap=True, name="IssueMessage"))
        where = f"{severity_label(issue.severity)} {issue.check_id}"
        if issue.location:
            where += f" · {issue.location}"
        texts.addWidget(label(where, wrap=True, name="IssueWhere"))
        if issue.fix_hint:
            texts.addWidget(label(f"→ {issue.fix_hint}", "body", wrap=True))
        layout.addLayout(texts, 1)


class ValidationPane(QWidget):
    acknowledge_requested = Signal(str)
    doctor_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ValidationPane")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(20, 20, 20, 20)
        self.layout_.setSpacing(10)
        self.summary = ""
        self.copy_button: QPushButton | None = None
        self.doctor_buttons: list[QPushButton] = []

    def show_report(
        self,
        state: ReportState,
        card: InfoCard,
        rejected: Sequence[ImportOutcome] = (),
        doctors: Sequence[str] = (),
    ) -> None:
        """``doctors``: names to offer when the project's doctor isn't in the list (S05)."""
        clear(self.layout_)
        self.doctor_buttons = []
        lay = self.layout_
        if rejected:
            lay.addWidget(label(S.LAST_IMPORT, "section"))
            for outcome in rejected:
                for issue in outcome.issues:
                    lay.addWidget(IssueCard(issue))
            lay.addSpacing(8)
        lay.addWidget(label(S.DIAGNOSTICS, "section"))
        if not state.issues:
            lay.addWidget(label(S.NO_ISSUES, "muted"))
        for issue in state.issues:
            lay.addWidget(IssueCard(issue))
            if issue.check_id == "S05":
                for name in doctors:
                    button = QPushButton(S.USE_DOCTOR.format(name=name))
                    button.clicked.connect(lambda _=False, n=name: self.doctor_chosen.emit(n))
                    self.doctor_buttons.append(button)
                    row = QHBoxLayout()
                    row.addWidget(button)
                    row.addStretch(1)
                    lay.addLayout(row)
        if state.status is Status.WARNING:
            if state.acknowledged:
                lay.addWidget(StatusLine(Status.VALID, S.ACKNOWLEDGE_DONE))
            else:
                button = QPushButton(S.ACKNOWLEDGE)
                button.clicked.connect(lambda: self.acknowledge_requested.emit(state.code))
                row = QHBoxLayout()
                row.addWidget(button)
                row.addStretch(1)
                lay.addLayout(row)
        lay.addSpacing(10)
        head = QHBoxLayout()
        head.addWidget(label(S.METADATA, "section"))
        head.addStretch(1)
        self.copy_button = QPushButton(S.COPY_SUMMARY)
        self.copy_button.setProperty("variant", "link")
        self.summary = card.markdown()
        self.copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.summary))
        head.addWidget(self.copy_button)
        lay.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for n, (name, value) in enumerate(card.rows):
            grid.addWidget(label(name, name="InfoLabel"), n, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(label(value, "body", wrap=True), n, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addStretch(1)

    def show_rejected(self, outcomes: Sequence[ImportOutcome]) -> None:
        clear(self.layout_)
        self.layout_.addWidget(label(S.LAST_IMPORT, "section"))
        for outcome in outcomes:
            for issue in outcome.issues:
                self.layout_.addWidget(IssueCard(issue))
        self.layout_.addStretch(1)

    def show_message(self, title: str, text: str) -> None:
        clear(self.layout_)
        self.layout_.addWidget(label(title, "section"))
        self.layout_.addWidget(label(text, "muted", wrap=True))
        self.layout_.addStretch(1)


class GatePage(QWidget):
    """Phase 02's last sub-step: every report at a glance, global import, acknowledgements."""

    open_report = Signal(str)
    acknowledge_requested = Signal(str)
    skip_requested = Signal(str, bool)
    import_requested = Signal(list, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 20, 24, 24)
        self.layout_.setSpacing(10)
        self.drop = DropZone(S.IMPORT_ALL, S.IMPORT_ALL_SUBTITLE)
        self.drop.paths_dropped.connect(lambda paths: self.import_requested.emit(paths, ""))
        self.passes = False

    def show_overview(self, states: Sequence[ReportState]) -> None:
        self.drop.setParent(None)
        clear(self.layout_)
        lay = self.layout_
        lay.addWidget(label(S.GATE_TITLE, "title"))
        lay.addWidget(label(S.GATE_BODY, "muted", wrap=True))
        blocking = [s for s in states if not s.passes]
        self.passes = not blocking
        status = Status.VALID if self.passes else Status.WARNING
        text = S.GATE_READY if self.passes else S.GATE_BLOCKED.format(n=len(blocking))
        lay.addWidget(StatusLine(status, text))
        lay.addSpacing(6)
        lay.addWidget(self.drop)
        self.drop.refresh_theme()
        lay.addSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        headers = (S.COL_REPORT, S.COL_STATUS, S.COL_SLOTS, S.COL_REQUIRED)
        for col, title in enumerate(headers):
            grid.addWidget(label(title.upper(), "section"), 0, col)
        link = color("accent_text")
        for row, state in enumerate(states, start=1):
            name = QLabel(f'<a href="{state.code}" style="color:{link}">{state.spec.nav_title}</a>')
            name.setTextFormat(Qt.TextFormat.RichText)
            name.linkActivated.connect(self.open_report)
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(name)
            cell.addWidget(label(state.code, "mono-muted"))
            grid.addLayout(cell, row, 0)
            lk = look(state.status)
            status_text = lk.label + (f" · {S.STATUS_ACKNOWLEDGED}" if state.acknowledged else "")
            status_line = StatusLine(state.status, status_text)
            status_line.setMinimumWidth(130)
            grid.addWidget(status_line, row, 1)
            grid.addWidget(label(f"{state.filled}/{len(state.slots)}", "mono-muted"), row, 2)
            grid.addWidget(label(S.YES if state.spec.required else S.NO, "small"), row, 3)
            actions = QHBoxLayout()
            if state.status is Status.WARNING and not state.acknowledged:
                ack = QPushButton(S.ACKNOWLEDGE)
                ack.clicked.connect(
                    lambda _=False, c=state.code: self.acknowledge_requested.emit(c)
                )
                actions.addWidget(ack)
            if not state.spec.required and not state.files:
                skip = QPushButton(S.UNSKIP_REPORT if state.skipped else S.SKIP_REPORT)
                skip.clicked.connect(
                    lambda _=False, c=state.code, s=state.skipped: self.skip_requested.emit(
                        c, not s
                    )
                )
                actions.addWidget(skip)
            actions.addStretch(1)
            grid.addLayout(actions, row, 4)
        grid.setColumnStretch(4, 1)
        grid.setVerticalSpacing(10)
        lay.addLayout(grid)
        lay.addStretch(1)

    def set_busy(self, text: str | None) -> None:
        self.drop.set_busy(text)


class ProjectPage(QWidget):
    """Phase 01: the project's fields stay editable (PRD §6.2)."""

    save_requested = Signal(str, str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(8)
        lay.addWidget(label(S.PROJECT_PAGE_TITLE, "title"))
        lay.addWidget(label(S.PROJECT_PAGE_BODY, "muted", wrap=True))
        lay.addSpacing(8)
        self.unit = QLineEdit()
        self.doctor = QLineEdit()
        self.description = QLineEdit()
        for title, widget in ((S.FIELD_UNIT, self.unit), (S.FIELD_DOCTOR, self.doctor),
                              (S.FIELD_DESCRIPTION, self.description)):  # fmt: skip
            lay.addWidget(label(title, "h3"))
            lay.addWidget(widget)
        self.years = label("", "body")
        self.folder = label("", "mono-muted", wrap=True)
        lay.addWidget(label(S.FIELD_YEAR, "h3"))
        lay.addWidget(self.years)
        lay.addWidget(self.folder)
        row = QHBoxLayout()
        self.save = QPushButton(S.SAVE)
        self.save.setProperty("variant", "primary")
        self.save.clicked.connect(
            lambda: self.save_requested.emit(
                self.unit.text(), self.doctor.text(), self.description.text()
            )
        )
        self.saved = label("", "small")
        row.addWidget(self.save)
        row.addWidget(self.saved)
        row.addStretch(1)
        lay.addSpacing(8)
        lay.addLayout(row)
        lay.addStretch(1)

    def show_info(self, info: ProjectInfo, folder: Path) -> None:
        self.unit.setText(info.unit)
        self.doctor.setText(info.doctor)
        self.description.setText(info.description)
        self.years.setText(" e ".join(str(y) for y in info.years))
        self.folder.setText(S.PROJECT_FOLDER.format(path=folder))
        self.saved.setText("")


class LockedPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.icon = QLabel()
        head.addWidget(self.icon)
        self.title = label("", "title")
        head.addWidget(self.title, 1)
        lay.addLayout(head)
        lay.addWidget(label(S.PHASE_LOCKED_TITLE, "h3"))
        lay.addWidget(label(S.PHASE_LOCKED_BODY, "muted", wrap=True))
        lay.addStretch(1)

    def show_phase(self, title: str) -> None:
        self.title.setText(title)
        self.icon.setPixmap(pixmap("lock", color("muted"), 22))
