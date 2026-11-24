# mimufs — Technical Specification

| | |
|---|---|
| **Companion to** | `PRD.md` v0.1 |
| **Repository** | https://github.com/diogocarapito/mimufs (GPL-3.0) |
| **Status** | Draft v0.1 — MVP / proof of concept |
| **Date** | 2026-11-24 |

---

## 1. Decisions at a glance

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3.12** | Existing repo, data ecosystem |
| GUI | **PySide6 (Qt 6, Widgets)**, `pyside6-essentials` | Native, mature, no embedded web server or web view, LGPL (GPL-3 compatible), already in the repo |
| Dataframes | **Polars** | Fast, low memory, strict types, good for 30k × 800 wide tables |
| Project store | **DuckDB** (one file per project) | Embedded, columnar, SQL for joins and pivots, single portable file |
| Arrow bridge | **pyarrow** | Required for zero-copy Polars ↔ DuckDB (verified: DuckDB 1.x cannot read Polars frames without it) |
| `.xls` / `.xlsx` reading | **openpyxl** (with Diogo's `openpyxl.worksheet._reader` compatibility patch) | Already proven on real MIM@UF exports; reads `.xlsx` natively. Format is detected from the file's bytes, not its extension (§5.0) |
| SClínico PDF reading | **tabula-py** (`read_pdf`), running tabula-java on a **bundled Java runtime** | Already proven on the real appointments PDF. Needs Java, which the app ships itself (§16.2) |
| Specs and rules | **YAML** validated by **pydantic v2** | Reports and rules are data, not code |
| XLSX export | **XlsxWriter** (via `polars.DataFrame.write_excel`) | Fast writer for large sheets |
| Charts (Phase 2) | pyqtgraph or Matplotlib (QtAgg); decided in Phase 2 | No QtWebEngine |
| Packaging | **Briefcase** (BeeWare): MSI + portable ZIP (Windows), `.app` in `.dmg` (macOS), `.deb` + Flatpak (Linux) | One tool and one config (`pyproject.toml`) for all OSes; per-user MSI needs no admin; ships a standard Python runtime rather than a self-extracting bootloader (fewer antivirus false positives on SPMS PCs); already used successfully with PySide6 (`pyside6-essentials`, no universal2) |
| CI/CD | **GitHub Actions** (3-OS matrix) | Free for public repos |
| Website | **Plain HTML/CSS** in `site/`, GitHub Pages, Cloudflare DNS | Free, static |
| Tooling | `uv` (env/lock), `ruff` (lint+format), `pytest`, `pytest-qt`, `pytest-socket`, `mypy` (core only) | Fast, reproducible |

### 1.1 Dependency licences (all GPL-3.0 compatible)

PySide6 (LGPL-3.0), Polars (MIT), DuckDB (MIT), pyarrow (Apache-2.0), openpyxl (MIT), tabula-py (MIT) and the tabula-java jar it ships (MIT), PyYAML (MIT), pydantic (MIT), XlsxWriter (BSD-2), platformdirs (MIT), packaging (Apache-2.0/BSD), Tabler Icons (MIT), Inter font (OFL-1.1). Bundled Java runtime: Eclipse Temurin / OpenJDK (GPL-2.0 with Classpath Exception), shipped as a separate program next to the app (aggregation, not linking). Optional fallback reader for legacy BIFF files: xlrd (BSD).

### 1.2 Removed from the current repo

`pyautogui`, `opencv-python`, `Pillow` (unless needed), `Nuitka`, `requests` (stdlib `urllib` is enough for the update check), `Dockerfile`. Before restructuring, tag the current state as **`legacy-autogui`**.

---

## 2. Architecture

```
┌──────────────────────────── mimufs.gui (PySide6) ─────────────────────────────┐
│  MainWindow ─ PhaseNav ─ StepPages (Project, Import, Aggregate, Quality,       │
│  Mapping, Export) ─ Widgets (DropZone, StatusBadge, InfoCard, IssueList,      │
│  PolarsTableModel, RuleReview, MappingBoard) ─ Workers (QThreadPool)          │
└───────────────▲───────────────────────────────────────────────────────────────┘
                │ calls pure functions, receives results + progress callbacks
┌───────────────┴────────────── mimufs.core (no Qt imports) ────────────────────┐
│ specs ─ readers ─ validation ─ ingest ─ aggregate ─ quality ─ mapping ─ export│
│                        │                                                      │
│                    project (DuckDB file + raw/ + logs/)                       │
└───────────────────────────────────────────────────────────────────────────────┘
┌──────────── mimufs.netguard ────────────┐  ┌──────── mimufs.update ─────────┐
│ audit hook: blocks all sockets except   │  │ fetch version.json (urllib),   │
│ the update check                        │  │ compare, notify                │
└─────────────────────────────────────────┘  └────────────────────────────────┘
```

**Rules**

- `mimufs.core` **never imports Qt**. It can be tested headlessly and reused as a library or CLI (`python -m mimufs.core …`), which keeps the original "library" goal of the repo.
- The GUI is a thin layer: it collects user input, calls core functions in worker threads, and renders the results.
- All long operations take a `progress: Callable[[float, str], None]` callback and a cancellation token.

---

## 3. Repository layout

```
mimufs/
├── pyproject.toml                 # project metadata, deps, tool config; version source of truth
├── uv.lock
├── LICENSE                        # GPL-3.0
├── README.md
├── CLAUDE.md                      # instructions for Claude Code
├── docs/ (PRD.md, TECH_SPECS.md, ui/, reference/)
├── CHANGELOG.md                   # Keep a Changelog format, PT-PT entries
├── src/mimufs/
│   ├── __init__.py                # __version__
│   ├── __main__.py                # entry point: installs netguard, starts GUI
│   ├── netguard.py
│   ├── update.py
│   ├── settings.py                # platformdirs-based user settings (JSON)
│   ├── core/
│   │   ├── project.py             # Project create/open/save, DuckDB connection
│   │   ├── specs/
│   │   │   ├── models.py          # pydantic models for report specs and rules
│   │   │   ├── loader.py
│   │   │   ├── reports/           # one YAML per report — 18 already written (17 MIM@UF + SClínico)
│   │   │   └── rules/             # quality rule sets (labs.yaml, biometrics.yaml)
│   │   ├── readers/
│   │   │   ├── excel.py           # format sniffing + openpyxl (patched) → RawSheet
│   │   │   ├── openpyxl_compat.py # Diogo's openpyxl.worksheet._reader patch, isolated and version-pinned
│   │   │   ├── mimuf_header.py    # metadata block + filter parser
│   │   │   ├── sclinico_pdf.py    # tabula-py read_pdf → appointments table
│   │   │   └── java_runtime.py    # points tabula at the bundled JRE
│   │   ├── validation/
│   │   │   ├── checks.py          # V01–V12 file checks
│   │   │   ├── set_checks.py      # S01–S04 report-level checks
│   │   │   └── result.py          # Status, Issue, ValidationResult
│   │   ├── ingest.py              # raw_* and stg_* tables
│   │   ├── aggregate.py           # patient dataset, event & aggregate tables
│   │   ├── quality/
│   │   │   ├── engine.py
│   │   │   ├── hba1c.py           # multi-interpretation resolver
│   │   │   └── derived.py         # BMI, eGFR, Friedewald
│   │   ├── mapping.py
│   │   ├── export.py
│   │   ├── dictionaries.py        # load bundled + user dictionaries, matching, versions
│   │   └── reference/             # icpc_mimuf_batches.json + dictionaries/ (medicamentos, ICPC-2, indicadores, manifest, README)
│   └── gui/
│       ├── app.py
│       ├── main_window.py
│       ├── theme/ (style.qss, palette.py, fonts/Inter*.ttf)
│       ├── icons/ (Tabler SVGs)
│       ├── strings_pt.py          # all UI strings, keyed (future i18n)
│       ├── steps/ (project.py, extraction.py, aggregate.py, quality.py, mapping.py, export.py)
│       ├── widgets/ (drop_zone.py, status_badge.py, info_card.py, issue_list.py,
│       │            table_model.py, rule_review.py, mapping_board.py, step_nav.py)
│       └── workers.py
├── tests/
│   ├── fixtures/make_fixtures.py  # generates synthetic MIM@UF-style files with openpyxl (no real data, ever)
│   ├── core/ …                    # unit tests per module
│   ├── gui/ …                     # pytest-qt smoke tests
│   └── e2e/test_pipeline_offline.py
├── packaging/
│   ├── windows/ (icon.ico, installer_background.bmp)
│   ├── macos/ (Info.plist, icon.icns, dmg settings)
│   ├── jre/build_jre.sh           # jlink a minimal Temurin runtime per OS/arch
│   └── linux/ (icon.png, Flatpak manifest overrides if needed)
├── scripts/
│   ├── build_site.py              # CHANGELOG.md → site/changelog.html, writes site/version.json
│   ├── check_specs_against_headers.py  # specs vs docs/reference/MIMUF_Header_examples.xlsx (already written)
│   ├── update_indicadores.py      # TODO: maintainer-only indicator dictionary updater
│   └── release_notes.py           # extracts a version's section from CHANGELOG.md
├── site/                          # GitHub Pages root
│   ├── index.html  sobre.html  changelog.html  version.json
│   ├── style.css  CNAME  (no JS frameworks, no external assets)
│   └── assets/
└── .github/workflows/
    ├── ci.yml
    ├── release.yml
    └── pages.yml
```

---

## 4. Project storage

A project is a folder:

```
USF_Exemplo_2024/
├── USF_Exemplo_2024.mimufs     # DuckDB database
├── raw/                        # byte-identical copies of imported files, named <sha256[:12]>__<original>.xls
├── exports/
└── logs/                       # app log (no patient data) + audit log exports
```

### 4.1 DuckDB connection

```python
duckdb.connect(path, config={
    "autoinstall_known_extensions": False,   # never download extensions
    "autoload_known_extensions": False,
    "allow_community_extensions": False,
    "threads": max(2, os.cpu_count() - 1),
})
```

### 4.2 Schema (core tables)

| Table | Purpose |
|---|---|
| `project` | name, unit, years[], doctor_name (as in MIM@UF), created_at, app_version, ruleset_version |
| `files` | file_id, sha256, original_name, raw_path, report_code, slot_key, n_rows, imported_at, status |
| `file_meta` | file_id, section (`title`/`filter`/`pages`), key, value |
| `issues` | issue_id, file_id NULL, report_code, check_id, severity, message, location, fix_hint |
| `acknowledgements` | target (step/report/file), issue_ids, acknowledged_at, note |
| `raw_<report>` | every source column as VARCHAR + `file_id`, `row_num` (exactly what was read) |
| `stg_<report>` | typed, renamed, normalised rows + `patient_key`, `file_id`, `slot_key` |
| `patients` | wide patient dataset (built in step 2) |
| `ev_problems`, `ev_new_problems`, `ev_prescriptions`, `ev_mcdt`, `ev_appointments` | long event tables |
| `list_exits` | patient_key, mf_nome, last_activity (date, source report), reason (`obito`/`transferencia`/`outro`/`por_rever`), note, decided_at. One row per patient in P01.01.L01 January but not December; filled by manual review |
| `agg_unit_indicators`, `agg_doctor_indicators`, `agg_top_problems`, `agg_acute_by_doctor`, `agg_meds_by_doctor` | aggregate reports |
| `qc_flags` | flag_id, variable, patient_key, value_raw, rule_id, candidates (JSON), suggested, confidence, decision, value_final |
| `audit_log` | ts, actor (`user`/`rule`), action, variable, patient_key, from, to, rule_id, rule_params_hash |
| `mapping_snapshot` | the mapping used for this build (copied from the user's settings, for reproducibility) |
| `dictionary_snapshot` | name, version, sha256 and (for user-edited dictionaries) the full content used for this build |
| `med_classification` | normalised medication name → matched terms → groups/diseases, for this project (feeds `med_grupo_*` / `med_doenca_*` columns and the "Não classificados" list) |

Writes happen inside transactions. The project is consistent after every completed action. No separate "save" button is needed; "Guardar cópia como…" exports a copy of the folder.

---

## 5. Reading MIM@UF files

### 5.0 Format detection

The extension is not trusted. `readers/excel.py` reads the first bytes of each file:

| Signature | Real format | Reader |
|---|---|---|
| `50 4B 03 04` (ZIP) | OOXML workbook (`.xlsx`, including MIM@UF files named `.xls`) | **openpyxl** + compat patch |
| `D0 CF 11 E0` (OLE2) | Legacy BIFF `.xls` | **xlrd** fallback (BIFF is not readable by openpyxl) |
| `<` / `<html` / text | HTML or CSV saved as `.xls` | Not supported → V01 🔴 "O ficheiro não é um Excel verdadeiro; exporte novamente do MIM@UF" |

The real format is stored in `files.format` and shown in the info card.

### 5.0.1 openpyxl compatibility patch

Diogo's working code imports `openpyxl.worksheet._reader` to make openpyxl read MIM@UF exports. Because `_reader` is a **private** module:

- the patch lives alone in `readers/openpyxl_compat.py` with `apply()` (idempotent) and a docstring explaining what MIM@UF quirk it works around;
- `openpyxl` is pinned to an exact version in `pyproject.toml`;
- a unit test loads a fixture that needs the patch: it fails without the patch and passes with it, so an openpyxl upgrade that breaks the patch is caught in CI;
- the patch is applied once, at reader import time, never globally at app start-up.

### 5.1 File anatomy (from the real headers)

All 17 MIM@UF reports are in `docs/reference/MIMUF_Header_examples.xlsx` (one sheet each, no patient rows) and annotated in `docs/reference/mimuf_header_samples.md`. The general shape:

```
r0   P01.01.L01. Inscritos &gt; Utente                    ← code + title, HTML-escaped, free text
r1   (blank)
r2   Filtro do relatório:
r3   (Mês = 2024-01) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo) [E (…)]
r4   (blank)
r5   Páginas:                                            ← absent in some reports (P05.01.L02)
r6…  Key: Value   or   Key = Value                       ← page-by selectors; may be "Total"
     (blank) (blank)
rH   NOP | Utente | (blank) | Sexo | Idade | …            ← header; 1 or 2 rows; untitled cells exist
rH+1… data
     Total | … | 23149 | 67.830                          ← optional footer (V12)
```

Variations that the parser must handle (all seen in the real headers):

| Variation | Where |
|---|---|
| Title code damaged (`1.01.L03.`) | P01.01.L03 example → identify by title text + header signature |
| Filter clause without parentheses (`Mês = 2000-12`, `Ano = 2000`) | P04.R06, P05.R01, P06.01.R02 |
| Operators `<>` and `>` (as `&lt;&gt;`, `&gt;`) | P02.01.R04, P04.01.L05 |
| Key suffix: `{Tipo Risco} (ID) = -24` | P05.01.L02 |
| List values: `Mês = 2000-11, 2000-10, …`; ICPC `code:DESCRIPTION` lists with commas and parentheses | P05.01.L02, P04.01.L01 |
| Exam value `651029:Colesterol total, s/l` (comma inside the value) | P07.03.01.L01 |
| Páginas with `=` instead of `:` | P06.01.01.L03 |
| Page value containing `:` (`NOME MEDICO: M 00000`) | P04.01.L05, P05.R01, P06.01.R02, P07.01.01.L01 |
| No Páginas section | P05.01.L02 |
| Two header rows (dimensions + month / `Métrica` + metric names) | P02.01.R01, R03, R04 |
| First header cell other than `NOP` (`Local`, `ICPC`, `Medicamento/CNPEM`, `DCI (CNPEM)`, `Exame MCDT`, `Mês`, `Unidade Funcional / Polo Hospitalar`) | many |
| `Métrica` layout columns | P04.01.L05, P04.R06, P05.R01, P06.*, P07.01.01.L01 |
| Unit only in a data column, not in filter/pages | P02.* |
| Header text cut in the file (`…(Custo - SNS`) | P06.01.R02 → prefix match |

### 5.2 Parser algorithm (`readers/mimuf_header.py`)

1. Read the first sheet with **openpyxl** (`load_workbook(path, read_only=True, data_only=True)` after `openpyxl_compat.apply()`) into a list of rows (`ws.iter_rows(values_only=True)`), keeping cells as strings/numbers. Cells are never coerced at this stage: typing happens in staging. `html.unescape` every metadata cell.
2. **Title**: regex `^(P\d{2}(?:\.\d{2}){0,2}\.[LR]\d{2})\.\s*(.+)$` → `code`, `title`. If it fails, match the title text against the specs' `title`, then confirm with the header signature (column names at their positions).
3. **Filter**: the first non-blank row after `Filtro do relatório:`, parsed by a small **tokenizer** (not a regex split):
   - split on top-level ` E ` between clauses, tracking parenthesis depth; a clause may or may not be wrapped in `(…)`;
   - each clause → `key op value`, with `op ∈ {=, <>, >=, <=, >, <}`; strip `{}` from keys and keep a suffix such as `(ID)` as part of the key;
   - list values split on `, ` only where the next token starts a new item (ICPC: `,\s*(?=[A-Z]\d{2}:)`; months: `,\s*(?=\d{4}-\d{2})`); otherwise the value is kept whole (e.g. `651029:Colesterol total, s/l`).
4. **Páginas** (optional): rows after `Páginas:` of the form `Key: Value` **or** `Key = Value`, split on the **first** separator only, until a blank row.
   - **Key aliases** normalised before checks: `Unidade Funcional / Polo Hospitalar` and `Unidade Funcional` → `unidade`; `Mês` → `mes`; `Trimestre` → `trimestre`; `Ano` → `ano`.
   - **Effective value** of a field = filter value if present, else page value (unless `Total`), else, for the unit, the distinct values of a `role: unit` column. `Total` in Páginas never conflicts with a filter restriction (P06.01.01.L03: filter `{Unidade Funcional} = USF Exemplo`, page `Unidade Funcional: Total` → unit = `USF Exemplo`).
5. **Header**: the first row with ≥ 2 non-empty cells after the metadata; `header.rows: 2` in the spec takes the next row too (metric names come from row 2). Columns are matched **by position** (`at`) against the spec; untitled cells get their spec `name`; `match: startswith` allows a cut header; `type: ignore` columns (`Métrica`, `Mês` label) are dropped.
6. **Data rows**: everything below the header until the first fully blank row.
   - **Footer removal (V12)**: scanning up from the last row, drop rows whose first cell is `Total` (trimmed, case-insensitive) **and** whose patient-ID columns are empty (for reports without patient IDs: whose dimension columns are empty). Stop at the first normal data row. The footer's numbers are **discarded**. Footer rows stay in `raw/` (byte copy) but not in `raw_<report>`.
   - Columns with `drop: true` (e.g. `Morada`, `Código Postal`, `Telefone` in P01.01.L03) are removed **here**, before anything is stored in the project database.
7. Output: `RawSheet(code, title, filter: list[Clause], pages: dict, header: list[str], rows: pl.DataFrame[str], n_rows, footer_rows, source_sha256, format)`.

Auto-detection of report and slot uses only this parsed metadata, never the file name. **Test**: the parser must read every sheet of `MIMUF_Header_examples.xlsx` and produce the spec's columns (each sheet saved as a separate file in the fixtures).

### 5.3 Patient key

```
patient_key = "SNS:" + utente   if utente matches ^\d{9}$
            = "NOP:" + nop      otherwise (and counted for V10)
```

When a patient appears with an SNS number in one report and only a NOP in another, a `nop → sns` crosswalk built from reports that contain both resolves the NOP to the SNS key. Unresolved NOP keys stay separate and appear in the join diagnostics.

---

## 6. Report specifications (YAML)

Each report is described by one file in `src/mimufs/core/specs/reports/` (**18 files already written**: the 17 MIM@UF reports, generated from the real headers and checked against them column by column, plus `SCLINICO.consultas.yaml`). Pydantic validates them on start-up, and CI fails if a spec is invalid or no longer matches `MIMUF_Header_examples.xlsx`.

### 6.1 Schema

```yaml
code: P10.01.L01
source: mimuf                       # mimuf | sclinico_pdf
title: Resultados Biométricos > Utente
group: Biometrias                   # checklist section in the left nav
level: patient                      # patient | patient_event | doctor | unit | family
required: true                      # optional reports can be skipped without blocking the gate
purpose: "…"                        # PT-PT, one line
instructions: ["…", "…"]            # PT-PT; {ano} and {unidade} are filled in; first line = TODO click-path
slots:                              # see 6.2
  kind: values
  key: filter.Tipo Dado
  months: [12]
  values: { peso: "(?i)^peso", altura: "(?i)^altura", … }   # slot id → regex on the filter value
pages_expect: { Flag Médico Família: C/ Med Fam }            # V06 (🟠 by default)
filter_expect: {}                                            # e.g. { Area MCDT: ANÁLISES CLÍNICAS }
doctor_pages: []                    # page keys holding a doctor (V06 doctor rule)
doctor_pages_default: total_or_project_doctor
no_pages: false                     # true for P05.01.L02
header:
  rows: 1                           # 2 for P02.*
  columns:
    - { at: 0, header: NOP,    name: NOP,    role: nop, type: str }
    - { at: 1, header: Utente, name: Utente, role: sns, type: str, required: true }
    - { at: 2, header: "",     name: Nome,   type: str, pii: true, export_default: false }
    - …
    - { at: 8, header: Resultado Último Registo, name: Resultado Último Registo, type: str, parse: decimal_pt }
```

Column keys: `at` (0-based position), `header` (exact text in the file, `""` = untitled), `name` (canonical), `type` (`str | cat | int | float | date | ignore`), `role` (`sns | nop | doctor | unit | icpc | medication | exam | indicator | prescriber | period`), `required`, `pii`, `drop`, `export_default`, `row2` (metric name lives in header row 2), `match: startswith`, `parse: decimal_pt`.

Output mapping to the patient dataset (`to_patients`) is added per spec in M2, following the column-naming rules in §8.

`decimal_pt` accepts `6,5`, `6.5`, `6` and stores the raw text alongside the parsed float, so that "missing decimal" detection can see whether a separator was present.

### 6.2 Slot kinds

| kind | Reports | Slot key | S01 completeness |
|---|---|---|---|
| `months` | P01.01.L01 ([1, 12]); P04.01.L05 (1–12); single-month reports ([12]) | `YYYY-MM` from the effective `Mês` | every listed month |
| `month_coverage` | P06.01.01.L03 (files by `Trimestre` or `Mês`); P05.01.L02 (one file whose filter lists months) | the set of months each file covers (`YYYY-Tn` → 3 months) | the 12 months covered, no overlap (🟠 on gaps or overlaps); shown as T1–T4 for P06 |
| `year` | P05.R01, P06.01.R02, P07.01.01.L01, SClínico | `Ano` | 1 file for the year |
| `values` | P07.03.01.L01 by `Exame MCDT`; P10.01.L01 by `Tipo Dado` | the slot id whose regex matches the filter value | every listed value. An unmatched value → 🟠 "Exame/tipo não reconhecido" with a picker to assign it to a slot (remembered in the user's settings) |
| `icpc_sets` | P04.01.L01 | the set whose codes the file's ICPC filter covers | union of filter codes ⊇ the 688 target codes (S02) |

### 6.3 ICPC batch helper

Target list = **every** ICPC-2 code in the bundled reference (components 1 and 7, all chapters), whether or not any patient has it.

- The batches are **data, not computed**: `core/reference/icpc_mimuf_batches.json` ships the 3 working sets Diogo supplied (A01→H99, 205 codes; K01→S73, 251 codes; S74→Z29, 232 codes; **688 codes** in total, no repeats). Each set is copied exactly as listed. The duplicates in the original list (`K87` ×2, `P76` ×5) were a mistake and have been removed; a unit test asserts the 3 sets have no duplicates and no overlap. The separator is normalised to `, ` (the source has two places without the space, `F99,H01` and `R99,S01`).
- Coverage (S02) uses the de-duplicated set of 688 codes. If MIM@UF's code list ever changes, a new JSON ships with an app update. An advanced setting lets the user re-split the list into a different number of batches (fallback algorithm: chapter order, ≤ 250 entries per batch).
- In the P04.01.L01 sub-step, the tutorial shows each batch as a row (range, code count, preview) with a **"Copiar códigos"** button that copies the batch to the clipboard (`QGuiApplication.clipboard()`), ready to paste into the MIM@UF ICPC filter. Paste format: codes only, `, `-separated (`paste_format: code_only`, confirmed).
- On import, the ICPC codes in each file's filter decide which batch (slot) it fills. S02 reports codes from the target list that no file covers, overlaps between files, and codes not in the target list. Codes that are covered but have no rows in the data are fine.

---

## 7. Validation engine

```python
class Status(IntEnum): PENDING=0; SKIPPED=1; VALID=2; WARNING=3; ERROR=4

@dataclass(frozen=True)
class Issue:
    check_id: str          # "V05"
    severity: Status       # WARNING | ERROR
    message: str           # PT-PT, user-facing
    location: str | None   # "ficheiro X · linha 3" / "espaço 2024-07"
    fix_hint: str | None   # PT-PT, actionable

@dataclass
class ValidationResult:
    status: Status          # worst severity among issues (or VALID)
    issues: list[Issue]
    info: dict              # data for the info card
```

- File checks (V01–V12) and set checks (S01–S04) are pure functions `(RawSheet | list[RawSheet], ReportSpec, ProjectCtx) -> list[Issue]`, registered in a dict so specs can disable or override severities.
- Status aggregation: file → slot (worst file in the slot) → report (worst slot; empty required slots = WARNING) → step (worst required report). Skipped optional reports are ignored.
- V09 (truncation): the ceiling depends on the **real** format found by sniffing (§5.0): 1,048,576 rows for OOXML (what openpyxl reads), 65,536 for legacy BIFF. A file at the ceiling is 🔴. If MIM@UF has its own export row limit, it is added to the spec as `max_export_rows` once known.
- Messages and fix hints come from templates in `strings_pt.py`, with placeholders such as `{expected_month}` and `{report_path}`.

---

## 8. Aggregation (step 2)

1. **Staging**: for each validated report, `raw_*` → `stg_*`. This step casts types, renames columns, attaches `patient_key` and `slot_key`, and de-duplicates rows that appear in more than one file (e.g. ICPC batch overlaps).
2. **Patient spine** (*long* layout): the union of all (`patient_key`, `ano`) pairs in patient-level reports, where `ano` is the project year a file belongs to (from its period). `in_p01` marks whether the patient is in P01.01.L01 for that year. The primary key of `patients` is (`patient_key`, `ano`): a 1-year project has one row per patient, a 2-year project up to two. Column names never carry the year.
3. **Wide pivots** (DuckDB `PIVOT` / Polars `pivot`):
   - `icpc_<CODE>` (bool, active problem), about 700 columns, which is most of the 700–800 total;
   - `icpcnovo_<CODE>_mes` (month of first appearance in P04.01.L05), or a compact `novos_problemas` list column (to decide by size);
   - `med_n2_<group>` / `med_n3_<group>` (prescribed in year: bool or count);
   - `lab_<var>_valor` / `_data`, `bio_<var>_valor` / `_data`;
   - `cons_<categoria>_n` (from mapped appointments, when available).
4. **Column naming**: `snake_case`, ASCII only, with a prefix per group (`dem_`, `mf_`, `icpc_`, `lab_`, `bio_`, `med_`, `mcdt_`, `cons_`, `risco_`). A generated **data dictionary** records each column's source report, slot, type, unit and the rules applied.
5. **Join diagnostics** are written to `issues` (check IDs `J01–J04`) and shown in the UI.
6. **List exits**: `list_exits` is built from P01.01.L01 (`inscrito_jan AND NOT inscrito_dez`). `last_activity` is the most recent date found in any event or result table, to help the EHR search. The reasons the user sets become `dem_saida_motivo` in `patients`; each change goes to `audit_log`. Re-building the dataset keeps the existing decisions (matched by `patient_key`).

Target: 30k × 800 build in < 30 s on 8 GB RAM. Booleans are stored as `BOOLEAN`/`UInt8`, and memory is checked in CI with a synthetic 30k × 800 fixture.

---

## 9. Data quality engine (step 3)

### 9.1 Rule model

```yaml
variable: lab_hba1c
unit: "%"
plausible: [3.5, 20.0]          # anything outside is flagged
typical:   [4.0, 14.0]          # used to score candidate interpretations
rules:
  - id: hba1c_ok
    when: "plausible"
    action: keep
  - id: hba1c_interpretations
    when: "not plausible"
    action: resolve_candidates   # see 9.2
    candidates: [missing_decimal, ifcc_mmol_mol, eag_mg_dl]
  - id: hba1c_out
    when: "no candidate in typical"
    action: suggest_missing      # set to NA (user confirms)
```

Rule sets are versioned (`ruleset_version`). Users can override parameters per project in the UI, and overrides are logged.

### 9.2 HbA1c resolver

For a raw value *v* outside the plausible range, compute each candidate interpretation:

| Candidate | Condition | Converted value |
|---|---|---|
| `missing_decimal` | *v* integer and no decimal separator in raw text, *v*/10 ∈ plausible | *v* / 10 |
| `ifcc_mmol_mol` | 15 ≤ *v* ≤ 200 and project setting "labs may report IFCC" = on | 0.09148 · *v* + 2.152 |
| `eag_mg_dl` | 50 ≤ *v* ≤ 500 | (*v* + 46.7) / 28.7 |

Keep only the candidates whose result falls in the **typical** range.

- **One candidate** → confidence `high` (eligible for batch accept).
- **More than one** → `ambiguous`: the user picks per value or per group. The project can set a **preference order** (e.g. "3-digit values = eAG first"), which turns the first candidate into the suggestion but keeps confidence `ambiguous`.
- **None** → suggest NA.

Examples: `65` → missing_decimal 6.5 · IFCC 8.1 · eAG 3.9 (dropped: atypical). With IFCC off → **6.5, high**. `110` → 11.0 · 12.2 (IFCC) · 5.5 (eAG) → **ambiguous**.

### 9.3 Default rules for other MVP variables (editable)

| Variable | Plausible | Detection → suggestion |
|---|---|---|
| Total cholesterol (mg/dL) | 50–700 | 1.3–18 with a decimal → mmol/L × 38.67 |
| HDL (mg/dL) | 5–200 | 0.1–5.2 → × 38.67 |
| LDL (mg/dL) | 5–500 | 0.1–13 → × 38.67; LDL > TC → flag |
| Triglycerides (mg/dL) | 10–5000 | < 10 with a decimal → mmol/L × 88.57 |
| Creatinine (mg/dL) | 0.2–20 | > 20 → µmol/L ÷ 88.4; integer 2–20 with no separator and *v*/10 typical → missing decimal (ambiguous) |
| Albuminuria ACR (mg/g) | 0–10 000 | Flag only (unit ambiguity mg/mmol × 8.84 offered as a candidate) |
| Weight (kg) | 0.5–350 | > 350 and age < 3 → grams ÷ 1000; adult < 25 → flag |
| Height (cm) | 30–230 | 0.3–2.3 → metres × 100; 300–2300 → mm ÷ 10; weight/height swap detection (weight 120–230 and height 30–150 in adults) |
| Systolic BP (mmHg) | 50–300 | systolic < diastolic → swap pair; systolic − diastolic < 10 → flag |
| Diastolic BP (mmHg) | 20–200 | (see systolic) |
| DM desde (year) | 1900–project year | 2 digits → 19xx/20xx (pivot = project year % 100); < birth year → flag |

Derived after cleaning: BMI (from clean weight/height, only when both are dated within 12 months of each other, configurable); optional eGFR (CKD-EPI 2021, no race term) and Friedewald LDL (TG < 400 mg/dL).

### 9.4 Decisions and audit

- `qc_flags.decision ∈ {pending, accepted, rejected, edited, set_na}`.
- `patients.<var>_valor` holds the **final** value. `patients.<var>_valor_raw` and `patients.<var>_qc` (flag_id) are kept alongside.
- Every decision appends to `audit_log`. Re-running a rule after a parameter change never overwrites user decisions silently: conflicting decisions are listed for review.

---

## 10. Mapping tool (step 4)

- Input: distinct values of a categorical column (MVP: appointment type from the SClínico appointments, §10.1) with their counts.
- User mapping store: `platformdirs.user_data_dir("mimufs")/mappings/<field>.json`

```json
{ "field": "tipo_consulta", "version": 3, "updated": "2026-11-24T10:00:00",
  "categories": ["Presencial - Saúde Adulto", "Não presencial", "Domicílio", "Ignorar"],
  "map": { "CONSULTA PROGRAMADA ADULTO": "Presencial - Saúde Adulto", "...": "..." },
  "rules": [ { "contains": "DOMIC", "to": "Domicílio" } ] }
```

- Order of application: explicit `map` → keyword `rules` → unmapped.
- At build time the mapping is **snapshotted** into the project (`mapping_snapshot`), so a project can always be reproduced even if the user's mapping changes later.
- Import/export as JSON. Importing merges, with a conflict view.

### 10.1 SClínico appointments (PDF, tabula-py)

- `readers/sclinico_pdf.py` calls `tabula.read_pdf(path, pages="all", …)` and concatenates the page tables. The exact options (`lattice`/`stream`, area, column handling, repeated page headers to drop) come from Diogo's working script, ported unchanged and covered by a test on a synthetic PDF with the same layout.
- Before the first call, `java_runtime.configure()` puts the **bundled** JRE's `bin` first on `PATH` (and sets `JAVA_HOME`), so tabula never uses, or needs, a Java installed on the machine. This matters on SPMS PCs, where users can't install Java. tabula-py runs in **subprocess mode** (the optional JPype extra is not installed): one Java start per PDF is fast enough, and it keeps Java out of the app's process.
- Output contract (same as the former CSV stub, so the rest of the pipeline doesn't change): `data_consulta (YYYY-MM-DD)`, `utente (SNS)`, `nop`, `profissional`, `tipo_consulta (raw text)`, `local` (optional). A CSV with these columns is still accepted as a manual fallback.
- Validation: pages read vs pages in the PDF, rows per page, required columns present, dates inside the project year (🔴/🟠 like the MIM@UF checks).
- If Java fails to start (e.g. blocked by antivirus), the step shows 🔴 with a plain message and offers the CSV fallback.

### 10.2 Dictionaries (`core/dictionaries.py`)

Bundled files in `src/mimufs/core/reference/dictionaries/` (sources, columns and known gaps in its `README.md`; versions and hashes in `dictionaries.json`):

| Dictionary | File | Rows | User-editable |
|---|---|---|---|
| Medicamentos | `medicamentos.csv` (`medicamento, grupo, doenca`) | 75 | yes |
| ICPC-2e v4.4 PT | `icpc2_pt_v4_4.csv` (`cod, componente, nome, nome_curto, incl, excl, crit, cons, nota, icd10`) | 726 | no |
| Indicadores | `indicadores_intervalos.csv` (`id_indicador, nome_indicador, intervalo_aceitavel, intervalo_esperado, min_/max_esperado, min_/max_aceitavel`) | 173 | no |

- **Loading**: bundled files via `importlib.resources`. For an editable dictionary, the **effective** dictionary is the user's copy in `platformdirs.user_data_dir("mimufs")/dictionaries/medicamentos.csv` if it exists, else the bundled one. "Repor original" deletes the user copy. Import/export CSV with the same columns; import validates columns and shows a diff before saving.
- **Medication matching**: normalise both sides (lower-case, strip accents, collapse spaces/punctuation); a term matches if it appears as a whole word in `Medicamento/CNPEM` (P06.01.01.L03) or in `DCI (CNPEM)`/`Medicamento` (P06.01.R02). A name collects **all** matching terms, so combinations get all their groups. Results go to `med_classification`; patient columns `med_grupo_<grupo>` and `med_doenca_<doenca>` (bool: prescribed in the year). Unmatched names are listed for the user ("Não classificados").
- **ICPC names**: `nome_curto` for tables, `nome` for tooltips/exports. Chapter + process codes present in the MIM@UF sets but not in the dictionary (A30, A44, …) get a derived name: chapter letter + the `-NN` process name.
- **Indicators**: joined to P02.* by `id_indicador`; each value is classified `esperado / aceitável / fora` (used by the P02 summaries and later by visualisation).
- **Reproducibility**: building the dataset stores each dictionary's version and hash in `dictionary_snapshot`, and the full content of a user-edited dictionary.
- **No runtime updates**: the app never fetches dictionaries. The indicator updater is a **maintainer script** (TODO, §19) that runs outside the app and ships results with a release.

---

## 11. Export (step 5)

- Tables: `patients` (A), the project doctor's patients (B: `mf_nome = project.doctor_name`; option "todos os médicos" = one sheet per `mf_nome` in XLSX, one file per doctor in CSV/Parquet), aggregates, data dictionary, audit log, export manifest.
- Doctor name matching: exact match first; otherwise accent- and case-insensitive match with token overlap, offered as suggestions (never applied silently).
- XLSX limits: 1,048,576 rows × 16,384 columns. 30k × 800 fits; written with XlsxWriter in `constant_memory` mode.
- **Pseudonymisation option**: `sha256(project_salt + sns)[:16]`. The salt is generated per project and stored in the project only, so the user can re-identify internally. The `Nome` column is dropped by default in exports (opt-in to include).
- **Manifest** (`export_manifest.json`): app version, ruleset version, mapping version, file hashes of all inputs, audit log hash, timestamp.

---

## 12. Privacy and network isolation

### 12.1 Guarantees

1. The **only** outbound connection is `GET https://mimufs.com/version.json`, made by `mimufs.update`.
2. No QtNetwork, QtWebEngine, remote fonts, crash reporters or analytics. QtNetwork plugins are excluded from the bundle.
3. Logs (`logs/app.log`, rotating) hold events and counts only. They never contain patient keys, names or values (enforced by a logging filter plus a test).

### 12.2 Enforcement: `mimufs.netguard`

Installed first thing in `__main__` with `sys.addaudithook`, which cannot be removed once installed:

```python
ALLOWED = {("mimufs.com", 443)}

def _hook(event, args):
    if event == "socket.getaddrinfo":
        host, port = args[0], args[1]
        if not _updater_active.get() or (host, port) not in ALLOWED:
            raise PermissionError(f"mimufs netguard: blocked DNS lookup for {host}")
    elif event == "socket.connect":
        if not _updater_active.get() or args[1][0] not in _resolved_update_ips:
            raise PermissionError("mimufs netguard: blocked connection")
```

- `_updater_active` is a `contextvars.ContextVar` set only inside `update.check()`.
- Any library that tries to phone home fails loudly in development and silently (logged) in release.
- This only covers Python-level sockets, which is why no Qt networking is used and DuckDB extension downloads are disabled. The **Java subprocess** used by tabula is outside Python, so the hook can't see it. tabula-java makes no network calls, and the OS-level offline test below covers it.

### 12.3 Tests

- `tests/e2e/test_pipeline_offline.py` runs **project → import → aggregate → quality → export** on the synthetic fixtures with `pytest-socket --disable-socket` **and** netguard active. It must pass on all 3 OSes in CI.
- On Linux, the same test also runs inside a network-less namespace (`unshare --net` or `docker run --network none`). That blocks **every** process, including the Java subprocess, so it proves the whole pipeline (PDF included) works with no network at all.
- A static check in CI greps the bundle for `QtNetwork`/`QtWebEngine` libraries and fails if any are found.

### 12.4 Documentation

The Sobre page and the in-app "Sobre" dialog state exactly what the update request contains (URL, method, User-Agent `mimufs/<version>`) and how to switch it off.

---

## 13. Update check (`mimufs.update`)

`site/version.json` (generated at release):

```json
{
  "latest": "0.2.0",
  "released": "2027-01-15",
  "min_supported": "0.1.0",
  "download_url": "https://mimufs.com/#download",
  "notes_pt": ["Novo relatório P05.01.L02", "Correção na validação de trimestres"]
}
```

Flow:

1. At start-up, if `settings.update_check` is on and the last check was more than 24 h ago, run the check in a worker thread.
2. Use `urllib.request` with a 5 s timeout, the **operating system's certificate store via `truststore`** (always on: SPMS networks probably inspect HTTPS, and their root certificate lives in the Windows store, not in Python's bundled certificates), User-Agent `mimufs/<ver>`, and no other headers.
3. Compare versions with `packaging.version.Version`. If `latest > current` and `latest != settings.ignored_version`, show the dialog (Descarregar / Lembrar mais tarde / Ignorar esta versão).
4. "Descarregar" opens `download_url` in the system browser (`QDesktopServices.openUrl`). There is no in-app downloading.
5. Settings: `update_check: bool` (default `true`), `ignored_version: str | null`, `last_check: iso8601`.

---

## 14. GUI design

### 14.1 Structure

Chosen direction: **B v2, console style**. The window is fixed, and the panes inside it scroll independently. There is no page-level scrolling. Reference mockups, screenshots and the theme token table: `docs/ui/` (start with `docs/ui/README.md`).

```
┌ TitleBar: app · project file · offline badge · theme toggle · settings ───────────────┐
├ PhaseNav (QTreeView, 296px, own scroll) ┬ Breadcrumb · status pill ────────────────────┤
│ ▾ 01 Projeto            ✓               │ ContentPane (QScrollArea) │ ValidationPane    │
│ ▾ 02 Extração  9/18     ⚠               │  title · slots · steps ·  │ (QScrollArea,     │
│     INSCRITOS                           │  drop zone                │  420px): issues,  │
│       ✓ Inscritos › Utente  2/2         │                           │  metadata         │
│     …                                   ├───────────────────────────┴───────────────────┤
│     ⚠ Rever e continuar                 │ LogPanel (collapsible QPlainTextEdit, own scroll)│
│ ▸ 03 Agregação          🔒              ├───────────────────────────────────────────────┤
│ …                                       │ Footer: ‹ Anterior · Sub-passo n de N · Seguinte ›│
└─────────────────────────────────────────┴───────────────────────────────────────────────┘
```

- **Start**: with no project open, the central area shows `HomePage` (no PhaseNav). Creating or opening a project switches to the layout above. Mockups: `docs/ui/mimufs-ui-v2-home-*.png`, `…-new-project-dark.png`.
- `PhaseNav`: a `QTreeView` over a `PhaseModel`. Top level = phases, children = sub-steps; section headers are rendered as non-selectable rows. Expand and collapse are free, including for locked phases (preview only). Only sub-steps of unlocked phases can be selected.
- Each phase defines an ordered list of sub-steps, which drives the footer *Anterior / Seguinte* buttons and the "Sub-passo n de N" counter. The last sub-step of each phase is a **gate** ("Rever e continuar") that unlocks the next phase.
- Splitters (`QSplitter`) between nav/content, content/validation and content/log, with sizes persisted in settings.
- Style: **Fusion** style plus QSS generated from a **token palette with two themes** (`dark`, `light`; same token names as the mockup: `bg, chrome, panel, panel2, border, line, text, strong, muted, accent, ok, warn, err, pend`). A theme toggle in the title bar is persisted in settings, with "seguir o sistema" as the default. Inter and JetBrains Mono are bundled; icons are Tabler (already in the repo).
- Status is never shown by colour alone: the badges combine icon, colour and label.

### 14.2 Key widgets

| Widget | Notes |
|---|---|
| `DropZone` | Accepts files and folders; emits paths; shows per-file progress; global and per-report modes |
| `StatusBadge` | 🟢/🟠/🔴/⚪ with tooltip summary |
| `ReportChecklist` | `QTreeView` grouped by `group`; shows slot progress (`9/12`) |
| `SlotGrid` | Grid of slot chips (months, quarters, values, batches), each clickable → issues |
| `InfoCard` | Read-only card from `ValidationResult.info`; "Copiar resumo" |
| `IssueList` | Severity-sorted, each with message, location and fix hint |
| `PolarsTableModel` | `QAbstractTableModel` over a Polars frame; fetches rows lazily in chunks of 1,000; column groups collapsible |
| `RuleReview` | Flag table with candidate values and actions; batch-accept per rule |
| `MappingBoard` | Left: raw values (search, multi-select); right: target categories (drop targets); keyword rule builder |
| `HomePage` | Landing page: recent projects (from settings), "+ Novo projeto", "Abrir projeto…", dictionaries card, privacy note. Shown when no project is open; the `mimufs` title returns to it |
| `NewProjectDialog` | Modal `QDialog`: Unidade* (`QLineEdit`), Médico* (pre-filled from settings), Descrição (`QPlainTextEdit`), Ano (`QComboBox`: previous year default, 2-year option), Pasta (`QLineEdit` + `QFileDialog`). Inline validation; on accept → `core.project.create()` in a worker → open the project at phase 02, first sub-step |
| `DictionaryManager` | Tabs per dictionary; `PolarsTableModel` + search; medication tab editable (add/edit/delete, import/export CSV, "Repor original", "Não classificados") |

### 14.3 Threading

`QThreadPool` + `QRunnable` workers with signals (`progress`, `finished(result)`, `failed(exc)`). Workers only call `mimufs.core`. The UI disables navigation during writes. DuckDB connections are per thread (the main connection is not shared across threads).

### 14.4 Strings

All UI text lives in `gui/strings_pt.py` (keyed constants). Report instructions live in the report YAML. PT-PT only for now, but this structure lets Qt Linguist or another catalogue be added later without touching widgets.

---

## 15. Testing

| Layer | Tooling | Content |
|---|---|---|
| Fixtures | `tests/fixtures/make_fixtures.py` (openpyxl writer; synthetic SClínico-style PDF via a small generator) | Synthetic MIM@UF files for every report spec, saved as **OOXML with an `.xls` extension** (like the real exports) and as `.xlsx`: valid, wrong month, wrong unit, missing column, blank-header variants, filter/page mismatch, footer variants, duplicate file, ICPC batches with gaps, plus one legacy BIFF and one non-Excel file renamed `.xls` (V01). **No real patient data in the repo, ever** (a pre-commit hook blocks `.xls` outside `tests/fixtures/generated/`, which is git-ignored) |
| Unit | pytest | Header parser, filter tokenizer, slot keying, every check V/S/J, HbA1c resolver (table-driven), unit conversions, mapping application |
| Golden | pytest | Fixture set → expected `patients` parquet (hash compare) |
| GUI smoke | pytest-qt (+ Xvfb on Linux) | Open app, create project, drop files, see statuses |
| Offline e2e | pytest-socket + netguard | Full pipeline with sockets blocked |
| Performance | pytest-benchmark (nightly) | 30k × 800 build time and memory |

---

## 16. Packaging and distribution

### 16.1 Artefacts (stable names → stable download links)

Briefcase names files `<app>-<version>…`; CI renames them to the stable names below before uploading.

| OS | Artefact | Briefcase command | Notes |
|---|---|---|---|
| Windows x64 | `mimufs-windows-x64-portable.zip` | `briefcase package windows -p zip --adhoc-sign` | Unzip and run `mimufs.exe`. No admin; works from the user folder or USB. The main option for SPMS PCs |
| Windows x64 | `mimufs-windows-x64.msi` | `briefcase package windows -p msi --adhoc-sign` | `system_installer = false` → **per-user install, no admin**. Needs WiX + .NET Framework 3.5 on the build runner |
| macOS arm64 | `mimufs-macos-arm64.dmg` | `briefcase package macOS --adhoc-sign` | Unsigned; site explains *Definições › Privacidade e Segurança › Abrir mesmo assim*. Built on an Apple Silicon runner, `universal_build = false` |
| macOS x86_64 | `mimufs-macos-x64.dmg` | same, on an Intel runner | Intel Macs (confirmed). Built on a GitHub-hosted Intel macOS runner (check the current label, e.g. `macos-15-intel`) |
| Linux x86_64 | `mimufs-linux-x86_64.deb` | `briefcase package linux system` | Ubuntu/Debian. Briefcase can target other distros (e.g. `.rpm`) through its Docker builds if there is demand |
| Linux x86_64 | `mimufs-linux-x86_64.flatpak` | `briefcase package linux flatpak` | Any distro; `flatpak install --user` needs no admin |

AppImage is **not** shipped: Briefcase supports it only on a best-effort basis, and `.deb` + Flatpak cover Linux users more reliably.

Link pattern: `https://github.com/diogocarapito/mimufs/releases/latest/download/<artefact>`.

### 16.2 Briefcase notes

- Configuration lives in `[tool.briefcase]` in `pyproject.toml`: app name `mimufs`, `formal_name = "mimufs"`, bundle id `com.mimufs`, `sources = ["src/mimufs"]`, `requires` = the runtime dependencies (with **`pyside6-essentials`**, not `pyside6`), icons per platform.
- Data files (`core/specs` YAML, `core/reference`, theme, fonts, icons) live inside `src/mimufs/` so Briefcase copies them with the sources. They are read through `importlib.resources`, never through paths relative to the working directory.
- **Trimming**: Briefcase `cleanup_paths` removes what mimufs never uses from the bundle: `QtNetwork`, `QtQml`, `QtQuick*`, `Qt3D*`, `QtMultimedia*`, `QtWebEngine*` (if present), their plugins, translations not needed, `tkinter`, tests folders of dependencies. Kept: `platforms`, `styles`, `imageformats/qsvg`, `iconengines/qsvgicon`. A CI check fails the build if any `QtNetwork`/`QtWebEngine` library is still in the bundle (§12.3).
- **macOS**: `universal_build = false`; one build per architecture (arm64, x86_64). Ad-hoc signing only (`--adhoc-sign`) until there is an Apple Developer account.
- **Windows**: ad-hoc (no) signing; `version_triple` derived from the SemVer version; `system_installer = false`.
- Size budget: ≤ 250 MB compressed (PySide6-essentials + Polars + DuckDB + pyarrow + the JRE are the bulk). Measure in M0.
- **Java runtime**: `packaging/jre/build_jre.sh` uses `jlink` on Eclipse Temurin (LTS, e.g. 21) with only the modules tabula-java needs (start from `java.base,java.desktop,java.xml,java.logging`; confirm with `jdeps` on the tabula jar), plus `--strip-debug --no-header-files --no-man-pages --compress`. Expected size is about 40–50 MB per platform. It is built **per OS and architecture** in the CI matrix and written to `src/mimufs/_runtime/jre/` (git-ignored) **before** `briefcase create`, so Briefcase bundles it like any other source file. `java_runtime.configure()` finds it with `importlib.resources`. On macOS, Briefcase's ad-hoc signing covers the JRE's binaries too; check in M0 that Gatekeeper accepts them after "Abrir mesmo assim".
- **Development**: `briefcase dev` runs the app from source; `briefcase run` runs the built bundle locally. Both are used in the M0 smoke test.

### 16.3 CI workflows

- **`ci.yml`** (push/PR): ruff → mypy (core) → pytest (unit, golden, offline e2e) on `ubuntu-latest`, `windows-latest`, `macos-latest`; pytest-qt smoke on Linux with Xvfb.
- **`release.yml`** (tag `v*`):
  1. Build matrix (Windows x64, macOS arm64, macOS x86_64, Linux x86_64): build the jlinked JRE → `briefcase create` → `briefcase build` → smoke-launch the bundle (`--selftest` flag: loads specs, opens a temp project, reads a fixture PDF with tabula, exits 0) → `briefcase package` (zip + msi / dmg / deb + flatpak) → rename to stable artefact names.
  2. Create a GitHub Release with notes extracted from `CHANGELOG.md`, and upload the artefacts with stable names.
  3. Run `scripts/build_site.py` → regenerate `site/changelog.html` and `site/version.json` → commit to `main` → triggers `pages.yml`.
- **`pages.yml`** (push to `site/**`): `actions/upload-pages-artifact` (path `site/`) → `actions/deploy-pages`.

### 16.4 Versioning

SemVer. `pyproject.toml` is the single source. `__version__` is read via `importlib.metadata.version("mimufs")`, which works in the bundle because Briefcase installs the app's own metadata (`dist-info`); check in M0, with `src/mimufs/__about__.py` as the fallback single source. `CHANGELOG.md` follows Keep a Changelog with PT-PT entries; the first bullet lines become `notes_pt` in `version.json`.

---

## 17. Website and DNS

### 17.1 Site

`site/index.html`, `sobre.html`, `changelog.html`, `style.css`, `version.json`, `CNAME` (`mimufs.com`). Hand-written HTML. The only JavaScript is an inline snippet of a few lines that highlights the visitor's OS download button. No external fonts, scripts or analytics.

### 17.2 Cloudflare DNS for GitHub Pages

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | 185.199.108.153 | DNS only |
| A | `@` | 185.199.109.153 | DNS only |
| A | `@` | 185.199.110.153 | DNS only |
| A | `@` | 185.199.111.153 | DNS only |
| AAAA | `@` | 2606:50c0:8000::153 … 2606:50c0:8003::153 (4 records) | DNS only |
| CNAME | `www` | `diogocarapito.github.io` | DNS only |

Then:

1. In the repo, go to *Settings › Pages*, set Source = GitHub Actions and the custom domain to `mimufs.com`, wait for the certificate, then tick **Enforce HTTPS**.
2. **Verify the domain** in your GitHub account settings (*Pages › Verified domains*, TXT record) to prevent takeover.
3. Keep Cloudflare on "DNS only" (grey cloud). Proxying can interfere with GitHub's certificate issuance. If you want to proxy later, use SSL mode **Full (strict)**.

---

## 18. Implementation plan (maps to PRD §11)

| Milestone | Engineering tasks | Done when |
|---|---|---|
| **M0** | Tag `legacy-autogui`; new layout and `pyproject`; netguard + update module; openpyxl reader (with compat patch) + format sniffing + header/filter parser; jlinked JRE + tabula smoke test on all 3 OSes; spec models + 3 sample specs; fixture generator; CI matrix; Briefcase bundles (zip, msi, dmg ×2, deb, flatpak) with `--selftest`; site skeleton + DNS + `version.json` | A bundle downloaded from mimufs.com launches on all 3 OSes and detects a newer test version |
| **M1 (PoC)** | HomePage + NewProjectDialog (Unidade, Médico, Descrição) → opens phase 02; dictionaries loaded (medication editable in DictionaryManager); parser passes on every sheet of `MIMUF_Header_examples.xlsx`; PhaseNav with sub-steps + footer navigation + "Rever e continuar" gate; SlotGrid + DropZone + InfoCard + IssueList + LogPanel; dark/light themes; ICPC copy helper; checks V01–V12, S01–S04; specs for P01.01.L01, P04.01.L01, P04.01.L05, P06.01.01.L03, P10.01.L01, P07.03.01.L01 | Deliberately broken fixtures produce the right 🟢/🟠/🔴 and messages in the UI |
| **M2** | Remaining specs; staging; patient spine; pivots; aggregates; join diagnostics; data dictionary | Golden dataset test passes; 30k × 800 < 30 s |
| **M3** | Rule engine; HbA1c resolver; labs + biometrics rules; RuleReview UI; audit log | Synthetic dirty-value suite passes; audit log complete |
| **M4** | Mapping store + MappingBoard; SClínico PDF reader (tabula, ported from Diogo's script) + CSV fallback; exports + pseudonymisation + manifest; settings; help | **v0.1.0** released via the pipeline |

---

## 19. Open technical questions and TODO

**Resolved 2026-11-24:** P07.03.01.L01 returns the last result only; quarters come from `Trimestre = YYYY-Tn`; deaths vs transfers are decided by manual review (§8, item 6); unit/"Total" handling is in §5.2; the ICPC filter accepts pasted lists (3 batches, §6.3); the target is all ICPC-2 codes; footers exist (`Total` row, confirmed format) and are removed (§5.2, V12); two-year projects use the long layout (§8); BI-CSP is excluded; the doctor name is set in Settings and per project; macOS Intel builds are in scope.

Open product questions are in PRD §12.2 (doctor pages, optional reports, 20 ICPC codes, glyxambi). Technical inputs are on the TODO lists below.

Also settled: the duplicate ICPC codes in set 2 were a mistake and have been removed (§6.3); footer numbers are discarded (no row-count check); HTTPS inspection on SPMS networks is assumed, so the update check always uses the OS certificate store (§13). If the check still fails behind a proxy, it fails silently and the user can download from the website.

**TODO**
- [ ] ICPC licensing: the app now ships the full ICPC-2 PT dictionary (names, criteria, notes) as Diogo asked; confirm redistribution is OK under WONCA/ACSS terms, or fall back to codes only + names from the user's exports.
- [ ] **Indicator dictionary updater** (`scripts/update_indicadores.py`, maintainer-only): port the scraping/PDF extraction from `github.com/diogocarapito/datasets_indicadores` (`scripts/extracao_indicadores_intervalos.py`, `sdm_crawler_scrapper.py`) to regenerate `indicadores_intervalos.csv`, print a diff, bump the version in `dictionaries.json`. Source file: https://github.com/diogocarapito/datasets_indicadores/blob/main/datasets/indicadores_intervalos_esperados_aceitaveis.csv
- [ ] Decide on the 20 ICPC codes not in the MIM@UF sets (PRD §12.2 item 3) and the doctor-page question (item 1).
- [ ] Confirm the real format of MIM@UF exports: openpyxl only reads OOXML, so if it opens them, they are `.xlsx` files with an `.xls` name. The sniffing in §5.0 handles both cases either way.

**TODO — Claude Code implementation step** (Diogo provides these when the implementation starts; until then the modules are written against the interfaces in §5.0.1 and §10.1, with tests marked `xfail`):
- [ ] **openpyxl patch**: the `openpyxl.worksheet._reader` code Diogo used to read MIM@UF exports, and the openpyxl version it was written for → `readers/openpyxl_compat.py`, version pinned in `pyproject.toml`.
- [ ] **Slot value names**: the exact `Exame MCDT` values for the 7 analyses (known: `651029:Colesterol total, s/l`) and the 5 `Tipo Dado` values (known: `Altura(Cm)`, `TAd`) → tighten the regexes in `P07.03.01.L01.yaml` / `P10.01.L01.yaml`. All other headers are done (§6).
- [ ] **MIM@UF click-paths** for every report's first instruction line (currently `TODO (Diogo)` in the specs).
- [ ] **SClínico PDF**: the `tabula.read_pdf(...)` call and the cleanup applied to its result (options such as `lattice`/`stream`/area, column names, removal of repeated page headers) → `readers/sclinico_pdf.py`.
