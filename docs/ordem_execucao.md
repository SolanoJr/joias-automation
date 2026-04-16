# Ordem de Execução (Numerada)

## Scripts principais (ordem)
- 1) [scripts/1_detect_etiqueta.py](scripts/1_detect_etiqueta.py) -> chama [scripts/detect_etiqueta.py](scripts/detect_etiqueta.py)
- 2) [scripts/2_preparar_quadrado_manual.py](scripts/2_preparar_quadrado_manual.py) -> chama [scripts/preparar_quadrado_manual.py](scripts/preparar_quadrado_manual.py)
- 3) [scripts/3_segment_rembg.py](scripts/3_segment_rembg.py) -> chama [scripts/segment_rembg.py](scripts/segment_rembg.py)
- 4) [scripts/4_renomear_final.py](scripts/4_renomear_final.py) -> chama [scripts/renomear_final.py](scripts/renomear_final.py)
- 5) [scripts/5_renomear_intermediarios.py](scripts/5_renomear_intermediarios.py) -> chama [scripts/renomear_intermediarios.py](scripts/renomear_intermediarios.py)
- 6) [scripts/6_validar_saidas.py](scripts/6_validar_saidas.py) -> chama [scripts/validar_saidas.py](scripts/validar_saidas.py)

## Pastas de saída numeradas (espelho)
Geradas automaticamente pelo script [scripts/organizar_pastas_numeradas.py](scripts/organizar_pastas_numeradas.py):

- [output/1_etiquetas](output/1_etiquetas)  <- [output/etiquetas](output/etiquetas)
- [output/2_paints](output/2_paints)  <- [output/paints](output/paints)
- [output/3_sem_etiqueta](output/3_sem_etiqueta)  <- [output/sem_etiqueta](output/sem_etiqueta)
- [output/4_quadrado_manual](output/4_quadrado_manual)  <- [output/quadrado_manual](output/quadrado_manual)
- [output/5_segmentado_rembg](output/5_segmentado_rembg)  <- [output/segmentado_rembg](output/segmentado_rembg)
- [output/6_final](output/6_final)  <- [output/final](output/final)

## Observação
- O pipeline principal usa os scripts numerados (`1_...` até `6_...`) e também as pastas numeradas (`output/1_*` até `output/6_*`).
- Os caminhos antigos sem enumeração não são mais a rota principal do fluxo.

## Convenção de nome (intermediárias)
- Regra principal: `nome_inicial - nome_final+sufixo.jpg` nas pastas `output/1_*` até `output/5_*`.
- Exceção: quando `nome_inicial == nome_final`, usa formato reduzido para evitar repetição.
- Exemplo com `paint`: `20260109_100355 - 1500392104_p.jpg`.
- Exemplo reduzido: `1200090006_sr.jpg`.

## Modo de teste (rápido) e modo completo
- Padrão: o pipeline processa só os primeiros 10 arquivos de entrada para acelerar testes.
- Completo: quando necessário, rodar com `--full` para processar todos os arquivos.
- A validação por baseline (`validar_saidas.py`) roda automaticamente no modo `--full`.

## Prioridade após performance
- Depois de finalizar as otimizações de velocidade, executar uma etapa obrigatória de QA visual do lote processado.
- Esse QA deve revisar qualidade visual e consistência de renomeação antes de considerar o ciclo encerrado.

Comandos:
- Teste rápido (padrão): `python scripts/pipeline.py`
- Teste rápido com limite customizado: `python scripts/pipeline.py --limit 15`
- Teste completo: `python scripts/pipeline.py --full`
