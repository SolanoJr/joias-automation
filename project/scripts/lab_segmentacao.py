import logging
import os
import numpy as np
import cv2
from rembg import new_session, remove
from PIL import Image, ImageOps
from pathlib import Path
from io import BytesIO

# Configuração de Logs para o Laboratório
logging.basicConfig(level=logging.INFO, format="%(asctime)s [LAB] %(levelname)s - %(message)s")

# ===== CONFIGURAÇÕES DO LABORATÓRIO =====
INPUT_DIR = Path("project/input_raw/fotos_originais")
OUTPUT_DIR = Path("project/output/lab_segmentacao")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Parâmetros de Processamento
CANVAS_SIZE = 1024
TARGET_RATIO = 0.85  # Joia deve ocupar 85% do canvas
ALPHA_THRESHOLD = 10
MORPH_KERNEL_SIZE = 5 # Tamanho do kernel para fechar buracos (Closing)
GAUSSIAN_BLUR_SIGMA = 1.0 # Suavização de borda

# Modelo de Segmentação
MODEL_NAME = "isnet-general-use"

def _to_rgba_image(rembg_output) -> Image.Image | None:
    if isinstance(rembg_output, Image.Image):
        return rembg_output.convert("RGBA")
    if isinstance(rembg_output, (bytes, bytearray)):
        try:
            return Image.open(BytesIO(rembg_output)).convert("RGBA")
        except Exception:
            return None
    if isinstance(rembg_output, np.ndarray):
        return Image.fromarray(rembg_output).convert("RGBA")
    return None

def processar_lab(imagem_path: Path, session):
    """
    Versão de Laboratório com foco em centralização por centroide e zoom adaptativo.
    """
    try:
        img_orig = Image.open(imagem_path)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert("RGBA")
    except Exception as e:
        logging.error(f"Erro ao abrir {imagem_path.name}: {e}")
        return None

    # 1. Segmentação Bruta
    try:
        rembg_output = remove(img_orig, session=session)
        rgba_img = _to_rgba_image(rembg_output)
    except Exception as e:
        logging.error(f"Erro no rembg {imagem_path.name}: {e}")
        return None

    # Converter para array para processamento OpenCV
    arr = np.array(rgba_img)
    alpha = arr[:, :, 3]

    # 2. Refinamento de Máscara (Morphology + Blur)
    # Criar máscara binária
    mask = (alpha > ALPHA_THRESHOLD).astype(np.uint8) * 255

    # Operação de Fechamento (Closing) para tapar buracos de reflexos
    kernel = np.ones((MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), np.uint8)
    mask_refined = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Suavização de bordas (Gaussian Blur)
    if GAUSSIAN_BLUR_SIGMA > 0:
        mask_refined = cv2.GaussianBlur(mask_refined, (0, 0), sigmaX=GAUSSIAN_BLUR_SIGMA)

    # 3. Localização por Centroide (Momentos)
    # Encontrar contornos na máscara refinada
    contours, _ = cv2.findContours(mask_refined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        logging.warning(f"Nenhum objeto encontrado em {imagem_path.name}")
        return None

    # Pegar o maior contorno (assume que é a joia)
    cnt = max(contours, key=cv2.contourArea)
    M = cv2.moments(cnt)

    if M["m00"] == 0:
        return None

    # Centro de Massa (Centroide)
    cX = int(M["m10"] / M["m00"])
    cY = int(M["m01"] / M["m00"])

    # 4. Cálculo de Zoom Adaptativo
    # Encontrar a caixa delimitadora (bbox) para saber o tamanho atual
    x, y, w, h = cv2.boundingRect(cnt)
    max_side_obj = max(w, h)

    # Queremos que o max_side_obj seja TARGET_RATIO * CANVAS_SIZE
    target_size = CANVAS_SIZE * TARGET_RATIO
    zoom_factor = target_size / max_side_obj

    # Aplicar recorte e redimensionamento
    # Criar uma imagem apenas com o objeto (usando a máscara refinada no alpha original)
    arr_refined = arr.copy()
    arr_refined[:, :, 3] = mask_refined
    joia_img = Image.fromarray(arr_refined, "RGBA")

    # Recortar a joia
    joia_crop = joia_img.crop((x, y, x + w, y + h))

    # Redimensionar com o fator de zoom
    new_w = int(w * zoom_factor)
    new_h = int(h * zoom_factor)
    joia_rescaled = joia_crop.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 5. Centralização Final no Canvas
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 255))

    # A posição (0,0) da joia_rescaled em relação ao centroide
    # O centroide original (cX, cY) agora está no centro do canvas (512, 512)
    # Mas como recortamos em (x,y), o centroide relativo ao crop é (cX-x, cY-y)
    # Ao escalar, o centroide relativo vira (cX-x)*zoom_factor , (cY-y)*zoom_factor

    rel_cX = (cX - x) * zoom_factor
    rel_cY = (cY - y) * zoom_factor

    paste_x = int((CANVAS_SIZE / 2) - rel_cX)
    paste_y = int((CANVAS_SIZE / 2) - rel_cY)

    canvas.paste(joia_rescaled, (paste_x, paste_y), joia_rescaled)

    return canvas.convert("RGB")

def main():
    imgs = sorted([*INPUT_DIR.glob("*.jpg"), *INPUT_DIR.glob("*.png")])[:10] # Limite de 10 para teste de lab
    if not imgs:
        logging.error(f"Nenhuma imagem em {INPUT_DIR}")
        return

    logging.info(f"Iniciando Lab de Segmentação em {len(imgs)} imagens...")
    session = new_session(MODEL_NAME)

    for p in imgs:
        logging.info(f"Processando Lab: {p.name}")
        resultado = processar_lab(p, session)
        if resultado:
            out_path = OUTPUT_DIR / f"lab_{p.name}"
            resultado.save(out_path, quality=95)
            logging.info(f"Salvo em: {out_path}")

if __name__ == "__main__":
    main()
