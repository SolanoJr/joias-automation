import os
import cv2
import numpy as np
from PIL import Image

from segment_anything import sam_model_registry, SamAutomaticMaskGenerator

# -------- CONFIG --------
INPUT_DIR = "input_raw/fotos_originais"
OUT_DIR = "output/segmentado_sam"
DEBUG_DIR = "output/debug_sam"
MODEL_PATH = "models/sam_vit_b.pth"
IMG_SIZE = 1024
MAX_IMAGES = 10  # teste controlado
# ------------------------

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

sam = sam_model_registry["vit_b"](checkpoint=MODEL_PATH)
sam.to(device="cpu")

mask_generator = SamAutomaticMaskGenerator(
    sam,
    points_per_side=32,
    pred_iou_thresh=0.88,
    stability_score_thresh=0.92,
    crop_n_layers=1,
    crop_n_points_downscale_factor=2,
    min_mask_region_area=1000,
)

def centralizar_quadrado(img, mask):
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return None

    x1, x2 = xs.min(), xs.max()
    y1, y2 = ys.min(), ys.max()

    obj = img[y1:y2, x1:x2]

    h, w = obj.shape[:2]
    size = max(h, w)

    canvas = np.ones((size, size, 3), dtype=np.uint8) * 255

    y_off = (size - h) // 2
    x_off = (size - w) // 2

    canvas[y_off:y_off+h, x_off:x_off+w] = obj
    return canvas

count = 0

for fname in os.listdir(INPUT_DIR):
    if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
        continue

    count += 1
    if count > MAX_IMAGES:
        break

    path = os.path.join(INPUT_DIR, fname)
    img_bgr = cv2.imread(path)
    if img_bgr is None:
        continue

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    masks = mask_generator.generate(img_rgb)

    if not masks:
        print(f"[SKIP] sem máscara: {fname}")
        continue

    # pega a maior máscara
    best = max(masks, key=lambda m: m["area"])
    mask = best["segmentation"].astype(np.uint8) * 255

    # debug máscara
    cv2.imwrite(
        os.path.join(DEBUG_DIR, fname),
        mask
    )

    # remove fundo
    fg = cv2.bitwise_and(img_bgr, img_bgr, mask=mask)

    final = centralizar_quadrado(fg, mask)
    if final is None:
        print(f"[FAIL] crop vazio: {fname}")
        continue

    out_path = os.path.join(OUT_DIR, fname)
    cv2.imwrite(out_path, final)

    print(f"[OK] {fname}")

print("DONE")
