# MIM@UF export header samples

Real header blocks from `docs/reference/MIMUF_Header_examples.xlsx` (one sheet per report), shared by Diogo on 2026-11-24. Unit anonymised as `USF Exemplo`, periods as `2000-xx`, doctors as `NOME MEDICO: M 00000`. **No patient rows.**

The report specs in `src/mimufs/core/specs/reports/*.yaml` were generated from this workbook and checked against it column by column (see `docs/TECH_SPECS.md` §6). Use the workbook directly as a parser test fixture.

`⟂` = empty cell. `[cN]` = 0-based column index. Titles keep the literal `&gt;`/`&lt;` HTML escapes as found in the files.

## Parser rules learned from these headers

1. Unescape HTML entities (`&gt;` `&lt;` `&amp;`) in every metadata cell before parsing.
2. Title regex `^(P\d{2}(?:\.\d{2}){0,2}\.[LR]\d{2})\.\s*(.+)$`; if it fails, identify the report by title text + header signature.
3. Filter: clauses may or may not be wrapped in parentheses; joined by ` E `; operators `=`, `<>`, `>`, `<`, `>=`, `<=`; keys may be wrapped in `{}` and may carry a suffix such as ` (ID)`; values can be lists (`, `-separated) and can contain commas, slashes and parentheses (split ICPC lists with `,\s*(?=[A-Z]\d{2}:)`).
4. Páginas lines use `Key: Value` **or** `Key = Value`; split on the first separator only (values such as `NOME MEDICO: M 00000` contain `:`). Some reports have **no Páginas** section.
5. Header row = the first row with ≥ 2 non-empty cells after the metadata. Some reports have **two header rows** (P02.*). The first header cell varies (`NOP`, `Local`, `ICPC`, `Medicamento/CNPEM`, `DCI (CNPEM)`, `Exame MCDT`, `Mês`, `Unidade Funcional / Polo Hospitalar`).
6. Untitled header cells are real columns (names, descriptions): name them from the spec by position.
7. `Métrica` columns are layout artefacts: ignore them.
8. Doctor page fields (`Médico Familia`, `Médico de Registo`, `Médico Consulta`, `Médico`): `Total` = whole unit; a specific doctor = only that doctor's page was exported (see check V06 in the PRD).
9. The unit can come from the filter, from Páginas, or only from a data column (P02.*).
10. A trailing `Total` row is a footer (V12), not data.

## P01.01.L01

```
P01.01.L01. Inscritos &gt; Utente
⟂
Filtro do relatório:
(Mês = 2000-01) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)
⟂
Páginas:
Mês: 2000-01
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: C/ Med Fam
Frequentador: Total
Grupo Etário: Total
⟂
[c0] NOP | [c1] Utente | [c2] ⟂ | [c3] Sexo | [c4] Idade | [c5] Data Nascimento | [c6] Médico Familia | [c7] Freguesia Habitação
```

Notes: Extracted twice (Jan + Dec). Untitled column 2 = patient name → `Nome`.

## P01.01.L03

```
1.01.L03. Inscritos &gt; Dados dos Utentes
⟂
Filtro do relatório:
(Mês = 2000-12) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)
⟂
Páginas:
Mês: 2000-12
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: Total
Enfermeiro de Família: Total
⟂
[c0] NOP | [c1] Tipo de inscrição atual | [c2] Utente | [c3] ⟂ | [c4] Sexo | [c5] Idade | [c6] Data Nascimento | [c7] Médico Familia | [c8] Motivo Isenção Tx. Moderadora | [c9] Morada | [c10] Código Postal | [c11] Telefone | [c12] Freguesia Habitação | [c13] País de Nacionalidade | [c14] Habilitacao Literaria | [c15] Profissao
```

Notes: ⚠ The title cell in this example reads `1.01.L03.` (leading `P0` missing — probably a copy/edit slip; the parser falls back to matching the title text and the header signature). Columns `Morada`, `Código Postal`, `Telefone` are **dropped at import** (not needed; data minimisation).

## P01.01.L04

```
P01.01.L04. Inscritos &gt; Contactos Actuais
⟂
Filtro do relatório:
(Mês = 2000-12) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)
⟂
Páginas:
Mês: 2000-12
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: Total
Frequentador Actual: Total
⟂
[c0] Local | [c1] NOP | [c2] Utente | [c3] ⟂ | [c4] Sexo | [c5] Data Nascimento | [c6] Idade | [c7] Médico Familia | [c8] Freguesia Habitação | [c9] Data Inscrição
```

Notes: Header starts with `Local`, not `NOP`.

## P01.01.L06

```
P01.01.L06. Famílias &gt; Contactos Actuais
⟂
Filtro do relatório:
(Mês = 2000-11) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)
⟂
Páginas:
Mês: 2000-11
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: Total
Médico Familia: Total
Frequentador Actual: Total
⟂
[c0] Local | [c1] Família | [c2] Nº Utentes Familia
```

Notes: Family-level: **no patient ID**. Used only as a unit-level aggregate. Sample month is 2000-11.

## P02.01.R01

```
P02.01.R01. Indicadores da unidade funcional
⟂
Filtro do relatório:
(Mês = 2000-12) E ({Tipo Indicador} = Acompanhamento Adequado, DGS, Grupos de Diagnósticos Homogéneos, NOVOS, Indicadores com o conceito de padronização, Indicadores USF/UCSP e UCC, Agregado Familiar, Morbilidade) E ({Ano Contratual} = 2000) E ({Grupo de Indicadores} = Todos os Indicadores)
⟂
Páginas:
Ano Contratual: 2000
Tipo FX/FL: FLUTUANTE
Grupo de Indicadores: Todos os Indicadores
Com ou Sem MdF: TOTAL
⟂
[c0] Unidade Funcional / Polo Hospitalar | [c1] Indicador | [c2] ⟂ | [c3] ⟂ | [c4] ⟂ | [c5] Mês | [c6] 2000-12 | [c7] 2000-12 | [c8] 2000-12
[c0] ⟂ | [c1] ⟂ | [c2] ⟂ | [c3] ⟂ | [c4] ⟂ | [c5] Métrica | [c6] Num. | [c7] Den. | [c8] Valor
```

Notes: **Two header rows**: row 1 = dimensions + `Mês` + the month above each metric; row 2 = `Métrica` + metric names. No unit in Páginas (unit is a column). Untitled columns 2–4: content to confirm with a real file.

## P02.01.R03

```
P02.01.R03. Indicadores por lista de utentes de médico
⟂
Filtro do relatório:
(Mês = 2000-12) E ({Tipo Indicador} = Acompanhamento Adequado, DGS, Grupos de Diagnósticos Homogéneos, NOVOS, Indicadores com o conceito de padronização, Indicadores USF/UCSP e UCC, Agregado Familiar, Morbilidade) E ({Ano Contratual} = 2000) E ({Grupo de Indicadores} = Todos os Indicadores)
⟂
Páginas:
Ano Contratual: 2000
Tipo FX/FL: FLUTUANTE
Grupo de Indicadores: Todos os Indicadores
Com ou Sem MdF: TOTAL
⟂
[c0] Unidade Funcional / Polo Hospitalar | [c1] Indicador | [c2] ⟂ | [c3] ⟂ | [c4] Médico Familia | [c5] ⟂ | [c6] Mês | [c7] 2000-12 | [c8] 2000-12 | [c9] 2000-12
[c0] ⟂ | [c1] ⟂ | [c2] ⟂ | [c3] ⟂ | [c4] ⟂ | [c5] ⟂ | [c6] Métrica | [c7] Num. | [c8] Den. | [c9] Valor
```

Notes: Two header rows, like R01, plus `Médico Familia` (col 4) and an untitled col 5.

## P02.01.R04

```
P02.01.R04. Indicadores por lista de utentes de médico - cumpridores e não cumpridores
⟂
Filtro do relatório:
({Alvo Indicador} = Utente) E ({Tipo Indicador} &lt;&gt; ACES, Indicadores das Unidades de Cuidados na Comunidade) E (Mês = 2000-02) E ({Ano Contratual} = 2000) E ({Grupo de Indicadores} = Todos os Indicadores)
⟂
Páginas:
Ano Contratual: 2000
Tipo Indicador: FLUTUANTE
Grupo de Indicadores: Todos os Indicadores
Com ou Sem MdF: CSP com médico
⟂
[c0] Unidade Funcional / Polo Hospitalar | [c1] Indicador | [c2] ⟂ | [c3] ⟂ | [c4] Médico Familia | [c5] ⟂ | [c6] Mês | [c7] 2000-02 | [c8] 2000-02 | [c9] 2000-02
[c0] ⟂ | [c1] ⟂ | [c2] ⟂ | [c3] ⟂ | [c4] ⟂ | [c5] ⟂ | [c6] Métrica | [c7] Utentes Cumpridores | [c8] Utentes Não Cumpridores | [c9] Total Utentes
```

Notes: Two header rows; metrics = cumpridores / não cumpridores / total. Filter uses `&lt;&gt;` (≠) and `{Alvo Indicador}`.

## P04.01.L01

```
P04.01.L01. Problemas &gt; Utente
⟂
Filtro do relatório:
(Mês = 2000-12) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo) E (ICPC = A76:OUTRO EXANTEMA VIRAL, A77:OUTRA DOENÇA VIRAL, NE, A78:OUTRA DOENÇA INFECCIOSA, NE, A79:CARCINOMATOSE (LOCALIZAÇÃO PRIMÁRIA DESCONHECIDA), NE, A80:LESÃO TRAUMÁTICA / ACIDENTE, NE, A81:POLITRAUMATISMOS / FERIMENTOS MÚLTIPLOS, A82:EFEITO SECUNDÁRIO DE UMA LESÃO TRAUMÁTICA, A84:INTOXICAÇÃO POR AGENTE MEDICINAL, A85:EFEITOS SECUNDÁRIOS DE UM FÁRMACO, A86:EFEITO TÓXICO DE UMA SUBSTÂNCIA NÃO-MEDICINAL, A87:COMPLICAÇÕES DO TRATAMENTO, A88:EFEITOS SECUNDÁRIOS POR FACTORES FÍSICOS, A89:EFEITOS DE UMA PRÓTESE, A90:MALFORMAÇÕES CONGÉNITAS, NE / MÚLTIPLAS, A91:INVESTIGAÇÃO COM RESULTADOS IRREGULARES, NE, A92:ALERGIA / REACÇÃO ALÉRGICA, NE, A93:RECÉM NASCIDO PREMATURO, A94:MORBILIDADE PERINATAL, A96:MORTE, A97:SEM DOENÇA, A98:MEDICINA PREVENTIVA / DE ACOMPANHAMENTO GERAL, A99:DOENÇA GERAL, NE, B02:GÂNGLIOS LINFÁTICOS AUMENTADOS DE VOLUME / DOLOROSOS, B04:SINAIS / SINTOMAS DO SANGUE, B25:MEDO DE SIDA, B26:MEDO DE CANCRO DO SANGUE / LINFÁTICO, B29:OUTROS SINAIS / SINTOMAS DO SANGUE / LINFÁTICO / BAÇO, B70:LINFADENITE AGUDA, B71:LINFADENITE CRÓNICA NÃO ESPECÍFICA, B72:DOENÇA DE HODGKIN / LINFOMAS)
⟂
Páginas:
Mês: 2000-12
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: Total
Médico Familia: Total
Médico de Registo: Total
⟂
[c0] NOP | [c1] Utente | [c2] ⟂ | [c3] Sexo | [c4] Idade | [c5] ICPC | [c6] ⟂ | [c7] Freguesia Habitação
```

Notes: Untitled col 2 = `Nome`, untitled col 6 = ICPC description. ICPC descriptions in the filter contain commas and parentheses.

## P04.01.L05

```
P04.01.L05. Novos Problemas &gt; Utente
⟂
Filtro do relatório:
(Mês = 2000-02) E ({Unidade Funcional} = USF Exemplo) E ({Nº Novos Utentes} &gt; 0)
⟂
Páginas:
Mês: 2000-02
Unidade Funcional: USF Exemplo
Flag Médico Família: Total
Médico Familia: Total
Médico de Registo: NOME MEDICO: M 00000
⟂
[c0] ICPC | [c1] ⟂ | [c2] NOP | [c3] Utente | [c4] ⟂ | [c5] Sexo | [c6] Idade | [c7] Métrica | [c8] Nº Novos Ut
```

Notes: Header starts with `ICPC`. Filter has `&gt;` (`{Nº Novos Utentes} > 0`). Páginas shows a **specific doctor** in `Médico de Registo` (`NOME MEDICO: M 00000` — note the extra `:` inside the value).

## P04.R06

```
P04.R06. Top Problemas &gt; UF e Médico
⟂
Filtro do relatório:
Mês = 2000-12
⟂
Páginas:
Mês: 2000-12
Unidade Funcional / Polo Hospitalar: USF Exemplo
Médico Familia: Total
⟂
[c0] ICPC | [c1] ⟂ | [c2] Métrica | [c3] Qtd Problemas | [c4] TOP
```

Notes: Filter **without parentheses** (`Mês = 2000-12`).

## P05.01.L02

```
P05.01.L02. Risco de Diabetes &gt; Nível de Risco por Utente
⟂
Filtro do relatório:
(Mês = 2000-11, 2000-10, 2000-09, 2000-08, 2000-07, 2000-06, 2000-05, 2000-04, 2000-03, 2000-02, 2000-01) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo) E ({Tipo Risco} (ID) = -24)
⟂
[c0] Mês | [c1] Unidade Funcional / Polo Hospitalar | [c2] Freguesia Habitação | [c3] Utente | [c4] ⟂ | [c5] Tipo Risco | [c6] Risco
```

Notes: **No Páginas section**: header follows the filter directly. Filter lists **several months** in one value (`Mês = 2000-11, 2000-10, …`) and has a key with a suffix (`{Tipo Risco} (ID) = -24`). Sample lists Jan–Nov only.

## P05.R01

```
P05.R01. Episódios &gt; Sexo e Grupo Etário
⟂
Filtro do relatório:
Ano = 2000
⟂
Páginas:
Grupo Etário 7: Total
Sexo: Total
Unidade Funcional / Polo Hospitalar: USF Exemplo
Ano: 2000
Flag Médico Família: Total
Médico Familia: Total
Médico Consulta: NOME MEDICO: M 00000
Area ICPC: Total
⟂
[c0] ICPC | [c1] ⟂ | [c2] Métrica | [c3] Qtd Consultas ICPC
```

Notes: Filter without parentheses (`Ano = 2000`). Páginas shows a specific doctor in `Médico Consulta`.

## P06.01.01.L03

```
P06.01.01.L03. Listagem de Medicamentos Prescritos por Utente - Marca e DCI
⟂
Filtro do relatório:
(Mês = 2000-12) E ({Unidade Funcional} = USF Exemplo)
⟂
Páginas:
Mês = 2000-12
Unidade Funcional: Total
Flag Médico Família: Total
Médico Familia: Total
Grupo Farmoterapeutico N2/CNPEM: Total
⟂
[c0] Medicamento/CNPEM | [c1] Embalagem/CNPEM | [c2] Grupo Farmoterapeutico N3/CNPEM | [c3] Utente | [c4] ⟂ | [c5] Sexo | [c6] Idade | [c7] Médico | [c8] ⟂ | [c9] Dia Prescrição | [c10] Métrica | [c11] Nº Receitas Prescritas | [c12] Nº Embalagens Prescritas
```

Notes: Páginas uses `Mês = 2000-12` (**`=` instead of `:`**). Unit `Total` in Páginas while the filter restricts it → filter wins. Other samples use `Trimestre = YYYY-Tn`. No `NOP` column.

## P06.01.R02

```
P06.01.R02. Medicamentos Prescritos &gt; DCI e Medicamento &gt; Médico
⟂
Filtro do relatório:
Ano = 2000
⟂
Páginas:
Ano: 2000
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: C/ Med Fam
Médico: NOME MEDICO: M 00000
⟂
[c0] DCI (CNPEM) | [c1] ⟂ | [c2] Medicamento | [c3] Embalagem | [c4] Métrica | [c5] Número Utentes com Prescrição | [c6] Nº Receitas Prescritas | [c7] Nº Embalagens Prescritas | [c8] PVP Medicam Prescritos | [c9] SNS Medicam Prescritos | [c10] Medicam Prescrito / 3º + Barato (Custo - PVP) | [c11] Medicam Prescrito / 3º + Barato (Custo - SNS) | [c12] Medicam Prescrito / 5º + Barato (Custo - PVP) | [c13] Medicam Prescrito / 5º + Barato (Custo - SNS
```

Notes: Páginas shows a specific doctor in `Médico`. Last header is cut in the file (`…(Custo - SNS` without `)`) → matched by prefix.

## P07.01.01.L01

```
P07.01.01.L01. Listagem de MCDTs Prescritos &gt; Utente
⟂
Filtro do relatório:
(Ano = 2000) E ({Area MCDT} = ANÁLISES CLÍNICAS)
⟂
Páginas:
Unidade Funcional / Polo Hospitalar: USF Exemplo
Ano: 2000
Area MCDT: ANÁLISES CLÍNICAS
Médico: NOME MEDICO: M 00000
⟂
[c0] Exame MCDT | [c1] Utente | [c2] ⟂ | [c3] Dia Prescrição | [c4] Métrica | [c5] Nº Exames Prescritos
```

Notes: Filter `{Area MCDT} = ANÁLISES CLÍNICAS`. Páginas shows a specific doctor in `Médico`.

## P07.03.01.L01

```
P07.03.01.L01. Resultados MCDTs &gt; Utente
⟂
Filtro do relatório:
({Exame MCDT} = 651029:Colesterol total, s/l) E (Mês = 2000-12) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)
⟂
Páginas:
Mês: 2000-12
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: C/ Med Fam
⟂
[c0] NOP | [c1] Utente | [c2] ⟂ | [c3] Sexo | [c4] Idade | [c5] Freguesia Habitação | [c6] Médico Familia | [c7] Data Último MCDT | [c8] Resultado Último MCDT
```

Notes: One extraction per exam: filter `{Exame MCDT} = 651029:Colesterol total, s/l` (`code:name`, name contains a comma).

## P10.01.L01

```
P10.01.L01. Resultados Biométricos &gt; Utente
⟂
Filtro do relatório:
({Tipo Dado} = Altura(Cm)) E (Mês = 2000-12) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)
⟂
Páginas:
Mês: 2000-12
Unidade Funcional / Polo Hospitalar: USF Exemplo
Flag Médico Família: C/ Med Fam
⟂
[c0] NOP | [c1] Utente | [c2] ⟂ | [c3] Sexo | [c4] Idade | [c5] Freguesia Habitação | [c6] Médico Familia | [c7] Data Último Registo | [c8] Resultado Último Registo
```

Notes: One extraction per type: filter `{Tipo Dado} = Altura(Cm)`.

## Footer rows (some reports)

```
Total | ⟂ | ⟂ | … | ⟂ | 23149 | 67.830
Total | ⟂ | ⟂ | … | ⟂ | 12000 | 40.000
```

Notes: first cell `Total`, patient-ID columns empty. Remove the row (V12) and discard the numbers.
