"""
lab_segmentacao.py — Pipeline de segmentação do Laboratório.

Processa uma imagem pelo pipeline completo:
  1. Pré-detecção heurística (opcional)
  2. Segmentação rembg (single ou ensemble)
  3. Refinamento de máscara multi-estágio
  4. Centralização e zoom no canvas
  5. Geração de diagnóstico

Cada etapa salva resultado parcial (output progressivo).
"""
from __future__ import annotations

import logging
import sys
import time
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from lab_config import (
    PROJECT_ROOT,
    CANVAS_SIZE,
    TARGET_RATIO,
    ALPHA_THRESHOLD,
    ZOOM_MAX,
    ZOOM_MIN,
    ENABLE_ENSEMBLE,
    ENSEMBLE_MODELS,
    ENSEMBLE_THRESHOLD,
    SINGLE_MODEL,
    ENABLE_PRE_DETECT,
    PRE_DETECT_CONF_MIN,
    OUTPUT_DIR,
)
from lab_mascara import refinar_mascara, calcular_centroide_e_bbox

logger = logging.getLogger("lab")

# Adicionar scripts ao path para importar detect_joia
_scripts_dir = str(PROJECT_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def _to_rgba_image(rembg_output) -> Image.Image | None:
    if isinstance(rembg_output, Image.Image):
        return rembg_output.convert("RGBA")
    if isinstance(rembg_output, (bytes, bytearray)):
        try:
            return Image.open(BytesIO(rembg_output)).convert("RGBA")
        except Exception:
            return None
    if isinstance(rembg_output, np.ndarray):
        try:
            return Image.fromarray(rembg_output).convert("RGBA")
        except Exception:
            return None
    return None


def _pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
    rgb = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _segmentar_single(img: Image.Image, session) -> Image.Image | None:
    from rembg import remove
    try:
        out = remove(img, session=session)
        return _to_rgba_image(out)
    except Exception as e:
        logger.error(f"Erro no rembg: {e}")
        return None


def _segmentar_ensemble(img: Image.Image) -> Image.Image | None:
    from rembg import new_session, remove

    masks: list[np.ndarray] = []
    base_arr = np.array(img.convert("RGBA"))

    for model_name in ENSEMBLE_MODELS:
        try:
            sess = new_session(model_name.strip())
            out = remove(img, session=sess)
            rgba = _to_rgba_image(out)
            if rgba is not None:
                alpha = np.array(rgba)[:, :, 3]
                masks.append((alpha > ALPHA_THRESHOLD).astype(np.uint8))
                logger.info(f"  Ensemble modelo '{model_name.strip()}' OK")
        except Exception as e:
            logger.warning(f"  Ensemble modelo '{model_name.strip()}' falhou: {e}")

    if not masks:
        return None

    if len(masks) == 1:
        combined = masks[0] * 255
    else:
        stack = np.stack(masks, axis=0)
        combined = (np.mean(stack, axis=0) >= ENSEMBLE_THRESHOLD).astype(np.uint8) * 255

    result = base_arr.copy()
    result[:, :, 3] = combined
    return Image.fromarray(result, "RGBA")


def _pre_detectar_e_cropar(img_pil: Image.Image) -> tuple[Image.Image, dict | None]:
    """Usa detect_joia para encontrar a região provável da joia."""
    if not ENABLE_PRE_DETECT:
        return img_pil, None

    try:
        from detect_joia import detectar_joia
    except ImportError:
        logger.warning("  detect_joia não disponível — pulando pré-detecção")
        return img_pil, None

    img_bgr = _pil_to_bgr(img_pil)
    det = detectar_joia(img_bgr)

    info = {
        "confianca": round(det.confianca, 3),
        "area_util": round(det.area_util, 3),
        "bbox": det.bbox,
        "usado": det.confianca >= PRE_DETECT_CONF_MIN,
    }

    if det.bbox is None or det.confianca < PRE_DETECT_CONF_MIN:
        logger.info(f"  Pré-detecção: confiança baixa ({det.confianca:.2f}) — usando imagem inteira")
        return img_pil, info

    x1, y1, x2, y2 = det.bbox
    h, w = img_bgr.shape[:2]

    marg_x = int((x2 - x1) * 0.15)
    marg_y = int((y2 - y1) * 0.15)
    x1 = max(0, x1 - marg_x)
    y1 = max(0, y1 - marg_y)
    x2 = min(w, x2 + marg_x)
    y2 = min(h, y2 + marg_y)

    cropped = img_pil.crop((x1, y1, x2, y2))
    logger.info(f"  Pré-detecção: conf={det.confianca:.2f} bbox=({x1},{y1},{x2},{y2})")
    return cropped, info


def _renderizar_no_canvas(
    rgba_img: Image.Image,
    mask: np.ndarray,
    centroide_bbox: tuple,
) -> Image.Image:
    """Centraliza a joia no canvas usando o centroide e zoom adaptativo."""
    cX, cY, x, y, w, h = centroide_bbox

    arr = np.array(rgba_img)
    arr[:, :, 3] = mask
    joia_img = Image.fromarray(arr, "RGBA")
    joia_crop = joia_img.crop((x, y, x + w, y + h))

    max_side = max(w, h)
    target_size = CANVAS_SIZE * TARGET_RATIO
    zoom = target_size / max_side
    zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))

    new_w = max(1, int(w * zoom))
    new_h = max(1, int(h * zoom))

    if new_w > CANVAS_SIZE or new_h > CANVAS_SIZE:
        scale_down = min(CANVAS_SIZE / new_w, CANVAS_SIZE / new_h) * 0.95
        new_w = max(1, int(new_w * scale_down))
        new_h = max(1, int(new_h * scale_down))
        zoom = zoom * scale_down

    joia_rescaled = joia_crop.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 255))

    rel_cX = (cX - x) * zoom
    rel_cY = (cY - y) * zoom
    paste_x = int((CANVAS_SIZE / 2) - rel_cX)
    paste_y = int((CANVAS_SIZE / 2) - rel_cY)

    paste_x = max(-(new_w // 2), min(CANVAS_SIZE - new_w // 2, paste_x))
    paste_y = max(-(new_h // 2), min(CANVAS_SIZE - new_h // 2, paste_y))

    canvas.paste(joia_rescaled, (paste_x, paste_y), joia_rescaled)
    return canvas.convert("RGB")


def processar_imagem(
    imagem_path: Path,
    session,
    output_dir: Path | None = None,
) -> dict:
    """
    Processa uma imagem pelo lab completo.

    Output progressivo: cada etapa salva resultado parcial.

    Retorna dict com:
      - resultado: Image.Image (RGB no canvas) ou None
      - metricas: dict com dados de diagnóstico
      - mask_rembg: np.ndarray da máscara pós-rembg (para comparativo)
      - mask_refined: np.ndarray da máscara final
      - original: Image.Image usada na segmentação
    """
    out_dir = output_dir or OUTPUT_DIR
    t0 = time.time()
    metricas: dict = {"arquivo": imagem_path.name, "etapas": []}

    # --- Abrir imagem ---
    try:
        img_orig = Image.open(imagem_path)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert("RGBA")
    except Exception as e:
        logger.error(f"Erro ao abrir {imagem_path.name}: {e}")
        metricas["erro"] = str(e)
        # Output progressivo: salvar status mesmo em falha
        _salvar_status_parcial(out_dir, imagem_path.name, "erro_abertura", metricas)
        return {"resultado": None, "metricas": metricas, "mask_rembg": None, "mask_refined": None, "original": None}

    metricas["tamanho_original"] = list(img_orig.size)
    metricas["etapas"].append("abertura_ok")

    # --- Pré-detecção ---
    img_para_seg, det_info = _pre_detectar_e_cropar(img_orig)
    if det_info is not None:
        metricas["pre_detect"] = det_info
    metricas["etapas"].append("pre_deteccao")

    # --- Segmentação ---
    if ENABLE_ENSEMBLE:
        rgba_seg = _segmentar_ensemble(img_para_seg)
        metricas["etapas"].append("ensemble")
    else:
        rgba_seg = _segmentar_single(img_para_seg, session)
        metricas["etapas"].append("single_model")

    if rgba_seg is None:
        logger.error(f"Segmentação falhou para {imagem_path.name}")
        metricas["erro"] = "segmentacao_falhou"
        _salvar_status_parcial(out_dir, imagem_path.name, "erro_segmentacao", metricas)
        return {"resultado": None, "metricas": metricas, "mask_rembg": None, "mask_refined": None, "original": img_para_seg}

    # --- Criar máscara binária ---
    arr_seg = np.array(rgba_seg)
    alpha = arr_seg[:, :, 3]
    mask_rembg = (alpha > ALPHA_THRESHOLD).astype(np.uint8) * 255

    img_bgr = _pil_to_bgr(img_para_seg)
    fg_antes = int(mask_rembg.sum() / 255)

    # Output progressivo: salvar máscara rembg pura
    metricas["etapas"].append("mascara_rembg_ok")

    # --- Refinamento ---
    mask_refined = refinar_mascara(mask_rembg, img_bgr)
    fg_depois = int(mask_refined.sum() / 255)
    metricas["fg_pixels_antes"] = fg_antes
    metricas["fg_pixels_depois"] = fg_depois
    metricas["fg_delta_pct"] = round((fg_depois - fg_antes) / max(1, fg_antes) * 100, 1)
    metricas["etapas"].append("refinamento")

    # --- Centroide e bbox ---
    cb = calcular_centroide_e_bbox(mask_refined)
    if cb is None:
        logger.warning(f"Nenhum objeto após refinamento em {imagem_path.name}")
        metricas["erro"] = "sem_objeto_pos_refinamento"
        _salvar_status_parcial(out_dir, imagem_path.name, "sem_objeto", metricas)
        return {"resultado": None, "metricas": metricas, "mask_rembg": mask_rembg, "mask_refined": mask_refined, "original": img_para_seg}

    cX, cY, bx, by, bw, bh = cb
    h_img, w_img = mask_refined.shape[:2]
    metricas["centroide"] = [cX, cY]
    metricas["bbox_joia"] = [bx, by, bw, bh]
    metricas["area_joia_ratio"] = round((bw * bh) / (w_img * h_img), 4)

    max_side = max(bw, bh)
    target_size = CANVAS_SIZE * TARGET_RATIO
    zoom = target_size / max_side
    zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
    metricas["zoom_factor"] = round(zoom, 3)

    # --- Renderizar no canvas ---
    resultado = _renderizar_no_canvas(rgba_seg, mask_refined, cb)
    metricas["etapas"].append("renderizacao")

    elapsed = time.time() - t0
    metricas["tempo_s"] = round(elapsed, 2)

    return {
        "resultado": resultado,
        "metricas": metricas,
        "mask_rembg": mask_rembg,
        "mask_refined": mask_refined,
        "original": img_para_seg,
    }


def _salvar_status_parcial(output_dir: Path, nome: str, status: str, metricas: dict):
    """Salva status parcial para output progressivo (mesmo em falha)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    status_file = output_dir / f"status_{Path(nome).stem}.txt"
    status_file.write_text(
        f"status: {status}\netapas: {', '.join(metricas.get('etapas', []))}\n",
        encoding="utf-8",
    )
