# v1.0.3 - 2026-03-09

## Summary
Versão de consolidação do novo fluxo de nomenclatura intermediária e execução numerada no pipeline principal.

## Added
- Etapa automática no pipeline para renomear saídas intermediárias por código/base usando sufixos por pasta (`_p`, `_e`, `_se`, `_qm`, `_sr`).
- Etapa automática para gerar pastas numeradas espelho de saída para facilitar conferência operacional.

## Changed
- `scripts/pipeline.py` agora executa explicitamente:
  - `scripts/renomear_intermediarios.py`
  - `scripts/organizar_pastas_numeradas.py`

## Naming Pattern
- `output/paints`: `codigo_p.jpg` / `base_semcod_p.jpg`
- `output/etiquetas`: `codigo_e.jpg` / `base_semcod_e.jpg`
- `output/sem_etiqueta`: `codigo_se.jpg` / `base_semcod_se.jpg`
- `output/quadrado_manual`: `codigo_qm.jpg` / `base_semcod_qm.jpg`
- `output/segmentado_rembg`: `codigo_sr.jpg` / `base_semcod_sr.jpg`
- `output/final`: `codigo.jpg` / `base_semcod.jpg`

## Notes
- Fluxo validado com `segmentado_rembg` consumindo `output/quadrado_manual`.
- Branch sincronizada e release publicado via automação `scripts/release.ps1`.
