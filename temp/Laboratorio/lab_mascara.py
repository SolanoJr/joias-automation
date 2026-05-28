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
    LABEL_GREEN_S_MAX,
    ENABLE_GEOMETRIC_FILTER,
    GEOMETRIC_MIN_RECT_AREA_RATIO,
    GEOMETRIC_MAX_ASPECT_RATIO_DIFF,
    ENABLE_WATERSHED_SEPARATION,
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
    ENABLE_INTENSITY_SEPARATION,
    INTENSITY_V_THRESHOLD,
    INTENSITY_MIN_RATIO,
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

    # 2) Filtragem de componentes pequenos (preserva pares como brincos)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask_bin, connectivity=8,
    )
    if num_labels > 2:
        areas = [stats[lbl, cv2.CC_STAT_AREA] for lbl in range(1, num_labels)]
        max_area = max(areas) if areas else 1
        for lbl in range(1, num_labels):
            area = stats[lbl, cv2.CC_STAT_AREA]
            # Manter se: tamanho absoluto significativo OU
            # tamanho relativo ao maior componente >= 15% (par/conjunto)
            if area / total_area < MIN_COMPONENT_RATIO and area / max_area < 0.15:
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
        mask_bin = _filtrar_etiquetas(mask_bin, img_bgr)

    # 5c) Filtro geométrico para remover retângulos perfeitos (etiquetas)
    if ENABLE_GEOMETRIC_FILTER:
        mask_bin = _filtrar_formas_geometricas(mask_bin)

    # 5d) Separação de objetos com Watershed (para brincos deitados/colados)
    if ENABLE_WATERSHED_SEPARATION:
        mask_bin = _separar_objetos_watershed(mask_bin)

    # 6) Filtro de brilho especular
    if ENABLE_SPECULAR_FILTER:
        mask_bin = _filtrar_brilho_especular(mask_bin, img_bgr)

    # 6b) Separação por intensidade — remove regiões muito claras (etiquetas)
    if ENABLE_INTENSITY_SEPARATION:
        mask_bin = _separar_por_intensidade(mask_bin, img_bgr)

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


def _filtrar_etiquetas(mask: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """
    Remove pixels de etiquetas (verde, branco) da máscara.
    Etiquetas de joias são tipicamente verdes ou brancas com texto.
    Se a pré-detecção falhou, este filtro usa a cor predominante
    da etiqueta como 'fundo garantido'.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h_ch = hsv[:, :, 0]
    s_ch = hsv[:, :, 1]
    v_ch = hsv[:, :, 2]

    # Etiqueta verde: H em [35-85], S em [LABEL_GREEN_S_MIN, LABEL_GREEN_S_MAX], V em [LABEL_GREEN_V_MIN, 255]
    verde = (
        (h_ch >= LABEL_GREEN_H_MIN) & (h_ch <= LABEL_GREEN_H_MAX) &
        (s_ch >= LABEL_GREEN_S_MIN) & (s_ch <= LABEL_GREEN_S_MAX) &
        (v_ch >= LABEL_GREEN_V_MIN)
    )

    # Etiqueta branca já é coberta pelo filtro de fundo branco (etapa 5),
    # mas reforçamos aqui com regiões brancas compactas (componentes conectados)
    branco = (v_ch >= 240) & (s_ch <= 20)

    etiqueta = verde | branco
    total_etiqueta = etiqueta.sum()
    if total_etiqueta == 0:
        return mask

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


def _filtrar_formas_geometricas(mask: np.ndarray) -> np.ndarray:
    """
    Remove formas que se assemelham a retângulos perfeitos, como etiquetas.
    Usa heurísticas baseadas em contornos e suas propriedades geométricas.
    """
    mask_out = mask.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h, w = mask.shape[:2]
    total_area = h * w

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area == 0:
            continue

        # Aproximação poligonal para verificar se é um retângulo
        perimeter = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * perimeter, True)

        # Verifica se é um retângulo (4 vértices) e remove imediatamente
        if len(approx) == 4:
            x, y, w_cnt, h_cnt = cv2.boundingRect(cnt)
            aspect_ratio = float(w_cnt) / h_cnt
            # Considera como etiqueta retangular, remove da máscara
            cv2.drawContours(mask_out, [cnt], -1, 0, cv2.FILLED)
            logger.info(f"  Filtro geométrico: removeu retângulo com área {area} e aspect_ratio {aspect_ratio:.2f}")

    # Safety check: se removeu demais, ignora
    if mask_out.sum() < mask.sum() * 0.15:
        logger.warning("  Filtro geométrico removeu demais — ignorando")
        return mask

    return mask_out


def _separar_objetos_watershed(mask: np.ndarray) -> np.ndarray:
    """
    Usa distanceTransform e watershed para separar objetos conectados na máscara.
    Útil para brincos deitados ou joias coladas em etiquetas.
    """
    # Converter a máscara para CV_8U se ainda não for
    mask_8u = mask.astype(np.uint8)

    # Encontrar a distância euclidiana para o pixel de fundo mais próximo
    dist_transform = cv2.distanceTransform(mask_8u, cv2.DIST_L2, 5)

    # Encontrar os picos locais (prováveis centros dos objetos)
    _, sure_fg = cv2.threshold(dist_transform, 0.7 * dist_transform.max(), 255, 0)
    sure_fg = np.uint8(sure_fg)

    # Encontrar a região de fundo (pixels que não são joia)
    unknown = cv2.subtract(mask_8u, sure_fg)

    # Marcadores para o algoritmo Watershed
    num_labels, markers = cv2.connectedComponents(sure_fg)
    # Adicionar 1 a todos os marcadores para que o fundo seja 1 e os objetos comecem em 2
    markers = markers + 1
    # Marcar a região desconhecida com 0
    markers[unknown == 255] = 0

    # Aplicar Watershed
    # A imagem original não é usada diretamente, mas é necessária para a função
    # Criamos uma imagem falsa 3 canais para o watershed
    img_fake = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    markers = cv2.watershed(img_fake, markers)

    # A máscara final é onde markers > 1 (não é fundo nem região desconhecida)
    mask_out = np.zeros_like(mask, dtype=np.uint8)
    mask_out[markers > 1] = 255

    logger.info(f"  Watershed: separou {num_labels - 1} objetos.")

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


def _separar_por_intensidade(mask: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """
    Remove regiões muito claras (etiquetas) da máscara baseado na intensidade (canal V do HSV).
    
    Etiquetas de joias são tipicamente brancas ou muito claras (V alto),
    enquanto as joias têm variações de cor e intensidade mais baixas.
    
    Esta é uma implementação leve para CPU (i5-2400S), usando apenas
    operações simples de threshold e connected components.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    v_ch = hsv[:, :, 2]
    
    # Regiões muito claras: V acima do threshold
    muito_claro = v_ch >= INTENSITY_V_THRESHOLD
    
    if muito_claro.sum() == 0:
        return mask
    
    mask_out = mask.copy()
    mask_out[muito_claro] = 0
    
    # Safety check: se removeu demais, ignorar
    if mask_out.sum() < mask.sum() * INTENSITY_MIN_RATIO:
        logger.warning("  Separação por intensidade removeu demais — ignorando")
        return mask
    
    fg_removed = int((mask.sum() - mask_out.sum()) / 255)
    if fg_removed > 0:
        logger.info(f"  Separação por intensidade: removeu {fg_removed} px")
    
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
