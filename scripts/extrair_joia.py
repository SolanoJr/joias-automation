import cv2
import numpy as np

def extrair_mascara_joia(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, thresh = cv2.threshold(
        blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    kernel = np.ones((7, 7), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None, None

    maior = max(contours, key=cv2.contourArea)

    area = cv2.contourArea(maior)
    if area < 3000:  # heurística simples
        return None, None

    mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.drawContours(mask, [maior], -1, 255, -1)

    x, y, w, h = cv2.boundingRect(maior)

    return mask, (x, y, w, h)
def recortar_joia(img_bgr, mask, bbox):
    x, y, w, h = bbox

    recorte = img_bgr[y:y+h, x:x+w]
    mask_recorte = mask[y:y+h, x:x+w]

    joia = cv2.bitwise_and(recorte, recorte, mask=mask_recorte)

    return joia
