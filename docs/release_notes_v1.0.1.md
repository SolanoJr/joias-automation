# v1.0.1 - 2026-03-06

## Summary
Versão focada em robustez operacional do pipeline, com validação automática de regressão, etapa intermediária para edição manual e rastreabilidade da origem na renomeação final.

## Added
- Novo validador de saídas com baseline em `scripts/validar_saidas.py`.
- Nova etapa `output/quadrado_manual` via `scripts/preparar_quadrado_manual.py`.
- Tag de versão estável publicada (`v1.0.0`) e release no GitHub.

## Changed
- `scripts/pipeline.py` agora inclui etapa de quadrado manual e validação automática no final (quando baseline existe).
- `scripts/renomear_final.py` passa a aplicar sufixos por fonte (`_p`, `_e`, `_se`).

## Fixed
- Prevenção de regressões silenciosas em qualidade/contagem nas saídas-chave.
- Melhor rastreabilidade da origem de leitura de código no nome final.

## Quality / Validation
- Pipeline executado: sim
- Validação automática (`scripts/validar_saidas.py`): ok
- Contagens finais:
  - `sem_etiqueta`: 50
  - `segmentado_rembg`: 50
  - `final`: 50
  - `CSV_ROWS`: 50

## Notes
- Nesta execução validada, as fontes de código no CSV ficaram concentradas em `paint` e `nenhum`.
- Sufixos `_e` e `_se` aparecem automaticamente quando essas fontes ocorrerem.
