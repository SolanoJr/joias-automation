import cv2
from pyzbar import pyzbar
from pathlib import Path

PASTA_ETIQUETAS = Path("output/etiquetas")

def tentar_ler_img(img):
    resultados = pyzbar.decode(img)
    for r in resultados:
        codigo = r.data.decode("utf-8")
        if codigo.isdigit() and len(codigo) >= 8:
            return codigo
    return None


def ler_barcode_imagem(caminho_imagem: str):
    img = cv2.imread(caminho_imagem)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    codigo = tentar_ler_img(gray)

    if codigo is None:
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        codigo = tentar_ler_img(blur)

    if codigo is None:
        upscale = cv2.resize(
            gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC
        )
        codigo = tentar_ler_img(upscale)

    return codigo


def main():
    print("Iniciando leitura de código de barras (robusto)...\n")

    for img_path in sorted(PASTA_ETIQUETAS.glob("*.jpg")):
        print(f"Imagem: {img_path.name}")

        codigo = ler_barcode_imagem(str(img_path))

        if codigo:
            print(f"Código válido: {codigo}")
        else:
            print("Nenhum código detectado")

        print("-" * 40)


if __name__ == "__main__":
    main()
