"""The project screen: phases and sub-steps on the left, the step in the middle, diagnostics on
the right, the validation log and the footer below (TECH_SPECS §14.1, docs/ui/)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mimufs.core.project import ImportOutcome, Project, ProjectError, ReportState
from mimufs.core.validation.info import build_card
from mimufs.core.validation.result import Status
from mimufs.gui import strings_pt as S
from mimufs.gui.panes import GatePage, LockedPage, ProjectPage, ValidationPane
from mimufs.gui.report_page import ReportPage
from mimufs.gui.status import color, locked_icon, look, status_icon
from mimufs.gui.widgets import FitScrollArea, LogPanel, StatusPill, label
from mimufs.gui.workers import Worker, WorkerPool

ROLE = Qt.ItemDataRole.UserRole
Key = tuple[str, ...]  # ("project",) ("report", code) ("gate",) ("locked", "03", n) ("phase", "02")


def phase_status(states: Sequence[ReportState]) -> Status:
    """Phase 02: 🟢 when every report passes; 🔴 on any error; ⚪ before the first import."""
    if all(s.passes for s in states) and any(s.files for s in states):
        return Status.VALID
    if any(s.status is Status.ERROR for s in states):
        return Status.ERROR
    if any(s.files for s in states):
        return Status.WARNING
    return Status.PENDING


def is_done(state: ReportState) -> bool:
    return state.status in (Status.VALID, Status.SKIPPED) or state.acknowledged


def progress_text(states: Sequence[ReportState]) -> str:
    return S.RECENT_PROGRESS.format(done=sum(is_done(s) for s in states), total=len(states))


class ProjectView(QWidget):
    progress_changed = Signal(str)

    def __init__(self, project: Project, workers: WorkerPool | None = None,
                 parent: QWidget | None = None) -> None:  # fmt: skip
        super().__init__(parent)
        self.project = project
        self.workers = workers or WorkerPool()
        self.states: dict[str, ReportState] = {}
        self.items: dict[Key, QTreeWidgetItem] = {}
        self.steps: dict[str, list[Key]] = {}  # phase number -> its sub-steps, in order
        self.headers: list[QTreeWidgetItem] = []  # group titles in phase 02
        self.current: Key = ("project",)
        self.last_outcomes: list[ImportOutcome] = []
        self.last_target = ""  # the report page the last import was dropped on ("" = gate)
        self.busy = False
        self.gate_passes = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)
        self._build_nav()
        self.refresh()
        self.select(self._first_report_key())

    # ------------------------------------------------------------------------ layout

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(296)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        header = QFrame()
        header.setObjectName("ProjectHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(16, 16, 16, 14)
        head.setSpacing(2)
        head.addWidget(label(S.PROJECT_KICKER, "kicker"))
        self.title = label("", "h3")
        self.doctor = label("", "small")
        self.description = label("", "small", wrap=True)
        for widget in (self.title, self.doctor, self.description):
            head.addWidget(widget)
        lay.addWidget(header)
        self.nav = QTreeWidget()
        self.nav.setObjectName("PhaseNav")
        self.nav.setColumnCount(2)
        self.nav.setHeaderHidden(True)
        self.nav.setIndentation(14)
        self.nav.setRootIsDecorated(True)
        self.nav.setUniformRowHeights(True)
        self.nav.itemSelectionChanged.connect(self._nav_selected)
        lay.addWidget(self.nav, 1)
        self.counts = label("", name="NavCounts")
        self.counts.setContentsMargins(16, 8, 16, 10)
        lay.addWidget(self.counts)
        return side

    def _build_main(self) -> QWidget:
        main = QWidget()
        lay = QVBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(20, 10, 20, 10)
        self.breadcrumb = label("", name="Breadcrumb")
        self.pill = StatusPill()
        top_layout.addWidget(self.breadcrumb, 1)
        top_layout.addWidget(self.pill)
        lay.addWidget(top)

        self.stack = QStackedWidget()
        self.project_page = ProjectPage()
        self.project_page.save_requested.connect(self._save_info)
        self.report_page = ReportPage()
        self.report_page.import_requested.connect(self.import_paths)
        self.report_page.remove_requested.connect(self._remove_file)
        self.report_page.skip_requested.connect(self._skip)
        self.gate_page = GatePage()
        self.gate_page.open_report.connect(lambda code: self.select(("report", code)))
        self.gate_page.acknowledge_requested.connect(self._acknowledge)
        self.gate_page.skip_requested.connect(self._skip)
        self.gate_page.import_requested.connect(self.import_paths)
        self.locked_page = LockedPage()
        self.scrolls: dict[QWidget, FitScrollArea] = {}
        for page in (self.project_page, self.report_page, self.gate_page, self.locked_page):
            area = FitScrollArea(page)
            self.scrolls[page] = area
            self.stack.addWidget(area)
        content = self.stack

        self.pane = ValidationPane()
        self.pane.acknowledge_requested.connect(self._acknowledge)
        pane_scroll = FitScrollArea(self.pane)
        pane_scroll.setMinimumWidth(340)
        self.pane_scroll = pane_scroll

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(content)
        splitter.addWidget(pane_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([680, 420])
        splitter.setChildrenCollapsible(False)
        lay.addWidget(splitter, 1)

        self.log = LogPanel()
        lay.addWidget(self.log)
        footer = QFrame()
        footer.setObjectName("Footer")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(20, 10, 20, 10)
        self.previous = QPushButton(S.PREVIOUS)
        self.previous.clicked.connect(lambda: self._step(-1))
        self.position = label("", name="FooterText")
        self.next = QPushButton(S.NEXT)
        self.next.setProperty("variant", "primary")
        self.next.clicked.connect(lambda: self._step(+1))
        foot.addWidget(self.previous)
        foot.addWidget(self.position)
        foot.addStretch(1)
        foot.addWidget(self.next)
        lay.addWidget(footer)
        return main

    def _build_nav(self) -> None:
        self.nav.clear()
        self.items = {}
        self.steps = {}
        self.headers = []
        groups: dict[str, list[str]] = {}
        for code, spec in self.project.specs.items():
            groups.setdefault(spec.group, []).append(code)
        order = [g for g in S.GROUP_ORDER if g in groups] + [
            g for g in groups if g not in S.GROUP_ORDER
        ]
        bold = QFont()
        bold.setBold(True)
        for number, name in S.PHASES:
            phase = QTreeWidgetItem(self.nav, [f"{number}  {name}", ""])
            phase.setData(0, ROLE, ("phase", number))
            phase.setFont(0, bold)
            phase.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.items[("phase", number)] = phase
            if number == "01":
                self._leaf(phase, ("project",), S.PHASE_SUBSTEPS["01"][0])
            elif number == "02":
                for group in order:
                    header = QTreeWidgetItem(phase, [group.upper(), ""])
                    header.setFlags(Qt.ItemFlag.NoItemFlags)
                    small = QFont()
                    small.setPointSizeF(max(small.pointSizeF() - 2, 7))
                    small.setBold(True)
                    header.setFont(0, small)
                    header.setData(0, ROLE, ("header", group))
                    self.headers.append(header)
                    for code in groups[group]:
                        self._leaf(phase, ("report", code), self.project.specs[code].nav_title)
                self._leaf(phase, ("gate",), S.GATE)
            else:
                for n, sub in enumerate(S.PHASE_SUBSTEPS.get(number, ())):
                    self._leaf(phase, ("locked", number, str(n)), sub)
        self.nav.expandItem(self.items[("phase", "02")])
        self.nav.resizeColumnToContents(1)
        self.nav.header().setStretchLastSection(False)
        self.nav.header().setSectionResizeMode(0, self.nav.header().ResizeMode.Stretch)

    def _leaf(self, parent: QTreeWidgetItem, key: Key, text: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [text, ""])
        item.setData(0, ROLE, key)
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.items[key] = item
        self.steps.setdefault(self.phase_of(key), []).append(key)
        return item

    # ------------------------------------------------------------------------ state

    def substeps(self, phase: str) -> list[Key]:
        return self.steps.get(phase, [])

    def phase_of(self, key: Key) -> str:
        if key[0] == "project":
            return "01"
        if key[0] in ("report", "gate"):
            return "02"
        return key[1]

    def _first_report_key(self) -> Key:
        return self.substeps("02")[0]

    def refresh(self) -> None:
        """Re-read the project and update every visible part."""
        info = self.project.info
        self.title.setText(info.title)
        self.doctor.setText(S.PROJECT_DOCTOR.format(doctor=info.doctor) if info.doctor else "")
        self.description.setText(info.description)
        self.states = self.project.overview()
        states = list(self.states.values())
        self.gate_passes = all(s.passes for s in states) and any(s.files for s in states)
        muted = QBrush(QColor(color("muted")))
        for key, item in self.items.items():
            if key[0] == "report":
                state = self.states[key[1]]
                item.setIcon(0, status_icon(state.status))
                item.setText(1, f"{state.filled}/{len(state.slots)}")
                item.setToolTip(0, f"{state.code} · {look(state.status).label}")
            elif key[0] == "gate":
                item.setIcon(0, status_icon(Status.VALID if self.gate_passes else Status.PENDING))
            elif key[0] == "project":
                item.setIcon(0, status_icon(Status.VALID))
            elif key[0] == "locked":
                item.setIcon(0, locked_icon())
                item.setForeground(0, muted)
            elif key[0] == "phase":
                number = key[1]
                if number == "01":
                    item.setIcon(0, status_icon(Status.VALID))
                elif number == "02":
                    item.setIcon(0, status_icon(phase_status(states)))
                    item.setText(1, f"{sum(is_done(s) for s in states)} / {len(states)}")
                else:
                    item.setIcon(0, locked_icon())
        for header in self.headers:
            header.setForeground(0, muted)
        counts = dict.fromkeys(("ok", "warn", "err", "pending"), 0)
        for s in states:
            if s.status is Status.ERROR:
                counts["err"] += 1
            elif s.status is Status.WARNING and not s.acknowledged:
                counts["warn"] += 1
            elif is_done(s):
                counts["ok"] += 1
            else:
                counts["pending"] += 1
        self.counts.setText(S.COUNTS_FOOTER.format(**counts))
        self.log.set_events(self.project.events())
        self.log.refresh_theme()
        self.progress_changed.emit(progress_text(states))
        self.show_step(self.current)

    # --------------------------------------------------------------------- navigation

    def select(self, key: Key) -> None:
        item = self.items.get(key)
        if item is None:
            return
        self.current = key
        parent = item.parent()
        if parent is not None:
            parent.setExpanded(True)
        self.nav.blockSignals(True)
        self.nav.setCurrentItem(item)
        self.nav.blockSignals(False)
        self.show_step(key)

    def _nav_selected(self) -> None:
        items = self.nav.selectedItems()
        if items:
            key = cast(Key, items[0].data(0, ROLE))
            if key and key[0] not in ("phase", "header"):
                self.current = key
                self.show_step(key)

    def show_step(self, key: Key) -> None:
        info = self.project.info
        phase = self.phase_of(key)
        phase_name = dict(S.PHASES)[phase]
        crumbs = [f"{phase} {phase_name}"]
        rejected = [o for o in self.last_outcomes if o.file_id is None]
        self.pane_scroll.setVisible(key[0] != "gate" or bool(rejected))
        if key[0] == "project":
            self.project_page.show_info(info, self.project.folder)
            self._show_page(self.project_page)
            self.pill.set_status(Status.VALID)
            self.pane.show_message(S.METADATA, str(self.project.db_path))
            crumbs.append(S.PHASE_SUBSTEPS["01"][0])
        elif key[0] == "report":
            state = self.states[key[1]]
            self.report_page.show_report(state, info.unit, info.years)
            self._show_page(self.report_page)
            self.pill.set_status(state.status)
            card = build_card(self.project, state)
            dropped_here = self.last_target == state.code
            mine = [o for o in rejected if dropped_here or o.code in (None, state.code)]
            self.pane.show_report(state, card, mine)
            crumbs += [state.spec.group, state.code]
        elif key[0] == "gate":
            self.gate_page.show_overview(list(self.states.values()))
            self._show_page(self.gate_page)
            self.pill.set_status(Status.VALID if self.gate_passes else Status.WARNING)
            if rejected:
                self.pane.show_rejected(rejected)
            else:
                self.pane.show_message(S.GATE_TITLE, S.GATE_BODY)
            crumbs.append(S.GATE)
        else:
            title = S.PHASE_SUBSTEPS.get(phase, ("",))[int(key[2])] if len(key) > 2 else phase_name
            self.locked_page.show_phase(title)
            self._show_page(self.locked_page)
            self.pill.set_status(Status.PENDING, S.STATUS_LOCKED)
            self.pane.show_message(S.PHASE_LOCKED_TITLE, S.PHASE_LOCKED_BODY)
            crumbs.append(title)
        self.breadcrumb.setText("  ›  ".join(crumbs))
        self.pane_scroll.refit_later()
        self._update_footer()

    def _show_page(self, page: QWidget) -> None:
        area = self.scrolls[page]
        self.stack.setCurrentWidget(area)
        area.refit_later()

    def _update_footer(self) -> None:
        phase = self.phase_of(self.current)
        steps = self.substeps(phase)
        index = steps.index(self.current) if self.current in steps else 0
        self.position.setText(S.SUBSTEP_OF.format(n=index + 1, total=len(steps)))
        self.previous.setEnabled(index > 0 or phase != "01")
        at_end = index == len(steps) - 1
        if phase == "02" and at_end:
            self.next.setEnabled(self.gate_passes)
        else:
            self.next.setEnabled(not (at_end and phase == "06"))

    def _step(self, delta: int) -> None:
        phase = self.phase_of(self.current)
        steps = self.substeps(phase)
        index = steps.index(self.current) if self.current in steps else 0
        target = index + delta
        if 0 <= target < len(steps):
            self.select(steps[target])
            return
        numbers = [n for n, _ in S.PHASES]
        neighbour = numbers.index(phase) + (1 if delta > 0 else -1)
        if 0 <= neighbour < len(numbers):
            other = self.substeps(numbers[neighbour])
            self.select(other[0] if delta > 0 else other[-1])

    # --------------------------------------------------------------------- actions

    def import_paths(self, paths: list[Path], code: str = "") -> None:
        if self.busy or not paths:
            return
        self.busy = True
        self.last_target = code
        self._set_busy(S.DROP_BUSY.format(name=paths[0].name))
        started = time.perf_counter()
        worker = Worker(self.project.import_paths, paths, code or None, with_progress=True)
        worker.signals.progress.connect(
            lambda _pct, name: self._set_busy(S.DROP_BUSY.format(name=name)) if name else None
        )
        self.workers.start(
            worker,
            on_finished=lambda outcomes: self._imported(outcomes, time.perf_counter() - started),
            on_failed=self._import_failed,
        )

    def _set_busy(self, text: str | None) -> None:
        self.report_page.set_busy(text)
        self.gate_page.set_busy(text)

    def _imported(self, outcomes: Any, seconds: float) -> None:
        self.busy = False
        self._set_busy(None)
        self.last_outcomes = list(outcomes)
        files = len(self.last_outcomes)
        self.log.set_summary(
            S.LOG_SUMMARY.format(files=files, seconds=f"{seconds:.1f}".replace(".", ","))
        )
        self.refresh()

    def _import_failed(self, exc: BaseException) -> None:
        self.busy = False
        self._set_busy(None)
        QMessageBox.warning(self, S.IMPORT_DIALOG, f"{type(exc).__name__}")
        self.refresh()

    def _remove_file(self, file_id: int) -> None:
        self.project.remove_file(file_id)
        self.last_outcomes = []
        self.refresh()

    def _acknowledge(self, code: str) -> None:
        try:
            self.project.acknowledge(code)
        except ProjectError as exc:
            QMessageBox.warning(self, S.ACKNOWLEDGE, str(exc))
        self.refresh()

    def _skip(self, code: str, skipped: bool) -> None:
        try:
            self.project.set_skipped(code, skipped)
        except ProjectError as exc:
            QMessageBox.warning(self, S.SKIP_REPORT, str(exc))
        self.refresh()

    def _save_info(self, unit: str, doctor: str, description: str) -> None:
        try:
            self.project.update_info(unit=unit, doctor=doctor, description=description)
        except ProjectError as exc:
            QMessageBox.warning(self, S.PROJECT_PAGE_TITLE, str(exc))
            return
        self.refresh()
        self.project_page.saved.setText(S.SAVED)

    @property
    def progress(self) -> str:
        return progress_text(list(self.states.values()))

    def refresh_theme(self) -> None:
        self.refresh()
