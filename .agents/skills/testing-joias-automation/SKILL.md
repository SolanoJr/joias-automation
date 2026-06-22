---
name: testing-joias-automation
description: Test the joias-automation pipeline and Laboratório de Segmentação end-to-end. Use when verifying pipeline changes, lab improvements, or modular architecture.
---

# Testing joias-automation

## Environment Setup

```bash
cd /home/ubuntu/joias-automation/project
source venv/bin/activate
# Dependencies should already be installed in the venv
python -c "import cv2, rembg, numpy; print('deps OK')"
```

## Devin Secrets Needed

None required. The project runs fully locally with CPU-only OpenCV and rembg.

## Key Directories

- `project/` — main pipeline code
- `project/input_raw/fotos_originais/` — input images (15 YOLO dataset crops)
- `project/output/` — pipeline output (gitignored)
- `project/models/best.pt` — YOLO model (gitignored, not available on Devin)
- `temp/Laboratorio/` — segmentation test lab
- `temp/Laboratorio/resultados/` — lab output

## Testing the Pipeline

### Modular execution (`--apenas`)
```bash
cd project
python pipeline.py --apenas detectar --limit 2   # Only stage 1 (YOLO detection)
python pipeline.py --apenas segmentar --limit 2   # Only stage 3 (rembg)
python pipeline.py --apenas renomear               # Only stages 4+5 (rename + CSV)
python pipeline.py --apenas preparar               # Only stage 2 (square prep)
```

**What to verify:**
- Log should show only the expected stage(s) running
- Step counter should match (e.g., `[1/1]` for single stage, `[1/2]` for renomear)
- No FileNotFoundError even when running from outside `project/`

### Full pipeline
```bash
python pipeline.py --limit 5     # Quick test with 5 images
python pipeline.py --full         # All images
```

**Note:** `--apenas detectar` will log "ERRO: modelo não encontrado" because `models/best.pt` is gitignored. This is expected — the YOLO model must be provided separately.

## Testing the Laboratório

### Basic run
```bash
cd temp/Laboratorio
python rodar_lab.py --seed 42 --n-min 3 --n-max 3
# Open resultados/relatorio_lab.html for visual audit
```

### What to verify
1. `resultados/lab_*.jpg` — should be 1024x1024 pixels
2. `resultados/diag_*.jpg` — side-by-side: original | mask overlay | result
3. `resultados/etapas_*.jpg` — before/after mask refinement comparison
4. `resultados/metricas_lab.json` — zoom_factor, tempo_s, fg_pixels_antes/depois
5. `resultados/relatorio_lab.html` — HTML report with table and inline images

### Amostragem (sampling) verification
```bash
python -c "
import sys; sys.path.insert(0, '.')
from lab_amostragem import selecionar_amostra
imgs = selecionar_amostra(seed=42)
print(f'{len(imgs)} selected')  # Should be 5-10
imgs2 = selecionar_amostra(seed=42)
assert [p.name for p in imgs] == [p.name for p in imgs2], 'Seed not reproducible!'
print('Seed reproducibility OK')
"
```

### Lab configuration via env vars
All lab settings are configurable via `LAB_*` environment variables. Key ones:
- `LAB_ENABLE_GRABCUT=0` — disable GrabCut (faster)
- `LAB_ENABLE_COLOR_REFINE=0` — disable color refinement
- `LAB_ENABLE_SPECULAR_FILTER=0` — disable specular highlight filter
- `LAB_ENABLE_EDGE_MASK=0` — disable edge-based mask reinforcement
- `LAB_AMOSTRA_MIN=5` / `LAB_AMOSTRA_MAX=10` — sample size range

## Testing Absolute Paths

All scripts use `PROJECT_ROOT = Path(__file__).resolve().parent.parent`. Verify by running from an arbitrary directory:
```bash
cd /tmp
python /path/to/joias-automation/project/pipeline.py --help  # Should not crash
cd /path/to/joias-automation
python temp/Laboratorio/rodar_lab.py --seed 99 --n-min 2 --n-max 2  # Should work from repo root
```

## Known Limitations

- **Pre-detection** (`detect_joia`) returns confidence 0.00 on YOLO dataset crops because they are already cropped. With full photos (jewelry on paper/background), pre-detection should activate normally.
- **YOLO model** is not available on Devin (gitignored). Detection stage will log an error but won't crash the pipeline.
- **Performance**: Lab processes ~17s/image on CPU. With 10 images, expect ~3 minutes.
- **No CI** configured on this repo. All testing is manual.

## Test Types

- **Shell-only testing** — no GUI/browser needed. Do NOT record screen.
- Verify outputs via file existence checks, image dimension checks, JSON parsing, and log message grep.
