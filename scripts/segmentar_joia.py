import cv2
import numpy as np
from pathlib import Path

INPUT_DIR = Path("input_raw/fotos_originais")
OUTPUT_DEBUG = Path("output/debug_segmentacao")

OUTPUT_DEBUG.mkdir(parents=True, exist_ok=True)

def segmentar_joia(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # suaviza sombras leves
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # threshold adaptativo (aguenta fundo irregular)
    thresh = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        51,
        5
    )

    # remove ruído pequeno
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)

    # acha contornos
    contours, _ = cv2.findContours(
        clean,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None, None

    # escolhe contorno mais "compacto"
    melhor = None
    melhor_score = 0

    h, w = gray.shape

    for c in contours:
        area = cv2.contourArea(c)
        if area < 500:
            continue

        x, y, cw, ch = cv2.boundingRect(c)

        # descarta coisas muito largas (etiqueta)
        if cw / ch > 3 or ch / cw > 3:
            continue

        # score favorece área média e forma compacta
        score = area / (cw * ch)

        if score > melhor_score:
            melhor_score = score
            melhor = c

    if melhor is None:
        return None, None

    mask = np.zeros_like(gray)
    cv2.drawContours(mask, [melhor], -1, 255, -1)

    x, y, cw, ch = cv2.boundingRect(melhor)
    bbox = (x, y, cw, ch)

    return mask, bbox


def main():
    for img_path in INPUT_DIR.glob("*.jpg"):
        img = cv2.imread(str(img_path))
        if img is None:
            continue

        mask, bbox = segmentar_joia(img)
        debug = img.copy()

        if bbox:
            x, y, w, h = bbox
            cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.imwrite(
            str(OUTPUT_DEBUG / f"{img_path.stem}_bbox.jpg"),
            debug
        )

        if mask is not None:
            cv2.imwrite(
                str(OUTPUT_DEBUG / f"{img_path.stem}_mask.jpg"),
                mask
            )


if __name__ == "__main__":
    main()
