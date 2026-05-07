# Ordem de Execução

## Pré-requisitos

- Python 3.10+
- Tesseract-OCR 5.x no PATH
- `pyzbar` instalado (opcional, mas recomendado — melhora leitura de barcodes)
- Imagens em `input_raw/fotos_originais/`
- Modelo YOLO em `models/best.pt`

### Instalar pyzbar (Windows)

```bash
pip install pyzbar
# Baixe e instale a DLL zbar de: https://github.com/NaturalHistoryMuseum/pyzbar
```

---

## Executar o pipeline

O ponto de entrada principal é `project/pipeline.py`. Execute sempre a partir da pasta `project/`:

```bash
# Teste rápido (10 imagens)
python pipeline.py

# Teste com N imagens
python pipeline.py --limit 5

# Processar todas as imagens + validação de regressão
python pipeline.py --full

# Reruns rápidos (preserva saídas, usa cache OCR)
python pipeline.py --incremental

# Ver o que seria processado sem executar nada
python pipeline.py --dry-run
python pipeline.py --dry-run --full
```

---

## Etapas do pipeline

| # | Script | Entrada | Saída |
|---|--------|---------|-------|
| 1 | `scripts/1_detect_etiqueta.py` | `input_raw/fotos_originais/` | `output/1_etiquetas/`, `output/2_paints/`, `output/3_sem_etiqueta/` |
| 2 | `scripts/2_preparar_quadrado_manual.py` | `output/3_sem_etiqueta/` | `output/4_quadrado_manual/` |
| 3 | `scripts/3_segment_rembg.py` | `output/4_quadrado_manual/` | `output/5_segmentado_rembg/` |
| 4 | `scripts/4_renomear_final.py` | `output/5_segmentado_rembg/` | `output/6_final/`, `output/resultados.csv`, `output/relatorio.html` |
| 5 | `scripts/5_renomear_intermediarios.py` | `output/1_*` a `output/5_*` | renomeia in-place com sufixos `_e`, `_p`, `_se`, `_qm`, `_sr` |
| 6 | `scripts/6_validar_saidas.py` | `output/resultados.csv` | validação de regressão (só `--full`) |

---

## Pastas de saída

```
output/
├── 1_etiquetas/        # Crops das etiquetas detectadas pelo YOLO
├── 2_paints/           # Crops dos paints (código pintado)
├── 3_sem_etiqueta/     # Imagens com etiqueta/paint apagados
├── 4_quadrado_manual/  # Imagens 1200×1200 com fundo branco
├── 5_segmentado_rembg/ # Joias segmentadas (fundo removido)
├── 6_final/            # Imagens finais renomeadas pelo código
├── cache_ocr/          # Cache de resultados OCR (SHA256)
├── pipeline.log        # Log completo do pipeline (append)
├── resultados.csv      # Metadados: base, código, fonte, status
└── relatorio.html      # Relatório visual com thumbnails
```

---

## Testar o pipeline sem rodar tudo

`scripts/testar_pipeline.py` roda verificações rápidas usando os crops já existentes em `output/`.

```bash
# Todos os testes (ambiente + lógica + paints + etiquetas + CSV)
python scripts/testar_pipeline.py

# Só verificações de ambiente (~1s)
python scripts/testar_pipeline.py --ambiente

# Só lógica interna (~1s, sem I/O)
python scripts/testar_pipeline.py --logica

# Só integridade do CSV (~1s)
python scripts/testar_pipeline.py --csv

# Detecção YOLO nas 2 primeiras imagens (~30s)
python scripts/testar_pipeline.py --deteccao

# Com detalhes de cada item
python scripts/testar_pipeline.py --paints --verbose
python scripts/testar_pipeline.py --etiquetas --verbose
```

O bloco `[0/4] Verificações de ambiente` roda primeiro e verifica:
- Modelo `models/best.pt` existe
- Tesseract está acessível
- `pyzbar` está instalado
- Pasta `input_raw/fotos_originais/` existe e contém imagens

---

## Convenção de nomes nos intermediários

Formato: `nome_inicial - nome_final+sufixo.jpg`

| Sufixo | Significado |
|--------|-------------|
| `_e` | crop de etiqueta |
| `_p` | crop de paint |
| `_se` | imagem sem etiqueta |
| `_qm` | quadrado manual |
| `_sr` | segmentado rembg |

Exemplo: `20260109_100355 - 1500392104_p.jpg`
Formato reduzido (quando base == código): `1200090006_sr.jpg`

---

## Variáveis de ambiente

Ver seção completa no `README.md` do projeto.

Variáveis mais usadas no dia a dia:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `YOLO_CONF_MIN` | `0.25` | Confiança mínima para detecção YOLO |
| `SEG_PARALLEL_WORKERS` | `2` | Workers paralelos na segmentação |
| `CODE_READER_FAST` | `0` | Reduz chamadas OCR (mais rápido, menos preciso) |
| `ENABLE_ENSEMBLE_SEGMENTATION` | `0` | Ativa ensemble de modelos rembg |
| `OCR_CACHE_ENABLED` | `1` | Ativa cache de resultados OCR |
| `USE_LISTA_REPROCESSAR` | `0` | Processa só arquivos listados em `output/analysis/lista_reprocessar_sem_etiqueta.txt` |
