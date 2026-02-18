import logging
import numpy as np
from rembg import new_session, remove
from PIL import Image
from pathlib import Path

# Configuração do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

INPUT_DIR = Path("input_raw/fotos_originais")
OUTPUT_DIR = Path("output/segmentado_rembg")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024
MARGIN_PERCENT = 0.08  # 8% de margem extra
MAX_SCALE = 0.85       # joia ocupa no máximo 85% da imagem final

# Criar uma nova sessão para o modelo ISNet
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


def processar(imagem_path):
    try:
        img = Image.open(imagem_path).convert("RGBA")
    except Exception as e:
        logging.error(f"Erro ao abrir a imagem {imagem_path.name}: {e}")
        return None

    try:
        # Usar a sessão criada para remover o fundo
        sem_fundo = remove(img, session=session)
    except Exception as e:
        logging.error(f"Erro ao remover o fundo da imagem {imagem_path.name}: {e}")
        return None

    arr = np.array(sem_fundo)

    # usar canal alpha
    alpha = arr[:, :, 3]

    # máscara mais rígida
    mask = alpha > 20

    coords = np.column_stack(np.where(mask))

    if coords.size == 0:
        logging.warning(f"Nenhuma joia detectada na imagem {imagem_path.name}")
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

    # controlar escala máxima
    max_size = int(SIZE * MAX_SCALE)
    joia.thumbnail((max_size, max_size), Image.LANCZOS)

    fundo = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))

    x = (SIZE - joia.width) // 2
    y = (SIZE - joia.height) // 2

    fundo.paste(joia, (x, y), joia)

    return fundo.convert("RGB")


if not any(INPUT_DIR.glob("*.jpg")):
    logging.error("Nenhuma imagem encontrada no diretório de entrada.")
else:
    for img_path in INPUT_DIR.glob("*.jpg"):
        logging.info(f"Processando {img_path.name}")
        resultado = processar(img_path)

        if resultado:
            try:
                resultado.save(OUTPUT_DIR / img_path.name, quality=95)
                logging.info(f"Imagem processada com sucesso: {img_path.name}")
            except Exception as e:
                logging.error(f"Erro ao salvar a imagem {img_path.name}: {e}")
        else:
            logging.warning(f"Falha ao processar: {img_path.name}")
