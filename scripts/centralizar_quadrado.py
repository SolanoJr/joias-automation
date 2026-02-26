from pathlib import Path
from PIL import Image
import numpy as np

IN_DIR = Path("output/segmentado_rembg")
OUT_DIR = Path("output/final_quadrado")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# parâmetros
MARGEM = 0.12     # 12% de margem no quadrado
TAM_SAIDA = 1024  # 1024x1024 (pode trocar pra 800 ou 1200)

def bbox_conteudo_rgb(img: Image.Image, branco_limite=245):
    """
    Encontra bbox do que NÃO é branco.
    Funciona para imagens em fundo branco (jpg).
    """
    arr = np.array(img.convert("RGB"))
    mask = np.any(arr < branco_limite, axis=2)  # pixels "não brancos"
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return None
    x1, x2 = xs.min(), xs.max()
    y1, y2 = ys.min(), ys.max()
    return (x1, y1, x2 + 1, y2 + 1)

def main():
    imgs = sorted(list(IN_DIR.glob("*.jpg")) + list(IN_DIR.glob("*.png")))
    if not imgs:
        print(f"ERRO: nenhuma imagem em {IN_DIR}")
        return

    ok, vazias = 0, 0

    for p in imgs:
        img = Image.open(p).convert("RGB")

        bb = bbox_conteudo_rgb(img)
        if bb is None:
            vazias += 1
            continue

        crop = img.crop(bb)

        # define tamanho do quadrado com margem
        w, h = crop.size
        lado = int(max(w, h) * (1 + MARGEM))
        lado = max(lado, 10)

        canvas = Image.new("RGB", (lado, lado), (255, 255, 255))
        x = (lado - w) // 2
        y = (lado - h) // 2
        canvas.paste(crop, (x, y))

        # redimensiona para tamanho padrão
        if TAM_SAIDA:
            canvas = canvas.resize((TAM_SAIDA, TAM_SAIDA), Image.LANCZOS)

        out = OUT_DIR / f"{p.stem}.jpg"
        canvas.save(out, quality=95)
        ok += 1

    print(f"OK: {ok}")
    print(f"Vazias/sem bbox: {vazias}")
    print(f"Saída: {OUT_DIR}")

if __name__ == "__main__":
    main()