import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO
import logging

# =============================
# CONFIG
# =============================
MODEL_PATH = Path("models/best.pt")
INPUT_DIR = Path("input_raw/fotos_originais")
OUTPUT_ETIQUETA = Path("output/etiquetas")
OUTPUT_SEM_ETIQUETA = Path("output/sem_etiqueta")

OUTPUT_ETIQUETA.mkdir(parents=True, exist_ok=True)
OUTPUT_SEM_ETIQUETA.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(message)s")

# =============================
# MODEL
# =============================
model = YOLO(MODEL_PATH)

# =============================
# FUNÇÕES
# =============================

def extrair_polys_obb(result):
    polys = []
    if hasattr(result, "obb") and result.obb is not None:
        obb = result.obb
        if hasattr(obb, "xyxyxyxy") and obb.xyxyxyxy is not None:
            arr = obb.xyxyxyxy.cpu().numpy()
            for p in arr:
                polys.append(p)
    return polys


def limpar_etiquetas_na_imagem(img_bgr, polys, branco=(255, 255, 255), dilate_px=12):
    """
    Remove etiqueta pintando de branco TODO o polígono OBB.
    dilate_px: aumenta um pouco a máscara pra cobrir bordas/sombras da etiqueta.
    """
    h, w = img_bgr.shape[:2]
    out = img_bgr.copy()

    mask = np.zeros((h, w), dtype=np.uint8)

    for poly in polys:
        poly = np.array(poly, dtype=np.int32)
        cv2.fillPoly(mask, [poly], 255)

    if dilate_px and dilate_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px, dilate_px))
        mask = cv2.dilate(mask, k, iterations=1)

    out[mask == 255] = branco
    return out


def order_points(pts):
    # pts: (4,2)
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect

def warp_from_poly(img, poly):
    # poly: (4,2) float/int
    pts = order_points(np.array(poly, dtype="float32"))

    (tl, tr, br, bl) = pts
    wA = np.linalg.norm(br - bl)
    wB = np.linalg.norm(tr - tl)
    hA = np.linalg.norm(tr - br)
    hB = np.linalg.norm(tl - bl)

    maxW = int(max(wA, wB))
    maxH = int(max(hA, hB))

    # evita warp minúsculo
    if maxW < 30 or maxH < 30:
        return None

    dst = np.array([
        [0, 0],
        [maxW - 1, 0],
        [maxW - 1, maxH - 1],
        [0, maxH - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(pts, dst)
    warped = cv2.warpPerspective(img, M, (maxW, maxH))
    return warped

def crop_with_padding(img, poly, pad=20):
    h, w = img.shape[:2]
    poly = np.array(poly, dtype=np.int32)
    x, y, bw, bh = cv2.boundingRect(poly)

    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(w, x + bw + pad)
    y2 = min(h, y + bh + pad)

    return img[y1:y2, x1:x2]


# =============================
# EXECUÇÃO
# =============================

logging.info("Detectando etiquetas...")

results = model.predict(
    source=str(INPUT_DIR),
    imgsz=640,
    conf=0.25,
    save=False
)

for r in results:
    img = cv2.imread(r.path)
    if img is None:
        continue

    polys = extrair_polys_obb(r)

    nome = Path(r.path).stem

    if polys:
        # salvar recortes
        for i, poly in enumerate(polys):
            # 1) crop com padding
            crop = crop_with_padding(img, poly, pad=25)
            out_file_raw = OUTPUT_ETIQUETA / f"{nome}_etiqueta_{i}_raw.jpg"
            cv2.imwrite(str(out_file_raw), crop)

            # 2) warp/retifica usando o poly original
            warped = warp_from_poly(img, poly)
            if warped is not None:
                out_file_warp = OUTPUT_ETIQUETA / f"{nome}_etiqueta_{i}_warp.jpg"
                cv2.imwrite(str(out_file_warp), warped)

        # salvar imagem limpa
        img_limpa = limpar_etiquetas_na_imagem(img, polys)
        cv2.imwrite(str(OUTPUT_SEM_ETIQUETA / f"{nome}.jpg"), img_limpa)

        logging.info(f"✔ {nome} -> {len(polys)} etiqueta(s)")
    else:
        # mesmo sem etiqueta, salvar original para próxima etapa
        cv2.imwrite(str(OUTPUT_SEM_ETIQUETA / f"{nome}.jpg"), img)
        logging.info(f"– {nome} -> sem etiqueta")

logging.info("Finalizado.")
