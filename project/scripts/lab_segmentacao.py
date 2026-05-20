"""
lab_segmentacao.py — Laboratório avançado de segmentação de joias.

Objetivo: testar e aprimorar a segmentação, centralização e zoom de joias
sem alterar o pipeline principal (segment_rembg.py).

Melhorias sobre a versão anterior:
  1. Pré-detecção heurística (detect_joia) para guiar o crop/foco
  2. Pipeline de refinamento de máscara multi-estágio
     - Opening → remoção de ruído
     - Filtragem de componentes pequenos
     - Closing → preenchimento de buracos
     - Hull convexo para formas oco (anéis, pulseiras)
  3. Refinamento por cor (HSV) — filtra pixels claramente de fundo
  4. GrabCut — refina bordas usando a máscara do rembg como seed
  5. Ensemble de modelos rembg com votação
  6. Zoom adaptativo com limites de segurança (cap no fator)
  7. Saída de diagnóstico — side-by-side, overlay, métricas JSON, HTML
"""

from __future__ import annotations

import json
import logging
import os
import time
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from rembg import new_session, remove

from detect_joia import detectar_joia

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LAB] %(levelname)s - %(message)s",
)

# ===== CONFIGURAÇÕES DO LABORATÓRIO =====
INPUT_DIR = Path(os.getenv("LAB_INPUT_DIR", "input_raw/fotos_originais"))
OUTPUT_DIR = Path(os.getenv("LAB_OUTPUT_DIR", "output/lab_segmentacao"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_SIZE = int(os.getenv("LAB_CANVAS_SIZE", "1024"))
TARGET_RATIO = float(os.getenv("LAB_TARGET_RATIO", "0.85"))
ALPHA_THRESHOLD = int(os.getenv("LAB_ALPHA_THRESHOLD", "10"))

# Morphology
MORPH_OPEN_KSIZE = int(os.getenv("LAB_MORPH_OPEN_KSIZE", "3"))
MORPH_CLOSE_KSIZE = int(os.getenv("LAB_MORPH_CLOSE_KSIZE", "7"))

# Filtragem de componentes pequenos (fração da área total)
MIN_COMPONENT_RATIO = float(os.getenv("LAB_MIN_COMPONENT_RATIO", "0.005"))

# GrabCut
ENABLE_GRABCUT = os.getenv("LAB_ENABLE_GRABCUT", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
GRABCUT_ITER = int(os.getenv("LAB_GRABCUT_ITER", "3"))

# Refinamento por cor (filtra fundo branco/papel)
ENABLE_COLOR_REFINE = os.getenv("LAB_ENABLE_COLOR_REFINE", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
COLOR_WHITE_V_MIN = int(os.getenv("LAB_COLOR_WHITE_V_MIN", "230"))
COLOR_WHITE_S_MAX = int(os.getenv("LAB_COLOR_WHITE_S_MAX", "30"))

# Ensemble
ENABLE_ENSEMBLE = os.getenv("LAB_ENABLE_ENSEMBLE", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
ENSEMBLE_MODELS = os.getenv("LAB_ENSEMBLE_MODELS", "isnet-general-use,u2net").split(",")
ENSEMBLE_THRESHOLD = float(os.getenv("LAB_ENSEMBLE_THRESHOLD", "0.5"))

# Modelo único (quando ensemble desligado)
SINGLE_MODEL = os.getenv("LAB_MODEL", "isnet-general-use")

# Zoom
ZOOM_MAX = float(os.getenv("LAB_ZOOM_MAX", "3.0"))
ZOOM_MIN = float(os.getenv("LAB_ZOOM_MIN", "0.5"))

# Pré-detecção heurística
ENABLE_PRE_DETECT = os.getenv("LAB_ENABLE_PRE_DETECT", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
PRE_DETECT_CONF_MIN = float(os.getenv("LAB_PRE_DETECT_CONF_MIN", "0.30"))

# Limite de imagens para teste
LAB_LIMIT = int(os.getenv("LAB_LIMIT", "10"))

# Hull convexo para formas oco
ENABLE_CONVEX_HULL = os.getenv("LAB_ENABLE_CONVEX_HULL", "0").strip().lower() in {
    "1", "true", "yes", "on",
}

# Diagnóstico
ENABLE_DIAGNOSTICS = os.getenv("LAB_ENABLE_DIAGNOSTICS", "1").strip().lower() in {
    "1", "true", "yes", "on",
}


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 1. Segmentação com rembg (single ou ensemble)
# ---------------------------------------------------------------------------

def _segmentar_single(img: Image.Image, session) -> Image.Image | None:
    try:
        out = remove(img, session=session)
        return _to_rgba_image(out)
    except Exception as e:
        logging.error(f"Erro no rembg: {e}")
        return None


def _segmentar_ensemble(img: Image.Image) -> Image.Image | None:
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
                logging.info(f"  Ensemble modelo '{model_name.strip()}' OK")
        except Exception as e:
            logging.warning(f"  Ensemble modelo '{model_name.strip()}' falhou: {e}")

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


# ---------------------------------------------------------------------------
# 2. Refinamento de máscara multi-estágio
# ---------------------------------------------------------------------------

def _refinar_mascara(mask_bin: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """
    Pipeline multi-estágio:
      a) Opening — remove ruído pequeno
      b) Filtragem de componentes pequenos
      c) Closing — preenche buracos
      d) (Opcional) Hull convexo
      e) (Opcional) Refinamento por cor
      f) (Opcional) GrabCut
    """
    h, w = mask_bin.shape[:2]
    total_area = h * w

    # a) Morphological opening
    if MORPH_OPEN_KSIZE > 1:
        k_open = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (MORPH_OPEN_KSIZE, MORPH_OPEN_KSIZE),
        )
        mask_bin = cv2.morphologyEx(mask_bin, cv2.MORPH_OPEN, k_open)

    # b) Filtragem de componentes pequenos
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask_bin, connectivity=8,
    )
    if num_labels > 2:
        for lbl in range(1, num_labels):
            area = stats[lbl, cv2.CC_STAT_AREA]
            if area / total_area < MIN_COMPONENT_RATIO:
                mask_bin[labels == lbl] = 0

    # c) Morphological closing
    if MORPH_CLOSE_KSIZE > 1:
        k_close = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (MORPH_CLOSE_KSIZE, MORPH_CLOSE_KSIZE),
        )
        mask_bin = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, k_close)

    # d) Hull convexo (para anéis / formas oco)
    if ENABLE_CONVEX_HULL:
        contours, _ = cv2.findContours(
            mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        if contours:
            hull_mask = np.zeros_like(mask_bin)
            for cnt in contours:
                hull = cv2.convexHull(cnt)
                cv2.drawContours(hull_mask, [hull], -1, 255, cv2.FILLED)
            mask_bin = cv2.bitwise_or(mask_bin, hull_mask)

    # e) Refinamento por cor
    if ENABLE_COLOR_REFINE:
        mask_bin = _refinar_por_cor(mask_bin, img_bgr)

    # f) GrabCut
    if ENABLE_GRABCUT:
        mask_bin = _aplicar_grabcut(mask_bin, img_bgr)

    return mask_bin


def _refinar_por_cor(mask: np.ndarray, img_bgr: np.ndarray) -> np.ndarray:
    """Remove da máscara pixels que são claramente fundo branco/papel."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    v_ch = hsv[:, :, 2]
    s_ch = hsv[:, :, 1]

    fundo_branco = (v_ch >= COLOR_WHITE_V_MIN) & (s_ch <= COLOR_WHITE_S_MAX)
    mask_out = mask.copy()
    mask_out[fundo_branco] = 0

    if mask_out.sum() < mask.sum() * 0.15:
        logging.warning("  Refinamento por cor removeu demais — ignorando")
        return mask

    return mask_out


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
            logging.warning("  GrabCut removeu demais — ignorando")
            return mask_init

        return result
    except Exception as e:
        logging.warning(f"  GrabCut falhou: {e}")
        return mask_init


# ---------------------------------------------------------------------------
# 3. Centralização e zoom
# ---------------------------------------------------------------------------

def _calcular_centroide_e_bbox(mask: np.ndarray) -> tuple | None:
    """
    Retorna (cX, cY, x, y, w, h) do maior contorno, ou None.
    """
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


# ---------------------------------------------------------------------------
# 4. Pré-detecção heurística
# ---------------------------------------------------------------------------

def _pre_detectar_e_cropar(
    img_pil: Image.Image,
) -> tuple[Image.Image, tuple | None]:
    """
    Usa detect_joia para encontrar a região provável da joia.
    Retorna (imagem_cropada_ou_original, detecção_info).
    """
    if not ENABLE_PRE_DETECT:
        return img_pil, None

    img_bgr = _pil_to_bgr(img_pil)
    det = detectar_joia(img_bgr)

    if det.bbox is None or det.confianca < PRE_DETECT_CONF_MIN:
        logging.info(
            f"  Pré-detecção: confiança baixa ({det.confianca:.2f}) — usando imagem inteira"
        )
        return img_pil, det

    x1, y1, x2, y2 = det.bbox
    h, w = img_bgr.shape[:2]

    marg_x = int((x2 - x1) * 0.15)
    marg_y = int((y2 - y1) * 0.15)
    x1 = max(0, x1 - marg_x)
    y1 = max(0, y1 - marg_y)
    x2 = min(w, x2 + marg_x)
    y2 = min(h, y2 + marg_y)

    cropped = img_pil.crop((x1, y1, x2, y2))
    logging.info(
        f"  Pré-detecção: conf={det.confianca:.2f} "
        f"bbox=({x1},{y1},{x2},{y2}) area={det.area_util:.1%}"
    )
    return cropped, det


# ---------------------------------------------------------------------------
# 5. Pipeline completo (por imagem)
# ---------------------------------------------------------------------------

def processar_lab(
    imagem_path: Path,
    session,
) -> dict:
    """
    Processa uma imagem pelo lab completo.
    Retorna dict com:
      - resultado: Image.Image (RGB no canvas) ou None
      - metricas: dict com dados de diagnóstico
      - mask_vis: np.ndarray da máscara final (para debug)
    """
    t0 = time.time()
    metricas: dict = {"arquivo": imagem_path.name, "etapas": []}

    try:
        img_orig = Image.open(imagem_path)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert("RGBA")
    except Exception as e:
        logging.error(f"Erro ao abrir {imagem_path.name}: {e}")
        return {"resultado": None, "metricas": metricas, "mask_vis": None}

    metricas["tamanho_original"] = list(img_orig.size)

    # --- Pré-detecção ---
    img_para_seg, det_info = _pre_detectar_e_cropar(img_orig)
    if det_info is not None:
        metricas["pre_detect"] = {
            "confianca": round(det_info.confianca, 3),
            "area_util": round(det_info.area_util, 3),
            "bbox": det_info.bbox,
            "usado": det_info.confianca >= PRE_DETECT_CONF_MIN,
        }

    # --- Segmentação ---
    if ENABLE_ENSEMBLE:
        rgba_seg = _segmentar_ensemble(img_para_seg)
        metricas["etapas"].append("ensemble")
    else:
        rgba_seg = _segmentar_single(img_para_seg, session)
        metricas["etapas"].append("single_model")

    if rgba_seg is None:
        logging.error(f"Segmentação falhou para {imagem_path.name}")
        return {"resultado": None, "metricas": metricas, "mask_vis": None}

    # --- Criar máscara binária ---
    arr_seg = np.array(rgba_seg)
    alpha = arr_seg[:, :, 3]
    mask_bin = (alpha > ALPHA_THRESHOLD).astype(np.uint8) * 255

    img_bgr = _pil_to_bgr(img_para_seg)
    fg_antes = int(mask_bin.sum() / 255)

    # --- Refinamento ---
    mask_refined = _refinar_mascara(mask_bin, img_bgr)
    fg_depois = int(mask_refined.sum() / 255)
    metricas["fg_pixels_antes"] = fg_antes
    metricas["fg_pixels_depois"] = fg_depois
    metricas["etapas"].append("refinamento")

    # --- Centroide e bbox ---
    cb = _calcular_centroide_e_bbox(mask_refined)
    if cb is None:
        logging.warning(f"Nenhum objeto após refinamento em {imagem_path.name}")
        return {"resultado": None, "metricas": metricas, "mask_vis": mask_refined}

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
        "mask_vis": mask_refined,
        "original": img_para_seg,
    }


# ---------------------------------------------------------------------------
# 6. Diagnóstico e relatório
# ---------------------------------------------------------------------------

def _gerar_imagem_diagnostico(
    original: Image.Image,
    mask: np.ndarray,
    resultado: Image.Image,
    nome: str,
) -> Image.Image:
    """Gera imagem 3-em-1: original | máscara overlay | resultado final."""
    size = 512

    orig_thumb = original.copy().convert("RGB")
    orig_thumb.thumbnail((size, size), Image.Resampling.LANCZOS)

    mask_rgb = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
    orig_bgr = _pil_to_bgr(original)
    orig_resized = cv2.resize(orig_bgr, (mask.shape[1], mask.shape[0]))
    overlay = cv2.addWeighted(orig_resized, 0.6, mask_rgb, 0.4, 0)
    overlay_pil = Image.fromarray(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
    overlay_pil.thumbnail((size, size), Image.Resampling.LANCZOS)

    res_thumb = resultado.copy()
    res_thumb.thumbnail((size, size), Image.Resampling.LANCZOS)

    panel_w = size * 3 + 20
    panel_h = size + 40
    panel = Image.new("RGB", (panel_w, panel_h), (40, 40, 40))

    y_off = 30
    panel.paste(orig_thumb, (5, y_off))
    panel.paste(overlay_pil, (size + 10, y_off))
    panel.paste(res_thumb, (size * 2 + 15, y_off))

    draw = ImageDraw.Draw(panel)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    labels = ["Original", "Máscara Overlay", "Resultado"]
    for i, label in enumerate(labels):
        draw.text((5 + i * (size + 5), 8), label, fill=(255, 255, 255), font=font)
    draw.text((5, panel_h - 18), nome, fill=(180, 180, 180), font=font)

    return panel


def _gerar_relatorio_html(
    resultados: list[dict],
    output_dir: Path,
) -> Path:
    """Gera relatório HTML com todas as imagens processadas."""
    html_path = output_dir / "relatorio_lab.html"
    rows = []
    for r in resultados:
        m = r.get("metricas", {})
        nome = m.get("arquivo", "?")
        ok = r.get("resultado") is not None
        zoom = m.get("zoom_factor", "-")
        tempo = m.get("tempo_s", "-")
        area = m.get("area_joia_ratio", "-")
        pre = m.get("pre_detect", {})
        pre_conf = pre.get("confianca", "-")
        pre_usado = pre.get("usado", "-")

        diag_file = f"diag_{Path(nome).stem}.jpg"
        result_file = f"lab_{nome}"

        status_class = "ok" if ok else "fail"
        status_text = "OK" if ok else "FALHOU"

        rows.append(f"""
        <tr class="{status_class}">
            <td>{nome}</td>
            <td>{status_text}</td>
            <td>{zoom}</td>
            <td>{area}</td>
            <td>{pre_conf}</td>
            <td>{pre_usado}</td>
            <td>{tempo}s</td>
            <td>
                {"<img src='" + diag_file + "' width='600'/>" if ok else "—"}
            </td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<title>Lab Segmentação — Relatório</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #eee; margin: 20px; }}
h1 {{ color: #e94560; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
th {{ background: #16213e; padding: 10px; text-align: left; }}
td {{ padding: 8px; border-bottom: 1px solid #333; vertical-align: top; }}
tr.ok td:nth-child(2) {{ color: #4ecca3; font-weight: bold; }}
tr.fail td:nth-child(2) {{ color: #e94560; font-weight: bold; }}
img {{ border-radius: 4px; max-width: 600px; }}
.summary {{ background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>🔬 Laboratório de Segmentação — Relatório</h1>
<div class="summary">
<p><strong>Total:</strong> {len(resultados)} imagens |
<strong>OK:</strong> {sum(1 for r in resultados if r.get('resultado') is not None)} |
<strong>Falhas:</strong> {sum(1 for r in resultados if r.get('resultado') is None)}</p>
<p><strong>Configuração:</strong> canvas={CANVAS_SIZE}px, target={TARGET_RATIO:.0%},
grabcut={'ON' if ENABLE_GRABCUT else 'OFF'},
cor={'ON' if ENABLE_COLOR_REFINE else 'OFF'},
ensemble={'ON' if ENABLE_ENSEMBLE else 'OFF'},
pre_detect={'ON' if ENABLE_PRE_DETECT else 'OFF'},
hull={'ON' if ENABLE_CONVEX_HULL else 'OFF'}</p>
</div>
<table>
<tr>
<th>Arquivo</th><th>Status</th><th>Zoom</th><th>Área Joia</th>
<th>Pré-Detect Conf</th><th>Pré-Detect Usado</th><th>Tempo</th>
<th>Diagnóstico (Original | Máscara | Resultado)</th>
</tr>
{"".join(rows)}
</table>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    return html_path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff")
    imgs: list[Path] = []
    for ext in exts:
        imgs.extend(INPUT_DIR.glob(ext))
    imgs = sorted(imgs)[:LAB_LIMIT]

    if not imgs:
        logging.error(f"Nenhuma imagem em {INPUT_DIR}")
        return

    logging.info(f"Lab de Segmentação — {len(imgs)} imagens")
    logging.info(
        f"Config: canvas={CANVAS_SIZE} target={TARGET_RATIO:.0%} "
        f"grabcut={ENABLE_GRABCUT} cor={ENABLE_COLOR_REFINE} "
        f"ensemble={ENABLE_ENSEMBLE} pre_detect={ENABLE_PRE_DETECT} "
        f"hull={ENABLE_CONVEX_HULL}"
    )

    session = None
    if not ENABLE_ENSEMBLE:
        session = new_session(SINGLE_MODEL)

    all_results: list[dict] = []
    all_metrics: list[dict] = []

    for idx, p in enumerate(imgs, start=1):
        logging.info(f"[{idx}/{len(imgs)}] {p.name}")
        result = processar_lab(p, session)
        all_results.append(result)
        all_metrics.append(result["metricas"])

        if result["resultado"] is not None:
            out_path = OUTPUT_DIR / f"lab_{p.name}"
            result["resultado"].save(out_path, quality=95)
            logging.info(f"  Salvo: {out_path}")

            if ENABLE_DIAGNOSTICS and result.get("original") and result.get("mask_vis") is not None:
                diag = _gerar_imagem_diagnostico(
                    result["original"],
                    result["mask_vis"],
                    result["resultado"],
                    p.name,
                )
                diag_path = OUTPUT_DIR / f"diag_{p.stem}.jpg"
                diag.save(diag_path, quality=90)
        else:
            logging.warning(f"  Falhou: {p.name}")

    # Salvar métricas
    metrics_path = OUTPUT_DIR / "metricas_lab.json"
    metrics_path.write_text(
        json.dumps(all_metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logging.info(f"Métricas salvas em: {metrics_path}")

    # Gerar relatório HTML
    if ENABLE_DIAGNOSTICS:
        html_path = _gerar_relatorio_html(all_results, OUTPUT_DIR)
        logging.info(f"Relatório HTML: {html_path}")

    ok = sum(1 for r in all_results if r["resultado"] is not None)
    logging.info(f"Lab concluído: {ok}/{len(imgs)} OK")


if __name__ == "__main__":
    main()
