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
