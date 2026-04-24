import logging
import os
import numpy as np
import cv2
from rembg import new_session, remove
from PIL import Image, ImageOps
from pathlib import Path
from io import BytesIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

USE_ORIGINAL_INPUT = False
ORIGINAL_INPUT_DIR = Path("input_raw/fotos_originais")
QUADRADO_MANUAL_INPUT_DIR = Path("output/4_quadrado_manual")
INPUT_DIR = ORIGINAL_INPUT_DIR if USE_ORIGINAL_INPUT else QUADRADO_MANUAL_INPUT_DIR
OUTPUT_DIR = Path("output/5_segmentado_rembg")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024
MAX_SCALE = 0.75
MARGIN_RATIO = 0.06
MARGIN_MIN = 24
MARGIN_MAX = 112
ALPHA_THRESHOLD = 10
DILATE_ITERATIONS = 1
FALLBACK_ORIGINAL_SE_FALHAR = True
FALLBACK_USAR_ORIGINAL = False
MIN_FOREGROUND_RATIO = 0.012
MIN_BBOX_AREA_RATIO = 0.02
MIN_COMPONENT_AREA_RATIO = 0.010
MANTER_APENAS_MAIOR_COMPONENTE = False

# ===== ZOOM ADAPTATIVO =====
ENABLE_ADAPTIVE_ZOOM = os.getenv("SEG_ADAPTIVE_ZOOM", "1").strip().lower() in {"1", "true", "yes", "on"}
ADAPTIVE_ZOOM_MULTIPLIER = float(os.getenv("SEG_ADAPTIVE_ZOOM_MULTIPLIER", "1.5"))

# ===== ENSEMBLE SEGMENTATION MODELS =====
ENABLE_ENSEMBLE_SEGMENTATION = os.getenv("ENABLE_ENSEMBLE_SEGMENTATION", "1").strip().lower() in {"1", "true", "yes", "on"}
ENSEMBLE_MODELS = os.getenv("ENSEMBLE_MODELS", "isnet-general-use,u2net").split(",")
ENSEMBLE_VOTING_THRESHOLD = float(os.getenv("ENSEMBLE_VOTING_THRESHOLD", "0.5"))

# ===== EXECUCAO / CACHE =====
FAST_MODE = os.getenv("SEG_FAST_MODE", "1").strip().lower() in {"1", "true", "yes", "on"}
FAST_MAX_SIDE = int(os.getenv("SEG_FAST_MAX_SIDE", "1280"))
SEG_ADAPTIVE_RETRY = os.getenv("SEG_ADAPTIVE_RETRY", "1").strip().lower() in {"1", "true", "yes", "on"}
SEG_ADAPTIVE_RETRY_MAX_SIDE = int(os.getenv("SEG_ADAPTIVE_RETRY_MAX_SIDE", "2048"))
SEG_SKIP_IF_UPTODATE = os.getenv("SEG_SKIP_IF_UPTODATE", "0").strip().lower() in {"1", "true", "yes", "on"}
SEG_SKIP_BY_EXISTENCE = os.getenv("SEG_SKIP_BY_EXISTENCE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _is_canonical_stem(stem: str) -> bool:
    s = (stem or "").strip()
    if not s:
        return False
    if " - " in s:
        return False
    if s.endswith("_qm"):
        return False
    return True


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
            if rembg_output.ndim == 2:
                return Image.fromarray(rembg_output).convert("RGBA")
            if rembg_output.ndim == 3:
                return Image.fromarray(rembg_output).convert("RGBA")
        except Exception:
            return None

    return None


def _renderizar_no_fundo_branco(rgba_img: Image.Image) -> Image.Image:
    base = rgba_img.convert("RGBA")
    max_size = int(SIZE * MAX_SCALE)
    base.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    fundo = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    x = (SIZE - base.width) // 2
    y = (SIZE - base.height) // 2
    fundo.paste(base, (x, y), base)
    return fundo.convert("RGB")


def _renderizar_fallback_original(imagem_path: Path, imagem_atual: Image.Image) -> Image.Image:
    if not FALLBACK_USAR_ORIGINAL:
        return _renderizar_no_fundo_branco(imagem_atual)

    original_path = ORIGINAL_INPUT_DIR / imagem_path.name
    if original_path.exists():
        try:
            original = Image.open(original_path)
            original = ImageOps.exif_transpose(original)
            original = original.convert("RGBA")
            return _renderizar_no_fundo_branco(original)
        except Exception:
            pass

    return _renderizar_no_fundo_branco(imagem_atual)


def _downscale_rapido(img: Image.Image, max_side_override: int | None = None) -> Image.Image:
    if not FAST_MODE:
        return img

    max_side = FAST_MAX_SIDE if max_side_override is None else int(max_side_override)
    if max_side <= 0:
        return img

    largura, altura = img.size
    maior_lado = max(largura, altura)
    if maior_lado <= max_side:
        return img

    escala = max_side / float(maior_lado)
    novo_w = max(1, int(largura * escala))
    novo_h = max(1, int(altura * escala))
    return img.resize((novo_w, novo_h), Image.Resampling.LANCZOS)


def _calcular_zoom_adaptativo(bbox_area_ratio: float) -> float:
    """
    Calcula fator de zoom baseado no tamanho relativo da joia.
    Usado para melhorar segmentação de joias pequenas.
    """
    if not ENABLE_ADAPTIVE_ZOOM or bbox_area_ratio <= 0:
        return 1.0
    
    # Se joia é grande o bastante, sem zoom
    if bbox_area_ratio >= 0.05:
        return 1.0
    # Se joia é pequena, aplicar zoom moderado
    elif bbox_area_ratio >= 0.02:
        return min(ADAPTIVE_ZOOM_MULTIPLIER * 2/3, 1.3)
    # Se joia é muito pequena, aplicar zoom agressivo
    elif bbox_area_ratio >= 0.01:
        return ADAPTIVE_ZOOM_MULTIPLIER
    else:
        # Rejeitada (< 1%), retorna 1.0
        return 1.0


def _segmentar_e_renderizar(
    imagem_path: Path,
    img_original: Image.Image,
    max_side_tentativa: int,
) -> tuple[Image.Image | None, str | None]:
    if not ENABLE_ENSEMBLE_SEGMENTATION or len(ENSEMBLE_MODELS) <= 1:
        # Modo single model (padrão)
        try:
            img_para_rembg = _downscale_rapido(img_original, max_side_override=max_side_tentativa)
            rembg_output = remove(img_para_rembg, session=session)
        except Exception as e:
            logging.error(f"Erro no rembg {imagem_path.name}: {e}")
            return None, "erro_rembg"

        sem_fundo = _to_rgba_image(rembg_output)
        if sem_fundo is None:
            logging.error(f"Tipo de saída do rembg não suportado em {imagem_path.name}")
            return None, "saida_nao_suportada"
    else:
        # Modo ensemble - tentar múltiplos modelos
        logging.info(f"Ensemble segmentation para {imagem_path.name}: tentando {len(ENSEMBLE_MODELS)} modelos")
        
        ensemble_masks = []
        img_para_rembg = _downscale_rapido(img_original, max_side_override=max_side_tentativa)
        
        for model_name in ENSEMBLE_MODELS:
            try:
                model_session = new_session(model_name.strip())
                rembg_output = remove(img_para_rembg, session=model_session)
                sem_fundo = _to_rgba_image(rembg_output)
                if sem_fundo is not None:
                    arr = np.array(sem_fundo)
                    alpha = arr[:, :, 3]
                    mask = (alpha > ALPHA_THRESHOLD).astype(np.uint8)
                    ensemble_masks.append(mask)
                    logging.debug(f"Modelo {model_name} OK para {imagem_path.name}")
                else:
                    logging.warning(f"Modelo {model_name} falhou para {imagem_path.name}")
            except Exception as e:
                logging.warning(f"Erro no modelo {model_name} para {imagem_path.name}: {e}")
        
        if not ensemble_masks:
            return None, "erro_ensemble_todos_falharam"
        
        # Voting ensemble: máscara final é a média das máscaras
        if len(ensemble_masks) > 1:
            mask_stack = np.stack(ensemble_masks, axis=0)
            ensemble_mask = np.mean(mask_stack, axis=0) > ENSEMBLE_VOTING_THRESHOLD
            ensemble_mask = ensemble_mask.astype(np.uint8) * 255
            
            # Criar imagem RGBA com a máscara ensemble
            arr = np.array(img_para_rembg.convert("RGBA"))
            arr[:, :, 3] = ensemble_mask
            sem_fundo = Image.fromarray(arr, "RGBA")
            logging.info(f"Ensemble voting aplicado para {imagem_path.name}")
        else:
            # Fallback para single model se apenas um funcionou
            arr = np.array(img_para_rembg.convert("RGBA"))
            arr[:, :, 3] = ensemble_masks[0] * 255
            sem_fundo = Image.fromarray(arr, "RGBA")

    # Continuar com processamento normal da máscara
    arr = np.array(sem_fundo)
    alpha = arr[:, :, 3]
    mask = alpha > ALPHA_THRESHOLD
    if DILATE_ITERATIONS > 0:
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.dilate(mask.astype(np.uint8), kernel, iterations=DILATE_ITERATIONS).astype(bool)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if MANTER_APENAS_MAIOR_COMPONENTE and num_labels > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        maior_idx = int(np.argmax(areas)) + 1
        maior_area = int(stats[maior_idx, cv2.CC_STAT_AREA])
        total_area = int(mask.shape[0] * mask.shape[1])
        comp_ratio = maior_area / float(total_area)

        if comp_ratio < MIN_COMPONENT_AREA_RATIO:
            return None, f"componente_pequeno({comp_ratio:.4f})"

        mask = labels == maior_idx

    coords = np.column_stack(np.where(mask))
    if coords.size == 0:
        return None, "nada_detectado"

    foreground_ratio = float(mask.mean())
    if foreground_ratio < MIN_FOREGROUND_RATIO:
        return None, f"mascara_pequena({foreground_ratio:.4f})"

    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)

    bbox_area_ratio = ((x2 - x1 + 1) * (y2 - y1 + 1)) / float(arr.shape[0] * arr.shape[1])
    if bbox_area_ratio < MIN_BBOX_AREA_RATIO:
        return None, f"bbox_pequena({bbox_area_ratio:.4f})"

    margem = int(min(arr.shape[:2]) * MARGIN_RATIO)
    margem = max(MARGIN_MIN, min(MARGIN_MAX, margem))

    x1 = max(0, x1 - margem)
    y1 = max(0, y1 - margem)
    x2 = min(arr.shape[1], x2 + margem + 1)
    y2 = min(arr.shape[0], y2 + margem + 1)

    joia = sem_fundo.crop((x1, y1, x2, y2))
    max_size = int(SIZE * MAX_SCALE)
    joia.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    
    # ===== ZOOM ADAPTATIVO: Upscale joias pequenas para melhor OCR =====
    zoom_factor = _calcular_zoom_adaptativo(bbox_area_ratio)
    if zoom_factor > 1.0:
        novo_w = int(joia.width * zoom_factor)
        novo_h = int(joia.height * zoom_factor)
        joia = joia.resize((novo_w, novo_h), Image.Resampling.LANCZOS)

    fundo = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    x = (SIZE - joia.width) // 2
    y = (SIZE - joia.height) // 2
    fundo.paste(joia, (x, y), joia)

    return fundo.convert("RGB"), None

def processar(imagem_path: Path):
    try:
        img = Image.open(imagem_path)
        img = ImageOps.exif_transpose(img)  # corrige imagem deitada
        img = img.convert("RGBA")
    except Exception as e:
        logging.error(f"Erro ao abrir {imagem_path.name}: {e}")
        return None

    tentativas = [FAST_MAX_SIDE]
    if SEG_ADAPTIVE_RETRY and FAST_MODE and SEG_ADAPTIVE_RETRY_MAX_SIDE > FAST_MAX_SIDE:
        tentativas.append(SEG_ADAPTIVE_RETRY_MAX_SIDE)

    ultimo_motivo = None
    for i, max_side in enumerate(tentativas, start=1):
        out, motivo = _segmentar_e_renderizar(imagem_path, img, max_side)
        if out is not None:
            if i > 1:
                logging.info(
                    f"Recuperado em retry {i}/{len(tentativas)} para {imagem_path.name} (max_side={max_side})"
                )
            return out

        ultimo_motivo = motivo or "falha"
        if i < len(tentativas):
            logging.info(
                f"Retry de segmentação para {imagem_path.name}: motivo={ultimo_motivo} -> max_side={tentativas[i]}"
            )

    if FALLBACK_ORIGINAL_SE_FALHAR:
        logging.warning(f"Fallback original em {imagem_path.name} (motivo final: {ultimo_motivo})")
        return _renderizar_fallback_original(imagem_path, img)
    return None

def main():
    imgs = [p for p in INPUT_DIR.glob("*.jpg") if _is_canonical_stem(p.stem)]
    if not imgs:
        logging.error(f"Nenhuma imagem em {INPUT_DIR}")
        return

    total = len(imgs)
    if FAST_MODE:
        logging.info(f"Modo rápido de segmentação ativo (FAST_MAX_SIDE={FAST_MAX_SIDE})")

    for idx, p in enumerate(imgs, start=1):
        out_path = OUTPUT_DIR / p.name
        if SEG_SKIP_BY_EXISTENCE and out_path.exists():
            logging.info(f"Processando [{idx}/{total}] {p.name} (cache_hit: segment pulado por existência)")
            continue

        if SEG_SKIP_IF_UPTODATE and out_path.exists():
            try:
                if out_path.stat().st_mtime >= p.stat().st_mtime:
                    logging.info(f"Processando [{idx}/{total}] {p.name} (cache_hit: segment pulado)")
                    continue
            except Exception:
                pass

        logging.info(f"Processando [{idx}/{total}] {p.name}")
        out = processar(p)
        if out is None:
            logging.warning(f"Falhou: {p.name}")
            continue
        out.save(out_path, quality=95)
        logging.info(f"OK -> {out_path}")

if __name__ == "__main__":
    main()
