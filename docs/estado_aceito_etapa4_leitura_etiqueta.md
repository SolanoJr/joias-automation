# Estado Aceito — Etapa 4 (Leitura de Etiqueta)

Data: 2026-03-12

## Decisão

Com base no lote de 50 e no lote de 120, a leitura de etiqueta está considerada estabilizada para produção em CPU com fallback simples + intensivo/OCR residual.

## Critérios de regressão aceitos

- `SEM_CODIGO <= 1.0%` do lote
- Alerta em `SEM_CODIGO > 0.5%`
- Falha em `SEM_CODIGO > 1.0%`
- `etiqueta_intensivo + etiqueta_ocr <= 20%` dos itens de etiqueta
- Tempo médio por etiqueta `<= 8.0s`

## Artefatos auditáveis aceitos

- `output/analysis/profile_etapa4_safety_120.csv`
- `output/resultados.csv`
- `output/analysis/safety_120_resumo.json`
- `output/analysis/bench_etiqueta_tempos_before.json`
- `output/analysis/bench_etiqueta_tempos_after.json`
