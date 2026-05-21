"""
lab_mascara.py — Refinamento de máscara de joia com heurísticas OpenCV.

Foco: ignorar brilho excessivo do metal e focar na silhueta da joia.
Todas as operações são CPU-only (OpenCV puro), sem modelos pesados.

Pipeline de refinamento:
  1. Opening — remove ruído pequeno
  2. Filtragem de componentes pequenos
  3. Closing — preenche buracos na silhueta
  4. (Opcional) Hull convexo — para formas oco (anéis)
  5. Filtro de fundo branco/papel (HSV)
  6. Filtro de brilho especular — remove reflexos que parecem fundo
  7. Reforço por bordas — usa Canny para recuperar silhueta perdida
  8. (Opcional) GrabCut — refina bordas finais
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from lab_config import (
    MORPH_OPEN_KSIZE,
    MORPH_CLOSE_KSIZE,
    MIN_COMPONENT_RATIO,
    ENABLE_CONVEX_HULL,
    ENABLE_COLOR_REFINE,
    COLOR_WHITE_V_MIN,
    COLOR_WHITE_S_MAX,
    ENABLE_SPECULAR_FILTER,
    SPECULAR_V_MIN,
    SPECULAR_S_MAX,
    ENABLE_EDGE_MASK,
    EDGE_CANNY_LOW,
    EDGE_CANNY_HIGH,
    EDGE_DILATE_ITER,
    ENABLE_GRABCUT,
    GRABCUT_ITER,
)

logger = logging.getLogger("lab")


def refinar_mascara(mask_bin: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """
    Pipeline multi-estágio de refinamento.
    Retorna máscara binária refinada (0 ou 255).
    """
    h, w = mask_bin.shape[:2]
    total_area = h * w

    # 1) Morphological opening — remove ruído pequeno
    if MORPH_OPEN_KSIZE > 1:
        k_open = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (MORPH_OPEN_KSIZE, MORPH_OPEN_KSIZE),
        )
        mask_bin = cv2.morphologyEx(mask_bin, cv2.MORPH_OPEN, k_open)

    # 2) Filtragem de componentes pequenos
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask_bin, connectivity=8,
    )
    if num_labels > 2:
        for lbl in range(1, num_labels):
            area = stats[lbl, cv2.CC_STAT_AREA]
            if area / total_area < MIN_COMPONENT_RATIO:
                mask_bin[labels == lbl] = 0

    # 3) Morphological closing — preenche buracos na silhueta
    if MORPH_CLOSE_KSIZE > 1:
        k_close = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (MORPH_CLOSE_KSIZE, MORPH_CLOSE_KSIZE),
        )
        mask_bin = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, k_close)

    # 4) Hull convexo (para anéis / formas oco)
    if ENABLE_CONVEX_HULL:
        mask_bin = _aplicar_hull_convexo(mask_bin)

    # 5) Filtro de fundo branco/papel
    if ENABLE_COLOR_REFINE:
        mask_bin = _filtrar_fundo_branco(mask_bin, img_bgr)

    # 6) Filtro de brilho especular
    if ENABLE_SPECULAR_FILTER:
        mask_bin = _filtrar_brilho_especular(mask_bin, img_bgr)

    # 7) Reforço por bordas — recupera silhueta perdida
    if ENABLE_EDGE_MASK:
        mask_bin = _reforcar_por_bordas(mask_bin, img_bgr)

    # 8) GrabCut
    if ENABLE_GRABCUT:
        mask_bin = _aplicar_grabcut(mask_bin, img_bgr)

    return mask_bin


def _aplicar_hull_convexo(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        hull_mask = np.zeros_like(mask)
        for cnt in contours:
            hull = cv2.convexHull(cnt)
            cv2.drawContours(hull_mask, [hull], -1, 255, cv2.FILLED)
        mask = cv2.bitwise_or(mask, hull_mask)
    return mask


def _filtrar_fundo_branco(mask: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """Remove pixels claramente de fundo branco/papel."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    v_ch = hsv[:, :, 2]
    s_ch = hsv[:, :, 1]

    fundo_branco = (v_ch >= COLOR_WHITE_V_MIN) & (s_ch <= COLOR_WHITE_S_MAX)
    mask_out = mask.copy()
    mask_out[fundo_branco] = 0

    # Safety check: se removeu demais, ignora
    if mask_out.sum() < mask.sum() * 0.15:
        logger.warning("  Filtro de fundo branco removeu demais — ignorando")
        return mask

    return mask_out


def _filtrar_brilho_especular(mask: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """
    Remove reflexos especulares (brilho intenso do metal) da máscara.

    Reflexos especulares têm valor muito alto (V > 245) e saturação
    muito baixa (S < 15). Esses pixels parecem fundo branco mas estão
    sobre a joia. Removê-los da máscara melhora a silhueta.

    Porém, só removemos se o pixel estiver na BORDA da máscara
    (dilatação - erosão), para não criar buracos no meio da joia.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    v_ch = hsv[:, :, 2]
    s_ch = hsv[:, :, 1]

    especular = (v_ch >= SPECULAR_V_MIN) & (s_ch <= SPECULAR_S_MAX)

    # Só aplicar na região de borda da máscara (não no interior)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    eroded = cv2.erode(mask, kernel, iterations=1)
    borda = cv2.subtract(mask, eroded)

    # Remover apenas reflexos que estão na borda
    remover = especular & (borda > 0)
    mask_out = mask.copy()
    mask_out[remover] = 0

    if mask_out.sum() < mask.sum() * 0.20:
        logger.warning("  Filtro especular removeu demais — ignorando")
        return mask

    return mask_out


def _reforcar_por_bordas(mask: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """
    Usa detecção de bordas (Canny) para recuperar partes da silhueta
    que podem ter sido perdidas pelo rembg ou pelos filtros anteriores.

    Funciona bem para joias com contornos nítidos contra fundo claro.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, EDGE_CANNY_LOW, EDGE_CANNY_HIGH)

    # Dilatar bordas para criar região contínua
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    edges_dilated = cv2.dilate(edges, kernel, iterations=EDGE_DILATE_ITER)

    # Preencher contornos fechados
    contours, _ = cv2.findContours(edges_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    edge_fill = np.zeros_like(mask)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        # Ignorar contornos muito pequenos ou que cobrem a imagem toda
        img_area = mask.shape[0] * mask.shape[1]
        if area < img_area * 0.01 or area > img_area * 0.95:
            continue
        cv2.drawContours(edge_fill, [cnt], -1, 255, cv2.FILLED)

    if edge_fill.sum() == 0:
        return mask

    # Intersecção: só adiciona bordas que fazem sentido com a máscara existente
    # (overlap significativo com a máscara atual)
    overlap = cv2.bitwise_and(mask, edge_fill)
    overlap_ratio = overlap.sum() / max(1, mask.sum())

    if overlap_ratio > 0.3:
        # Boa correlação: combinar
        mask_out = cv2.bitwise_or(mask, edge_fill)
        # Limpar com closing
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_out = cv2.morphologyEx(mask_out, cv2.MORPH_CLOSE, k)
        return mask_out

    return mask


def _aplicar_grabcut(mask_init: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """Refina bordas da máscara usando GrabCut com a máscara do rembg como seed."""
    h, w = img_bgr.shape[:2]
    if h < 50 or w < 50:
        return mask_init

    gc_mask = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)
    gc_mask[mask_init > 0] = cv2.GC_PR_FGD

    kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    sure_fg = cv2.erode(mask_init, kernel_erode, iterations=2)
    gc_mask[sure_fg > 0] = cv2.GC_FGD

    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    expanded = cv2.dilate(mask_init, kernel_dilate, iterations=2)
    sure_bg = cv2.bitwise_not(expanded)
    gc_mask[sure_bg > 0] = cv2.GC_BGD

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(
            img_bgr, gc_mask, None, bgd_model, fgd_model,
            GRABCUT_ITER, cv2.GC_INIT_WITH_MASK,
        )
        result = np.where(
            (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0,
        ).astype(np.uint8)

        if result.sum() < mask_init.sum() * 0.20:
            logger.warning("  GrabCut removeu demais — ignorando")
            return mask_init

        return result
    except Exception as e:
        logger.warning(f"  GrabCut falhou: {e}")
        return mask_init


def calcular_centroide_e_bbox(mask: np.ndarray) -> tuple | None:
    """Retorna (cX, cY, x, y, w, h) do maior contorno, ou None."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    cnt = max(contours, key=cv2.contourArea)
    M = cv2.moments(cnt)
    if M["m00"] == 0:
        return None

    cX = int(M["m10"] / M["m00"])
    cY = int(M["m01"] / M["m00"])
    x, y, w, h = cv2.boundingRect(cnt)
    return cX, cY, x, y, w, h
