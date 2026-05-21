---
name: testing-lab-segmentacao
description: Test the segmentation lab (lab_segmentacao.py) end-to-end. Use when verifying segmentation, centering, zoom, or mask refinement changes.
---

# Testing Lab Segmentação

## Setup

```bash
cd project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Test Images

The repo has real jewelry images in `datasets/codigo_v1/images/valid/` that can be used for testing. Copy them to the expected input dir:

```bash
mkdir -p input_raw/fotos_originais
cp ../datasets/codigo_v1/images/valid/*.jpg input_raw/fotos_originais/
```

**Note:** These YOLO dataset images are already cropped, so the `detect_joia` pre-detection heuristic may report low confidence (0.00) and fall back to using the full image. This is expected behavior — with real full-scene photos, pre-detection should activate properly.

## Running the Lab

```bash
cd project
source venv/bin/activate

# Quick test (3 images, all features)
LAB_LIMIT=3 python scripts/lab_segmentacao.py

# Test with specific features disabled
LAB_ENABLE_GRABCUT=0 LAB_ENABLE_COLOR_REFINE=0 LAB_LIMIT=2 python scripts/lab_segmentacao.py

# Test with ensemble (slower, uses multiple models)
LAB_ENABLE_ENSEMBLE=1 LAB_LIMIT=2 python scripts/lab_segmentacao.py
```

## Key Environment Variables

All prefixed with `LAB_*`:
- `LAB_LIMIT` — number of images to process
- `LAB_ENABLE_GRABCUT` — GrabCut edge refinement (default: 1)
- `LAB_ENABLE_COLOR_REFINE` — HSV white/paper removal (default: 1)
- `LAB_ENABLE_PRE_DETECT` — Pre-detection heuristic (default: 1)
- `LAB_ENABLE_ENSEMBLE` — Multi-model ensemble (default: 0)
- `LAB_ENABLE_CONVEX_HULL` — Convex hull for rings (default: 0)
- `LAB_ENABLE_DIAGNOSTICS` — Generate diagnostic images + HTML (default: 1)

## Verifying Output

After running, check `output/lab_segmentacao/`:

1. **`lab_*.jpg`** — Final result images (should be 1024x1024)
2. **`diag_*.jpg`** — 3-panel diagnostic (Original | Mask Overlay | Result, ~1556x552)
3. **`metricas_lab.json`** — Metrics per image (zoom_factor, centroide, bbox, fg_pixels, tempo)
4. **`relatorio_lab.html`** — HTML report for visual review

### Automated Verification Script

```python
import json
from PIL import Image
from pathlib import Path
import numpy as np

output_dir = Path("output/lab_segmentacao")

# Check metrics
with open(output_dir / "metricas_lab.json") as f:
    metrics = json.load(f)

for m in metrics:
    assert 0.5 <= m["zoom_factor"] <= 3.0, f"Zoom out of range: {m['zoom_factor']}"
    assert m["fg_pixels_depois"] > 0, "Mask destroyed"
    assert "single_model" in m["etapas"] or "ensemble" in m["etapas"]

# Check result images
for p in output_dir.glob("lab_*.jpg"):
    img = Image.open(p)
    assert img.size == (1024, 1024), f"Wrong size: {img.size}"
    arr = np.array(img)
    assert np.mean(arr[400:624, 400:624]) < 250, "Center is empty (all white)"
    assert np.mean(arr[0:100, 0:100]) > 240, "Corner not white (background issue)"

print("All checks passed!")
```

## Important Notes

- The lab script runs from `project/` directory and imports `detect_joia` from `scripts/`
- First run downloads the rembg model (~179MB) to `~/.u2net/`
- GrabCut is the slowest step (~10-20s per image); disable with `LAB_ENABLE_GRABCUT=0` for faster iteration
- The lab does NOT modify the main pipeline (`segment_rembg.py`)
- `temp/` directory is in `.gitignore` — any files there won't be committed
