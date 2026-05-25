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
    ENABLE_LABEL_FILTER,
    LABEL_GREEN_H_MIN,
    LABEL_GREEN_H_MAX,
    LABEL_GREEN_S_MIN,
    LABEL_GREEN_V_MIN,
    LABEL_DIST_SEPARATE,
    ENABLE_EDGE_OBJECT_REMOVAL,
    EDGE_OBJECT_METALLIC_S_MIN,
    ENABLE_SPECULAR_FILTER,
    SPECULAR_V_MIN,
    SPECULAR_S_MAX,
    SPECULAR_NEIGHBOR_KSIZE,
    SPECULAR_NEIGHBOR_S_MIN,
    SPECULAR_MIN_CLUSTER_PX,
    ENABLE_EDGE_MASK,
    EDGE_CANNY_LOW,
    EDGE_CANNY_HIGH,
    EDGE_DILATE_ITER,
    ENABLE_GRABCUT,
    GRABCUT_ITER,
    PRE_DETECT_CONF_MIN,
)

logger = logging.getLogger("lab")


def refinar_mascara(
    mask_bin: np.ndarray,
    img_bgr: np.ndarray,
    pre_detect_ok: bool = False,
) -> np.ndarray:
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

    # 2) Filtragem de componentes (preserva pares; descarta etiqueta por brilho)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask_bin, connectivity=8,
    )
    if num_labels > 2:
        hsv_full = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        areas = [stats[lbl, cv2.CC_STAT_AREA] for lbl in range(1, num_labels)]
        max_area = max(areas) if areas else 1
        for lbl in range(1, num_labels):
            area = stats[lbl, cv2.CC_STAT_AREA]
            too_small_abs = area / total_area < MIN_COMPONENT_RATIO
            too_small_rel = area / max_area < 0.15
            if not (too_small_abs and too_small_rel):
                # Candidate to keep — but check if it looks like a label
                if area / max_area >= 0.15 and area / max_area < 0.85:
                    comp_pixels = labels == lbl
                    mean_s = float(hsv_full[:, :, 1][comp_pixels].mean())
                    mean_v = float(hsv_full[:, :, 2][comp_pixels].mean())
                    # Paper/label: very low saturation + high brightness
                    if mean_s < 25 and mean_v > 200:
                        logger.info(
                            f"  Componente {lbl}: descartado (papel/etiqueta "
                            f"S={mean_s:.0f} V={mean_v:.0f})"
                        )
                        mask_bin[labels == lbl] = 0
                        continue
                continue
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

    # 5b) Filtro de etiquetas (verde/branco como fundo garantido)
    if ENABLE_LABEL_FILTER:
        mask_bin = _filtrar_etiquetas(mask_bin, img_bgr, pre_detect_ok=pre_detect_ok)

    # 5c) Remoção de objetos de borda (papel/etiqueta colada nas margens)
    if ENABLE_EDGE_OBJECT_REMOVAL:
        mask_bin = _remover_objetos_borda(mask_bin, img_bgr)

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


def _filtrar_etiquetas(
    mask: np.ndarray,
    img_bgr: np.ndarray,
    pre_detect_ok: bool = False,
) -> np.ndarray:
    """
    Remove pixels de etiquetas (verde, branco) da máscara.
    - Verde agressivo: H 30-95, S ≥ 25
    - Branco-etiqueta: V ≥ 230, S ≤ 25 (excluindo metal brilhante)
    - Se a pré-detecção encontrou a joia, usa distanceTransform + erosão
      para desconectar a joia de etiquetas brancas coladas.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h_ch = hsv[:, :, 0]
    s_ch = hsv[:, :, 1]
    v_ch = hsv[:, :, 2]

    # --- Etiqueta verde (range expandido) ---
    verde = (
        (h_ch >= LABEL_GREEN_H_MIN) & (h_ch <= LABEL_GREEN_H_MAX)
        & (s_ch >= LABEL_GREEN_S_MIN) & (v_ch >= LABEL_GREEN_V_MIN)
    )

    # --- Etiqueta branca (excluindo brilho metálico) ---
    branco_candidato = (v_ch >= 230) & (s_ch <= 25)
    # Proteger pixels brilhantes com vizinhança saturada (metal)
    s_blur = cv2.blur(s_ch.astype(np.float32), (15, 15))
    metalico_vizinho = s_blur >= 20
    branco = branco_candidato & (~metalico_vizinho)

    etiqueta = verde | branco

    # --- Separação por distanceTransform (se pré-detect OK) ---
    if pre_detect_ok and LABEL_DIST_SEPARATE:
        mask_out = _separar_joia_etiqueta_dist(mask, etiqueta, img_bgr)
    else:
        mask_out = mask.copy()
        mask_out[etiqueta] = 0

    # Safety: se removeu demais, ignorar
    if mask_out.sum() < mask.sum() * 0.15:
        logger.warning("  Filtro de etiquetas removeu demais — ignorando")
        return mask

    fg_removed = int((mask.sum() - mask_out.sum()) / 255)
    if fg_removed > 0:
        logger.info(f"  Filtro de etiquetas: removeu {fg_removed} px")

    return mask_out


def _separar_joia_etiqueta_dist(
    mask: np.ndarray,
    etiqueta_map: np.ndarray,
    img_bgr: np.ndarray,
) -> np.ndarray:
    """
    Usa erosão + distanceTransform para desconectar a joia de etiquetas
    brancas/verdes que estejam coladas na máscara. Depois reconstrói
    apenas os componentes com brilho metálico.
    """
    # Erosão forte para quebrar pontes finas entre joia e etiqueta
    k_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    eroded = cv2.erode(mask, k_erode, iterations=2)

    # distanceTransform: pixels longe da borda (centro) sobrevivem
    dist = cv2.distanceTransform(eroded, cv2.DIST_L2, 5)
    # Normalizar e binarizar: manter apenas núcleos sólidos
    if dist.max() > 0:
        dist_norm = dist / dist.max()
    else:
        dist_norm = dist
    nucleos = (dist_norm >= 0.25).astype(np.uint8) * 255

    # Expandir núcleos de volta (dilatar) para recuperar a forma original
    k_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    nucleos_expandidos = cv2.dilate(nucleos, k_dilate, iterations=2)

    # Intersecção com a máscara original: recuperar forma
    reconstruido = cv2.bitwise_and(mask, nucleos_expandidos)

    # Agora classificar componentes: manter apenas os metálicos
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        reconstruido, connectivity=8,
    )
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask_out = np.zeros_like(mask)

    for lbl in range(1, num_labels):
        comp_pixels = labels == lbl
        area = stats[lbl, cv2.CC_STAT_AREA]
        if area < 50:
            continue
        mean_s = float(hsv[:, :, 1][comp_pixels].mean())
        mean_v = float(hsv[:, :, 2][comp_pixels].mean())
        # Componente metálico: tem alguma saturação OU brilho alto com variação
        v_std = float(hsv[:, :, 2][comp_pixels].std())
        is_metallic = mean_s >= 15 or v_std >= 30
        is_paper = mean_s < 15 and mean_v > 210 and v_std < 20
        if is_paper:
            logger.info(
                f"  distTransform: componente {lbl} descartado "
                f"(papel S={mean_s:.0f} V={mean_v:.0f} Vstd={v_std:.0f})"
            )
            continue
        # Manter: usar a forma original (não erodida) nesta região
        region_original = cv2.bitwise_and(mask, mask, mask=comp_pixels.astype(np.uint8) * 255)
        # Expandir um pouco para recuperar bordas perdidas na erosão
        k_recover = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        region_expanded = cv2.dilate(region_original, k_recover, iterations=1)
        region_final = cv2.bitwise_and(mask, region_expanded)
        mask_out = cv2.bitwise_or(mask_out, region_final)

    # Se a reconstrução perdeu demais, fallback para remoção simples
    if mask_out.sum() < mask.sum() * 0.20:
        logger.warning("  distTransform: reconstrução fraca, fallback simples")
        mask_out = mask.copy()
        mask_out[etiqueta_map] = 0

    return mask_out


def _remover_objetos_borda(
    mask: np.ndarray,
    img_bgr: np.ndarray,
) -> np.ndarray:
    """
    Identifica componentes que tocam as bordas do crop.
    Se o componente toca a borda E não tem brilho especular/metálico,
    é marcado como fundo (papel/etiqueta).
    """
    h, w = mask.shape[:2]
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask, connectivity=8,
    )
    if num_labels <= 1:
        return mask

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask_out = mask.copy()
    removed_any = False

    for lbl in range(1, num_labels):
        x0 = stats[lbl, cv2.CC_STAT_LEFT]
        y0 = stats[lbl, cv2.CC_STAT_TOP]
        bw = stats[lbl, cv2.CC_STAT_WIDTH]
        bh = stats[lbl, cv2.CC_STAT_HEIGHT]
        area = stats[lbl, cv2.CC_STAT_AREA]

        # Verificar se toca alguma borda do crop
        touches_left = x0 == 0
        touches_top = y0 == 0
        touches_right = (x0 + bw) >= w
        touches_bottom = (y0 + bh) >= h
        touches_border = touches_left or touches_top or touches_right or touches_bottom

        if not touches_border:
            continue

        # Ignorar se for o componente dominante (joia principal)
        total_fg = int(mask.sum() / 255)
        if total_fg > 0 and area / total_fg > 0.5:
            continue

        # Analisar cor: componentes metálicos têm saturação ou variação de V
        comp_pixels = labels == lbl
        mean_s = float(hsv[:, :, 1][comp_pixels].mean())
        mean_v = float(hsv[:, :, 2][comp_pixels].mean())
        v_std = float(hsv[:, :, 2][comp_pixels].std())

        is_metallic = (
            mean_s >= EDGE_OBJECT_METALLIC_S_MIN
            or (mean_v > 150 and v_std > 40)
        )

        if not is_metallic:
            mask_out[comp_pixels] = 0
            removed_any = True
            logger.info(
                f"  Borda: componente {lbl} removido "
                f"(toca borda, S={mean_s:.0f} V={mean_v:.0f} Vstd={v_std:.0f})"
            )

    if removed_any and mask_out.sum() < mask.sum() * 0.15:
        logger.warning("  Filtro de borda removeu demais — ignorando")
        return mask

    return mask_out


def _filtrar_brilho_especular(mask: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """
    Remove reflexos especulares (brilho intenso do metal) da máscara,
    distinguindo brilho de metal (na joia) de fundo branco real.

    Usa três heurísticas para decidir se um pixel brilhante é fundo:
      1. Vizinhança de saturação — se pixels ao redor têm cor (S alto),
         o brilho é reflexo sobre a joia → preservar.
      2. Região de borda — só remove candidatos na borda da máscara.
      3. Cluster mínimo — ignora grupos < N pixels (ruído isolado).
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    v_ch = hsv[:, :, 2]
    s_ch = hsv[:, :, 1]

    # Candidatos especulares: V alto, S baixo
    especular = (v_ch >= SPECULAR_V_MIN) & (s_ch <= SPECULAR_S_MAX)

    if especular.sum() == 0:
        return mask

    # Heurística 1: vizinhança de saturação
    # Blur grande no canal S para capturar contexto ao redor
    k = SPECULAR_NEIGHBOR_KSIZE
    s_neighborhood = cv2.blur(
        s_ch.astype(np.float32), (k, k),
    )
    # Pixels com vizinhos coloridos estão SOBRE a joia → proteger
    on_jewelry = s_neighborhood >= SPECULAR_NEIGHBOR_S_MIN

    # Heurística 2: restringir à borda da máscara
    kernel_borda = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    eroded = cv2.erode(mask, kernel_borda, iterations=1)
    borda = cv2.subtract(mask, eroded)

    # Só remove se: especular E na borda E sem cor ao redor
    candidatos = especular & (borda > 0) & (~on_jewelry)

    if candidatos.sum() == 0:
        return mask

    # Heurística 3: filtrar clusters pequenos demais (ruído)
    cand_mask = np.zeros_like(mask)
    cand_mask[candidatos] = 255
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        cand_mask, connectivity=8,
    )
    remover = np.zeros_like(mask, dtype=bool)
    for lbl in range(1, num_labels):
        if stats[lbl, cv2.CC_STAT_AREA] >= SPECULAR_MIN_CLUSTER_PX:
            remover[labels == lbl] = True

    if not remover.any():
        return mask

    mask_out = mask.copy()
    mask_out[remover] = 0

    # Fechar buracos mínimos criados pela remoção
    k_heal = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask_out = cv2.morphologyEx(mask_out, cv2.MORPH_CLOSE, k_heal)

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
    """
    Retorna (cX, cY, x, y, w, h) englobando TODOS os contornos significativos.
    Isso garante que pares (brincos, conjuntos) fiquem centralizados juntos.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Filtrar contornos com área > 0
    valid = [c for c in contours if cv2.contourArea(c) > 0]
    if not valid:
        return None

    # Concatenar todos os contornos significativos para bbox único
    max_area = max(cv2.contourArea(c) for c in valid)
    relevant = [c for c in valid if cv2.contourArea(c) >= max_area * 0.10]
    all_pts = np.vstack(relevant)
    x, y, w, h = cv2.boundingRect(all_pts)

    # Centroide ponderado por área de cada contorno
    total_m00 = 0.0
    sum_cx = 0.0
    sum_cy = 0.0
    for cnt in relevant:
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            total_m00 += M["m00"]
            sum_cx += M["m10"]
            sum_cy += M["m01"]

    if total_m00 == 0:
        return None

    cX = int(sum_cx / total_m00)
    cY = int(sum_cy / total_m00)
    return cX, cY, x, y, w, h
