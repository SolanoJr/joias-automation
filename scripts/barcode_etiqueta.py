import cv2
from pyzbar import pyzbar
from pathlib import Path
import os
import sys
import contextlib

PASTA_ETIQUETAS = Path("output/etiquetas")

@contextlib.contextmanager
def silenciar_stderr():
    old = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = old

def _tentar_ler_array(img_array):
    with silenciar_stderr():
        resultados = pyzbar.decode(img_array)
    for r in resultados:
        codigo = r.data.decode("utf-8").strip()
        if codigo.isdigit() and len(codigo) >= 8:
            return codigo
    return None

def _rotacoes(img):
    # img pode ser 2D (gray) ou 3D (BGR)
    yield img
    yield cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    yield cv2.rotate(img, cv2.ROTATE_180)
    yield cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

def ler_barcode_imagem(caminho_img: Path):
    img = cv2.imread(str(caminho_img))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # tentativas em ordem do "menos intrusivo" pro "mais intrusivo"
    variantes = []
    variantes.append(gray)  # 1) cru
    variantes.append(cv2.GaussianBlur(gray, (3, 3), 0))  # 2) blur leve

    # 3) upscale leve e médio
    variantes.append(cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC))
    variantes.append(cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC))

    # tenta cada variante em todas as rotações
    for v in variantes:
        for vr in _rotacoes(v):
            codigo = _tentar_ler_array(vr)
            if codigo:
                return codigo

    return None

def ler_codigos_da_pasta(pasta: Path = PASTA_ETIQUETAS):
    resultados = {}
    for img_path in sorted(pasta.glob("*_warp.jpg")):
        resultados[img_path.name] = ler_barcode_imagem(img_path)

    # If no warp images are found, fallback to raw images
    if not resultados:
        for img_path in sorted(pasta.glob("*_raw.jpg")):
            resultados[img_path.name] = ler_barcode_imagem(img_path)

    return resultados

if __name__ == "__main__":
    print("Iniciando leitura de código de barras (simples)...\n")
    resultados = ler_codigos_da_pasta(PASTA_ETIQUETAS)

    ok = 0
    for nome, codigo in resultados.items():
        print(f"Imagem: {nome}")
        if codigo:
            ok += 1
            print(f"Código válido: {codigo}")
        else:
            print("Nenhum código detectado")
        print("-" * 40)

    print(f"\nResumo: {ok} OK / {len(resultados)} total")
