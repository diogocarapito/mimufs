"""A mimufs project: one folder, one DuckDB file, byte copies of every import (TECH_SPECS §4).

::

    USF_Exemplo_2024/
    ├── USF_Exemplo_2024.mimufs   # DuckDB: project info, files, issues, raw_<report> tables
    ├── raw/                      # byte-identical copies: <sha256[:12]>__<original name>
    ├── exports/
    └── logs/

Each thread gets its own long-lived connection (``connect()``), so the GUI thread and worker
threads never share one, and nothing pays DuckDB's connect cost per query. ``close()`` closes
them all (the window calls it when it switches projects).

Importing a file never changes or deletes earlier data; removing a file deletes its rows from
the project tables but keeps its byte copy in ``raw/``.

Patient data stays in this folder. Nothing here logs cell values (CLAUDE.md rule 2).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import threading
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from mimufs import __version__
from mimufs.core import db
from mimufs.core.readers import sclinico_pdf
from mimufs.core.readers.excel import FileFormat, UnreadableFileError
from mimufs.core.readers.mimuf_header import (
    HeaderParseError,
    RawSheet,
    parse_filter,
    read_mimuf_file,
)
from mimufs.core.specs import load_specs
from mimufs.core.specs.models import MimufReportSpec, MonthCoverageSlots, ReportSpec
from mimufs.core.validation import messages as M
from mimufs.core.validation.checks import check_file
from mimufs.core.validation.context import ProjectCtx
from mimufs.core.validation.result import Issue, Status, status_of, worst
from mimufs.core.validation.set_checks import (
    ReportFile,
    check_report,
    closest_doctors,
    report_doctors,
)
from mimufs.core.validation.slots import Placement, SlotDef, expected_slots

log = logging.getLogger(__name__)

SUFFIX = ".mimufs"
SCHEMA_VERSION = "1"
MAX_LOG_EVENTS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR);
CREATE SEQUENCE IF NOT EXISTS file_id_seq START 1;
CREATE TABLE IF NOT EXISTS files (
    file_id INTEGER PRIMARY KEY,
    sha256 VARCHAR NOT NULL,
    original_name VARCHAR NOT NULL,
    raw_path VARCHAR NOT NULL,
    report_code VARCHAR NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    format VARCHAR,
    sheet_name VARCHAR,
    code_source VARCHAR,
    title VARCHAR,
    title_raw VARCHAR,
    filter_text VARCHAR,
    pages VARCHAR,          -- JSON object
    has_pages BOOLEAN,
    header VARCHAR,         -- JSON list
    header2 VARCHAR,        -- JSON list or null
    columns VARCHAR,        -- JSON list of stored raw columns (c0, c1, …)
    footer VARCHAR,         -- JSON list of removed footer rows (kept for the info card)
    n_rows INTEGER,
    max_row INTEGER,
    slot_keys VARCHAR,      -- JSON list (set by validation)
    months VARCHAR,         -- JSON list
    period VARCHAR,
    status INTEGER
);
CREATE SEQUENCE IF NOT EXISTS issue_id_seq START 1;
CREATE TABLE IF NOT EXISTS issues (
    issue_id INTEGER PRIMARY KEY,
    report_code VARCHAR NOT NULL,
    file_id INTEGER,
    check_id VARCHAR NOT NULL,
    severity INTEGER NOT NULL,
    message VARCHAR NOT NULL,
    location VARCHAR,
    fix_hint VARCHAR
);
CREATE TABLE IF NOT EXISTS report_state (
    report_code VARCHAR PRIMARY KEY,
    skipped BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    ack_digest VARCHAR,
    ack_note VARCHAR
);
CREATE TABLE IF NOT EXISTS event_log (
    ts TIMESTAMP NOT NULL,
    kind VARCHAR NOT NULL,     -- "OK" or a check id
    report_code VARCHAR,
    message VARCHAR NOT NULL
);
"""


class ProjectError(Exception):
    """A project cannot be created or opened. ``str(exc)`` is PT-PT and safe to show."""


@dataclass(frozen=True)
class ProjectInfo:
    unit: str
    doctor: str
    years: tuple[int, ...]
    description: str = ""
    name: str = ""
    created_at: datetime | None = None
    app_version: str = __version__

    @property
    def title(self) -> str:
        return f"{self.unit} · {'–'.join(str(y) for y in self.years)}"


@dataclass(frozen=True)
class FileRecord:
    file_id: int
    report_code: str
    original_name: str
    sha256: str
    imported_at: datetime
    n_rows: int
    n_footer: int
    period: str
    slot_keys: tuple[str, ...]
    months: tuple[str, ...]
    status: Status
    format: str


@dataclass(frozen=True)
class ImportOutcome:
    """What happened to one dropped file (shown in the log and the diagnostics pane)."""

    name: str
    code: str | None
    file_id: int | None  # None: not stored (unreadable, unknown, wrong report)
    status: Status
    issues: tuple[Issue, ...] = ()
    slots: tuple[str, ...] = ()  # slot labels the file filled


@dataclass(frozen=True)
class SlotState:
    slot: SlotDef
    status: Status
    file_ids: tuple[int, ...]


@dataclass(frozen=True)
class ReportState:
    code: str
    spec: ReportSpec
    status: Status
    skipped: bool
    acknowledged: bool  # a WARNING the user accepted ("Continuar mesmo assim")
    files: tuple[FileRecord, ...]
    slots: tuple[SlotState, ...]
    issues: tuple[Issue, ...]  # file and report issues, worst first

    @property
    def filled(self) -> int:
        return sum(s.status not in (Status.PENDING, Status.SKIPPED) for s in self.slots)

    @property
    def available(self) -> bool:
        """False for a report the app can't import yet (SClínico, until its reader is ready)."""
        return isinstance(self.spec, MimufReportSpec) or sclinico_pdf.PDF_READER_READY

    @property
    def passes(self) -> bool:
        """Can phase 02 be left with this report as it is?"""
        if self.skipped:
            return True
        if self.status is Status.PENDING:
            return not self.spec.required or not self.available
        if self.status is Status.WARNING:
            return self.acknowledged
        return self.status is Status.VALID


def default_name(unit: str, years: Sequence[int]) -> str:
    base = re.sub(r"[^\w-]+", "_", f"{unit}_{'-'.join(str(y) for y in years)}", flags=re.UNICODE)
    return base.strip("_") or "projeto"


def _table(code: str) -> str:
    return "raw_" + re.sub(r"\W", "_", code)


def _digest(issues: Iterable[Issue]) -> str:
    text = "\n".join(sorted(f"{i.check_id}|{i.file_id}|{i.message}" for i in issues))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Project:
    """An open project. Cheap to construct; all state lives in the database file."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.folder = db_path.parent
        self.raw_dir = self.folder / "raw"
        self.exports_dir = self.folder / "exports"
        self.logs_dir = self.folder / "logs"
        self._specs = load_specs()
        self._local = threading.local()
        self._connections: list[duckdb.DuckDBPyConnection] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ create / open

    @classmethod
    def create(cls, folder: Path, info: ProjectInfo) -> Project:
        name = info.name or default_name(info.unit, info.years)
        if not info.unit.strip():
            raise ProjectError("Indique a unidade.")
        folder = folder.expanduser()
        db_path = folder / f"{name}{SUFFIX}"
        if db_path.exists():
            raise ProjectError(f"Já existe um projeto nesta pasta: {db_path.name}.")
        try:
            for sub in ("raw", "exports", "logs"):
                (folder / sub).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                f"Não foi possível criar a pasta do projeto ({exc.strerror})."
            ) from None
        project = cls(db_path)
        with project.connect() as con:
            con.execute(_SCHEMA)
            stamp = datetime.now().replace(microsecond=0)
            values = {
                "schema_version": SCHEMA_VERSION,
                "name": name,
                "unit": info.unit.strip(),
                "doctor": info.doctor.strip(),
                "description": info.description.strip(),
                "years": json.dumps(list(info.years)),
                "created_at": stamp.isoformat(),
                "app_version": __version__,
            }
            con.executemany("INSERT INTO meta VALUES (?, ?)", list(values.items()))
        log.info("project created (%d year(s))", len(info.years))
        return project

    @classmethod
    def open(cls, path: Path) -> Project:
        path = path.expanduser()
        if path.is_dir():
            found = sorted(path.glob(f"*{SUFFIX}"))
            if not found:
                raise ProjectError("Esta pasta não tem nenhum projeto do mimufs.")
            path = found[0]
        if not path.is_file():
            raise ProjectError("O ficheiro do projeto não existe.")
        project = cls(path)
        try:
            with project.connect() as con:
                rows = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchall()
                con.execute(_SCHEMA)  # newer tables, if the project predates them
        except duckdb.Error:
            raise ProjectError("O ficheiro não é um projeto do mimufs válido.") from None
        if not rows:
            raise ProjectError("O ficheiro não é um projeto do mimufs válido.")
        return project

    @contextmanager
    def connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """This thread's connection to the project database (opened on first use)."""
        con: duckdb.DuckDBPyConnection | None = getattr(self._local, "con", None)
        if con is None:
            con = db.connect(self.db_path)
            self._local.con = con
            with self._lock:
                self._connections.append(con)
        yield con

    def close(self) -> None:
        """Close every connection (all threads). The project can be used again afterwards."""
        with self._lock:
            for con in self._connections:
                with suppress(duckdb.Error):
                    con.close()
            self._connections.clear()
        self._local = threading.local()

    # ------------------------------------------------------------------------ info

    @property
    def info(self) -> ProjectInfo:
        with self.connect() as con:
            meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        created = meta.get("created_at")
        return ProjectInfo(
            unit=meta["unit"],
            doctor=meta.get("doctor", ""),
            years=tuple(json.loads(meta["years"])),
            description=meta.get("description", ""),
            name=meta.get("name", ""),
            created_at=datetime.fromisoformat(created) if created else None,
            app_version=meta.get("app_version", ""),
        )

    @property
    def ctx(self) -> ProjectCtx:
        info = self.info
        return ProjectCtx(unit=info.unit, doctor=info.doctor, years=info.years)

    def update_info(self, *, unit: str | None = None, doctor: str | None = None,
                    description: str | None = None) -> None:  # fmt: skip
        """Edit the project fields (phase 01). Unit or doctor changes re-validate everything."""
        changes = {k: v.strip() for k, v in
                   {"unit": unit, "doctor": doctor, "description": description}.items()
                   if v is not None}  # fmt: skip
        if "unit" in changes and not changes["unit"]:
            raise ProjectError("Indique a unidade.")
        with self.connect() as con:
            for key, value in changes.items():
                con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", [key, value])
        if {"unit", "doctor"} & set(changes):
            for code in self.imported_codes():
                self.revalidate(code)

    # ------------------------------------------------------------------------ specs

    @property
    def specs(self) -> dict[str, ReportSpec]:
        return self._specs

    def report_codes(self) -> list[str]:
        return list(self._specs)

    # ---------------------------------------------------------------------- import

    def import_paths(
        self,
        paths: Iterable[Path],
        expected_code: str | None = None,
        progress: Callable[[int, str], None] | None = None,
    ) -> list[ImportOutcome]:
        """Import files and folders (recursively). ``expected_code``: the report page they
        were dropped on (a file of another report is then refused with V02)."""
        files = sorted(_expand(paths))
        outcomes: list[ImportOutcome] = []
        touched: set[str] = set()
        for n, path in enumerate(files, start=1):
            if progress:
                progress(int(100 * (n - 1) / max(len(files), 1)), path.name)
            outcome = self._import_one(path, expected_code)
            outcomes.append(outcome)
            if outcome.code and outcome.file_id is not None:
                touched.add(outcome.code)
        report_issues: dict[str, list[Issue]] = {}
        for code in touched:
            issues = self.revalidate(code)
            report_issues[code] = [i for i in issues if i.file_id is None]
        final = [self._final_outcome(o) for o in outcomes]
        for o in final:
            self._log_outcome(o)
        for code, issues in report_issues.items():
            for issue in issues:
                self.log_event(issue.check_id, code, issue.message)
        if progress:
            progress(100, "")
        return final

    def _import_one(self, path: Path, expected_code: str | None) -> ImportOutcome:
        name = path.name
        try:
            data = path.read_bytes()
        except OSError:
            return _rejected(name, None, "V01.corrupt")
        if data[:5] == b"%PDF-" or path.suffix.lower() == ".csv":
            hint = "Ainda não é possível ler a lista de consultas do SClínico nesta versão."
            return _rejected(name, "SCLINICO.consultas", "V01.unsupported",
                             what="lista de consultas do SClínico", hint=hint)  # fmt: skip
        try:
            raw = read_mimuf_file(path)
        except UnreadableFileError as exc:
            key = "V01.not_excel" if exc.reason == "not_excel" else "V01.corrupt"
            return _rejected(name, None, key)
        except HeaderParseError:
            return _rejected(name, None, "V01.no_header")
        spec = raw.spec
        if spec is None or raw.code is None:
            return _rejected(name, None, "V02.unknown", title=raw.title or raw.title_raw)
        if expected_code and raw.code != expected_code:
            return _rejected(name, raw.code, "V02.wrong_report", found=raw.code,
                             found_title=spec.title, expected=expected_code)  # fmt: skip
        file_id = self._store(path, data, raw)
        return ImportOutcome(name, raw.code, file_id, Status.PENDING)

    def _store(self, path: Path, data: bytes, raw: RawSheet) -> int:
        sha = hashlib.sha256(data).hexdigest()
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        copy = self.raw_dir / f"{sha[:12]}__{path.name}"
        if not copy.exists():
            shutil.copyfile(path, copy)  # byte-identical (CLAUDE.md rule 4)
        assert raw.code is not None
        table = _table(raw.code)
        columns = [c for c in raw.rows.columns if c != "_row"]
        with self.connect() as con:
            con.execute("BEGIN TRANSACTION")
            try:
                (file_id,) = con.execute("SELECT nextval('file_id_seq')").fetchall()[0]
                con.execute(
                    "INSERT INTO files (file_id, sha256, original_name, raw_path, report_code, "
                    "imported_at, format, sheet_name, code_source, title, title_raw, filter_text, "
                    "pages, has_pages, header, header2, columns, footer, n_rows, max_row, "
                    "status) VALUES (" + ", ".join(["?"] * 21) + ")",
                    [
                        file_id, sha, path.name, copy.relative_to(self.folder).as_posix(),
                        raw.code, datetime.now().replace(microsecond=0), str(raw.format),
                        raw.sheet_name, raw.code_source, raw.title, raw.title_raw,
                        raw.filter_text, json.dumps(raw.pages, ensure_ascii=False),
                        raw.has_pages, json.dumps(raw.header, ensure_ascii=False),
                        json.dumps(raw.header2, ensure_ascii=False) if raw.header2 else None,
                        json.dumps(columns), json.dumps(raw.footer_rows, ensure_ascii=False),
                        raw.n_rows, raw.max_row, int(Status.PENDING),
                    ],
                )  # fmt: skip
                self._store_rows(con, table, file_id, raw.rows, columns)
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return int(file_id)

    @staticmethod
    def _store_rows(con: duckdb.DuckDBPyConnection, table: str, file_id: int,
                    rows: pl.DataFrame, columns: list[str]) -> None:  # fmt: skip
        """Every source column as VARCHAR + file_id + row_num (TECH_SPECS §4.2 raw_<report>)."""
        con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" (file_id INTEGER, row_num INTEGER)')
        existing = {r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]
        ).fetchall()}  # fmt: skip
        for col in columns:
            if col not in existing:
                con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" VARCHAR')
        frame = rows.select(
            pl.lit(file_id, pl.Int32).alias("file_id"),
            pl.col("_row").cast(pl.Int32).alias("row_num"),
            *[pl.col(c) for c in columns],
        )
        con.register("incoming", frame.to_arrow())
        try:
            con.execute(f'INSERT INTO "{table}" BY NAME SELECT * FROM incoming')
        finally:
            con.unregister("incoming")

    def remove_file(self, file_id: int) -> None:
        """Remove a file from the project (its byte copy stays in raw/)."""
        with self.connect() as con:
            row = con.execute(
                "SELECT report_code, original_name FROM files WHERE file_id = ?", [file_id]
            ).fetchall()
            if not row:
                return
            code, name = row[0]
            con.execute(f'DELETE FROM "{_table(code)}" WHERE file_id = ?', [file_id])
            con.execute("DELETE FROM files WHERE file_id = ?", [file_id])
        self.revalidate(code)
        self.log_event("OK", code, f"{name} removido do projeto.")

    # ------------------------------------------------------------------ validation

    def load_sheet(self, file_id: int) -> RawSheet:
        """Rebuild the parsed sheet of a stored file (for re-validation and staging)."""
        with self.connect() as con:
            cur = con.execute("SELECT * FROM files WHERE file_id = ?", [file_id])
            names = [d[0] for d in cur.description]
            rec = dict(zip(names, cur.fetchall()[0], strict=True))
            columns: list[str] = json.loads(rec["columns"])
            select = ", ".join(f'"{c}"' for c in columns)
            table = _table(rec["report_code"])
            sql = (
                f"SELECT {select + ', ' if select else ''}row_num AS _row "
                f'FROM "{table}" WHERE file_id = ? ORDER BY row_num'
            )
            frame = con.sql(sql, params=[file_id]).pl()  # relation → Polars, no extra copy
        frame = frame.with_columns(
            *[pl.col(c).cast(pl.Utf8) for c in columns], pl.col("_row").cast(pl.UInt32)
        )
        spec = self._specs.get(rec["report_code"])
        return RawSheet(
            code=rec["report_code"],
            code_source=rec["code_source"],
            title=rec["title"],
            title_raw=rec["title_raw"],
            filter_text=rec["filter_text"],
            filter=parse_filter(rec["filter_text"]),
            pages=json.loads(rec["pages"]),
            has_pages=bool(rec["has_pages"]),
            header=tuple(json.loads(rec["header"])),
            header2=tuple(json.loads(rec["header2"])) if rec["header2"] else None,
            rows=frame,
            footer_rows=tuple(tuple(r) for r in json.loads(rec["footer"] or "[]")),
            max_row=int(rec["max_row"]),
            format=FileFormat(rec["format"]),
            sheet_name=rec["sheet_name"] or "",
            source_sha256=rec["sha256"],
            spec=spec if isinstance(spec, MimufReportSpec) else None,
        )

    def revalidate(self, code: str) -> list[Issue]:
        """Run every check for one report and store the results."""
        spec = self._specs.get(code)
        ctx = self.ctx
        with self.connect() as con:
            rows = con.execute(
                "SELECT file_id, original_name, sha256 FROM files WHERE report_code = ? "
                "ORDER BY file_id", [code]
            ).fetchall()  # fmt: skip
        file_issues: list[Issue] = []
        report_files: list[ReportFile] = []
        placements: dict[int, Placement] = {}
        if isinstance(spec, MimufReportSpec):
            for file_id, name, sha in rows:
                raw = self.load_sheet(file_id)
                result = check_file(raw, spec, ctx, name, file_id)
                file_issues += result.issues
                placements[file_id] = result.placement
                report_files.append(ReportFile(file_id, name, sha, raw, result.placement))
            report_issues = check_report(spec, report_files, ctx)
        else:
            report_issues = []
        issues = file_issues + report_issues
        with self.connect() as con:
            con.execute("BEGIN TRANSACTION")
            con.execute("DELETE FROM issues WHERE report_code = ?", [code])
            for issue in issues:
                con.execute(
                    "INSERT INTO issues VALUES (nextval('issue_id_seq'), ?, ?, ?, ?, ?, ?, ?)",
                    [code, issue.file_id, issue.check_id, int(issue.severity), issue.message,
                     issue.location, issue.fix_hint],
                )  # fmt: skip
            for file_id, placement in placements.items():
                own = [i for i in issues if i.file_id == file_id]
                con.execute(
                    "UPDATE files SET slot_keys = ?, months = ?, period = ?, status = ? "
                    "WHERE file_id = ?",
                    [json.dumps(placement.slot_keys), json.dumps(placement.months),
                     placement.period, int(status_of(own)), file_id],
                )  # fmt: skip
            con.execute("COMMIT")
        return issues

    def revalidate_all(self) -> None:
        for code in self.imported_codes():
            self.revalidate(code)

    def imported_codes(self) -> list[str]:
        with self.connect() as con:
            rows = con.execute("SELECT DISTINCT report_code FROM files").fetchall()
        return sorted(r[0] for r in rows)

    # ------------------------------------------------------------- user decisions

    def set_skipped(self, code: str, skipped: bool) -> None:
        """Skip an optional report (⚪ dashed); it then never blocks the gate."""
        spec = self._specs[code]
        if skipped and spec.required:
            raise ProjectError("Este relatório é obrigatório e não pode ser dispensado.")
        with self.connect() as con:
            con.execute(
                "INSERT INTO report_state (report_code, skipped) VALUES (?, ?) "
                "ON CONFLICT (report_code) DO UPDATE SET skipped = excluded.skipped",
                [code, skipped],
            )
        self.log_event("OK", code, "Relatório dispensado." if skipped else "Relatório retomado.")

    def acknowledge(self, code: str, note: str = "") -> None:
        """ "Continuar mesmo assim": accept the report's current warnings (recorded, PRD §6.1)."""
        state = self.report_state(code)
        if state.status is Status.ERROR:
            raise ProjectError("Há erros por corrigir: não é possível continuar mesmo assim.")
        digest = _digest(state.issues)
        with self.connect() as con:
            con.execute(
                "INSERT INTO report_state (report_code, acknowledged_at, ack_digest, ack_note) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (report_code) DO UPDATE SET "
                "acknowledged_at = excluded.acknowledged_at, ack_digest = excluded.ack_digest, "
                "ack_note = excluded.ack_note",
                [code, datetime.now().replace(microsecond=0), digest, note],
            )
        n = len(state.issues)
        self.log_event(
            "OK", code, f"Avisos confirmados pelo utilizador ({n}): continuar mesmo assim."
        )

    def doctor_candidates(self, code: str = "P01.01.L01", n: int = 3) -> list[str]:
        """Doctors of a doctor-list report, most like the project's doctor first (S05)."""
        spec = self._specs.get(code)
        if not isinstance(spec, MimufReportSpec):
            return []
        files = [
            ReportFile(
                f.file_id,
                f.original_name,
                f.sha256,
                self.load_sheet(f.file_id),
                Placement(f.slot_keys, f.months, f.period),
            )
            for f in self.files(code)
        ]
        return closest_doctors(self.info.doctor, report_doctors(spec, files), n)

    # ------------------------------------------------------------------- read state

    def files(self, code: str | None = None) -> list[FileRecord]:
        sql = ("SELECT file_id, report_code, original_name, sha256, imported_at, n_rows, "
               "footer, period, slot_keys, months, status, format FROM files")  # fmt: skip
        params: list[Any] = []
        if code:
            sql += " WHERE report_code = ?"
            params.append(code)
        with self.connect() as con:
            rows = con.execute(sql + " ORDER BY file_id", params).fetchall()
        return [
            FileRecord(
                file_id=r[0],
                report_code=r[1],
                original_name=r[2],
                sha256=r[3],
                imported_at=r[4],
                n_rows=r[5] or 0,
                n_footer=len(json.loads(r[6] or "[]")),
                period=r[7] or "",
                slot_keys=tuple(json.loads(r[8] or "[]")),
                months=tuple(json.loads(r[9] or "[]")),
                status=Status(r[10] or 0),
                format=r[11],
            )
            for r in rows
        ]

    def issues(self, code: str) -> list[Issue]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT check_id, severity, message, location, fix_hint, file_id FROM issues "
                "WHERE report_code = ? ORDER BY severity DESC, issue_id", [code]
            ).fetchall()  # fmt: skip
        return [Issue(r[0], Status(r[1]), r[2], r[3], r[4], r[5]) for r in rows]

    def report_state(self, code: str) -> ReportState:
        spec = self._specs[code]
        files = tuple(self.files(code))
        issues = tuple(self.issues(code))
        with self.connect() as con:
            st = con.execute(
                "SELECT skipped, ack_digest FROM report_state WHERE report_code = ?", [code]
            ).fetchall()  # fmt: skip
        skipped = bool(st and st[0][0])
        ack_digest = st[0][1] if st else None
        slots = tuple(_slot_states(spec, files, self.info.years))
        if skipped and not files:
            status = Status.SKIPPED
        elif not files:
            status = Status.PENDING
        else:
            status = worst([*(f.status for f in files), status_of(issues)])
        acknowledged = (
            status is Status.WARNING and ack_digest is not None and ack_digest == _digest(issues)
        )
        return ReportState(code, spec, status, skipped and not files, acknowledged, files,
                           slots, issues)  # fmt: skip

    def overview(self) -> dict[str, ReportState]:
        return {code: self.report_state(code) for code in self._specs}

    # ----------------------------------------------------------------------- event log

    def log_event(self, kind: str, code: str | None, message: str) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO event_log VALUES (?, ?, ?, ?)",
                [datetime.now().replace(microsecond=0), kind, code, message],
            )

    def events(self, limit: int = MAX_LOG_EVENTS) -> list[tuple[datetime, str, str | None, str]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT ts, kind, report_code, message FROM event_log ORDER BY ts DESC, rowid DESC "
                "LIMIT ?", [limit]
            ).fetchall()  # fmt: skip
        return [(r[0], r[1], r[2], r[3]) for r in reversed(rows)]

    def _final_outcome(self, outcome: ImportOutcome) -> ImportOutcome:
        if outcome.file_id is None or outcome.code is None:
            return outcome
        state_issues = [i for i in self.issues(outcome.code) if i.file_id == outcome.file_id]
        rec = next((f for f in self.files(outcome.code) if f.file_id == outcome.file_id), None)
        spec = self._specs[outcome.code]
        labels: tuple[str, ...] = ()
        if rec is not None and isinstance(spec, MimufReportSpec):
            by_key = {s.key: s.label for s in expected_slots(spec, self.info.years)}
            labels = tuple(by_key.get(k, k) for k in rec.slot_keys)
        status = rec.status if rec else Status.PENDING
        return ImportOutcome(outcome.name, outcome.code, outcome.file_id, status,
                             tuple(state_issues), labels)  # fmt: skip

    def _log_outcome(self, o: ImportOutcome) -> None:
        if o.status in (Status.VALID, Status.PENDING) and not o.issues:
            slots = f" · {', '.join(o.slots)}" if o.slots else ""
            self.log_event("OK", o.code, f"{o.name} importado{slots}.")
            return
        for issue in o.issues:
            self.log_event(issue.check_id, o.code, f"{o.name} · {issue.message}")


# ----------------------------------------------------------------------------- helpers


def _expand(paths: Iterable[Path]) -> set[Path]:
    out: set[Path] = set()
    for path in paths:
        if path.is_dir():
            out |= {
                p for p in path.rglob("*") if p.is_file() and not p.name.startswith((".", "~$"))
            }
        elif path.is_file():
            out.add(path)
    return out


def _rejected(name: str, code: str | None, template: str, **values: object) -> ImportOutcome:
    message, hint = M.text(template, **values)
    issue = Issue(template.split(".")[0], Status.ERROR, message, name, hint)
    return ImportOutcome(name, code, None, Status.ERROR, (issue,))


def _slot_states(
    spec: ReportSpec, files: Sequence[FileRecord], years: Sequence[int]
) -> list[SlotState]:
    if not isinstance(spec, MimufReportSpec):
        ids = tuple(f.file_id for f in files)
        status = worst((f.status for f in files), Status.PENDING)
        y = years[0]
        return [SlotState(SlotDef(str(y), str(y), y, ()), status, ids)]
    out = []
    coverage = isinstance(spec.slots, MonthCoverageSlots)
    for slot in expected_slots(spec, years):
        if coverage:
            # quarters/months of a coverage report: filled by whichever files cover its months
            covering = [f for f in files if set(f.months) & set(slot.months)]
            covered = {m for f in covering for m in f.months} & set(slot.months)
            status = worst((f.status for f in covering), Status.PENDING)
            if covering and covered != set(slot.months):
                status = max(status, Status.WARNING)  # partly covered: "incompleto"
            out.append(SlotState(slot, status, tuple(f.file_id for f in covering)))
            continue
        in_slot = [f for f in files if slot.key in f.slot_keys]
        status = worst((f.status for f in in_slot), Status.PENDING)
        out.append(SlotState(slot, status, tuple(f.file_id for f in in_slot)))
    return out


__all__ = [
    "SUFFIX",
    "FileRecord",
    "ImportOutcome",
    "Project",
    "ProjectError",
    "ProjectInfo",
    "ReportState",
    "SlotState",
    "default_name",
]
