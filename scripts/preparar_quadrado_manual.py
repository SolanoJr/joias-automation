from pathlib import Path

from PIL import Image, ImageOps


INPUT_DIR = Path("output/sem_etiqueta")
OUTPUT_DIR = Path("output/quadrado_manual")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1200
CONTENT_RATIO = 0.88
LIMPAR_DESTINO = True


def preparar(imagem_path: Path):
    try:
        img = Image.open(imagem_path)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except Exception:
        return None

    max_size = int(SIZE * CONTENT_RATIO)

    # não recorta nada: só redimensiona para caber
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    fundo = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
    x = (SIZE - img.width) // 2
    y = (SIZE - img.height) // 2
    fundo.paste(img, (x, y))
    return fundo


def main():
    if not INPUT_DIR.exists():
        print(f"ERRO: não existe {INPUT_DIR}")
        return

    if LIMPAR_DESTINO:
        for p in OUTPUT_DIR.glob("*.jpg"):
            p.unlink(missing_ok=True)

    imgs = sorted(INPUT_DIR.glob("*.jpg"))
    if not imgs:
        print(f"ERRO: nenhuma imagem em {INPUT_DIR}")
        return

    ok = 0
    for p in imgs:
        out = preparar(p)
        if out is None:
            continue
        out.save(OUTPUT_DIR / p.name, quality=95)
        ok += 1

    print(f"Quadrado manual OK: {ok}/{len(imgs)}")
    print(f"Saída: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
