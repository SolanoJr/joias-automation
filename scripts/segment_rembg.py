import logging
import numpy as np
import cv2
from rembg import new_session, remove
from PIL import Image, ImageOps
from pathlib import Path
from io import BytesIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

USE_ORIGINAL_INPUT = True
ORIGINAL_INPUT_DIR = Path("input_raw/fotos_originais")
SEM_ETIQUETA_INPUT_DIR = Path("output/sem_etiqueta")
INPUT_DIR = ORIGINAL_INPUT_DIR if USE_ORIGINAL_INPUT else SEM_ETIQUETA_INPUT_DIR
OUTPUT_DIR = Path("output/segmentado_rembg")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024
MAX_SCALE = 0.78
MARGIN_RATIO = 0.05
MARGIN_MIN = 24
MARGIN_MAX = 96
ALPHA_THRESHOLD = 10
DILATE_ITERATIONS = 1
FALLBACK_ORIGINAL_SE_FALHAR = True
MIN_FOREGROUND_RATIO = 0.012
MIN_BBOX_AREA_RATIO = 0.02

session = new_session("isnet-general-use")


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

def processar(imagem_path: Path):
    try:
        img = Image.open(imagem_path)
        img = ImageOps.exif_transpose(img)  # corrige imagem deitada
        img = img.convert("RGBA")
    except Exception as e:
        logging.error(f"Erro ao abrir {imagem_path.name}: {e}")
        return None

    try:
        rembg_output = remove(img, session=session)
    except Exception as e:
        logging.error(f"Erro no rembg {imagem_path.name}: {e}")
        return None

    sem_fundo = _to_rgba_image(rembg_output)
    if sem_fundo is None:
        logging.error(f"Tipo de saída do rembg não suportado em {imagem_path.name}")
        if FALLBACK_ORIGINAL_SE_FALHAR:
            logging.warning(f"Fallback original em {imagem_path.name}")
            return _renderizar_no_fundo_branco(img)
        return None

    arr = np.array(sem_fundo)
    alpha = arr[:, :, 3]
    mask = alpha > ALPHA_THRESHOLD
    if DILATE_ITERATIONS > 0:
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.dilate(mask.astype(np.uint8), kernel, iterations=DILATE_ITERATIONS).astype(bool)

    coords = np.column_stack(np.where(mask))
    if coords.size == 0:
        logging.warning(f"Nada detectado em {imagem_path.name}")
        if FALLBACK_ORIGINAL_SE_FALHAR:
            logging.warning(f"Fallback original em {imagem_path.name}")
            return _renderizar_no_fundo_branco(img)
        return None

    foreground_ratio = float(mask.mean())
    if foreground_ratio < MIN_FOREGROUND_RATIO:
        logging.warning(
            f"Máscara muito pequena em {imagem_path.name} (ratio={foreground_ratio:.4f}); usando fallback original"
        )
        if FALLBACK_ORIGINAL_SE_FALHAR:
            return _renderizar_no_fundo_branco(img)
        return None

    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)

    bbox_area_ratio = ((x2 - x1 + 1) * (y2 - y1 + 1)) / float(arr.shape[0] * arr.shape[1])
    if bbox_area_ratio < MIN_BBOX_AREA_RATIO:
        logging.warning(
            f"BBox muito pequena em {imagem_path.name} (bbox={bbox_area_ratio:.4f}); usando fallback original"
        )
        if FALLBACK_ORIGINAL_SE_FALHAR:
            return _renderizar_no_fundo_branco(img)
        return None

    margem = int(min(arr.shape[:2]) * MARGIN_RATIO)
    margem = max(MARGIN_MIN, min(MARGIN_MAX, margem))

    x1 = max(0, x1 - margem)
    y1 = max(0, y1 - margem)
    x2 = min(arr.shape[1], x2 + margem + 1)
    y2 = min(arr.shape[0], y2 + margem + 1)

    joia = sem_fundo.crop((x1, y1, x2, y2))

    max_size = int(SIZE * MAX_SCALE)
    joia.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    fundo = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    x = (SIZE - joia.width) // 2
    y = (SIZE - joia.height) // 2
    fundo.paste(joia, (x, y), joia)

    return fundo.convert("RGB")

def main():
    imgs = list(INPUT_DIR.glob("*.jpg"))
    if not imgs:
        logging.error(f"Nenhuma imagem em {INPUT_DIR}")
        return

    for p in imgs:
        logging.info(f"Processando {p.name}")
        out = processar(p)
        if out is None:
            logging.warning(f"Falhou: {p.name}")
            continue
        out.save(OUTPUT_DIR / p.name, quality=95)
        logging.info(f"OK -> {OUTPUT_DIR / p.name}")

if __name__ == "__main__":
    main()
