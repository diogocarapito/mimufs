# Bundled dictionaries

Reference data shipped **inside** the app. The app never downloads them: new versions arrive only with app updates (privacy rule: no network except the update check). See `docs/TECH_SPECS.md` §10.2.

| File | Content | Source | Editable in the app? |
|---|---|---|---|
| `medicamentos.csv` | Medication term → clinical group → disease | Diogo (2026-11-24) | **Yes**: Settings › Dicionários › Medicamentos (user copy) |
| `icpc2_pt_v4_4.csv` | ICPC-2e v4.4 PT: 726 codes (686 symptoms/diagnoses + 40 process codes), with names, inclusion/exclusion criteria, notes, ICD-10 | SDM / ACSS, 2015-03-27 | No (view and search only) |
| `indicadores_intervalos.csv` | 173 indicators with expected and acceptable ranges | `github.com/diogocarapito/datasets_indicadores` (`datasets/indicadores_intervalos_esperados_aceitaveis.csv`, commit `5c05426`, 2024-10-24) | No (view only; updated by the maintainer, see TODO) |
| `../icpc_mimuf_batches.json` | The 3 ICPC code sets pasted into MIM@UF (688 codes) | Diogo | No |

## medicamentos.csv

Columns: `medicamento` (term matched against the MIM@UF medication name), `grupo`, `doenca`.

- **Matching**: lower-case, accents removed, whole-word match of the term inside `Medicamento/CNPEM` (P06.01.01.L03) or `Medicamento`/`DCI` (P06.01.R02). A name can match several terms, and a term can appear in several rows. Combination products therefore get every group they belong to (e.g. `xigduo` → SGLT2 + biguanida).
- **Unmatched names** are listed in the app so the user can add them.
- Changes made when importing Diogo's file:
  - column `doneça` renamed to `doenca`;
  - `biaguanida` corrected to `biguanida`;
  - `glyxambi` (empagliflozina + linagliptina) moved from `biguanida` to **`inibidor de DPP-4`** (it was listed as biguanida + SGLT2, but contains no metformin). Revert in the app if this was intended.
- Known gaps to fill later (not added): e.g. semaglutido (oral), tirzepatido, glimepirida, alogliptina/saxagliptina, insulina glargina brands (Toujeo), clortalidona (generic), felodipina, diltiazem, captopril/fosinopril/quinapril.

## icpc2_pt_v4_4.csv

Columns: `cod, componente, nome, nome_curto, incl, excl, crit, cons, nota, icd10`. Process codes are stored as `-30`…`-69`.

Differences found against the MIM@UF code sets (`icpc_mimuf_batches.json`):
- **22 codes in the MIM@UF sets are not in this dictionary**: A30, A31, A34, A37, A44, A50, A57, A60, A62, B59, B60, B62, D51, D52, L43, L50, L59, L61, L62, R52, W52, X53. They are **process codes with a chapter letter** (e.g. `A44` = chapter A + process `-44` "Vacinação/medicação preventiva"). The app derives their name from the process code (`-NN`) plus the chapter.
- **20 dictionary codes are not in the MIM@UF sets**: A07, A20, A96, B26, F17, H79, L26, N72, P05, S28, T11, W17, W21, W70, W72, W73, W75, W95, W96, X10. MIM@UF does offer at least A96 (Morte) and B26 (they appear in a real P04.01.L01 filter), so problems coded with these are currently **not extracted**. Decision pending (TODO).

## indicadores_intervalos.csv

Columns: `id_indicador, nome_indicador, intervalo_aceitavel, intervalo_esperado, min_esperado, max_esperado, min_aceitavel, max_aceitavel`. Joined to P02.01.R01/R03/R04 by indicator id. Licence of the source repo: Apache-2.0 (compatible with GPL-3.0).

**TODO**: the source is built by scraping the SDM and the contracting PDF (`scripts/extracao_indicadores_intervalos.py` and `sdm_crawler_scrapper.py` in the source repo). Add a **maintainer-only** script `scripts/update_indicadores.py` that regenerates this file (run by hand or in CI, never by the app), shows a diff, and bumps the dictionary version.

## Versioning

Each dictionary has a version (`dictionaries.json` manifest: file, version, sha256, source, date). Every project snapshots the dictionary versions it used, so a project stays reproducible when the dictionaries change.
