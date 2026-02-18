import cv2
from pyzbar import pyzbar
from pathlib import Path

PASTA_ETIQUETAS = Path("output/etiquetas")

def _tentar_decode(img):
    resultados = pyzbar.decode(img)
    for r in resultados:
        codigo = r.data.decode("utf-8").strip()
        if codigo.isdigit() and len(codigo) >= 8:
            return codigo
    return None

def ler_codigo_de_imagem(img_path: Path) -> str | None:
    img = cv2.imread(str(img_path))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # tentativa 1: grayscale
    codigo = _tentar_decode(gray)

    # tentativa 2: blur leve
    if codigo is None:
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        codigo = _tentar_decode(blur)

    # tentativa 3: upscale
    if codigo is None:
        upscale = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        codigo = _tentar_decode(upscale)

    return codigo

def ler_codigos_pasta(pasta: Path = PASTA_ETIQUETAS) -> dict[str, str]:
    """
    Retorna dict: { 'arquivo_etiqueta.jpg': 'codigo' }
    Só inclui os que deram leitura válida.
    """
    saida = {}
    for img_path in sorted(pasta.glob("*.jpg")):
        codigo = ler_codigo_de_imagem(img_path)
        if codigo:
            saida[img_path.name] = codigo
    return saida

if __name__ == "__main__":
    print("Iniciando leitura de código de barras (robusto)...\n")

    for img_path in sorted(PASTA_ETIQUETAS.glob("*.jpg")):
        print(f"Imagem: {img_path.name}")
        codigo = ler_codigo_de_imagem(img_path)
        if codigo:
            print(f"Código válido: {codigo}")
        else:
            print("Nenhum código detectado")
        print("-" * 40)

"""
STATUS: FUNCIONAL
Data: 29/01/2026+
Leitura de código de barras validada em múltiplas imagens reais.
Este script é o método principal (OCR descartado como fallback por enquanto).
"""
