import logging
import numpy as np
from rembg import new_session, remove
from PIL import Image, ImageOps
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

INPUT_DIR = Path("output/sem_etiqueta")
OUTPUT_DIR = Path("output/segmentado_rembg")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024
MAX_SCALE = 0.85
MARGIN = 40

session = new_session("isnet-general-use")

def processar(imagem_path: Path):
    try:
        img = Image.open(imagem_path)
        img = ImageOps.exif_transpose(img)  # corrige imagem deitada
        img = img.convert("RGBA")
    except Exception as e:
        logging.error(f"Erro ao abrir {imagem_path.name}: {e}")
        return None

    try:
        sem_fundo = remove(img, session=session)
    except Exception as e:
        logging.error(f"Erro no rembg {imagem_path.name}: {e}")
        return None

    arr = np.array(sem_fundo)
    alpha = arr[:, :, 3]
    mask = alpha > 20

    coords = np.column_stack(np.where(mask))
    if coords.size == 0:
        logging.warning(f"Nada detectado em {imagem_path.name}")
        return None

    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)

    x1 = max(0, x1 - MARGIN)
    y1 = max(0, y1 - MARGIN)
    x2 = min(arr.shape[1], x2 + MARGIN)
    y2 = min(arr.shape[0], y2 + MARGIN)

    joia = sem_fundo.crop((x1, y1, x2, y2))

    max_size = int(SIZE * MAX_SCALE)
    joia.thumbnail((max_size, max_size), Image.LANCZOS)

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
