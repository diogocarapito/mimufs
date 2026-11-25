# mimufs — Product Requirements Document

| | |
|---|---|
| **Product** | mimufs — local desktop app for MIM@UF data ETL (and, later, visualization) |
| **Repository** | https://github.com/diogocarapito/mimufs (public, GPL-3.0) |
| **Website** | https://mimufs.com (GitHub Pages) |
| **Owner** | Diogo Carapito |
| **Status** | Draft v0.1 — MVP / proof of concept scope |
| **Date** | 2026-11-24 |

---

## 1. Summary

Family medicine units (USF/UCSP) in Portugal hold a large amount of clinical activity data in **MIM@UF**, but getting a usable, analysis-ready dataset out of it is slow and error-prone: dozens of reports, each with its own filters, some needing one extraction per month or quarter, some needing batches of ICPC codes, all exported as `.xls` files with a metadata block on top and inconsistent column headers.

**mimufs** is an open-source, cross-platform (macOS / Windows / Linux) desktop app that **guides a clinician, step by step, from "I have never used these MIM@UF reports" to a clean, validated, patient-level dataset**, entirely on their own computer. It checks every file the user imports, tells them exactly what is right or wrong with it, assembles all files into one dataset, helps them clean implausible values with transparent and reversible rules, and exports ready-made tables.

**Privacy is the core feature.** Patient data never leaves the machine. The only network call the app ever makes is an optional check for new versions.

## 2. Problem

1. **Knowing what to extract is hard.** The useful reports are spread across MIM@UF menus (P01–P10), each with its own filters. Users with little MIM@UF experience don't know which reports, filters or periods they need.
2. **Some reports need many extractions.** For example, new problems need 12 monthly files, prescriptions need 4 quarterly files, problem lists need several batches of ICPC codes, and biometrics and lab results need one file per data type.
3. **Mistakes go unnoticed.** Common mistakes include a wrong month, the wrong unit, a missing "C/ Med Fam" flag, a forgotten ICPC batch, a file silently truncated at the `.xls` row limit, or the same month imported twice. They only show up (if ever) at analysis time.
4. **Raw values are dirty.** Examples: HbA1c entered as `65` (missing decimal point), as `110` (average glucose in mg/dL), or in IFCC mmol/mol. Height may be in metres, and systolic/diastolic blood pressure may be swapped.
5. **Free-text categories differ per unit and per person.** Appointment types are one example.
6. **Existing workarounds** (Excel macros, ad-hoc Python, cloud tools) either need technical skills or send sensitive data somewhere it shouldn't go.

## 3. Goals and non-goals

### 3.1 Goals (MVP / proof of concept)

- G1. A guided, step-by-step **ETL workflow** with clear status at every step (green / orange / red).
- G2. **Per-report extraction instructions** written for novice MIM@UF users.
- G3. **Automatic validation** of every imported file (metadata *and* structure) with human-readable explanations.
- G4. A **per-report info card** summarising the relevant metadata. Multi-file reports (monthly, quarterly, batches) are merged into a single card.
- G5. **Aggregation** of all validated files into one patient-level dataset, about 30,000 patients × 700–800 columns.
- G6. **Data quality assessment and cleaning** for lab results and biometrics, with rule-based suggestions, user confirmation, original values kept, and a full audit log.
- G7. A **user-defined mapping tool** to standardise appointment types (and, later, other categorical fields).
- G8. **Output tables**: all USF patients; patients per doctor.
- G9. **100% local processing.** No telemetry and no third-party services.
- G10. An **update notifier**: checks whether a new version exists, shows a short changelog and asks whether to download it.
- G11. A **static website** on mimufs.com with downloads, an About page and a changelog.

### 3.2 Non-goals (MVP)

- Data visualization / dashboards (Phase 2).
- Automating MIM@UF itself (clicking through the platform). The earlier `pyautogui` experiment in the repo is retired; the app *guides*, the user *extracts*.
- Multi-user, servers, sync, cloud backups.
- Code signing / notarisation (users will see "unidentified developer" warnings; the website explains how to proceed).
- Languages other than PT-PT in the UI.
- Silent auto-update.

## 4. Users

| Persona | Context | Needs |
|---|---|---|
| **Novice clinician** (family doctor, nurse, intern) | Uses MIM@UF rarely, on an SNS PC managed by SPMS (Windows, usually **no admin rights**) | Exact click-by-click instructions; immediate "is this file right?" feedback; no installation hurdles |
| **Unit coordinator / quality lead** | Prepares annual unit reports, indicator reviews, audits | Complete, reproducible datasets for 1–2 years; per-doctor tables |
| **Analyst clinician** (e.g. Diogo) | Comfortable with Python/R | Clean exports (CSV/Parquet/XLSX), a transparent audit log, reproducible rules |

**Environments:** SPMS-managed Windows 10/11 PCs (no admin, possibly strict antivirus) and personal laptops (macOS Apple Silicon/Intel, Windows, Linux).

**UI language:** PT-PT. Code, docs, specs: English.

## 5. Product principles

1. **Local by design.** Nothing about patients ever leaves the computer. This must be demonstrable, not just promised (see TECH_SPECS §12).
2. **Guide, don't assume.** Every step says what to do, why, and how to know it worked.
3. **Never block silently.** Every orange or red state explains *what* is wrong, *where*, and *how to fix it*.
4. **Never destroy data.** Raw imports are kept as they were. Every correction is reversible and logged.
5. **Reproducible.** The same files plus the same rules and decisions always give the same dataset. Projects can be re-opened and re-run.
6. **Configuration over code.** Report definitions, validation rules and cleaning rules live in versioned data files (YAML), so new reports can be added without touching the app's code.

## 6. Core workflow

The app is a **linear wizard with a persistent step list**. Each step has a status badge, and later steps unlock when earlier ones pass.

**Navigation model (chosen UI direction: "B v2 — console"; mockups in `docs/ui/`).** Each phase below is a big step made of small **sub-steps**, and both live in the **left navigation bar**. Phases expand and collapse; locked phases can be expanded to preview their sub-steps. In phase 1, every report is a sub-step, and the phase ends with a "Rever e continuar" sub-step that acts as the gate. A footer has *Anterior / Seguinte* buttons and shows "Sub-passo n de N". The app behaves like a desktop application, not a web page. The window never scrolls as a whole; each pane (navigation, content, validation panel, log) scrolls on its own. A collapsible validation log sits at the bottom. **Dark and light themes** can be switched from the title bar, and the choice is remembered in settings.

```
0. Projeto  →  1. Extração & Importação  →  2. Agregação  →  3. Qualidade dos dados
           →  4. Normalização (tipos de consulta)  →  5. Tabelas & Exportação
           →  [Phase 2: 6. Visualização]
```

### 6.1 Step status model

| Status | Icon | Meaning | Can proceed? |
|---|---|---|---|
| **Valid** | 🟢 green check | All checks passed | Yes |
| **Warning** | 🟠 orange triangle | Usable but incomplete or suspicious (e.g. 11 of 12 months, a filter mismatch) | Yes, **after explicit acknowledgement** ("Continuar mesmo assim"), which is recorded in the project log |
| **Error** | 🔴 red danger | Cannot be used (wrong report, wrong unit, truncated, unreadable) | No, until fixed or the file is removed |
| **Pending** | ⚪ grey | Not started | — |
| **Optional/skipped** | ⚪ dashed | Report marked optional and skipped by the user | Yes |

A step's status is the worst status among its items, ignoring skipped optional items.

### 6.2 Landing page and Step 0 — New project

**Landing page ("Projetos")** — what the app shows on start when no project is open (mockup: `docs/ui/mimufs-ui-v2-home-*.png`):
- **Recent projects**: name (unit · year), doctor and description, folder path, progress ("Passo 02 · 9/18 relatórios" or "Concluído"), last opened. Click opens the project where it was left.
- Buttons **"+ Novo projeto"** (primary) and **"Abrir projeto…"** (pick a `.mimufs` file).
- **Dictionaries** card: medication, ICPC-2 and indicators, with counts and a "Gerir dicionários" button (§7.5).
- Privacy note: no data leaves the computer; the only connection is the update check.
- Clicking the `mimufs` name in the title bar returns to this page from any project.

**"Novo projeto" dialog** (modal, mockup: `docs/ui/mimufs-ui-v2-new-project-dark.png`):

| Field | Required | Notes |
|---|---|---|
| **Unidade** | yes | Exactly as it appears in MIM@UF (filter "Unidade Funcional"), e.g. `USF Exemplo`. Used by check V03 |
| **Médico** | yes | Doctor name as it appears in MIM@UF. Pre-filled from Settings (set on first launch); editable per project |
| **Descrição** | no | Free text, e.g. "Relatório anual da USF" |
| Ano | yes (pre-filled) | Previous year by default; options include a 2-year range (max 2) |
| Pasta do projeto | yes (pre-filled) | Default `~/Documentos/mimufs/<Unidade>_<Ano>`; "Escolher…" opens a folder picker |

- Inline validation: empty Unidade or Médico shows a message under the field and blocks creation.
- Warning shown in the dialog: *the folder will contain identifiable clinical data; keep it only on an encrypted disk.*
- **After "Criar projeto"**: the project folder and database are created, phase 01 "Projeto" is marked ✓ (its values stay editable there), and the app opens the **first sub-step of phase 02 (Extração & Importação)**, with every report "Por importar".
- After P01.01.L01 is imported, the app checks the doctor name against the doctors found in the file (`NOME: M 00000` format). If there's no exact match, it shows 🟠 with the closest names to pick from.
- A project = one folder holding a single project database file (`<name>.mimufs`), a `raw/` copy of every imported file, `exports/`, and `logs/`. Opening a project restores every step's state.

### 6.3 Step 1 — Extraction & Import (MVP focus)

The screen has three panes:

- **Left: report checklist**, grouped by source/theme. Each item shows a status icon and a progress counter (e.g. `P04.01.L05 · 9/12 meses`).
- **Centre: the selected report**:
  - **Why**: one line on what the report is used for in the dataset.
  - **How to extract**: numbered, click-by-click MIM@UF instructions, including the exact filters, any on-platform transformations, and screenshots (optional, added later).
  - **Required extractions ("slots")**: a grid of the expected files, e.g. Jan…Dec, T1…T4, ICPC batch 1…n, or one per Tipo Dado. Each slot shows its own status.
  - **Drop zone**: drag & drop one or many `.xls` files, or a folder. The app **auto-detects** which report and slot each file belongs to from its metadata, so the user doesn't need to name files.
- **Right: info card** (see §6.3.3) plus the list of validation issues for the selected file or slot.

Users can also drop *all* their files at once on a global drop zone; the app sorts them into reports and slots and lists any it couldn't recognise.

#### 6.3.1 Report catalogue (MVP)

Defaults below assume the project year is Y (e.g. 2024). Every MIM@UF row has a spec in `src/mimufs/core/specs/reports/<code>.yaml`, generated from the real headers in `docs/reference/MIMUF_Header_examples.xlsx` and checked against them column by column.

| # | Data | Source / code | Extractions ("slots") | Level | Required | Notes |
|---|---|---|---|---|---|---|
| 1 | Appointments carried out | SClínico Administrativo (PDF) | 1 per project year | event | yes | Read from the PDF with tabula (Diogo's script); CSV fallback (§7.1) |
| 2 | Registered patients by family doctor | P01.01.L01 Inscritos > Utente | **2**: Jan Y and Dec Y | patient | yes | Jan vs Dec shows who left the list; reason set by manual review (§6.4) |
| 3 | Patient data | P01.01.L03 Inscritos > Dados dos Utentes | 1 (Dec Y) | patient | yes | Nationality, education, profession, registration type, fee-exemption reason. **Morada, Código Postal and Telefone are dropped at import** |
| 4 | Current registration | P01.01.L04 Inscritos > Contactos Actuais | 1 (Dec Y) | patient | no | Registration date (`Data Inscrição`) and `Local` |
| 5 | Families | P01.01.L06 Famílias > Contactos Actuais | 1 (Dec Y) | family | no | Members per family. **No patient ID**: unit-level aggregate only |
| 6 | Unit indicators | P02.01.R01 | 1 (Dec Y) | unit | yes | ~200 indicators; two header rows (Num., Den., Valor); compared with the indicator dictionary |
| 7 | Indicators by doctor | P02.01.R03 | 1 (Dec Y) | doctor | yes | Same, per family doctor |
| 8 | Compliant / non-compliant patients | P02.01.R04 | 1 (Dec Y) | doctor | no | Cumpridores, não cumpridores, total per indicator and doctor |
| 9 | Problem list by patient | P04.01.L01 Problemas > Utente | **3 ICPC sets**: A01→H99 (205), K01→S73 (251), S74→Z29 (232) | patient | yes | Target = the 688 codes of the MIM@UF sets. The tutorial shows each set with a copy button; the app checks coverage |
| 10 | Top problems | P04.R06 Top Problemas > UF e Médico | 1 (Dec Y) | unit | no | |
| 11 | New problems by patient | P04.01.L05 Novos Problemas > Utente | **12**: one per month | patient-event | yes | |
| 12 | Episodes by ICPC | P05.R01 Episódios > Sexo e Grupo Etário | 1 (year Y) | doctor | no | Consultations per ICPC code; no patient IDs |
| 13 | Diabetes risk | P05.01.L02 Risco de Diabetes | 1 file listing **all months** of Y | patient | no | The filter lists the months; 🟠 if any month is missing |
| 14 | Medicines prescribed by patient | P06.01.01.L03 | files by **quarter or month** that together cover Y | patient-event | yes | Prescriber and group N3; also classified with the medication dictionary (§7.5) |
| 15 | Medicines by DCI and doctor | P06.01.R02 | 1 (year Y) | doctor | no | Includes costs (PVP, SNS) |
| 16 | Lab tests prescribed by patient | P07.01.01.L01 | 1 (year Y), `Area MCDT = ANÁLISES CLÍNICAS` | patient-event | yes | |
| 17 | Lab results by patient | P07.03.01.L01 | **one per analysis** (7): total cholesterol, HDL, triglycerides, LDL, HbA1c, creatinine, albuminuria | patient | yes | Filter `{Exame MCDT} = code:name` identifies the slot; last result of the period only |
| 18 | Biometrics by patient | P10.01.L01 | **one per Tipo Dado** (5): weight, height, systolic BP, diastolic BP, DM desde | patient | yes | Filter `{Tipo Dado} = …` (e.g. `Altura(Cm)`) identifies the slot |
| D1 | ICPC-2e v4.4 PT dictionary | SDM / ACSS | bundled | — | — | 726 codes with names, criteria, ICD-10 (§7.5) |
| D2 | Medication dictionary | Diogo | bundled, **user-editable** | — | — | Term → group → disease (§7.5) |
| D3 | Indicator dictionary | `datasets_indicadores` | bundled | — | — | Expected and acceptable ranges for 173 indicators (§7.5) |

Optional reports can be skipped (⚪ dashed) without blocking the gate. Expected volume: about **45 files per project** (2 + 1 + 1 + 1 + 3 + 3 + 1 + 12 + 1 + 1 + 4 + 1 + 1 + 7 + 5 + the SClínico PDF), up to **30,000 distinct patients**.

#### 6.3.2 Validation (per file and per report)

Each imported file is parsed into **metadata** (report code and title, filter expression, "Páginas" key/values) and **table** (header plus rows), then checked:

**File-level checks**

| ID | Check | Fail → |
|---|---|---|
| V01 | File is a readable `.xls`/`.xlsx` | 🔴 "Ficheiro ilegível ou não é um export do MIM@UF" |
| V02 | Report code recognised (e.g. `P01.01.L01`); if the title cell is damaged, the report is recognised by title text + header signature | 🔴 unknown report, or 🔴 "este ficheiro é o P01.01.L03, não o P01.01.L01" when dropped on the wrong report |
| V03 | Unit equals the project unit. The unit is read from the **filter** (`Unidade Funcional / Polo Hospitalar` or `Unidade Funcional`), because "Páginas" can show `Total` | 🔴 |
| V04 | Period (`Mês`) inside the project year and matching an expected slot | 🔴 outside year · 🟠 unexpected month |
| V05 | Filter expression and "Páginas" agree (e.g. filter `Mês = 2024-01` but page `Mês: 2024-12`). A page value of `Total` where the filter restricts the field is **not** a conflict | 🟠 "Filtro e páginas indicam meses diferentes" |
| V06 | Required filter/page values present (e.g. `Flag Médico Família = C/ Med Fam` for P01.01.L01; `Tipo Dado` for P10). **Doctor pages** (`Médico Familia`, `Médico de Registo`, `Médico Consulta`, `Médico`): `Total` ✓; the project's doctor ✓ with a note "só os dados de <médico>"; another doctor 🔴 "exportou a página de outro médico" | 🟠 or 🔴, set per report |
| V07 | Required columns present, in the expected positions (from the spec). Known untitled columns are named by position (e.g. `Nome`, `ICPC_Descricao`); `Métrica` columns are ignored | 🔴 missing required · 🟠 unexpected extra column |
| V08 | Row count > 0 | 🟠 "Relatório vazio" |
| V09 | Row count not at the format's row ceiling (1,048,576 for `.xlsx`-type files, which is what MIM@UF exports turned out to be; 65,536 for legacy `.xls`) | 🔴 "Exportação provavelmente truncada; divida a extração" |
| V10 | Patient ID present and well-formed (9-digit SNS number; falls back to NOP) | 🟠 with count of rows using the NOP fallback or with no ID |
| V11 | Same file / same slot imported twice | 🟠 duplicate; the user chooses which to keep |
| V12 | Footer row at the bottom of the table: first cell `Total`, empty middle cells, totals in the last columns (e.g. `Total … 23149 · 67.830`) | Removed automatically (status unchanged); its numbers are discarded. The info card shows "Rodapé removido"; the row is kept in the raw copy |

**Report-level (set) checks**

| ID | Check | Fail → |
|---|---|---|
| S01 | All required slots filled (12 months, Jan+Dec, all Tipo Dado / analyses), or, for month-coverage reports (P06.01.01.L03, P05.01.L02), all 12 months covered with no overlap | 🟠 list of missing slots or months · 🟠 overlapping months |
| S02 | ICPC coverage (P04.01.L01): union of the ICPC codes in all batch filters covers the target ICPC list | 🟠 list of missing codes · 🟠 codes in more than one batch (overlaps are fine but flagged) |
| S03 | Consistent unit and flags across all files of the report | 🔴 |
| S04 | Column structure identical across all files of the report | 🔴 |
| S05 | The project's doctor is one of the family doctors in P01.01.L01 (§6.2) | 🟠 with the closest names; one click uses the exact MIM@UF name |

Every issue message answers three questions: **what** is wrong, **where** (file, row/cell or slot), and **how to fix it** (e.g. "Volte ao MIM@UF, P04.01.L05, escolha Mês = 2024-07 e exporte novamente").

#### 6.3.3 Info card

For each report (multi-file reports merged into one card):

- Code, title, source, level (patient/doctor/unit)
- Unit, period covered (e.g. `2024-01 → 2024-12`, with gaps highlighted)
- Filters applied (parsed and readable, e.g. "Flag Médico Família: C/ Med Fam")
- Files: count, names, import date
- Rows: total, per slot; distinct patients; rows using the NOP fallback
- Columns detected (with renamed/blank headers noted)
- Report-specific extras: ICPC codes covered (n / target), Tipo Dado list, doctors found
- Status and an issue summary

The card can be exported as a short text/Markdown summary (useful as methods documentation).

### 6.4 Step 2 — Aggregation

- One click: **"Construir dataset"**. Runs only when all *required* reports are green or acknowledged orange.
- Builds:
  - **Patient dataset**: one row per patient **per project year** (*long* layout: a 2-year project has two rows per patient, with an `ano` column; a 1-year project has one), about 700–800 columns (demographics, list status Jan/Dec, nationality, household, ICPC problems, new problems by month, diabetes risk, medication groups, MCDTs, lab results, biometrics, appointment counts by standardised type).
  - **Event tables** (long format): problems, new problems, prescriptions, MCDTs, appointments.
  - **Aggregate tables**: unit indicators (with expected/acceptable ranges), indicators by doctor, top problems, acute problems by doctor, medicines by doctor.
- Shows **join diagnostics**: patients matched by SNS number vs by NOP fallback, patients present in clinical reports but absent from P01.01.L01 (orange), and duplicate IDs (red).
- **Sub-step "Saídas da lista" (manual review)**: lists every patient registered in January but not in December (P01.01.L01). The user checks each case in the EHR and sets the reason: *óbito*, *transferência*, *outro* or *por rever*. It shows name, SNS number, family doctor, age and the last clinical activity found in the other reports, to help the search. The decisions are stored in the project and logged in the audit log, and they create `dem_saida_motivo` in the dataset. The sub-step is 🟢 when no case is *por rever*, and 🟠 when the user acknowledges the open cases. The list can be exported (XLSX) for review at the desk.
- Shows a **dataset summary**: rows, columns by group, % missing per column group.

### 6.5 Step 3 — Data quality

For each variable (MVP: **lab results** and **biometrics**):

- **Profile**: n, missing %, min/median/max, a histogram (simple, in Qt), and the count of values outside the plausible range.
- **Rules**: each variable has an ordered list of detection and correction rules (see TECH_SPECS §9). Each rule shows:
  - how many values it flags,
  - the suggested correction with a short explanation (e.g. *"110 → 5,5 % (assumido glicemia média estimada em mg/dL: (110+46,7)/28,7)"*),
  - a confidence level (high / ambiguous).
- **Review table** of flagged values: patient (pseudonymised display optional), original value, suggested value, rule, and an action (accept / reject / edit manually / set missing).
- **Batch actions**: accept all high-confidence suggestions of a rule; ambiguous values always need a per-value or per-group decision.
- **Original values are kept**: the dataset stores `value_raw`, `value_clean` and `correction_id`. Every change goes into an **audit log** (who, when, rule, from → to), which can be exported.
- Rule parameters (ranges, thresholds) can be edited per project, and edits are logged.

MVP variables: total cholesterol, HDL, triglycerides, LDL, HbA1c, creatinine, albuminuria, weight, height, systolic BP, diastolic BP, "DM desde" (year). Derived variables (BMI, and optionally eGFR CKD-EPI 2021 and Friedewald LDL) are computed **after** cleaning, from clean values.

Step status: 🟢 when no unresolved flags remain (values accepted, corrected or explicitly kept as-is); 🟠 when unresolved flags remain and the user acknowledges them.

### 6.6 Step 4 — Normalisation (appointment types)

- The app lists all **distinct raw values** of the appointment type field with their frequencies.
- The user creates **their own target categories** (e.g. "Presencial – Saúde Adulto", "Não presencial", "Domicílio") and assigns raw values to them with multi-select, search, drag & drop, and "suggest by keyword" (e.g. everything containing "DOMIC").
- Unmapped values are listed. The step is 🟢 when every value with ≥1 occurrence is mapped (or explicitly mapped to "Ignorar").
- Mappings are **personal and reusable**: saved in the user's app settings (not inside the project) and applied to the next project. They can be exported and imported as JSON to share with colleagues.
- The tool is generic, so the same component can later normalise other categorical fields.
- In the MVP the data comes from the SClínico appointments PDF (or its CSV fallback) — see §7.1.

### 6.7 Step 5 — Tables & Export

- **Table A — All USF patients**: the full patient dataset, all columns.
- **Table B — Patients of the project's doctor** (the name set in §6.2): the same columns, filtered to that doctor's list (family doctor in P01.01.L01). Once the SClínico importer exists, a second variant adds "patients *seen* by this doctor" (from appointments). An option exports Table B for **every** doctor of the unit (one sheet/file each), for coordinators.
- **Aggregate tables** (indicators, top problems, etc.).
- Formats: **XLSX** and **CSV** (default), **Parquet** (optional, for analysts). Options: include raw columns as well as clean ones; include the audit log; **pseudonymise** the SNS number (salted hash) or drop names.
- Data dictionary: a generated sheet/file describing every column (source report, rule, unit).
- Export summary: files written, sizes, timestamp, app version, rule-set version (for reproducibility).

### 6.8 Phase 2 — Visualization (out of MVP scope)

The project database and the patient dataset are designed so that a Visualization step can be added without changing the ETL: unit indicators vs expected ranges, per-doctor comparisons, problem prevalence, control of chronic conditions (e.g. % HbA1c < 8 %), age/sex pyramids. The library choice (pyqtgraph vs Matplotlib/QtAgg) will be made in Phase 2.

## 7. Supporting features

### 7.1 SClínico importer

- Step 1 lists "Lista de consultas realizadas (SClínico)" as a report.
- The user drops the **PDF** exported from SClínico Administrativo. The app reads it locally with tabula (it ships its own Java, so nothing needs installing), using the logic from Diogo's working script.
- Fallback: a CSV with the documented columns, for when the PDF can't be read.
- Until the importer exists (M4), the report is listed with a note and does **not** block "Rever e continuar" (decided 2026-11-25, so the M1 gate can be passed).

### 7.2 Update notifier

- **On by default.** At start-up (at most once every 24 h), the app fetches `https://mimufs.com/version.json`. The request carries no identifiers, cookies or usage data, only the app version in the User-Agent.
- If a newer version exists, a non-blocking dialog shows the version, release date and a short changelog (PT-PT), with buttons: **Descarregar** (opens the download page in the browser), **Lembrar mais tarde**, **Ignorar esta versão**.
- Settings: turn off automatic checks entirely; silence notifications for a specific version; "Verificar agora" button.
- If offline, it fails silently (logged locally).

### 7.3 Settings

Doctor name (as in MIM@UF, used for new projects); dictionaries (§7.5); update check on/off; default export format; default rule-set edits; personal mappings (manage/import/export); interface theme (dark / light / follow system); "Sobre" (version, license, privacy statement, links).

### 7.4 Help

- Contextual help on each step.
- A local, bundled "Como funciona" page: no web views, no external links needed to use the app.

### 7.5 Dictionaries

Three reference dictionaries ship with the app (`src/mimufs/core/reference/dictionaries/`, see its README). They are never downloaded by the app; new versions come with app updates.

| Dictionary | Content | Used for | Editable by the user |
|---|---|---|---|
| **Medicamentos** | Term (brand or DCI) → clinical group (e.g. "inibidor de SGLT2") → disease (`diabetes`, `hta`) | Patient columns per group and disease from P06.01.01.L03 (and P06.01.R02); combination products get all their groups | **Yes**: add, edit, delete rows; import/export CSV; "Repor original". Edits live in the user's settings and are reused by every project |
| **ICPC-2 (v4.4 PT)** | 726 codes: names, short names, inclusion/exclusion criteria, notes, ICD-10 | Readable names and descriptions in the app and in exports; derived names for chapter + process codes (e.g. A44) | No (view and search) |
| **Indicadores** | 173 indicators with expected and acceptable ranges | Flagging unit and doctor indicators outside the ranges (P02.*) | No (view); updated by the maintainer |

- **"Gerir dicionários"** screen (from the landing page and Settings): one tab per dictionary, a searchable table, and for medication the edit actions above plus an **"Não classificados"** list: medication names from the current project that match no term, so the user can add them.
- Every project records the dictionary versions it used, so a project can always be reproduced.

## 8. Website (mimufs.com)

Plain HTML + one CSS file, minimal style, hosted on GitHub Pages with the custom domain (DNS on Cloudflare). PT-PT.

- **Início**: one-paragraph pitch, the privacy promise, **download buttons** per OS (the visitor's OS is auto-detected and highlighted), short install notes for unsigned builds (macOS "Abrir mesmo assim", Windows SmartScreen "Executar mesmo assim", Linux `.deb` or `flatpak install --user`).
- **Sobre**: what it does, who made it, license, how to contribute, privacy statement.
- **Changelog**: generated from `CHANGELOG.md` at release time.
- `version.json`: machine-readable latest version, used by the app.

No analytics, cookies or third-party scripts/fonts on the website either.

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| **Privacy** | No outbound network traffic except the update check (verified by automated test). No telemetry, crash reporting or remote fonts/web views. Logs never contain patient data. |
| **Platforms** | Windows 10/11 x64; macOS 14+ (Apple Silicon **and Intel**; raised from 12+ on 2026-11-24 to use current Qt); Linux x86_64 (`.deb` and Flatpak) **deferred to a later release** (decided 2026-11-25; the first releases ship Windows and macOS only). |
| **No admin rights** | Windows **portable ZIP** that runs from the user folder or a USB drive, plus a per-user installer that needs no admin. |
| **Performance** | Import and validate 100 files in < 60 s; build the dataset (30k × 800) in < 30 s; UI stays responsive (long work runs in background with progress). Target machine: 8 GB RAM, 4-core laptop. |
| **Reliability** | Projects saved after every completed action; crash-safe (no partial writes). |
| **Reproducibility** | Every export records the app version, rule-set version and audit log hash. |
| **Accessibility** | Status is never shown by colour alone (icon + text); keyboard navigable; min. 12 pt text. |
| **Licensing** | GPL-3.0; all dependencies GPL-compatible. |
| **Size** | Installer ≤ 250 MB per platform. |

## 10. Success criteria for the proof of concept

1. On a fresh SPMS-managed Windows PC (no admin), a novice user can download the portable ZIP, run it, create a project and import the P01, P04.01.L05 (12 months) and P10 (all Tipo Dado) reports, with correct green/orange/red feedback for deliberately broken test files.
2. The app builds a patient dataset that matches a hand-built reference dataset for the same files.
3. HbA1c and biometric cleaning suggestions are correct on a synthetic test set, and every change appears in the audit log.
4. A network-blocked test run of the full pipeline passes.
5. mimufs.com serves the downloads, About page and changelog, and the app detects a newer test version.

## 11. Release plan

| Milestone | Content |
|---|---|
| **M0 — Foundations** | Repo restructure, core/GUI split, report spec format, `.xls` reader and metadata parser, synthetic fixtures, CI builds for 3 OSes, website skeleton plus `version.json` |
| **M1 — PoC: Extraction & Import** | Landing page + new-project dialog, dictionaries (medication editable), report checklist, instructions, drop zone, auto-detection, validation V01–V12 / S01–S04, info cards (5–6 reports) |
| **M2 — Aggregation** | All MIM@UF reports in the catalogue, patient dataset, aggregate tables, join diagnostics |
| **M3 — Quality** | Rule engine, labs and biometrics rules, review UI, audit log |
| **M4 — Normalisation & Export** | Mapping tool, SClínico PDF importer (+ CSV fallback), tables A/B, exports, data dictionary → **v0.1.0 public release** |
| **Phase 2** | Visualization, more variables, more reports |

## 12. Open questions and TODO

### 12.1 Resolved (2026-11-24)

- **P07.03.01.L01**: returns only the **last result** of the period per patient, so the HbA1c resolver has no earlier values to compare against.
- **Deaths vs transfers**: decided by **manual review in the EHR** (sub-step "Saídas da lista", §6.4).
- **Quarters (P06.01.01.L03)**: filter `Trimestre = YYYY-Tn` and page `Trimestre: YYYY-Tn`. In this report the unit appears as `{Unidade Funcional}` in the filter and `Unidade Funcional: Total` in "Páginas".

- **ICPC filter**: MIM@UF accepts a **pasted list** of about 250 codes, so all ICPC-2 codes fit in **3 extractions**. The tutorial shows the 3 code sets with a "Copiar códigos" button each.
- **Paste format**: codes only, separated by `, ` (from the working lists Diogo supplied: 688 unique codes in 3 sets, shipped as `reference/icpc_mimuf_batches.json`).
- **ICPC target list**: **all** ICPC-2 codes, even ones no patient has.
- **Footers**: some exports have them: a `Total` row with totals in the last columns. They are detected and removed (check V12).
- **Two-year projects**: *long* layout, one row per patient per year.
- **BI-CSP**: excluded from the MVP.
- **Doctor**: set once at first launch and in Settings, pre-filled in each project; Table B uses it.
- **macOS Intel**: yes, build it.

- **ICPC duplicates**: the repeated `K87` and `P76` in set 2 were a mistake and have been removed (set 2 = 251 codes).

- **Report headers**: real headers for all 17 MIM@UF reports received (`docs/reference/MIMUF_Header_examples.xlsx`); specs generated and checked against them. New reports added: P01.01.L04, P02.01.R04; P06.01.L02 corrected to **P06.01.R02**; P05.R01 is "Episódios > Sexo e Grupo Etário".
- **Landing page and new-project dialog** (Unidade, Médico, Descrição): §6.2.
- **Dictionaries** (medication, ICPC-2, indicators): §7.5.

### 12.2 Still open

1. **Doctor pages**: in the header examples, P04.01.L05 (`Médico de Registo`), P05.R01 (`Médico Consulta`), P06.01.R02 (`Médico`) and P07.01.01.L01 (`Médico`) were exported with **one specific doctor** selected. Should these be extracted for the **whole unit** (`Total`) or for the **project's doctor**? Until decided, both are accepted (check V06) and another doctor is an error.
2. **Optional reports**: P01.01.L04, P01.01.L06, P02.01.R04, P04.R06, P05.R01, P05.01.L02 and P06.01.R02 are marked optional. Confirm which should be required.
3. **ICPC codes missing from the MIM@UF sets**: 20 dictionary codes are not in the 3 sets (A07, A20, A96, B26, F17, H79, L26, N72, P05, S28, T11, W17, W21, W70, W72, W73, W75, W95, W96, X10). MIM@UF offers at least A96 (Morte) and B26, so problems with these codes are not extracted today. Add them to the sets (checking each set still fits MIM@UF's paste limit)?
4. **Medication dictionary**: `glyxambi` was listed as biguanida + SGLT2; it contains empagliflozina + linagliptina (no metformin), so it was changed to SGLT2 + DPP-4. Confirm.

### 12.3 TODO

- [ ] **ICPC-2 PT licensing**: the app now only needs to ship the **bare codes** (the 3 MIM@UF sets). Descriptions can come from the user's own P04.01.L01 exports (the column after `ICPC`). Still to check: is shipping a list of ICPC-2 codes, with no descriptions, OK under WONCA copyright? Fallback: the user pastes or imports the list on first run.
- [ ] **Indicator dictionary updater**: maintainer-only script that re-scrapes the SDM / contracting PDF (logic from `datasets_indicadores`) and regenerates `indicadores_intervalos.csv` with a diff and a version bump. Never run by the app. Source: https://github.com/diogocarapito/datasets_indicadores/blob/main/datasets/indicadores_intervalos_esperados_aceitaveis.csv
- [ ] **Claude Code implementation step**: Diogo provides (1) the `openpyxl.worksheet._reader` code and the openpyxl version used, (2) the exact names of the 7 analyses (`Exame MCDT`, only `651029:Colesterol total, s/l` is known) and the 5 `Tipo Dado` values (only `Altura(Cm)` and `TAd` are known), and (3) the `tabula.read_pdf(...)` call plus the cleanup of its result (options, column names, removal of repeated page headers). See TECH_SPECS §19.
