# UI reference: direction "B v2"

The chosen UI direction for mimufs. Open the HTML files in any browser. They work offline (fonts fall back to system fonts) and are interactive.

| File | What it is |
|---|---|
| `mimufs-ui-v2-dark.html` | Interactive mockup, dark theme by default (sun/moon button in the title bar switches theme). Starts on the **landing page**: try "+ Novo projeto" (dialog with validation → opens phase 02 with everything "Por importar") or click a recent project (shows a project mid-way, with all statuses) |
| `mimufs-ui-v2-light.html` | The same mockup, light theme by default |
| `mimufs-ui-v2-home-dark.png`, `mimufs-ui-v2-home-light.png` | Landing page |
| `mimufs-ui-v2-new-project-dark.png` | New-project dialog (with a validation message) |
| `mimufs-ui-v2-dark.png`, `mimufs-ui-v2-light.png` | A project in phase 02 (report sub-step with issues) |

Editable source (design canvas): https://claude.ai/artifact/1Rq6Kpb3FstmpNVF9Fp4iJ (artboards "B v2 · escuro", "B v2 · claro" and "B v2 · início e novo projeto").

## What to take from it

These are **reference mockups, not code to port**. The real UI is PySide6 (Qt Widgets); see `docs/TECH_SPECS.md` §14 for the widget mapping.

Match:
- **Landing page + "Novo projeto" dialog**: Unidade*, Médico* (pre-filled), Descrição, Ano, Pasta; on create, open phase 02 at its first sub-step.
- **Window model**: fixed desktop window; the window never scrolls, each pane scrolls on its own (left nav, content, validation pane, log).
- **Navigation**: left nav = phases (01–06) with **sub-steps**; phases expand and collapse; locked phases can be expanded to preview. Phase 02's sub-steps are the reports, grouped by theme, plus a final **"Rever e continuar"** gate.
- **Footer**: ‹ Anterior · "Sub-passo n de N" · Seguinte ›; on the last sub-step, the next phase button stays locked until the gate passes.
- **Report screen**: code/source/level line, title, purpose; "Extrações necessárias" slot tiles; "Como extrair do MIM@UF" numbered steps; ICPC copy helper (P04.01.L01 only); drop zone; right pane with "Diagnóstico" (issues with what/where/how-to-fix) and "Metadados" (info card).
- **Log panel**: collapsible validation log at the bottom.
- **Status language**: icon + colour + label, never colour alone (✓ Válido, ⚠ Incompleto, ⛔ Erro, ○ Por importar, 🔒 Bloqueado).
- **Themes**: dark and light share one set of token names, listed below.

| Token | Dark | Light |
|---|---|---|
| bg | `#0E1116` | `#F4F5F7` |
| chrome | `#0B0D11` | `#E9ECF0` |
| panel | `#141921` | `#FFFFFF` |
| panel2 | `#10141A` | `#F8F9FA` |
| border | `#232A35` | `#D6DBE1` |
| line | `#1E252F` | `#E6E9ED` |
| text | `#D7DDE4` | `#1F2630` |
| strong | `#F1F4F8` | `#0E1116` |
| muted | `#8B95A3` | `#59626F` |
| accent | `#FBBF24` | `#B45309` (text `#9A4708`) |
| ok / warn / err / pend | `#4ADE80` / `#FBBF24` / `#F87171` / `#8B95A3` | `#15803D` / `#B45309` / `#B91C1C` / `#6B7280` |

Fonts: Inter (UI), JetBrains Mono (codes, labels, log). Both are bundled with the app (OFL); no remote fonts.

All data in the mockup (counts, names such as "Ana Sousa", messages) is **fictional** and only illustrates states. The MIM@UF menu paths in the instructions are placeholders, to be replaced with the real click-by-click steps.
