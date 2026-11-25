"""PT-PT texts of every validation issue: what is wrong, and how to fix it (PRD §6.3.2).

These live in ``core`` (not ``gui/strings_pt.py``) because the checks that produce them must not
import Qt (CLAUDE.md rule 3); the GUI only displays them. Every message answers *what*; the
``location`` field of the issue answers *where*; the fix hint answers *how to fix it*.
"""

from __future__ import annotations

from collections.abc import Iterable

MONTHS_PT = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")

#: key -> (message, fix hint). Placeholders are filled with str.format.
TEMPLATES: dict[str, tuple[str, str | None]] = {
    # V01 — readable MIM@UF export
    "V01.not_excel": (
        "O ficheiro não é um Excel verdadeiro (por exemplo, uma página web guardada como .xls).",
        "Exporte novamente do MIM@UF para Excel e largue o ficheiro que o MIM@UF gerou.",
    ),
    "V01.corrupt": (
        "O ficheiro Excel está danificado ou incompleto.",
        "Exporte novamente do MIM@UF e largue o novo ficheiro.",
    ),
    "V01.no_header": (
        "O ficheiro não tem o cabeçalho de um relatório do MIM@UF "
        "(título e «Filtro do relatório»).",
        "Largue o ficheiro tal como o MIM@UF o exportou, sem o abrir e guardar no Excel.",
    ),
    "V01.unsupported": (
        "Este tipo de ficheiro ainda não é suportado ({what}).",
        "{hint}",
    ),
    # V02 — report recognised
    "V02.unknown": (
        "Relatório não reconhecido: «{title}».",
        "Confirme que exportou um dos relatórios da lista e largue o ficheiro sem o alterar.",
    ),
    "V02.wrong_report": (
        "Este ficheiro é o {found} ({found_title}), não o {expected}.",
        "Largue-o no relatório {found}, ou use «Importar tudo» em «Rever e continuar».",
    ),
    # V03 — unit
    "V03.mismatch": (
        "A unidade «{found}» é diferente da do projeto («{expected}»).",
        "Volte a exportar com Unidade Funcional = {expected} e substitua o ficheiro.",
    ),
    "V03.missing": (
        "Não foi possível confirmar a unidade: não aparece no filtro, nas páginas nem nos dados.",
        "Confirme no MIM@UF que o filtro inclui Unidade Funcional = {expected}.",
    ),
    # V04 — period and slot
    "V04.no_period": (
        "Não foi possível ler o período ({what}) no filtro nem nas páginas.",
        "Exporte de novo, escolhendo {what} no MIM@UF.",
    ),
    "V04.outside_year": (
        "O período {period} está fora do ano do projeto ({years}).",
        "Volte a exportar com {what} = {suggestion}.",
    ),
    "V04.unexpected_month": (
        "O mês {period} não é um dos meses pedidos para este relatório ({expected}).",
        "Volte a exportar com Mês = {suggestion}.",
    ),
    "V04.unknown_value": (
        "{key} «{value}» não corresponde a nenhuma das extrações pedidas ({expected}).",
        "Confirme o valor escolhido em {key} no MIM@UF e exporte de novo.",
    ),
    "V04.unknown_icpc_set": (
        "Os códigos ICPC do filtro não correspondem a nenhum dos lotes ({n} códigos).",
        "Use o botão «Copiar códigos» de cada lote e cole a lista no filtro ICPC do MIM@UF.",
    ),
    # V05 — filter vs pages
    "V05.conflict": (
        "O filtro indica {key} = {filter_value}, mas as páginas indicam {page_value}.",
        "Confirme o valor escolhido e volte a exportar com {key} = {filter_value}.",
    ),
    # V06 — required filter/page values
    "V06.value": (
        "{key} devia ser «{expected}», mas o ficheiro tem «{found}».",
        "Volte a exportar com {key} = {expected}.",
    ),
    "V06.missing": (
        "Não foi possível confirmar {key} = {expected}: não aparece no filtro nem nas páginas.",
        "Confirme no MIM@UF que escolheu {key} = {expected}.",
    ),
    "V06.slot_filter": (
        "Falta o filtro {key}, que identifica a extração.",
        "Escolha um só valor em {key} no MIM@UF e exporte de novo.",
    ),
    "V06.other_doctor": (
        "Exportou a página de outro médico em «{key}»: {found}.",
        "Escolha {key} = Total (ou o médico do projeto) e exporte de novo.",
    ),
    # V07 — columns
    "V07.missing": (
        "Falta a coluna «{expected}» (coluna {position}).",
        "Exporte o relatório sem esconder, mover ou acrescentar colunas.",
    ),
    "V07.mismatch": (
        "A coluna {position} devia ser «{expected}», mas é «{found}».",
        "Exporte o relatório sem esconder, mover ou acrescentar colunas.",
    ),
    "V07.blank": (
        "A coluna {position} devia ser «{expected}», mas está sem título.",
        "Exporte o relatório sem esconder, mover ou acrescentar colunas.",
    ),
    "V07.extra": (
        "Coluna inesperada «{found}» (coluna {position}); será ignorada.",
        "Se acrescentou colunas no MIM@UF, exporte sem elas.",
    ),
    # V08 — rows
    "V08.empty": (
        "Relatório vazio: o ficheiro não tem linhas de dados.",
        "Confirme os filtros no MIM@UF; se o resultado é mesmo vazio, pode continuar.",
    ),
    # V09 — truncation
    "V09.truncated": (
        "O ficheiro tem {rows} linhas, o máximo deste formato: "
        "a exportação foi provavelmente cortada.",
        "Divida a extração (por exemplo, por período) e exporte cada parte em separado.",
    ),
    # V10 — patient IDs
    "V10.ids": (
        "{summary}",
        "É normal em poucos casos. Se forem muitas linhas, confirme a coluna Utente na exportação.",
    ),
    # V11 — duplicates
    "V11.same_file": (
        "Ficheiro idêntico a «{other}», que já foi importado.",
        "Remova um dos dois.",
    ),
    "V11.same_slot": (
        "A extração {slot} já tem outro ficheiro («{other}»).",
        "Remova o ficheiro que não quer usar.",
    ),
    # S01 — completeness
    "S01.missing_slots": (
        "Falta{plural_s} {n} extraç{plural_oes}: {items}.",
        "Exporte do MIM@UF as extrações em falta (ver «Como extrair»).",
    ),
    "S01.missing_months": (
        "Meses sem dados: {items}.",
        "Exporte os meses ou trimestres em falta.",
    ),
    "S01.overlap": (
        "Meses em mais de um ficheiro: {items}.",
        "Remova os ficheiros repetidos ou exporte períodos que não se sobreponham.",
    ),
    # S02 — ICPC coverage
    "S02.missing_set": (
        "Falta o lote {n} ({first} → {last}, {count} códigos).",
        "Copie os códigos do lote {n} («Copiar códigos») e exporte-o do MIM@UF.",
    ),
    "S02.missing": (
        "Faltam {n} códigos ICPC da lista de referência: {items}.",
        "Exporte o lote que os contém (botão «Copiar códigos»).",
    ),
    "S02.overlap": (
        "{n} códigos ICPC aparecem em mais de um ficheiro: {items}.",
        "Não é grave: as linhas repetidas são removidas na agregação. Confirme e continue.",
    ),
    # S05 — the project's doctor in the list of family doctors (PRD §6.2)
    "S05.doctor": (
        "O médico do projeto («{doctor}») não aparece entre os médicos de família deste relatório.",
        "Escolha o nome exato (por exemplo: {closest}) ou corrija-o em «01 Projeto».",
    ),
    # S03 / S04 — consistency across the files of a report
    "S03.inconsistent": (
        "Os ficheiros deste relatório não têm {what} igual: {items}.",
        "Exporte todos os ficheiros com os mesmos filtros.",
    ),
    "S04.columns": (
        "Os ficheiros deste relatório não têm as mesmas colunas ({items}).",
        "Exporte todos os ficheiros com a mesma configuração de colunas.",
    ),
}


def text(template: str, /, **values: object) -> tuple[str, str | None]:
    message, hint = TEMPLATES[template]
    return message.format(**values), (hint.format(**values) if hint else None)


def listing(items: Iterable[str], limit: int = 12) -> str:
    """``a, b, c`` or ``a, b, … (+9)`` for long lists."""
    items = list(items)
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f", … (+{len(items) - limit})"


def month_label(period: str) -> str:
    """``2024-07`` → ``Jul 2024``."""
    year, _, month = period.partition("-")
    try:
        return f"{MONTHS_PT[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return period


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many
