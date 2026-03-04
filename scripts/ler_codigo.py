import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from barcode_etiqueta import ler_barcode_imagem

PAINTS_DIR = Path("output/paints")
ETI_DIR = Path("output/etiquetas")
SEM_ETIQUETA_DIR = Path("output/sem_etiqueta")
ORIGINAIS_DIR = Path("input_raw/fotos_originais")

# Se o tesseract não estiver no PATH, descomenta e ajusta:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DIGITS_RE = re.compile(r"\d+")
MIN_CODIGO_LEN = 8
MAX_CODIGO_LEN = 16


def _normalizar_codigo(texto: str | None) -> str | None:
    if not texto:
        return None

    candidatos = DIGITS_RE.findall(texto)
    if not candidatos:
        return None

    validos = [c for c in candidatos if MIN_CODIGO_LEN <= len(c) <= MAX_CODIGO_LEN]
    if not validos:
        return None

    # prefere tamanhos mais comuns em códigos reais
    prioridade = {10: 0, 8: 1, 12: 2, 13: 3, 14: 4, 16: 5}
    validos.sort(key=lambda c: (prioridade.get(len(c), 99), -len(c)))
    return validos[0]


def _ocr_paint(paint_path: Path) -> str | None:
    img = cv2.imread(str(paint_path))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(blur)

    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adapt = cv2.adaptiveThreshold(
        clahe,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )
    nitida = cv2.addWeighted(clahe, 1.7, blur, -0.7, 0)

    cfg = "--psm 7 -c tessedit_char_whitelist=0123456789"

    candidatos = [
        gray,
        clahe,
        otsu,
        255 - otsu,
        adapt,
        255 - adapt,
        nitida,
    ]

    for base in candidatos:
        for escala in (1.0, 1.8, 2.2, 2.8):
            if escala == 1.0:
                candidate = base
            else:
                candidate = cv2.resize(base, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)

            text = pytesseract.image_to_string(candidate, config=cfg)
            text = text.strip().replace(" ", "").replace("\n", "")
            codigo = _normalizar_codigo(text)
            if codigo:
                return codigo

            cfg_alt = "--psm 6 -c tessedit_char_whitelist=0123456789"
            text_alt = pytesseract.image_to_string(candidate, config=cfg_alt)
            text_alt = text_alt.strip().replace(" ", "").replace("\n", "")
            codigo_alt = _normalizar_codigo(text_alt)
            if codigo_alt:
                return codigo_alt

    return None


def _ocr_paint_intensivo(paint_path: Path) -> str | None:
    img = cv2.imread(str(paint_path))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(blur)

    variantes = [clahe]
    for k in (3, 5):
        kernel = np.ones((k, k), np.uint8)
        variantes.append(cv2.morphologyEx(clahe, cv2.MORPH_CLOSE, kernel, iterations=1))
        variantes.append(cv2.morphologyEx(clahe, cv2.MORPH_OPEN, kernel, iterations=1))

    psm_configs = [
        "--psm 7 -c tessedit_char_whitelist=0123456789",
        "--psm 6 -c tessedit_char_whitelist=0123456789",
        "--psm 11 -c tessedit_char_whitelist=0123456789",
    ]

    for base in variantes:
        _, otsu = cv2.threshold(base, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for cand in (base, otsu, 255 - otsu):
            for escala in (2.0, 2.8, 3.2):
                up = cv2.resize(cand, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                for cfg in psm_configs:
                    text = pytesseract.image_to_string(up, config=cfg)
                    text = text.strip().replace(" ", "").replace("\n", "")
                    codigo = _normalizar_codigo(text)
                    if codigo:
                        return codigo

    return None


def _ocr_imagem_completa(caminho_img: Path) -> str | None:
    img = cv2.imread(str(caminho_img))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    # regiões mais prováveis de conter código (base e faixa central)
    regioes = [
        gray,
        gray[int(h * 0.55):h, :],
        gray[int(h * 0.45):int(h * 0.95), int(w * 0.10):int(w * 0.90)],
    ]

    psm_configs = [
        "--psm 7 -c tessedit_char_whitelist=0123456789",
        "--psm 6 -c tessedit_char_whitelist=0123456789",
        "--psm 11 -c tessedit_char_whitelist=0123456789",
    ]

    for reg in regioes:
        if reg.size == 0:
            continue

        blur = cv2.GaussianBlur(reg, (3, 3), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(blur)
        _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adapt = cv2.adaptiveThreshold(
            clahe,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            7,
        )

        for base in (clahe, otsu, 255 - otsu, adapt, 255 - adapt):
            for escala in (1.5, 2.2, 3.0):
                up = cv2.resize(base, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                for cfg in psm_configs:
                    texto = pytesseract.image_to_string(up, config=cfg)
                    texto = texto.strip().replace(" ", "").replace("\n", "")
                    codigo = _normalizar_codigo(texto)
                    if codigo:
                        return codigo

    return None


def ler_codigo_unico(base: str) -> tuple[str | None, str]:
    """
    Retorna (codigo, fonte) onde fonte ∈ {"paint", "etiqueta", "nome", "nenhum"}
    Regra do projeto: só existe 1 código por imagem (ou paint ou etiqueta).
    """

    # 1) Paint (OCR)
    paints = sorted(PAINTS_DIR.glob(f"{base}_paint_*.jpg"))
    for paint in paints:
        codigo = _ocr_paint(paint)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                return codigo_norm, "paint"

    for paint in paints:
        codigo = _ocr_paint_intensivo(paint)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                return codigo_norm, "paint_intensivo"

    # 2) Etiqueta (barcode)
    etiquetas = sorted(ETI_DIR.glob(f"{base}_etiqueta_*.jpg"))
    for etiqueta in etiquetas:
        codigo = ler_barcode_imagem(etiqueta)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                return codigo_norm, "etiqueta"

    for etiqueta in etiquetas:
        codigo = ler_barcode_imagem(etiqueta, modo="intensivo")
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                return codigo_norm, "etiqueta_intensivo"

    # 3) Fallback em imagem completa (quando crop falha)
    sem_etiqueta = SEM_ETIQUETA_DIR / f"{base}.jpg"
    if sem_etiqueta.exists():
        codigo = _ocr_imagem_completa(sem_etiqueta)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                return codigo_norm, "ocr_sem_etiqueta"

    original = ORIGINAIS_DIR / f"{base}.jpg"
    if original.exists():
        codigo = ler_barcode_imagem(original, modo="intensivo")
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                return codigo_norm, "barcode_original"

        codigo = _ocr_imagem_completa(original)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                return codigo_norm, "ocr_original"

    # 4) Fallback: nome já é número
    if base.isdigit() and len(base) >= 8:
        return base, "nome"

    return None, "nenhum"