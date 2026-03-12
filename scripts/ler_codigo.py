import re
import os
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from barcode_etiqueta import ler_barcode_imagem

PAINTS_DIR = Path("output/2_paints")
ETI_DIR = Path("output/1_etiquetas")
SEM_ETIQUETA_DIR = Path("output/3_sem_etiqueta")
ORIGINAIS_DIR = Path("input_raw/fotos_originais")

# Se o tesseract não estiver no PATH, descomenta e ajusta:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DIGITS_RE = re.compile(r"\d+")
CODIGO_LEN_ALVO = 10
CODE_READER_FAST = os.getenv("CODE_READER_FAST", "0").strip().lower() in {"1", "true", "yes", "on"}
OCR_TIMEOUT_SECONDS = 1
MAX_OCR_CALLS_PAINT = 12 if CODE_READER_FAST else 40
MAX_OCR_CALLS_PAINT_INTENSIVO = 12 if CODE_READER_FAST else 36
MAX_OCR_CALLS_IMAGEM_COMPLETA = 10 if CODE_READER_FAST else 24
ENABLE_OCR_IMAGEM_COMPLETA = False
MAX_OCR_CALLS_ETIQUETA = 60
MIN_VOTOS_ETIQUETA = 2
ALLOW_SHORT_BARCODE = os.getenv("ALLOW_SHORT_BARCODE", "0").strip().lower() in {"1", "true", "yes", "on"}
SHORT_BARCODE_MIN_DIGITS = 8
SHORT_BARCODE_MIN_CONSENSUS = 2
ENABLE_PAINT_INTENSIVO = os.getenv("ENABLE_PAINT_INTENSIVO", "0").strip().lower() in {"1", "true", "yes", "on"}
PRIORITIZE_BARCODE_FIRST = os.getenv("PRIORITIZE_BARCODE_FIRST", "0").strip().lower() in {"1", "true", "yes", "on"}
OCR_ETIQUETA_ADAPTIVE = os.getenv("OCR_ETIQUETA_ADAPTIVE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _append_profile(
    perfil_rows,
    base: str,
    etapa: str,
    tempo_s: float,
    fonte_codigo: str = "",
    status: str = "",
    nivel_ocr: str = "",
    modo_adaptive: str = "",
    early_stop: str = "",
):
    if perfil_rows is None:
        return
    perfil_rows.append(
        {
            "base": base,
            "etapa": etapa,
            "tempo_s": f"{tempo_s:.4f}",
            "fonte_codigo": fonte_codigo,
            "status": status,
            "nivel_ocr": nivel_ocr,
            "modo_adaptive": modo_adaptive,
            "early_stop": early_stop,
        }
    )


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


def _ocr_etiqueta(caminho_img: Path, nivel_confianca: str = "baixa") -> str | None:
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

    psm_full = [
        "--psm 7 -c tessedit_char_whitelist=0123456789",
        "--psm 6 -c tessedit_char_whitelist=0123456789",
        "--psm 11 -c tessedit_char_whitelist=0123456789",
    ]

    if OCR_ETIQUETA_ADAPTIVE:
        if nivel_confianca == "alta":
            psm_configs = psm_full[:2]
            escalas = (2.0, 2.6)
            usar_rotacao_180 = False
            usar_rotacao_ccw = False
            limite_chamadas = min(MAX_OCR_CALLS_ETIQUETA, 18)
        elif nivel_confianca == "media":
            psm_configs = psm_full[:2]
            escalas = (1.8, 2.5)
            usar_rotacao_180 = False
            usar_rotacao_ccw = False
            limite_chamadas = min(MAX_OCR_CALLS_ETIQUETA, 30)
        else:
            psm_configs = psm_full
            escalas = (1.8, 2.5, 3.0)
            usar_rotacao_180 = False
            usar_rotacao_ccw = True
            limite_chamadas = min(MAX_OCR_CALLS_ETIQUETA, 45)
    else:
        psm_configs = psm_full
        escalas = (1.8, 2.5, 3.0)
        usar_rotacao_180 = False
        usar_rotacao_ccw = True
        limite_chamadas = MAX_OCR_CALLS_ETIQUETA

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
            candidatos_orientacao = [base, cv2.rotate(base, cv2.ROTATE_90_CLOCKWISE)]
            if usar_rotacao_ccw:
                candidatos_orientacao.append(cv2.rotate(base, cv2.ROTATE_90_COUNTERCLOCKWISE))
            if usar_rotacao_180:
                candidatos_orientacao.append(cv2.rotate(base, cv2.ROTATE_180))

            for orientado in candidatos_orientacao:
                for escala in escalas:
                    up = cv2.resize(orientado, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                    for cfg in psm_configs:
                        codigo = _ocr_digits(up, cfg)
                        chamadas += 1
                        if codigo:
                            return codigo

                        if chamadas >= limite_chamadas:
                            return None

    return None


def _normalizar_resultado_barcode(resultado) -> tuple[str | None, dict]:
    if isinstance(resultado, tuple):
        codigo, meta = resultado
        if isinstance(meta, dict):
            return codigo, meta
        return codigo, {}
    return resultado, {}


def _fonte_etiqueta_simples(simple_stage: str) -> str:
    stage = (simple_stage or "").strip().lower()
    if stage == "raw":
        return "etiqueta_raw"
    if stage == "resize2x":
        return "etiqueta_resize2x"
    if stage == "threshold":
        return "etiqueta_threshold"
    return "etiqueta_raw"


def _tentar_barcode_etiqueta_fallback(
    base: str,
    etiquetas: list[Path],
    indice_global: int | None,
    total_global: int | None,
    perfil_rows: list[dict] | None,
) -> tuple[str | None, str | None]:
    if not etiquetas:
        return None, None

    t_simple = time.perf_counter()
    for idx_et, etiqueta in enumerate(etiquetas, start=1):
        if indice_global and total_global:
            print(
                f"[ler_codigo] lendo etiqueta {idx_et}/{len(etiquetas)} {etiqueta.name} | "
                f"imagem {indice_global}/{total_global}"
            )

        codigo, meta = _normalizar_resultado_barcode(
            ler_barcode_imagem(
                etiqueta,
                min_digits=CODIGO_LEN_ALVO,
                return_meta=True,
                simple_only=True,
            )
        )
        codigo_norm = _normalizar_codigo(codigo)
        if codigo_norm:
            fonte = _fonte_etiqueta_simples(meta.get("simple_stage", ""))
            _append_profile(
                perfil_rows,
                base,
                "barcode_etiqueta_simples",
                time.perf_counter() - t_simple,
                fonte,
                "ok",
                early_stop="True",
            )
            return codigo_norm, fonte

    _append_profile(
        perfil_rows,
        base,
        "barcode_etiqueta_simples",
        time.perf_counter() - t_simple,
        "",
        "falhou",
        early_stop="False",
    )

    t_int = time.perf_counter()
    for idx_et, etiqueta in enumerate(etiquetas, start=1):
        if indice_global and total_global:
            print(
                f"[ler_codigo] etiqueta intensivo {idx_et}/{len(etiquetas)} {etiqueta.name} | "
                f"imagem {indice_global}/{total_global}"
            )

        codigo = ler_barcode_imagem(etiqueta, modo="intensivo", min_digits=CODIGO_LEN_ALVO)
        codigo_norm = _normalizar_codigo(codigo)
        if codigo_norm:
            _append_profile(
                perfil_rows,
                base,
                "barcode_etiqueta_intensivo",
                time.perf_counter() - t_int,
                "etiqueta_intensivo",
                "ok",
                early_stop="True",
            )
            return codigo_norm, "etiqueta_intensivo"

    _append_profile(
        perfil_rows,
        base,
        "barcode_etiqueta_intensivo",
        time.perf_counter() - t_int,
        "",
        "falhou",
        early_stop="False",
    )

    return None, None


def ler_codigo_unico(
    base: str,
    indice_global: int | None = None,
    total_global: int | None = None,
    perfil_rows: list[dict] | None = None,
) -> tuple[str | None, str]:
    """
    Retorna (codigo, fonte) onde fonte ∈ {"paint", "etiqueta", "nome", "nenhum"}
    Regra do projeto: só existe 1 código por imagem (ou paint ou etiqueta).
    """

    etiquetas = sorted(ETI_DIR.glob(f"{base}_etiqueta_*.jpg"))
    candidatos_etiqueta: list[str] = []
    candidatos_etiqueta_curtos: Counter[str] = Counter()

    barcode_sinais_fortes = 0
    barcode_sinais_fracos = 0

    if PRIORITIZE_BARCODE_FIRST and etiquetas:
        codigo_eti, fonte_eti = _tentar_barcode_etiqueta_fallback(
            base,
            etiquetas,
            indice_global,
            total_global,
            perfil_rows,
        )
        if codigo_eti:
            return codigo_eti, fonte_eti or "etiqueta_raw"

    # 1) Paint (OCR)
    paints = sorted(PAINTS_DIR.glob(f"{base}_paint_*.jpg"))
    t_paint = time.perf_counter()
    for idx_paint, paint in enumerate(paints, start=1):
        if indice_global and total_global:
            print(
                f"[ler_codigo] lendo paint {idx_paint}/{len(paints)} {paint.name} | "
                f"imagem {indice_global}/{total_global}"
            )
        codigo = _ocr_paint(paint)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                _append_profile(perfil_rows, base, "ocr_paint", time.perf_counter() - t_paint, "paint", "ok")
                return codigo_norm, "paint"
    _append_profile(perfil_rows, base, "ocr_paint", time.perf_counter() - t_paint, "", "falhou")

    t_paint_int = time.perf_counter()
    for idx_paint, paint in enumerate(paints, start=1):
        if not ENABLE_PAINT_INTENSIVO:
            break
        if indice_global and total_global:
            print(
                f"[ler_codigo] paint intensivo {idx_paint}/{len(paints)} {paint.name} | "
                f"imagem {indice_global}/{total_global}"
            )
        codigo = _ocr_paint_intensivo(paint)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                _append_profile(perfil_rows, base, "ocr_paint_intensivo", time.perf_counter() - t_paint_int, "paint_intensivo", "ok")
                return codigo_norm, "paint_intensivo"
    if ENABLE_PAINT_INTENSIVO:
        _append_profile(perfil_rows, base, "ocr_paint_intensivo", time.perf_counter() - t_paint_int, "", "falhou")

    # 2) Etiqueta (barcode/ocr) com consenso mínimo
    if not PRIORITIZE_BARCODE_FIRST:
        codigo_eti, fonte_eti = _tentar_barcode_etiqueta_fallback(
            base,
            etiquetas,
            indice_global,
            total_global,
            perfil_rows,
        )
        if codigo_eti:
            return codigo_eti, fonte_eti or "etiqueta_raw"

    nivel_ocr_etiqueta = "baixa"
    if OCR_ETIQUETA_ADAPTIVE:
        if barcode_sinais_fortes >= 2:
            nivel_ocr_etiqueta = "alta"
        elif (barcode_sinais_fortes + barcode_sinais_fracos) > 0:
            nivel_ocr_etiqueta = "media"
        print(f"[ler_codigo] ocr_etiqueta_adaptive nivel={nivel_ocr_etiqueta} base={base}")

    t_ocr_eti = time.perf_counter()
    for idx_et, etiqueta in enumerate(etiquetas, start=1):
        if indice_global and total_global:
            print(
                f"[ler_codigo] ocr etiqueta {idx_et}/{len(etiquetas)} {etiqueta.name} | "
                f"imagem {indice_global}/{total_global}"
            )
        codigo = _ocr_etiqueta(etiqueta, nivel_confianca=nivel_ocr_etiqueta)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                candidatos_etiqueta.append(codigo_norm)

                min_votos_parcial = MIN_VOTOS_ETIQUETA
                if len(candidatos_etiqueta) <= 1:
                    min_votos_parcial = 1

                parcial = _selecionar_por_votos(candidatos_etiqueta, min_votos=min_votos_parcial)
                if parcial:
                    _append_profile(
                        perfil_rows,
                        base,
                        "ocr_etiqueta",
                        time.perf_counter() - t_ocr_eti,
                        "etiqueta_ocr",
                        "ok_early_stop",
                        nivel_ocr=nivel_ocr_etiqueta,
                        modo_adaptive=str(bool(OCR_ETIQUETA_ADAPTIVE)),
                        early_stop="True",
                    )
                    return parcial, "etiqueta_ocr"

    _append_profile(
        perfil_rows,
        base,
        "ocr_etiqueta",
        time.perf_counter() - t_ocr_eti,
        "",
        "fim",
        nivel_ocr=nivel_ocr_etiqueta,
        modo_adaptive=str(bool(OCR_ETIQUETA_ADAPTIVE)),
        early_stop="False",
    )

    # Sem consenso adicional aqui: OCR é fallback real e retorna no primeiro válido.

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
        codigo, _ = _normalizar_resultado_barcode(
            ler_barcode_imagem(original, modo="intensivo", min_digits=CODIGO_LEN_ALVO)
        )
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if codigo_norm:
                # barcode no original é mais frágil; usa apenas se também houve concordância da etiqueta
                if codigo_norm in candidatos_etiqueta:
                    return codigo_norm, "barcode_original_consenso"

        if ALLOW_SHORT_BARCODE and candidatos_etiqueta_curtos:
            _, meta_original = _normalizar_resultado_barcode(
                ler_barcode_imagem(
                    original,
                    modo="intensivo",
                    min_digits=SHORT_BARCODE_MIN_DIGITS,
                    return_meta=True,
                )
            )
            counts_original = meta_original.get("all_counts", {})
            candidatos_cross: list[tuple[str, int, int]] = []
            for cod, qtd_et in candidatos_etiqueta_curtos.items():
                if len(cod) < SHORT_BARCODE_MIN_DIGITS or len(cod) >= CODIGO_LEN_ALVO:
                    continue
                qtd_or = int(counts_original.get(cod, 0))
                if qtd_or >= 1 and qtd_et >= 1:
                    candidatos_cross.append((cod, qtd_et, qtd_or))

            if candidatos_cross:
                melhor_cross = sorted(candidatos_cross, key=lambda x: (x[1] + x[2], x[1], x[2], len(x[0])), reverse=True)[0]
                return melhor_cross[0], "barcode_curto_cross"

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