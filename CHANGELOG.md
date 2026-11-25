# Changelog

Todas as alterações relevantes do mimufs ficam registadas neste ficheiro.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/) e as versões seguem o
[Versionamento Semântico](https://semver.org/lang/pt-PT/).

Notas para quem mantém o projeto (em inglês, como o resto do código):

- Each release is a `## [X.Y.Z] - YYYY-MM-DD` section. The release workflow refuses a tag
  without a dated section for its version, and `scripts/build_site.py` turns the newest one into
  `site/version.json` (its first bullets become the update dialog's `notes_pt`).
- Entries are in PT-PT, written for clinicians, one line each.

## [Não publicado]

M1 — Extração e importação.

### Adicionado

- Página inicial com projetos recentes, «Novo projeto» e «Abrir projeto…».
- Cada projeto é uma pasta no seu computador, com cópia exata de cada ficheiro importado.
- Passo «Extração & Importação»: um sub-passo por relatório, com as extrações necessárias, as instruções e uma zona para largar ficheiros ou pastas.
- O mimufs reconhece o relatório e a extração (mês, trimestre, lote ICPC, análise, tipo de dado) pelo cabeçalho de cada ficheiro, sem depender do nome.
- Verificações de cada ficheiro e de cada relatório (V01–V12, S01–S05), cada uma a dizer o que está mal, onde e como corrigir.
- Botão «Copiar códigos» para colar os 3 lotes de códigos ICPC no MIM@UF.
- «Continuar mesmo assim» para avisos aceites, e relatórios opcionais que podem ser dispensados.
- «Rever e continuar»: o estado de todos os relatórios e a importação de todos os ficheiros de uma vez.
- Ficha de metadados por relatório, com «copiar resumo».
- Definições (médico, tema, verificação de novas versões) e gestão dos dicionários (medicamentos editável).

## [0.0.2] - 2026-11-24

Primeira versão de teste publicada (M0 — Fundações). Ainda não processa projetos.

### Adicionado

- Primeira versão instalável para Windows e macOS 14 ou mais recente (Apple Silicon e Intel). Linux numa versão futura.
- Leitura dos ficheiros exportados do MIM@UF (incluindo os `.xls` que na verdade são `.xlsx`).
- Reconhecimento automático dos 17 relatórios do MIM@UF a partir do cabeçalho de cada ficheiro.
- Java incluído na aplicação para ler o PDF de consultas do SClínico (não é preciso instalar nada).
- Proteção de rede: a aplicação não consegue enviar dados para a internet.
- Aviso de novas versões, que pode ser ignorado.
- Temas claro e escuro.

### Corrigido

- No Windows, o PDF de consultas com acentos (por exemplo, «Médico») passa a ser lido corretamente.

## [0.0.1] - 2026-11-24 [NÃO PUBLICADA]

A compilação para Linux falhou e nenhum ficheiro foi publicado. Substituída pela 0.0.2.
