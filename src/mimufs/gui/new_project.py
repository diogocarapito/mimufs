"""The "Novo projeto" dialog (PRD §6.2, mockup docs/ui/mimufs-ui-v2-new-project-dark.png)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import platformdirs
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mimufs.core.project import ProjectInfo, default_name
from mimufs.gui import strings_pt as S
from mimufs.gui.iconset import pixmap
from mimufs.gui.status import color
from mimufs.gui.widgets import label, restyle


def default_parent() -> Path:
    return Path(platformdirs.user_documents_dir()) / "mimufs"


def year_options(today: date | None = None) -> list[tuple[str, tuple[int, ...]]]:
    """Previous year first (the default), then older years and 2-year ranges (max 2 years)."""
    year = (today or date.today()).year
    options: list[tuple[str, tuple[int, ...]]] = [
        (str(y), (y,)) for y in (year - 1, year, year - 2, year - 3)
    ]
    options += [(S.FIELD_YEARS_TWO.format(a=y - 1, b=y), (y - 1, y)) for y in (year - 1, year)]
    return options


class NewProjectDialog(QDialog):
    def __init__(self, doctor: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NewProjectDialog")
        self.setWindowTitle(S.NEW_PROJECT_TITLE)
        self.setModal(True)
        self.setMinimumWidth(560)
        self.result_info: ProjectInfo | None = None
        self.result_folder: Path | None = None
        self._folder_edited = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(6)
        layout.addWidget(label(S.NEW_PROJECT_TITLE, "h2"))
        layout.addWidget(label(S.NEW_PROJECT_SUBTITLE, "muted", wrap=True))
        layout.addSpacing(10)

        self.unit = QLineEdit()
        self.unit_error = label("", "error")
        self._field(layout, S.FIELD_UNIT, self.unit, self.unit_error, S.FIELD_UNIT_HELP)
        self.doctor = QLineEdit(doctor)
        self.doctor_error = label("", "error")
        self._field(layout, S.FIELD_DOCTOR, self.doctor, self.doctor_error, S.FIELD_DOCTOR_HELP)
        self.description = QPlainTextEdit()
        self.description.setFixedHeight(64)
        self._field(layout, S.FIELD_DESCRIPTION, self.description, None, None)

        row = QHBoxLayout()
        row.setSpacing(12)
        year_box = QVBoxLayout()
        year_box.addWidget(label(S.FIELD_YEAR, "h3"))
        self.year = QComboBox()
        for text, years in year_options():
            self.year.addItem(text, years)
        year_box.addWidget(self.year)
        row.addLayout(year_box, 1)
        folder_box = QVBoxLayout()
        folder_box.addWidget(label(S.FIELD_FOLDER, "h3"))
        folder_row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.textEdited.connect(self._mark_folder_edited)
        choose = QPushButton(S.CHOOSE_FOLDER)
        choose.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(choose)
        folder_box.addLayout(folder_row)
        row.addLayout(folder_box, 3)
        layout.addSpacing(4)
        layout.addLayout(row)

        warning = QHBoxLayout()
        warning.setSpacing(8)
        self.warning_icon = QLabel()
        self.warning_icon.setPixmap(pixmap("alert-triangle", color("warn"), 16))
        warning.addWidget(self.warning_icon, 0, Qt.AlignmentFlag.AlignTop)
        warning.addWidget(label(S.FOLDER_WARNING, "small", wrap=True), 1)
        layout.addSpacing(10)
        layout.addLayout(warning)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addSpacing(8)
        layout.addWidget(line)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(S.CANCEL)
        cancel.clicked.connect(self.reject)
        self.create_button = QPushButton(S.CREATE_PROJECT)
        self.create_button.setProperty("variant", "primary")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._create)
        buttons.addWidget(cancel)
        buttons.addWidget(self.create_button)
        layout.addLayout(buttons)

        self.unit.textChanged.connect(self._update_folder)
        self.year.currentIndexChanged.connect(self._update_folder)
        self._update_folder()
        self.unit.setFocus()

    def _field(self, layout: QVBoxLayout, title: str, widget: QWidget,
               error: QLabel | None, help_text: str | None) -> None:  # fmt: skip
        layout.addSpacing(6)
        layout.addWidget(label(title, "h3"))
        layout.addWidget(widget)
        if error is not None:
            error.setVisible(False)
            layout.addWidget(error)
        if help_text:
            layout.addWidget(label(help_text, "small", wrap=True))

    @property
    def years(self) -> tuple[int, ...]:
        data = self.year.currentData()
        return tuple(data) if data else (date.today().year - 1,)

    def _mark_folder_edited(self) -> None:
        self._folder_edited = True

    def _update_folder(self) -> None:
        if self._folder_edited:
            return
        name = default_name(self.unit.text().strip() or "USF", self.years)
        self.folder.setText(str(default_parent() / name))

    def _choose_folder(self) -> None:
        start = str(default_parent())
        chosen = QFileDialog.getExistingDirectory(self, S.FIELD_FOLDER, start)
        if chosen:
            name = default_name(self.unit.text().strip() or "USF", self.years)
            self.folder.setText(str(Path(chosen) / name))
            self._folder_edited = True

    def _show_error(self, widget: QLineEdit, error: QLabel, text: str) -> None:
        widget.setProperty("invalid", bool(text))
        restyle(widget)
        error.setText(text)
        error.setVisible(bool(text))

    def validate(self) -> bool:
        unit_ok = bool(self.unit.text().strip())
        doctor_ok = bool(self.doctor.text().strip())
        self._show_error(self.unit, self.unit_error, "" if unit_ok else S.FIELD_UNIT_REQUIRED)
        self._show_error(
            self.doctor, self.doctor_error, "" if doctor_ok else S.FIELD_DOCTOR_REQUIRED
        )
        return unit_ok and doctor_ok and bool(self.folder.text().strip())

    def _create(self) -> None:
        if not self.validate():
            return
        self.result_info = ProjectInfo(
            unit=self.unit.text().strip(),
            doctor=self.doctor.text().strip(),
            years=self.years,
            description=self.description.toPlainText().strip(),
        )
        self.result_folder = Path(self.folder.text().strip()).expanduser()
        self.accept()
