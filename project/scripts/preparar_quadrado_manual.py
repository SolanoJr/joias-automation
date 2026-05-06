from pathlib import Path
import os

from PIL import Image, ImageOps


INPUT_DIR = Path("output/3_sem_etiqueta")
OUTPUT_DIR = Path("output/4_quadrado_manual")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1200
CONTENT_RATIO = 0.88
LIMPAR_DESTINO = True

PREP_SKIP_BY_EXISTENCE = os.getenv("PREP_SKIP_BY_EXISTENCE", "0").strip().lower() in {"1", "true", "yes", "on"}
PREP_SKIP_IF_UPTODATE = os.getenv("PREP_SKIP_IF_UPTODATE", "0").strip().lower() in {"1", "true", "yes", "on"}


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

    if LIMPAR_DESTINO and not PREP_SKIP_BY_EXISTENCE and not PREP_SKIP_IF_UPTODATE:
        for p in OUTPUT_DIR.glob("*.jpg"):
            p.unlink(missing_ok=True)

    imgs = sorted(INPUT_DIR.glob("*.jpg"))
    if not imgs:
        print(f"ERRO: nenhuma imagem em {INPUT_DIR}")
        return

    ok = 0
    for p in imgs:
        out_path = OUTPUT_DIR / p.name

        if PREP_SKIP_BY_EXISTENCE and out_path.exists():
            ok += 1
            continue

        if PREP_SKIP_IF_UPTODATE and out_path.exists():
            try:
                if out_path.stat().st_mtime >= p.stat().st_mtime:
                    ok += 1
                    continue
            except Exception:
                pass

        out = preparar(p)
        if out is None:
            continue
        out.save(out_path, quality=95)
        ok += 1

    print(f"Quadrado manual OK: {ok}/{len(imgs)}")
    print(f"Saída: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
