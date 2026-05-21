# joias_automation — project package

Pipeline completo de processamento de imagens de joias com OCR automático para leitura de códigos.

## ⚡ Início Rápido

```bash
# 1. Crie e ative o ambiente virtual
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows
# source venv/bin/activate         # Linux/Mac

# 2. Instale dependências
pip install -r requirements.txt

# 3. Coloque imagens em:
#    input_raw/fotos_originais/

# 4. Execute
python pipeline.py                 # teste rápido (10 imagens)
python pipeline.py --limit 5       # teste com 5 imagens
python pipeline.py --full          # processar todas as imagens
```

## 📋 Pré-requisitos do Sistema

| Dependência | Versão | Instalação |
|-------------|--------|------------|
| Python | 3.10+ | python.org |
| Tesseract-OCR | 5.x | [github.com/UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (Windows) |

> **Windows:** Após instalar o Tesseract, certifique-se que `C:\Program Files\Tesseract-OCR` está no PATH.
> Ou descomente e ajuste a linha no topo de `scripts/ler_codigo.py`:
> ```python
> # pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
> ```

## 🔄 Pipeline (6 etapas)

```
input_raw/fotos_originais/
        ↓
[1] Detectar etiquetas e paints (YOLOv8)  → output/1_etiquetas/, output/2_paints/
        ↓
[2] Preparar imagem quadrada 1200×1200    → output/3_sem_etiqueta/, output/4_quadrado_manual/
        ↓
[3] Segmentar fundo (rembg ensemble)      → output/5_segmentado_rembg/
        ↓
[4] Renomear pelo código lido (OCR)       → output/6_final/, output/resultados.csv
        ↓
[5] Renomear intermediários com sufixos   → _p, _e, _se, _qm, _sr
        ↓
[6] Validar regressão (só --full)
```

## 📁 Estrutura de Saída

```
output/
├── 1_etiquetas/        # Crops das etiquetas detectadas
├── 2_paints/           # Crops dos paints (código pintado)
├── 3_sem_etiqueta/     # Imagens com etiqueta/paint apagados
├── 4_quadrado_manual/  # Imagens 1200×1200 com fundo branco
├── 5_segmentado_rembg/ # Joias segmentadas (fundo removido)
├── 6_final/            # Imagens finais renomeadas pelo código
├── cache_ocr/          # Cache de resultados OCR (SHA256)
└── resultados.csv      # Metadados: base, código, fonte, status
```

## 🎛️ Opções do Pipeline

```bash
python pipeline.py                        # Modo teste: 10 imagens
python pipeline.py --limit 20             # Modo teste: N imagens
python pipeline.py --full                 # Todas as imagens + validação
python pipeline.py --incremental          # Preserva saídas, usa cache
python pipeline.py --mode subprocess      # Força execução em subprocessos
python pipeline.py --apenas detectar      # Só detecção YOLO (etapa 1)
python pipeline.py --apenas segmentar     # Só segmentação rembg (etapa 3)
python pipeline.py --apenas renomear      # Só renomeação + CSV (etapas 4+5)
```

## 📦 Dependências Python

Principais:
- `ultralytics` — YOLOv8 para detecção de etiquetas/paints
- `rembg` + `onnxruntime` — segmentação de fundo (isnet + u2net)
- `pytesseract` — OCR de códigos
- `opencv-python` — processamento de imagem
- `torch` / `torchvision` — backend deep learning

Ver `requirements.txt` para lista completa com versões fixadas.

## 🌍 Variáveis de Ambiente

Todas as variáveis aceitam `1`/`true`/`yes`/`on` como verdadeiro e `0`/`false` como falso (onde aplicável).

### Pipeline (`pipeline.py`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `USE_LISTA_REPROCESSAR` | `0` | Se `1`, processa apenas os arquivos listados em `output/analysis/lista_reprocessar_sem_etiqueta.txt` |

### Detecção YOLO (`detect_etiqueta.py`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `YOLO_CONF_MIN` | `0.25` | Confiança mínima para aceitar uma detecção YOLO |
| `PROCESS_LIMIT` | `""` | Limita o número de imagens processadas (definido automaticamente pelo pipeline no modo teste) |
| `DETECT_SKIP_BY_EXISTENCE` | `0` | Pula detecção se o arquivo de saída já existe (modo incremental) |
| `DETECT_SKIP_IF_UPTODATE` | `0` | Pula detecção se o arquivo de saída é mais recente que a entrada (modo incremental) |

### Leitura de código OCR (`ler_codigo.py`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `CODE_READER_FAST` | `0` | Reduz o número máximo de chamadas OCR (mais rápido, menor precisão) |
| `ALLOW_SHORT_BARCODE` | `0` | Aceita barcodes com menos de 10 dígitos (mínimo `SHORT_BARCODE_MIN_DIGITS`) |
| `ENABLE_PAINT_INTENSIVO` | `1` | Ativa OCR intensivo no paint (mais variantes de pré-processamento) |
| `PRIORITIZE_BARCODE_FIRST` | `0` | Tenta barcode antes do OCR de paint no estágio 1 |
| `OCR_ETIQUETA_ADAPTIVE` | `1` | Adapta número de chamadas OCR ao nível de confiança da etiqueta |
| `LER_CODIGO_CANONICAL_ONLY` | `0` | Processa apenas arquivos com nome canônico (modo incremental) |
| `CODE_READ_TIMEOUT_SIMPLE_S` | `5.0` | Budget de tempo (segundos) para o estágio 1 (simples) |
| `CODE_READ_TIMEOUT_INTENSIVO_S` | `12.0` | Budget de tempo (segundos) para o estágio 2 (intensivo) |
| `CODE_READ_TIMEOUT_OCR_S` | `15.0` | Budget de tempo (segundos) para o estágio 3 (OCR de etiqueta) |
| `CODE_READ_TIMEOUT_ITEM_S` | `35.0` | Budget de tempo total por imagem (todos os estágios) |
| `ENABLE_ADAPTIVE_PREPROCESSING` | `1` | Ativa pré-processamento adaptativo (CLAHE + sharpening) |
| `CLAHE_CLIP_LIMIT` | `2.0` | Parâmetro clipLimit do CLAHE |
| `CLAHE_TILE_SIZE` | `8` | Tamanho do tile do CLAHE (pixels) |
| `ENABLE_OCR_ADAPTIVE_ZOOM` | `1` | Amplia automaticamente imagens pequenas antes do OCR |
| `OCR_ZOOM_THRESHOLD_SMALL` | `100` | Lado mínimo (px) para aplicar zoom `OCR_ZOOM_MULTIPLIER_SMALL` |
| `OCR_ZOOM_THRESHOLD_MEDIUM` | `200` | Lado mínimo (px) para aplicar zoom `OCR_ZOOM_MULTIPLIER_MEDIUM` |
| `OCR_ZOOM_MULTIPLIER_SMALL` | `2.0` | Fator de zoom para imagens muito pequenas |
| `OCR_ZOOM_MULTIPLIER_MEDIUM` | `1.5` | Fator de zoom para imagens médias |
| `OCR_CACHE_ENABLED` | `1` | Ativa cache de resultados OCR em `output/cache_ocr/` (SHA256) |

### Segmentação (`segment_rembg.py`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `SEG_PARALLEL_WORKERS` | `2` | Número de workers paralelos para segmentação |
| `SEG_MODEL` | `isnet-general-use` | Modelo rembg padrão (modo single) |
| `SEG_FAST_MODE` | `1` | Redimensiona entrada para `SEG_FAST_MAX_SIDE` antes de segmentar |
| `SEG_FAST_MAX_SIDE` | `1280` | Lado máximo (px) no modo rápido |
| `SEG_ADAPTIVE_RETRY` | `1` | Tenta novamente com resolução maior se a segmentação falhar |
| `SEG_ADAPTIVE_RETRY_MAX_SIDE` | `2048` | Lado máximo (px) na tentativa adaptativa |
| `SEG_SKIP_BY_EXISTENCE` | `0` | Pula segmentação se o arquivo de saída já existe (modo incremental) |
| `SEG_SKIP_IF_UPTODATE` | `0` | Pula segmentação se o arquivo de saída é mais recente que a entrada |
| `SEG_ADAPTIVE_ZOOM` | `1` | Ativa zoom adaptativo antes da segmentação |
| `SEG_ADAPTIVE_ZOOM_MULTIPLIER` | `1.5` | Fator de zoom adaptativo |
| `ENABLE_ENSEMBLE_SEGMENTATION` | `0` | Ativa ensemble de modelos rembg (mais lento, mais preciso) |
| `ENSEMBLE_MODELS` | `isnet-general-use,u2net` | Modelos usados no ensemble (separados por vírgula) |
| `ENSEMBLE_VOTING_THRESHOLD` | `0.5` | Limiar de votação para o ensemble |

### Preparação (`preparar_quadrado_manual.py`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PREP_SKIP_BY_EXISTENCE` | `0` | Pula preparação se o arquivo de saída já existe |
| `PREP_SKIP_IF_UPTODATE` | `0` | Pula preparação se o arquivo de saída é mais recente que a entrada |

### Renomeação (`renomear_final.py` / `renomear_intermediarios.py`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `RENOMEAR_FINAL_CANONICAL_ONLY` | `0` | Processa apenas arquivos com stem canônico (modo incremental) |
| `KEEP_CANONICAL_INTERMEDIATES` | `0` | Preserva intermediários já renomeados canonicamente (modo incremental) |

### Barcode (`barcode_etiqueta.py`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `BARCODE_FAST_PREP` | `0` | Usa pré-processamento simplificado para leitura de barcode |

---

## ⚠️ Problemas Conhecidos

### Imagens com status `SEMCOD` (sem código)
Ocorre quando o modelo YOLO não detecta etiqueta nem paint, **ou** quando o OCR não consegue ler o código. Causas comuns:
- Tipo de joia não representado no dataset de treino (anéis, brincos ornamentados)
- Iluminação muito diferente do treino
- Paint muito pequeno ou desfocado
- Etiqueta com código de barras de baixa qualidade

### Leitura de etiquetas com código de barras
O leitor de barcode usa `pyzbar` (opcional) + OpenCV `BarcodeDetector`. Se `pyzbar` não estiver instalado, apenas o OpenCV é usado (menor taxa de leitura). Para instalar:
```bash
pip install pyzbar
# Windows: também instalar zbar DLL de https://github.com/NaturalHistoryMuseum/pyzbar
```

## 🚀 Performance

| Etapa | Tempo (50 imgs) | % do total |
|-------|----------------|------------|
| 1. Detecção YOLO | ~175s | 23% |
| 2. Preparação | ~20s | 3% |
| 3. Segmentação rembg | ~175s | 23% |
| 4. OCR (gargalo) | ~330s | 43% |
| 5. Renomeação | ~69s | 9% |

**Dicas de performance:**
- Use `--incremental` para reruns (cache OCR = 88-94% mais rápido)
- O cache OCR fica em `output/cache_ocr/` (SHA256 dos arquivos)
- Modo ensemble de segmentação pode ser desabilitado: `ENABLE_ENSEMBLE_SEGMENTATION=0`
