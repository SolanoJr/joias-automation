import cv2
import pytesseract
import re
from pathlib import Path

PASTA_ETIQUETAS = Path("output/etiquetas")

def preprocessar(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Aumenta contraste
    gray = cv2.equalizeHist(gray)

    # Binarização
    _, thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return thresh

def extrair_codigo(texto):
    numeros = re.findall(r"\d{10}", texto)

    for n in numeros:
        if re.match(r"^120\d{7}$", n):
            return n

    return None

print("Iniciando OCR v2.1...\n")

for img_path in PASTA_ETIQUETAS.glob("*.jpg"):
    print(f"Imagem: {img_path.name}")

    img = cv2.imread(str(img_path))
    proc = preprocessar(img)

    texto = pytesseract.image_to_string(
        proc,
        config="--psm 6 -c tessedit_char_whitelist=0123456789"
    )

    print("OCR bruto:")
    print(texto.strip())

    codigo = extrair_codigo(texto)
    print("OCR validado:", codigo)
    print("-" * 40)
