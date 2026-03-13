# Estabilidade Lote 50 (base atual + 2 repetições)

## Contexto
- Mesmas condições operacionais da rodada base (`B_base_atual`).
- Sem alterações de código entre as repetições.
- Rodadas comparadas: `B_base_atual`, `stability_r1`, `stability_r2`.

## Métricas por rodada

| Rodada | Tempo total (s) | Tempo etapa 4 (s) | p50 item etapa 4 (s) | p95 item etapa 4 (s) | Final OK | SEM_CODIGO |
|---|---:|---:|---:|---:|---:|---:|
| B_base_atual | 769.6 | 33.4945 | 0.5366 | 1.65151 | 50 | 0 |
| stability_r1 | 665.9 | 21.5870 | 0.3469 | 0.885925 | 50 | 0 |
| stability_r2 | 679.7 | 22.9394 | 0.3690 | 0.944855 | 50 | 0 |

## Top simples mais lentos (resumo)
- Reincidente nas 3 rodadas: `1200910006`.
- Reincidentes em 2+ rodadas: `1200830006`, `1200210006`, `1200940006`, `1201330006`, `1201060006`, `1200870026`, `1200880006`.

## Variação entre rodadas
- Tempo total: min 665.9, max 769.6, delta 103.7 (+15.57% vs min).
- Tempo etapa 4: min 21.587, max 33.4945, delta 11.9075 (+55.16% vs min).
- p50 item etapa 4: min 0.3469, max 0.5366, delta 0.1897 (+54.68% vs min).
- p95 item etapa 4: min 0.885925, max 1.65151, delta 0.765585 (+86.42% vs min).
- SEM_CODIGO: 0 em todas as rodadas.

## Leitura objetiva
- Entre as repetições novas (`r1` e `r2`), a variação é baixa e o desempenho ficou próximo.
- A rodada `B_base_atual` ficou pior que ambas as repetições novas, sugerindo oscilação operacional pontual naquela execução.
- Não há evidência de regressão funcional (SEM_CODIGO permaneceu em 0).

## Nota de métrica
- A “taxa de acerto” usada aqui é proxy operacional (ex.: `Final OK`/`SEM_CODIGO`) e **não** ground truth formal.
