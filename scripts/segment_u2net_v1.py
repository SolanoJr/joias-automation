import os
from pathlib import Path
from PIL import Image, ImageOps
from rembg import remove, new_session
from io import BytesIO
import numpy as np

INPUT_DIR = Path("input_raw/fotos_originais")
OUTPUT_DIR = Path("output_u2net")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

session = new_session("u2net")

SIZE = 1024
MARGIN_PERCENT = 0.08  # 8% de margem extra
MAX_SCALE = 0.85       # joia ocupa no máximo 85% da imagem final

def expand_bbox(bbox, width, height):
    x1, y1, x2, y2 = bbox
    bw = x2 - x1
    bh = y2 - y1

    margin_x = int(bw * MARGIN_PERCENT)
    margin_y = int(bh * MARGIN_PERCENT)

    x1 = max(0, x1 - margin_x)
    y1 = max(0, y1 - margin_y)
    x2 = min(width, x2 + margin_x)
    y2 = min(height, y2 + margin_y)

    return (x1, y1, x2, y2)

def processar(img_path):
    print(f"Processando {img_path.name}")

    img = Image.open(img_path).convert("RGBA")
    img = ImageOps.exif_transpose(img)

    resultado = remove(img, session=session)

    if isinstance(resultado, bytes):
        resultado = Image.open(BytesIO(resultado))
    elif not isinstance(resultado, Image.Image):
        raise TypeError(f"Unexpected type for resultado. Expected bytes or PIL.Image.Image, got {type(resultado)}.")

    arr = np.array(resultado)

    # usar canal alpha
    alpha = arr[:, :, 3]

    # máscara mais rígida
    mask = alpha > 20

    coords = np.column_stack(np.where(mask))

    if coords.size == 0:
        print(f"Nenhuma joia detectada na imagem {img_path.name}")
        return None

    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)

    # margem fixa em pixels (mais estável que percentual)
    MARGIN = 40

    x1 = max(0, x1 - MARGIN)
    y1 = max(0, y1 - MARGIN)
    x2 = min(arr.shape[1], x2 + MARGIN)
    y2 = min(arr.shape[0], y2 + MARGIN)

    joia = resultado.crop((x1, y1, x2, y2))

    # controlar escala máxima
    max_size = int(SIZE * MAX_SCALE)
    joia.thumbnail((max_size, max_size), Image.LANCZOS)

    fundo = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))

    x = (SIZE - joia.width) // 2
    y = (SIZE - joia.height) // 2

    fundo.paste(joia, (x, y), joia)

    return fundo.convert("RGB")

if __name__ == "__main__":
    for img_path in INPUT_DIR.glob("*.jpg"):
        resultado = processar(img_path)
        if resultado:
            resultado.save(OUTPUT_DIR / f"{img_path.stem}.jpg", quality=95)
