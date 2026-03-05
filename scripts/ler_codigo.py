import re
from collections import Counter
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
CODIGO_LEN_ALVO = 10
OCR_TIMEOUT_SECONDS = 1
MAX_OCR_CALLS_PAINT = 40
MAX_OCR_CALLS_PAINT_INTENSIVO = 36
MAX_OCR_CALLS_IMAGEM_COMPLETA = 24
ENABLE_OCR_IMAGEM_COMPLETA = False
MAX_OCR_CALLS_ETIQUETA = 24
MIN_VOTOS_ETIQUETA = 2


def _normalizar_codigo(texto: str | None) -> str | None:
    if not texto:
        return None

    candidatos = DIGITS_RE.findall(texto)
    if not candidatos:
        return None

    validos = [c for c in candidatos if len(c) == CODIGO_LEN_ALVO]
    if not validos:
        return None

    # retorna o mais frequente na extração local
    contagem = Counter(validos)
    validos.sort(key=lambda c: (-contagem[c], c))
    return validos[0]


def _selecionar_por_votos(candidatos: list[str], min_votos: int = 2) -> str | None:
    if not candidatos:
        return None

    contagem = Counter(candidatos)
    codigo, votos = contagem.most_common(1)[0]
    if votos >= min_votos:
        return codigo
    return None


def _ocr_digits(img: np.ndarray, config: str) -> str | None:
    try:
        texto = pytesseract.image_to_string(img, config=config, timeout=OCR_TIMEOUT_SECONDS)
    except BaseException:
        return None

    texto = texto.strip().replace(" ", "").replace("\n", "")
    return _normalizar_codigo(texto)


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

    chamadas = 0
    for base in candidatos:
        for escala in (1.0, 1.8, 2.2, 2.8):
            if escala == 1.0:
                candidate = base
            else:
                candidate = cv2.resize(base, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)

            codigo = _ocr_digits(candidate, cfg)
            chamadas += 1
            if codigo:
                return codigo

            cfg_alt = "--psm 6 -c tessedit_char_whitelist=0123456789"
            codigo_alt = _ocr_digits(candidate, cfg_alt)
            chamadas += 1
            if codigo_alt:
                return codigo_alt

            if chamadas >= MAX_OCR_CALLS_PAINT:
                return None

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

    chamadas = 0
    for base in variantes:
        _, otsu = cv2.threshold(base, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for cand in (base, otsu, 255 - otsu):
            for escala in (2.0, 2.8, 3.2):
                up = cv2.resize(cand, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                for cfg in psm_configs:
                    codigo = _ocr_digits(up, cfg)
                    chamadas += 1
                    if codigo:
                        return codigo

                    if chamadas >= MAX_OCR_CALLS_PAINT_INTENSIVO:
                        return None

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

    chamadas = 0
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
                    codigo = _ocr_digits(up, cfg)
                    chamadas += 1
                    if codigo:
                        return codigo

                    if chamadas >= MAX_OCR_CALLS_IMAGEM_COMPLETA:
                        return None

    return None


def _ocr_etiqueta(caminho_img: Path) -> str | None:
    img = cv2.imread(str(caminho_img))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    regioes = [
        gray,
        gray[int(h * 0.55):h, :],
        gray[int(h * 0.45):h, int(w * 0.05):int(w * 0.95)],
    ]

    psm_configs = [
        "--psm 7 -c tessedit_char_whitelist=0123456789",
        "--psm 6 -c tessedit_char_whitelist=0123456789",
        "--psm 11 -c tessedit_char_whitelist=0123456789",
    ]

    chamadas = 0
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
            for escala in (1.8, 2.5, 3.0):
                up = cv2.resize(base, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                for cfg in psm_configs:
                    codigo = _ocr_digits(up, cfg)
                    chamadas += 1
                    if codigo:
                        return codigo

                    if chamadas >= MAX_OCR_CALLS_ETIQUETA:
                        return None

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

    # 2) Etiqueta (barcode/ocr) com consenso mínimo
    etiquetas = sorted(ETI_DIR.glob(f"{base}_etiqueta_*.jpg"))
    candidatos_etiqueta: list[str] = []

    for etiqueta in etiquetas:
        codigo = ler_barcode_imagem(etiqueta)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                candidatos_etiqueta.append(codigo_norm)

    for etiqueta in etiquetas:
        codigo = ler_barcode_imagem(etiqueta, modo="intensivo")
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                candidatos_etiqueta.append(codigo_norm)

    for etiqueta in etiquetas:
        codigo = _ocr_etiqueta(etiqueta)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                candidatos_etiqueta.append(codigo_norm)

    codigo_consenso = _selecionar_por_votos(candidatos_etiqueta, min_votos=MIN_VOTOS_ETIQUETA)
    if codigo_consenso:
        return codigo_consenso, "etiqueta_consenso"

    # 3) Fallback em imagem completa (quando crop falha)
    if ENABLE_OCR_IMAGEM_COMPLETA:
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
                # barcode no original é mais frágil; usa apenas se também houve concordância da etiqueta
                if codigo_norm in candidatos_etiqueta:
                    return codigo_norm, "barcode_original_consenso"

        if ENABLE_OCR_IMAGEM_COMPLETA:
            codigo = _ocr_imagem_completa(original)
            if codigo:
                codigo_norm = _normalizar_codigo(codigo)
                if codigo_norm:
                    return codigo_norm, "ocr_original"

    # 4) Fallback: nome já é número
    if base.isdigit() and len(base) == CODIGO_LEN_ALVO:
        return base, "nome"

    return None, "nenhum"