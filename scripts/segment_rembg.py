from rembg import remove
from PIL import Image
from pathlib import Path

INPUT_DIR = Path("input_raw/fotos_originais")
OUTPUT_DIR = Path("output/segmentado_rembg")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024  # imagem final quadrada

def processar(imagem_path):
    img = Image.open(imagem_path).convert("RGBA")

    # remove fundo
    sem_fundo = remove(img)

    # bounding box da joia
    bbox = sem_fundo.getbbox()
    if not bbox:
        return None

    joia = sem_fundo.crop(bbox)

    # redimensionar mantendo proporção
    joia.thumbnail((SIZE, SIZE))

    # fundo branco
    fundo = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))

    x = (SIZE - joia.width) // 2
    y = (SIZE - joia.height) // 2

    fundo.paste(joia, (x, y), joia)

    return fundo.convert("RGB")

for img_path in INPUT_DIR.glob("*.jpg"):
    print(f"Processando {img_path.name}")
    resultado = processar(img_path)

    if resultado:
        resultado.save(OUTPUT_DIR / img_path.name)
    else:
        print("Falhou:", img_path.name)
