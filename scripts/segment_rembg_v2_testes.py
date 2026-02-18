from rembg import new_session, remove
from PIL import Image, ImageEnhance, ImageOps
from pathlib import Path
from io import BytesIO
import numpy as np

INPUT_DIR = Path("input_raw/fotos_originais")
OUTPUT_DIR = Path("output/segmentado_rembg")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024
MARGIN_PERCENT = 0.08  # 8% de margem extra
MAX_SCALE = 0.85       # joia ocupa no máximo 85% da imagem final

session = new_session("isnet-general-use")

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

def ensure_pil_image(image):
    if isinstance(image, bytes):
        return Image.open(BytesIO(image))
    elif isinstance(image, np.ndarray):
        return Image.fromarray(image)
    elif isinstance(image, Image.Image):
        return image
    else:
        raise TypeError("Unsupported image type")

def pre_process(img):
    """Aplica melhorias de contraste e nitidez na imagem."""
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Sharpness(img).enhance(1.1)
    return img

def reforcar_alpha(img):
    """Reforça o canal alpha da imagem."""
    r, g, b, a = img.split()
    a = a.point(lambda p: 255 if p > 180 else p)
    return Image.merge("RGBA", (r, g, b, a))

def reduzir_branco_fundo(img):
    # Corrige orientação EXIF (imagem deitada)
    img = ImageOps.exif_transpose(img)

    arr = np.array(img)

    # Se tiver canal alpha, separa
    if arr.shape[2] == 4:
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3]
    else:
        rgb = arr
        alpha = None

    # Detecta pixels quase brancos
    mask = (rgb[:, :, 0] > 240) & \
           (rgb[:, :, 1] > 240) & \
           (rgb[:, :, 2] > 240)

    rgb[mask] = [230, 230, 230]

    if alpha is not None:
        arr = np.dstack((rgb, alpha))
    else:
        arr = rgb

    return Image.fromarray(arr)

def processar(imagem_path):
    img = Image.open(imagem_path).convert("RGBA")

    # Reduzir o branco do fundo
    img = reduzir_branco_fundo(img)

    # Pré-processamento da imagem
    img = pre_process(img)

    sem_fundo = remove(img, session=session)

    # Reforçar o canal alpha
    sem_fundo = reforcar_alpha(sem_fundo)

    # Garantir que `sem_fundo` seja uma imagem PIL
    sem_fundo = ensure_pil_image(sem_fundo)

    arr = np.array(sem_fundo)

    # usar canal alpha
    alpha = arr[:, :, 3]

    # máscara mais rígida
    mask = alpha > 20

    coords = np.column_stack(np.where(mask))

    if coords.size == 0:
        return None

    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)

    # margem fixa em pixels (mais estável que percentual)
    MARGIN = 40

    x1 = max(0, x1 - MARGIN)
    y1 = max(0, y1 - MARGIN)
    x2 = min(arr.shape[1], x2 + MARGIN)
    y2 = min(arr.shape[0], y2 + MARGIN)

    joia = sem_fundo.crop((x1, y1, x2, y2))

    max_size = int(SIZE * 0.85)
    joia.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    fundo = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))

    x = (SIZE - joia.width) // 2
    y = (SIZE - joia.height) // 2

    fundo.paste(joia, (x, y), joia)

    return fundo.convert("RGB")

for img_path in INPUT_DIR.glob("*.jpg"):
    print(f"Processando {img_path.name}")
    resultado = processar(img_path)

    if resultado:
        resultado.save(OUTPUT_DIR / img_path.name, quality=95)
    else:
        print("Falhou:", img_path.name)
