import cv2
from pyzbar import pyzbar
from pathlib import Path

PASTA_ETIQUETAS = Path("output/etiquetas")

def tentar_ler(img):
    resultados = pyzbar.decode(img)
    for r in resultados:
        codigo = r.data.decode("utf-8")
        if codigo.isdigit() and len(codigo) >= 8:
            return codigo
    return None

print("Iniciando leitura de código de barras (robusto)...\n")

for img_path in sorted(PASTA_ETIQUETAS.glob("*.jpg")):
    print(f"Imagem: {img_path.name}")

    img = cv2.imread(str(img_path))
    if img is None:
        print("Erro ao abrir imagem")
        print("-" * 40)
        continue

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # tentativa 1: grayscale puro
    codigo = tentar_ler(gray)

    # tentativa 2: blur leve
    if codigo is None:
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        codigo = tentar_ler(blur)

    # tentativa 3: upscale
    if codigo is None:
        upscale = cv2.resize(
            gray,
            None,
            fx=1.5,
            fy=1.5,
            interpolation=cv2.INTER_CUBIC
        )
        codigo = tentar_ler(upscale)

    if codigo:
        print(f"Código válido: {codigo}")
    else:
        print("Nenhum código detectado")

    print("-" * 40)



    """
STATUS: FUNCIONAL
Data: 29/01/2026
Leitura de código de barras validada em múltiplas imagens reais.
Este script é o método principal (OCR descartado como fallback).
NÃO alterar sem novo teste completo.
"""

# TODO PRÓXIMO PASSO:
# Integrar este script ao pipeline principal após o recorte YOLO
# Decidir formato de saída:
# - Renomear imagem final com código OU
# - Exportar CSV/JSON
