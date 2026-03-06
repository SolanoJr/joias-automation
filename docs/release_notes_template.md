# Release Notes Template

Use este modelo para cada nova versão.

## Título
`vX.Y.Z` - `AAAA-MM-DD`

## Summary
Resumo curto da entrega em 2-4 linhas.

## Added
- 
- 

## Changed
- 
- 

## Fixed
- 
- 

## Quality / Validation
- Pipeline executado: `sim/não`
- Validação automática (`scripts/validar_saidas.py`): `ok/falhou`
- Contagens finais (`sem_etiqueta`, `segmentado_rembg`, `final`, `CSV_ROWS`):
  - 

## Notes
- Riscos conhecidos:
  - 
- Próximos passos:
  - 

## Comandos úteis
Automação completa (1 comando):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release.ps1 -ReleaseVersion vX.Y.Z -NotesFile docs/release_notes_vX.Y.Z.md
```

Criar release com arquivo de notas:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" release create vX.Y.Z --repo SolanoJr/joias-automation --title "vX.Y.Z" --notes-file docs/release_notes_vX.Y.Z.md
```

Visualizar release:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" release view vX.Y.Z --repo SolanoJr/joias-automation
```
