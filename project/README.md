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
```

## 📦 Dependências Python

Principais:
- `ultralytics` — YOLOv8 para detecção de etiquetas/paints
- `rembg` + `onnxruntime` — segmentação de fundo (isnet + u2net)
- `pytesseract` — OCR de códigos
- `opencv-python` — processamento de imagem
- `torch` / `torchvision` — backend deep learning

Ver `requirements.txt` para lista completa com versões fixadas.

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
