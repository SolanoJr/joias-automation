# Contexto do Projeto (para outra IA)

## Projeto
- Nome: `joias_automation`
- Objetivo: processar fotos de joias, remover etiqueta/pintura, segmentar e renomear automaticamente por código.
- Ambiente: Windows + Python (venv 3.10.11)

## Fluxo atual principal (enumerado)
1. `scripts/1_detect_etiqueta.py`
2. `scripts/2_preparar_quadrado_manual.py`
3. `scripts/3_segment_rembg.py`
4. `scripts/4_renomear_final.py`
5. `scripts/5_renomear_intermediarios.py`
6. `scripts/6_validar_saidas.py` (somente no modo full)

## Pastas principais de saída (enumeradas)
- `output/1_etiquetas`
- `output/2_paints`
- `output/3_sem_etiqueta`
- `output/4_quadrado_manual`
- `output/5_segmentado_rembg`
- `output/6_final`
- `output/resultados.csv`

## Padrão de nomes aprovado
- Intermediárias (`output/1_*` até `output/5_*`):
  - padrão principal: `nome_inicial - nome_final+sufixo.jpg`
  - exceção: quando `nome_inicial == nome_final`, usar formato reduzido `nome_final+sufixo.jpg`
- `output/6_final`: `codigo.jpg` ou `base_semcod.jpg`

### Exemplos (paint, nomes diferentes)
- `output/2_paints`: `20260109_100355 - 1500392104_p.jpg`
- `output/4_quadrado_manual`: `20260109_100355 - 1500392104_qm.jpg`
- `output/5_segmentado_rembg`: `20260109_100355 - 1500392104_sr.jpg`

### Exemplo (inicial igual ao final)
- `output/5_segmentado_rembg`: `1200090006_sr.jpg`
- `output/6_final`: `codigo.jpg` ou `base_semcod.jpg`

## Modo de execução/teste
- Padrão (rápido): `python scripts/pipeline.py` (10 primeiros arquivos)
- Completo: `python scripts/pipeline.py --full`
- Limite customizado no modo rápido: `python scripts/pipeline.py --limit 15`

## Estado atual
- Fluxo enumerado está em uso no pipeline.
- Segmentação lê de `output/4_quadrado_manual`.
- Nomenclatura por sufixo já aplicada nas intermediárias.
- Semcod no lote de 10 caiu de 2 para 1 após ajuste de consenso da etiqueta.

## Problema principal em aberto
- Ainda há casos de `semcod` no lote rápido.
- Objetivo atual: reduzir/zerar `semcod` sem quebrar:
  - padrão de nomes
  - fluxo enumerado
  - qualidade visual de `sem_etiqueta` / `paints`

## Arquivos-chave para análise
- `scripts/ler_codigo.py`
- `scripts/detect_etiqueta.py`
- `scripts/renomear_final.py`
- `scripts/renomear_intermediarios.py`
- `scripts/pipeline.py`

## Pedido recomendado para outra IA
"Sugira melhorias concretas e de baixo risco para reduzir `semcod` (barcode + OCR), com patches pequenos e testáveis no modo de 10 arquivos. Priorize precisão (evitar falso positivo) e mantenha o padrão de nomes e fluxo enumerado atuais."