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
- **`docs/`** - documentação técnica e arquitetura
- **`datasets/`** - dados de treinamento usados
- **`temp/`** - arquivos históricos, backups e **Laboratório de testes**
- **`temp/Laboratorio/`** - sistema de testes de segmentação (ver abaixo)

## 🔄 Pipeline

O pipeline processa imagens em 6 etapas:

1. **Detectar etiquetas e paints** → `1_detect_etiqueta.py`
2. **Preparar quadrado manual** → `2_preparar_quadrado_manual.py`
3. **Segmentar (rembg)** → `3_segment_rembg.py`
4. **Renomear e gerar CSV** → `4_renomear_final.py`
5. **Renomear intermediários** → `5_renomear_intermediarios.py`
6. **Validar saídas** → `6_validar_saidas.py` (apenas modo `--full`)

Veja `project/scripts/` ou `docs/ordem_execucao.md` para detalhes.

## 🎯 Módulos Independentes

O pipeline agora suporta execução de módulos individuais:

```bash
python pipeline.py --apenas detectar    # só detecção YOLO (etapa 1)
python pipeline.py --apenas preparar     # só preparação quadrada (etapa 2)
python pipeline.py --apenas segmentar    # só segmentação rembg (etapa 3)
python pipeline.py --apenas renomear     # só renomeação + CSV (etapas 4+5)
python pipeline.py                       # pipeline completo (padrão)
```

## 🔬 Laboratório de Segmentação

Sistema de testes em `temp/Laboratorio/` para melhorar a máscara de segmentação:

```bash
cd temp/Laboratorio
python rodar_lab.py              # 5-10 imagens aleatórias
python rodar_lab.py --seed 42    # reprodutível
python rodar_lab.py --todas       # todas as imagens
# Abra resultados/relatorio_lab.html para auditoria visual
```

Módulos do lab:
- `lab_mascara.py` — heurísticas OpenCV para refinar máscara (brilho especular, silhueta por bordas)
- `lab_amostragem.py` — seleção inteligente de 5-10 imagens
- `lab_auditoria.py` — comparações visuais antes/depois para revisão humana
- `lab_segmentacao.py` — pipeline completo de teste

## 📊 Compreender o Código

- **Gargalos principais**: `scripts/ler_codigo.py` (OCR), `scripts/segment_rembg.py` (segmentação)
- **Análises detalhadas**: pasta `temp/` contém histórico de análises e planos anteriores

## 🛠️ Desenvolvimento

Para adicionar features ou otimizações:
1. Edite em `project/scripts/`
2. Teste: `python pipeline.py --limit 10`
3. Use o Laboratório (`temp/Laboratorio/`) para testar melhorias de segmentação

## 📦 Dependências Principais

- `ultralytics` - YOLO para detecção
- `rembg` + `onnxruntime` - segmentação de fundo (isnet + u2net)
- `pytesseract` - OCR (requer Tesseract-OCR instalado no sistema)
- `opencv-python` - processamento de imagem

Veja `project/requirements.txt` para lista completa com versões fixadas.

## ⚠️ Pré-requisito do Sistema

**Tesseract-OCR** deve estar instalado separadamente:
- Windows: https://github.com/UB-Mannheim/tesseract/wiki
- Linux: `sudo apt install tesseract-ocr`
- Mac: `brew install tesseract`

## 📝 Notas

- `project/` pode ser copiado como um projeto independente
- Todos os scripts usam caminhos absolutos baseados em `PROJECT_ROOT` (funciona de qualquer diretório)
- `temp/` contém históricos, planos antigos e o Laboratório de testes
- Documentação histórica (BUGS, PLANOs, progresso) foi movida para `temp/`
