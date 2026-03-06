# v1.0.2 - 2026-03-06

## Summary
Versão focada em automação do processo de release para reduzir trabalho manual e padronizar publicação de versões.

## Added
- Novo script de automação de release em `scripts/release.ps1`.
- Fluxo único para commit opcional, push da `main`, criação/push de tag e criação de release no GitHub.

## Changed
- Template de notas atualizado em `docs/release_notes_template.md` com comando de automação em 1 linha.

## Fixed
- Tratamento de casos sem saída do `git` no script de release para evitar falhas por valor nulo.
- Parâmetro renomeado para `-ReleaseVersion` para evitar conflito com parâmetros nativos do PowerShell.

## Notes
- `DryRun` validado com sucesso para `v1.0.2` antes da publicação real.
