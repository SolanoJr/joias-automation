# joias-automation

Sistema completo de processamento de imagens de joias com OCR automático para leitura de códigos.

## 🚀 Iniciar Rápido

A pasta **`project/`** é totalmente self-contained. Você pode copiá-la para qualquer lugar e executar:

```bash
cd project
python -m venv venv
.\venv\Scripts\Activate.ps1  # (Windows) ou source venv/bin/activate (Linux)
pip install -r requirements.txt
python pipeline.py --limit 5  # teste rápido com 5 imagens
python pipeline.py --full     # processar todas as imagens
```

## 📁 Estrutura do Repositório

### `project/` (PRINCIPAL)
- **self-contained**: contém tudo necessário para rodar
- `input_raw/fotos_originais/` - dados de entrada
- `output/` - resultados processados
- `models/best.pt` - modelo YOLOv8 pré-treinado
- `scripts/` - pipeline e utilitários
- `pipeline.py` - executor principal
- `requirements.txt` - dependências Python

### Pastas de Contexto (para estudo/entendimento)
- **`scripts/`** - wrappers que apontam para `project/scripts/` (interface legada)
- **`docs/`** - documentação técnica e arquitetura
- **`datasets/`** - dados de treinamento usados
- **`input_raw/`** - cópia original dos dados (veja também em `project/input_raw/`)
- **`runs/`** - resultados históricos de treinamento YOLO
- **`temp/`** - arquivos de backup, análises antigas, debug

### Documentação
- **`PLANO_REORGANIZACAO.md`** - como reorganizamos o projeto
- **`PLANO_IMPLEMENTACAO_OCR_CACHE.md`** - implementação de cache de OCR
- **`README_progress.md`** - histórico de progresso e versões
- **`reorg_analysis.ipynb`** - notebook de análise

## 🔄 Pipeline

O pipeline processa imagens em 6 etapas:

1. **Detectar etiquetas e paints** → `1_detect_etiqueta.py`
2. **Preparar quadrado manual** → `2_preparar_quadrado_manual.py`
3. **Segmentar (rembg)** → `3_segment_rembg.py`
4. **Renomear e gerar CSV** → `4_renomear_final.py`
5. **Renomear intermediários** → `5_renomear_intermediarios.py`
6. **Validar saídas** → `6_validar_saidas.py` (apenas modo `--full`)

Veja `project/scripts/` ou `docs/ordem_execucao.md` para detalhes.

## 📊 Compreender o Código

- **Gargalos principais**: `scripts/ler_codigo.py` (OCR), `scripts/segment_rembg.py` (segmentação)
- **Performance**: veja `PLANO_IMPLEMENTACAO_OCR_CACHE.md`
- **Análises detalhadas**: pasta `temp/` contém histórico de análises

## 🛠️ Desenvolvimento

Para adicionar features ou otimizações:
1. Edite em `project/scripts/`
2. Teste: `python pipeline.py --limit 10`
3. Scripts em `scripts/` (raiz) servem como forwarding para `project/scripts/`

## 📦 Dependências Principais

- `ultralytics` - YOLO para detecção
- `rembg` - segmentação de fundo
- `pytesseract` - OCR
- `opencv-python` - processamento de imagem

Veja `project/requirements.txt` para lista completa.

## 📝 Notas

- `project/` pode ser copiado como um projeto independente
- Pastas ao redor servem como repositório do conhecimento/histórico
- `temp/` contém backups e versões antigas (seguro remover)
