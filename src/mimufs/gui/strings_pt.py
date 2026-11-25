"""Every user-visible string of the GUI, in PT-PT (CLAUDE.md rule 6, TECH_SPECS §14.4).

Widgets import constants from here and never hold literal UI text, so a translation catalogue
can be added later without touching them. Report instructions live in the report YAML.
"""

from __future__ import annotations

APP_NAME = "mimufs"

# Title bar
NO_PROJECT = "Nenhum projeto aberto"
THEME_TO_LIGHT = "Mudar para o tema claro"
THEME_TO_DARK = "Mudar para o tema escuro"
SETTINGS_SOON = "Definições (disponível em breve)"
NETGUARD_ACTIVE_TOOLTIP = (
    "Proteção de rede ativa: nenhum dado sai deste computador.\n"
    "A única ligação permitida é a verificação de novas versões (mimufs.com).\n"
    "Tentativas bloqueadas desde o arranque: {blocked}."
)
NETGUARD_INACTIVE = "proteção de rede inativa"
NETGUARD_INACTIVE_TOOLTIP = (
    "A proteção de rede não está ativa nesta sessão (modo de desenvolvimento ou testes)."
)


def offline_badge(connections: int) -> str:
    """``offline · 0 ligações de rede`` (connections made by the update check)."""
    noun = "ligação" if connections == 1 else "ligações"
    return f"offline · {connections} {noun} de rede"


# Home (no project open)
HOME_KICKER = "MIMUFS · V{version}"
HOME_TITLE = "Projetos"
HOME_SUBTITLE = "Processamento dos dados do MIM@UF e do SClínico, inteiramente neste computador."
OPEN_PROJECT = "Abrir projeto…"
NEW_PROJECT = "+ Novo projeto"
COMING_SOON = "Disponível na próxima versão de teste."
RECENT_PROJECTS = "PROJETOS RECENTES"
NO_RECENT_PROJECTS = "Ainda não há projetos. Crie o primeiro com “+ Novo projeto”."
PRIVACY_NOTE = (
    "Nenhum dado sai deste computador. A única ligação à internet é a verificação de novas "
    "versões, que pode desligar nas Definições."
)

# Update dialog
UPDATE_TITLE = "Nova versão disponível"
UPDATE_BODY = "Está disponível a versão {latest} do mimufs. Tem instalada a versão {current}."
UPDATE_RELEASED = "Publicada em {date}."
UPDATE_UNSUPPORTED = "Esta versão já não é suportada. Atualize antes de continuar a trabalhar."
UPDATE_NOTES = "Novidades"
UPDATE_HOWTO = "A transferência abre no navegador. Os seus projetos não são alterados."
UPDATE_DOWNLOAD = "Descarregar"
UPDATE_LATER = "Lembrar mais tarde"
UPDATE_IGNORE = "Ignorar esta versão"

# Status (icon + colour + label, never colour alone: CLAUDE.md rule 7)
STATUS_VALID = "Válido"
STATUS_WARNING = "Incompleto"
STATUS_ERROR = "Erro"
STATUS_PENDING = "Por importar"
STATUS_SKIPPED = "Dispensado"
STATUS_LOCKED = "Bloqueado"
STATUS_ACKNOWLEDGED = "Confirmado"
SEVERITY_WARNING = "Aviso"
SEVERITY_ERROR = "Erro"
COUNTS_FOOTER = "{ok} ok · {warn} aviso · {err} erro · {pending} falta"

# Home: recent projects and dictionaries
RECENT_PROGRESS = "Passo 02 · {done}/{total} relatórios"
RECENT_OPENED = "Aberto {when}"
RECENT_MISSING = "Projeto não encontrado"
RECENT_REMOVE = "Remover da lista"
DICTIONARIES = "DICIONÁRIOS"
DICT_TITLES = {
    "medicamentos": "Medicamentos",
    "icpc2": "ICPC-2 (v4.4 PT)",
    "indicadores": "Indicadores",
}
DICT_UNITS = {"medicamentos": "termos", "icpc2": "códigos", "indicadores": "intervalos"}
DICT_EDITABLE = "editável"
DICT_EDITED = "editado"
MANAGE_DICTIONARIES = "Gerir dicionários"
OPEN_PROJECT_FILTER = "Projetos do mimufs (*.mimufs)"
OPEN_PROJECT_TITLE = "Abrir projeto"
OPEN_FAILED = "Não foi possível abrir o projeto"

# New project dialog (PRD §6.2)
NEW_PROJECT_TITLE = "Novo projeto"
NEW_PROJECT_SUBTITLE = "Depois de criar, o mimufs abre o primeiro passo: Extração & Importação."
FIELD_UNIT = "Unidade *"
FIELD_UNIT_HELP = "Exatamente como aparece no MIM@UF (filtro «Unidade Funcional»)."
FIELD_UNIT_REQUIRED = "Indique a unidade."
FIELD_DOCTOR = "Médico *"
FIELD_DOCTOR_HELP = "Nome como aparece no MIM@UF. Pré-preenchido a partir das Definições."
FIELD_DOCTOR_REQUIRED = "Indique o médico."
FIELD_DESCRIPTION = "Descrição"
FIELD_YEAR = "Ano"
FIELD_YEARS_TWO = "{a} e {b}"
FIELD_FOLDER = "Pasta do projeto"
CHOOSE_FOLDER = "Escolher…"
FOLDER_WARNING = "A pasta vai conter dados clínicos identificáveis. Guarde-a só num disco cifrado."
CANCEL = "Cancelar"
CREATE_PROJECT = "Criar projeto"
CREATE_FAILED = "Não foi possível criar o projeto"

# Project view: phases and navigation
PROJECT_KICKER = "PROJETO"
PROJECT_DOCTOR = "Médico: {doctor}"
PHASES = (
    ("01", "Projeto"),
    ("02", "Extração & Importação"),
    ("03", "Agregação"),
    ("04", "Qualidade dos dados"),
    ("05", "Normalização"),
    ("06", "Tabelas & Exportação"),
)
PHASE_SUBSTEPS = {
    "01": ("Dados do projeto",),
    "03": ("Construir dataset", "Saídas da lista"),
    "04": ("Regras de qualidade",),
    "05": ("Tipos de consulta",),
    "06": ("Tabelas e exportação",),
}
GROUP_ORDER = (
    "Consultas", "Inscritos", "Indicadores", "Problemas", "Medicação & MCDT", "Biometrias",
)  # fmt: skip
GATE = "Rever e continuar"
PREVIOUS = "‹ Anterior"
NEXT = "Seguinte ›"
SUBSTEP_OF = "Sub-passo {n} de {total}"
PHASE_LOCKED_TITLE = "Este passo ainda não está disponível"
PHASE_LOCKED_BODY = (
    "Termine «Rever e continuar» na Extração & Importação. A agregação dos dados chega numa "
    "próxima versão do mimufs."
)

# Phase 01 page
PROJECT_PAGE_TITLE = "Dados do projeto"
PROJECT_PAGE_BODY = "Alterar a unidade ou o médico volta a validar todos os ficheiros importados."
SAVE = "Guardar"
SAVED = "Guardado."
PROJECT_FOLDER = "Pasta: {path}"

# Report page
REPORT_CODE_LINE = "{code} · {source} · nível {level}"
REQUIRED_SLOTS = "EXTRAÇÕES NECESSÁRIAS · {filled}/{total}"
HOW_TO_EXTRACT = "COMO EXTRAIR DO MIM@UF"
HOW_TO_EXTRACT_SCLINICO = "COMO EXPORTAR DO SCLÍNICO"
ICPC_HELPER = "CÓDIGOS ICPC PARA COLAR NO MIM@UF"
ICPC_BATCH = "Lote {n} · {first} → {last} · {count} códigos"
COPY_CODES = "Copiar códigos"
COPIED = "Copiado ✓"
DROP_TITLE = "Largue ficheiros (.xls, .xlsx) ou uma pasta"
DROP_SUBTITLE = "Relatório e extração detetados pelo cabeçalho de cada ficheiro"
DROP_BUSY = "A importar {name}…"
IMPORT_BUTTON = "Importar…"
IMPORT_DIALOG = "Importar ficheiros do MIM@UF"
IMPORT_FILTER = "Exportações do MIM@UF (*.xls *.xlsx);;Todos os ficheiros (*)"
FILES_HEADER = "FICHEIROS IMPORTADOS · {n}"
FILE_LINE = "{slots} · {rows} linhas"
REMOVE_FILE = "Remover"
REMOVE_CONFIRM = "Remover «{name}» do projeto? A cópia original fica guardada na pasta raw/."
OPTIONAL_REPORT = "Relatório opcional."
NOT_AVAILABLE = (
    "A leitura deste ficheiro chega numa próxima versão do mimufs. Por agora não bloqueia "
    "o passo «Rever e continuar»."
)
SKIP_REPORT = "Dispensar este relatório"
UNSKIP_REPORT = "Retomar este relatório"
SOURCE_MIMUF = "MIM@UF"
SOURCE_SCLINICO = "SClínico"
LEVELS = {
    "patient": "Utente",
    "patient_event": "Utente (eventos)",
    "doctor": "Médico",
    "unit": "Unidade",
    "family": "Família",
}

# Validation pane and log
DIAGNOSTICS = "DIAGNÓSTICO"
NO_ISSUES = "Sem problemas."
METADATA = "METADADOS"
COPY_SUMMARY = "copiar resumo"
ACKNOWLEDGE = "Continuar mesmo assim"
ACKNOWLEDGE_DONE = "Avisos confirmados. Pode continuar."
USE_DOCTOR = "Usar «{name}»"
LAST_IMPORT = "ÚLTIMA IMPORTAÇÃO"
LOG_TITLE = "REGISTO DE VALIDAÇÃO"
LOG_SUMMARY = "{files} ficheiros · {seconds} s"

# Gate (PRD §6.1)
GATE_TITLE = "Rever e continuar"
GATE_BODY = (
    "Todos os relatórios obrigatórios têm de estar válidos, ou com os avisos confirmados. "
    "Os relatórios opcionais podem ser dispensados."
)
GATE_READY = "Tudo pronto: pode avançar para a Agregação."
GATE_BLOCKED = "Ainda falta: {n} relatório(s)."
IMPORT_ALL = "Importar tudo"
IMPORT_ALL_SUBTITLE = "Largue aqui todos os ficheiros: o mimufs distribui-os pelos relatórios."
COL_REPORT = "Relatório"
COL_CODE = "Código"
COL_STATUS = "Estado"
COL_SLOTS = "Extrações"
COL_REQUIRED = "Obrigatório"
YES = "sim"
NO = "não"

# Settings (PRD §7.3)
SETTINGS_TITLE = "Definições"
SETTINGS_DOCTOR = "Médico (como aparece no MIM@UF)"
SETTINGS_DOCTOR_HELP = "Usado para pré-preencher os novos projetos."
SETTINGS_THEME = "Tema"
THEME_SYSTEM = "Seguir o sistema"
THEME_DARK = "Escuro"
THEME_LIGHT = "Claro"
SETTINGS_UPDATES = "Procurar novas versões ao abrir (uma vez por dia)"
CHECK_NOW = "Verificar agora"
UPDATE_NONE = "Tem a versão mais recente."
UPDATE_FAILED = "Não foi possível verificar (sem ligação?)."
UPDATE_CHECKING = "A verificar…"
ABOUT = "Sobre"
ABOUT_TEXT = (
    "mimufs {version} · software livre (GPL-3.0).\n"
    "Nenhum dado sai deste computador. A única ligação à internet é o pedido "
    "GET https://mimufs.com/version.json, com o cabeçalho «User-Agent: mimufs/{version}», "
    "que pode desligar acima."
)
CLOSE = "Fechar"
SETTINGS_ENABLED = "Definições"

# Dictionary manager (PRD §7.5)
DICT_MANAGER_TITLE = "Dicionários"
DICT_SEARCH = "Procurar…"
DICT_ADD = "Adicionar"
DICT_DELETE = "Apagar selecionados"
DICT_SAVE = "Guardar alterações"
DICT_IMPORT = "Importar CSV…"
DICT_EXPORT = "Exportar CSV…"
DICT_RESET = "Repor original"
DICT_RESET_CONFIRM = "Repor o dicionário de medicamentos original? As suas edições serão apagadas."
DICT_READONLY = "Só leitura. Atualizado com as novas versões do mimufs."
DICT_SAVED = "Dicionário guardado ({n} termos)."
DICT_ROWS = "{shown} de {total} linhas"
