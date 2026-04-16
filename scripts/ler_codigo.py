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
ENABLE_OCR_IMAGEM_COMPLETA = True
MAX_OCR_CALLS_ETIQUETA = 60
MIN_VOTOS_ETIQUETA = 2
ALLOW_SHORT_BARCODE = os.getenv("ALLOW_SHORT_BARCODE", "0").strip().lower() in {"1", "true", "yes", "on"}
SHORT_BARCODE_MIN_DIGITS = 8
SHORT_BARCODE_MIN_CONSENSUS = 2
ENABLE_PAINT_INTENSIVO = os.getenv("ENABLE_PAINT_INTENSIVO", "1").strip().lower() in {"1", "true", "yes", "on"}
PRIORITIZE_BARCODE_FIRST = os.getenv("PRIORITIZE_BARCODE_FIRST", "0").strip().lower() in {"1", "true", "yes", "on"}
OCR_ETIQUETA_ADAPTIVE = os.getenv("OCR_ETIQUETA_ADAPTIVE", "0").strip().lower() in {"1", "true", "yes", "on"}
LER_CODIGO_CANONICAL_ONLY = os.getenv("LER_CODIGO_CANONICAL_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
CODE_READ_TIMEOUT_SIMPLE_S = float((os.getenv("CODE_READ_TIMEOUT_SIMPLE_S") or "2.0").strip() or "2.0")
CODE_READ_TIMEOUT_INTENSIVO_S = float((os.getenv("CODE_READ_TIMEOUT_INTENSIVO_S") or "8.0").strip() or "8.0")
CODE_READ_TIMEOUT_OCR_S = float((os.getenv("CODE_READ_TIMEOUT_OCR_S") or "12.0").strip() or "12.0")
CODE_READ_TIMEOUT_ITEM_S = float((os.getenv("CODE_READ_TIMEOUT_ITEM_S") or "20.0").strip() or "20.0")


def _now() -> float:
    return time.perf_counter()


def _deadline_exceeded(deadline: float | None) -> bool:
    if deadline is None:
        return False
    return _now() >= deadline


def _stage_deadline(item_deadline: float | None, stage_budget_s: float) -> float | None:
    if stage_budget_s <= 0:
        return None
    local = _now() + stage_budget_s
    if item_deadline is None:
        return local
    return min(local, item_deadline)


def _is_valid_candidate(codigo: str | None) -> bool:
    if not codigo:
        return False
    if codigo.isdigit() and len(codigo) == CODIGO_LEN_ALVO:
        return True
    if re.fullmatch(r"[A-Z0-9]{7,10}", codigo) and sum(ch.isdigit() for ch in codigo) >= 7:
        return True
    return False


def _has_useful_signal(
    etiquetas: list[Path],
    paints: list[Path],
    has_partial_6plus: bool,
    has_short_candidate: bool,
) -> bool:
    return bool(has_partial_6plus or has_short_candidate or paints)


def _listar_por_patterns(folder: Path, patterns: list[str]) -> list[Path]:
    encontrados: dict[str, Path] = {}
    for pattern in patterns:
        for p in sorted(folder.glob(pattern)):
            encontrados[str(p.resolve())] = p
    return sorted(encontrados.values(), key=lambda x: x.name)


def _listar_etiquetas(base: str) -> list[Path]:
    if LER_CODIGO_CANONICAL_ONLY:
        return _listar_por_patterns(ETI_DIR, [f"{base}_etiqueta_*.jpg"])

    return _listar_por_patterns(
        ETI_DIR,
        [
            f"{base}_etiqueta_*.jpg",
            f"{base} - *_e*.jpg",
        ],
    )


def _listar_paints(base: str) -> list[Path]:
    if LER_CODIGO_CANONICAL_ONLY:
        return _listar_por_patterns(PAINTS_DIR, [f"{base}_paint_*.jpg"])

    return _listar_por_patterns(
        PAINTS_DIR,
        [
            f"{base}_paint_*.jpg",
            f"{base} - *_p*.jpg",
        ],
    )


def _buscar_sem_etiqueta(base: str) -> Path | None:
    if LER_CODIGO_CANONICAL_ONLY:
        candidatos = _listar_por_patterns(SEM_ETIQUETA_DIR, [f"{base}.jpg"])
        if candidatos:
            return candidatos[0]
        return None

    candidatos = _listar_por_patterns(
        SEM_ETIQUETA_DIR,
        [
            f"{base}.jpg",
            f"{base} - *_se*.jpg",
        ],
    )
    if candidatos:
        return candidatos[0]
    return None


def _buscar_original(base: str) -> Path | None:
    candidatos = _listar_por_patterns(
        ORIGINAIS_DIR,
        [
            f"{base}.jpg",
            f"{base}.jpeg",
            f"{base}.png",
        ],
    )
    if candidatos:
        return candidatos[0]
    return None


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

    texto_limpo = texto.strip().upper().replace(" ", "").replace("\n", "")
    if not texto_limpo:
        return None

    # Prioriza código numérico completo de 10 dígitos
    candidatos_digits = DIGITS_RE.findall(texto_limpo)
    validos_digits = [c for c in candidatos_digits if len(c) == CODIGO_LEN_ALVO]
    if validos_digits:
        contagem = Counter(validos_digits)
        validos_digits.sort(key=lambda c: (-contagem[c], c))
        return validos_digits[0]

    # Fallback para códigos alfanuméricos típicos de paint (ex: CR3904506)
    alnum_candidatos = re.findall(r"[A-Z0-9]{7,10}", texto_limpo)
    for candidato in alnum_candidatos:
        if sum(ch.isdigit() for ch in candidato) < 7:
            continue
        if candidato.isdigit():
            # não aceitar números curtos sem prefixo; só aceitamos numérico completo
            continue
        return candidato

    return None


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
    if not texto:
        return None
    return texto.upper()


def _ocr_paint(paint_path: Path, deadline: float | None = None) -> str | None:
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

    cfg = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

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
        if _deadline_exceeded(deadline):
            return None
        for escala in (1.0, 1.8, 2.2, 2.8):
            if _deadline_exceeded(deadline):
                return None
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


def _ocr_paint_intensivo(paint_path: Path, deadline: float | None = None) -> str | None:
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
        "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    ]

    chamadas = 0
    for base in variantes:
        if _deadline_exceeded(deadline):
            return None
        _, otsu = cv2.threshold(base, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for cand in (base, otsu, 255 - otsu):
            if _deadline_exceeded(deadline):
                return None
            for escala in (2.0, 2.8, 3.2):
                if _deadline_exceeded(deadline):
                    return None
                up = cv2.resize(cand, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                for cfg in psm_configs:
                    if _deadline_exceeded(deadline):
                        return None
                    codigo = _ocr_digits(up, cfg)
                    chamadas += 1
                    if codigo:
                        return codigo

                    if chamadas >= MAX_OCR_CALLS_PAINT_INTENSIVO:
                        return None

    return None


def _ocr_imagem_completa(caminho_img: Path, deadline: float | None = None) -> str | None:
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
        if _deadline_exceeded(deadline):
            return None
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
            if _deadline_exceeded(deadline):
                return None
            for escala in (1.5, 2.2, 3.0):
                if _deadline_exceeded(deadline):
                    return None
                up = cv2.resize(base, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                for cfg in psm_configs:
                    if _deadline_exceeded(deadline):
                        return None
                    codigo = _ocr_digits(up, cfg)
                    chamadas += 1
                    if codigo:
                        return codigo

                    if chamadas >= MAX_OCR_CALLS_IMAGEM_COMPLETA:
                        return None

    return None


def _ocr_etiqueta(caminho_img: Path, nivel_confianca: str = "baixa", deadline: float | None = None) -> str | None:
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
        if _deadline_exceeded(deadline):
            return None
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
            if _deadline_exceeded(deadline):
                return None
            candidatos_orientacao = [base, cv2.rotate(base, cv2.ROTATE_90_CLOCKWISE)]
            if usar_rotacao_ccw:
                candidatos_orientacao.append(cv2.rotate(base, cv2.ROTATE_90_COUNTERCLOCKWISE))
            if usar_rotacao_180:
                candidatos_orientacao.append(cv2.rotate(base, cv2.ROTATE_180))

            for orientado in candidatos_orientacao:
                if _deadline_exceeded(deadline):
                    return None
                for escala in escalas:
                    if _deadline_exceeded(deadline):
                        return None
                    up = cv2.resize(orientado, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                    for cfg in psm_configs:
                        if _deadline_exceeded(deadline):
                            return None
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
    modo: str = "all",
    deadline: float | None = None,
) -> tuple[str | None, str | None, dict]:
    if not etiquetas:
        return None, None, {"partial_6plus": False, "short_promissor": False}

    info = {"partial_6plus": False, "short_promissor": False}

    def _capturar_sinal(raw_codigo, meta):
        texto = str(raw_codigo or "")
        nums = DIGITS_RE.findall(texto)
        if any(len(n) >= 6 for n in nums):
            info["partial_6plus"] = True
        counts = (meta or {}).get("all_counts", {}) if isinstance(meta, dict) else {}
        for k, v in counts.items():
            if int(v or 0) >= 1 and len(str(k)) >= 6:
                info["short_promissor"] = True
                break

    if modo in {"all", "simple"}:
        t_simple = time.perf_counter()
        timeout_simple = False
        for idx_et, etiqueta in enumerate(etiquetas, start=1):
            if _deadline_exceeded(deadline):
                timeout_simple = True
                break
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
            _capturar_sinal(codigo, meta)
            codigo_norm = _normalizar_codigo(codigo)
            if _is_valid_candidate(codigo_norm):
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
                return codigo_norm, fonte, info

        _append_profile(
            perfil_rows,
            base,
            "barcode_etiqueta_simples",
            time.perf_counter() - t_simple,
            "",
            "timeout" if timeout_simple else "falhou",
            early_stop="False",
        )

    if modo in {"all", "intensivo"}:
        t_int = time.perf_counter()
        timeout_int = False
        for idx_et, etiqueta in enumerate(etiquetas, start=1):
            if _deadline_exceeded(deadline):
                timeout_int = True
                break
            if indice_global and total_global:
                print(
                    f"[ler_codigo] etiqueta intensivo {idx_et}/{len(etiquetas)} {etiqueta.name} | "
                    f"imagem {indice_global}/{total_global}"
                )

            codigo, meta = _normalizar_resultado_barcode(
                ler_barcode_imagem(etiqueta, modo="intensivo", min_digits=CODIGO_LEN_ALVO, return_meta=True)
            )
            _capturar_sinal(codigo, meta)
            codigo_norm = _normalizar_codigo(codigo)
            if _is_valid_candidate(codigo_norm):
                _append_profile(
                    perfil_rows,
                    base,
                    "barcode_etiqueta_intensivo",
                    time.perf_counter() - t_int,
                    "etiqueta_intensivo",
                    "ok",
                    early_stop="True",
                )
                return codigo_norm, "etiqueta_intensivo", info

        _append_profile(
            perfil_rows,
            base,
            "barcode_etiqueta_intensivo",
            time.perf_counter() - t_int,
            "",
            "timeout" if timeout_int else "falhou",
            early_stop="False",
        )

    return None, None, info


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

    item_deadline = _stage_deadline(None, CODE_READ_TIMEOUT_ITEM_S)
    etiquetas = _listar_etiquetas(base)
    paints = _listar_paints(base)
    candidatos_etiqueta: list[str] = []

    # estágio 1: simples (barato e confiável)
    stage_simple_deadline = _stage_deadline(item_deadline, CODE_READ_TIMEOUT_SIMPLE_S)
    codigo_eti_s, fonte_eti_s, info_sinal = _tentar_barcode_etiqueta_fallback(
        base,
        etiquetas,
        indice_global,
        total_global,
        perfil_rows,
        modo="simple",
        deadline=stage_simple_deadline,
    )
    if _is_valid_candidate(codigo_eti_s):
        return codigo_eti_s, fonte_eti_s or "etiqueta_raw"

    t_paint = time.perf_counter()
    timeout_simple = False
    for idx_paint, paint in enumerate(paints, start=1):
        if _deadline_exceeded(stage_simple_deadline):
            timeout_simple = True
            break
        if indice_global and total_global:
            print(
                f"[ler_codigo] lendo paint {idx_paint}/{len(paints)} {paint.name} | "
                f"imagem {indice_global}/{total_global}"
            )
        codigo = _ocr_paint(paint, deadline=stage_simple_deadline)
        if codigo:
            codigo_norm = _normalizar_codigo(codigo)
            if _is_valid_candidate(codigo_norm):
                _append_profile(perfil_rows, base, "ocr_paint", time.perf_counter() - t_paint, "paint", "ok", early_stop="True")
                return codigo_norm, "paint"
    _append_profile(
        perfil_rows,
        base,
        "ocr_paint",
        time.perf_counter() - t_paint,
        "",
        "timeout" if timeout_simple else "falhou",
        early_stop="False",
    )

    has_partial_6plus = bool(info_sinal.get("partial_6plus", False))
    has_short_candidate = bool(info_sinal.get("short_promissor", False))
    sinal_util = _has_useful_signal(etiquetas, paints, has_partial_6plus, has_short_candidate)

    # estágio 2: intensivo (somente com sinal útil)
    if sinal_util and not _deadline_exceeded(item_deadline):
        stage_int_deadline = _stage_deadline(item_deadline, CODE_READ_TIMEOUT_INTENSIVO_S)
        codigo_eti_i, fonte_eti_i, info_sinal_i = _tentar_barcode_etiqueta_fallback(
            base,
            etiquetas,
            indice_global,
            total_global,
            perfil_rows,
            modo="intensivo",
            deadline=stage_int_deadline,
        )
        if _is_valid_candidate(codigo_eti_i):
            return codigo_eti_i, fonte_eti_i or "etiqueta_intensivo"

        has_partial_6plus = has_partial_6plus or bool(info_sinal_i.get("partial_6plus", False))
        has_short_candidate = has_short_candidate or bool(info_sinal_i.get("short_promissor", False))

        t_paint_int = time.perf_counter()
        timeout_paint_int = False
        for idx_paint, paint in enumerate(paints, start=1):
            if not ENABLE_PAINT_INTENSIVO:
                break
            if _deadline_exceeded(stage_int_deadline):
                timeout_paint_int = True
                break
            if indice_global and total_global:
                print(
                    f"[ler_codigo] paint intensivo {idx_paint}/{len(paints)} {paint.name} | "
                    f"imagem {indice_global}/{total_global}"
                )
            codigo = _ocr_paint_intensivo(paint, deadline=stage_int_deadline)
            if codigo:
                codigo_norm = _normalizar_codigo(codigo)
                if _is_valid_candidate(codigo_norm):
                    _append_profile(
                        perfil_rows,
                        base,
                        "ocr_paint_intensivo",
                        time.perf_counter() - t_paint_int,
                        "paint_intensivo",
                        "ok",
                        early_stop="True",
                    )
                    return codigo_norm, "paint_intensivo"
        if ENABLE_PAINT_INTENSIVO:
            _append_profile(
                perfil_rows,
                base,
                "ocr_paint_intensivo",
                time.perf_counter() - t_paint_int,
                "",
                "timeout" if timeout_paint_int else "falhou",
                early_stop="False",
            )
    elif not sinal_util:
        _append_profile(
            perfil_rows,
            base,
            "gate_intensivo",
            0.0,
            "",
            "bloqueado_sem_evidencia",
            early_stop="False",
        )

    # estágio 3: OCR (somente com sinal útil)
    sinal_util = _has_useful_signal(etiquetas, paints, has_partial_6plus, has_short_candidate)
    if sinal_util and not _deadline_exceeded(item_deadline):
        stage_ocr_deadline = _stage_deadline(item_deadline, CODE_READ_TIMEOUT_OCR_S)
        nivel_ocr_etiqueta = "baixa"

        t_ocr_eti = time.perf_counter()
        timeout_ocr = False
        for idx_et, etiqueta in enumerate(etiquetas, start=1):
            if _deadline_exceeded(stage_ocr_deadline):
                timeout_ocr = True
                break
            if indice_global and total_global:
                print(
                    f"[ler_codigo] ocr etiqueta {idx_et}/{len(etiquetas)} {etiqueta.name} | "
                    f"imagem {indice_global}/{total_global}"
                )
            codigo = _ocr_etiqueta(etiqueta, nivel_confianca=nivel_ocr_etiqueta, deadline=stage_ocr_deadline)
            if codigo:
                codigo_norm = _normalizar_codigo(codigo)
                if _is_valid_candidate(codigo_norm):
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
                            modo_adaptive="False",
                            early_stop="True",
                        )
                        return parcial, "etiqueta_ocr"

        _append_profile(
            perfil_rows,
            base,
            "ocr_etiqueta",
            time.perf_counter() - t_ocr_eti,
            "",
            "timeout" if timeout_ocr else "fim",
            nivel_ocr=nivel_ocr_etiqueta,
            modo_adaptive="False",
            early_stop="False",
        )

    if _deadline_exceeded(item_deadline):
        _append_profile(perfil_rows, base, "timeout_item", CODE_READ_TIMEOUT_ITEM_S, "", "timeout_item", early_stop="False")

    if ENABLE_OCR_IMAGEM_COMPLETA:
        original = _buscar_original(base)
        if original and not _deadline_exceeded(item_deadline):
            t_full = time.perf_counter()
            codigo = _ocr_imagem_completa(original, deadline=item_deadline)
            if codigo:
                codigo_norm = _normalizar_codigo(codigo)
                if _is_valid_candidate(codigo_norm):
                    _append_profile(
                        perfil_rows,
                        base,
                        "ocr_imagem_completa",
                        time.perf_counter() - t_full,
                        "imagem_completa",
                        "ok",
                        early_stop="True",
                    )
                    return codigo_norm, "imagem_completa"
            _append_profile(
                perfil_rows,
                base,
                "ocr_imagem_completa",
                time.perf_counter() - t_full,
                "",
                "falhou",
                early_stop="False",
            )

    # 4) Fallback: nome já é número
    if base.isdigit() and len(base) == CODIGO_LEN_ALVO:
        return base, "nome"

    return None, "nenhum"