# Plano de Reorganização - Seguro 🔒

## Status Atual
```
joias_automation/
├── scripts/
│   ├── 1_detect_etiqueta.py (ATIVO - pipeline)
│   ├── 2_preparar_quadrado_manual.py (ATIVO - pipeline)
│   ├── 3_segment_rembg.py (ATIVO - pipeline)
│   ├── 4_renomear_final.py (ATIVO - pipeline)
│   ├── 5_renomear_intermediarios.py (ATIVO - pipeline)
│   ├── 6_validar_saidas.py (ATIVO - pipeline)
│   ├── detect_etiqueta.py (ATIVO - core)
│   ├── ler_codigo.py (ATIVO - core)
│   ├── segment_rembg.py (ATIVO - core)
│   ├── pipeline.py (ATIVO - executor principal)
│   ├── detect_etiqueta_backup.py (BACKUP - criado durante debug)
│   ├── barcode_etiqueta.py (?)
│   ├── bench_barcode_13.py (teste)
│   ├── preparar_quadrado_manual.py (duplicado?)
│   ├── renomear_final.py (duplicado?)
│   ├── renomear_intermediarios.py (duplicado?)
│   ├── revisao_semcod.py (teste/debug)
│   ├── validar_saidas.py (duplicado?)
│   └── _debug_full_ocr.py (debug)
├── input_raw/ (entrada - necessário)
├── output/ (saída - necessário)
├── temp/ (backup/testes)
├── docs/ (documentação)
├── datasets/ (dados de treino)
├── runs/ (resultados de treino YOLO)
├── models/ (modelos)
├── venv/ (ambiente virtual)
└── [Muitos .md de análise]
```

## Ações Propostas

### ✅ MANTER (Essencial)
- `scripts/1_*.py` até `scripts/6_*.py` - Pipeline
- `scripts/pipeline.py` - Executor
- `scripts/detect_etiqueta.py` - Core
- `scripts/ler_codigo.py` - Core
- `scripts/segment_rembg.py` - Core
- `input_raw/` - Entrada
- `output/` - Saída
- `datasets/` - Treino
- `runs/` - Resultados YOLO
- `models/` - Modelos salvos
- `requirements.txt` - Dependências

### 📦 MOVER PARA TEMP (Backup/Reference)
- `detect_etiqueta_backup.py`
- Documentos de análise (.md)
- Logs (pipeline_*.log)
- Scripts de teste/debug

### 🗑️ DELETAR (Lixo)
- `barcode_etiqueta.py` (duplicado?)
- `bench_barcode_13.py` (teste)
- `preparar_quadrado_manual.py` (duplicado do 2_)
- `renomear_final.py` (duplicado do 4_)
- `renomear_intermediarios.py` (duplicado do 5_)
- `revisao_semcod.py` (debug)
- `validar_saidas.py` (duplicado do 6_)
- `_debug_full_ocr.py` (debug)
- test_*.py (teste de ambiente)

### 📁 NOVA ESTRUTURA
```
joias_automation/
├── src/                    (código-fonte)
│   ├── pipeline.py        (executor principal)
│   ├── 1_detect_etiqueta.py
│   ├── 2_preparar_quadrado_manual.py
│   ├── 3_segment_rembg.py
│   ├── 4_renomear_final.py
│   ├── 5_renomear_intermediarios.py
│   ├── 6_validar_saidas.py
│   ├── detect_etiqueta.py
│   ├── ler_codigo.py
│   └── segment_rembg.py
├── data/
│   ├── input/             (antes: input_raw/)
│   ├── output/            (saídas processadas)
│   └── models/            (modelos treinados)
├── datasets/              (dados de treino)
├── runs/                  (resultados YOLO)
├── temp/                  (backup, configs antigas, debug)
├── docs/                  (documentação)
├── venv/                  (ambiente virtual)
├── requirements.txt
├── README.md
└── launch.sh / launch.bat (scripts para iniciar)
```

## Estratégia SEGURA
1. ✅ Criar nova estrutura em paralelo
2. ✅ Testar que tudo ancora funciona
3. ✅ Se quebrar = revert fácil
4. ✅ Commit ao GIT entre cada etapa
5. ✅ Deletar lixo só depois de confirmar
