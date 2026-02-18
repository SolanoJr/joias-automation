import os
import cv2
import numpy as np
from PIL import Image

from segment_anything import sam_model_registry, SamAutomaticMaskGenerator

# -------- CONFIG --------
INPUT_DIR = "input_raw/fotos_originais"
OUT_DIR = "output/joias_limpa"
MODEL_PATH = "models/sam_vit_b.pth"
IMG_SIZE = 1024
os.makedirs(OUT_DIR, exist_ok=True)

# Load SAM model
sam = sam_model_registry["vit_b"](checkpoint=MODEL_PATH)
sam.to(device="cpu")

mask_generator = SamAutomaticMaskGenerator(
    sam,
    points_per_side=32,
    pred_iou_thresh=0.88,
    stability_score_thresh=0.92,
    crop_n_layers=1,
    crop_n_points_downscale_factor=2,
    min_mask_region_area=500,  # Smaller area to detect labels
)

def remove_label(img, masks):
    # Sort masks by area (smallest to largest)
    masks = sorted(masks, key=lambda m: m["area"])

    # Assume the smallest mask is the label
    label_mask = masks[0]["segmentation"].astype(np.uint8) * 255

    # Invert the label mask to keep everything but the label
    inverted_mask = cv2.bitwise_not(label_mask)

    # Remove the label by applying the inverted mask
    img_no_label = cv2.bitwise_and(img, img, mask=inverted_mask)

    return img_no_label

for fname in os.listdir(INPUT_DIR):
    if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
        continue

    path = os.path.join(INPUT_DIR, fname)
    img_bgr = cv2.imread(path)
    if img_bgr is None:
        continue

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    # Generate masks
    masks = mask_generator.generate(img_rgb)

    if not masks:
        print(f"[SKIP] No masks found: {fname}")
        continue

    # Remove the label
    img_cleaned = remove_label(img_bgr, masks)

    # Save the cleaned image
    out_path = os.path.join(OUT_DIR, fname)
    cv2.imwrite(out_path, img_cleaned)

    print(f"[OK] Processed: {fname}")

print("DONE")