"""
ler_codigo.py — Leitura de código de produto a partir de crops de imagem.

Estratégia de leitura em 4 estágios (do mais rápido/confiável ao mais lento):

  Estágio 1 — Simples (rápido, ~5s budget):
    • Barcode simples na etiqueta (pyzbar + OpenCV BarcodeDetector)
    • OCR no paint (texto pintado na joia)
    Retorna imediatamente se encontrar código válido.

  Estágio 2 — Intensivo (só se estágio 1 deu sinal parcial, ~12s budget):
    • Barcode intensivo na etiqueta (mais variantes de pré-processamento)
    • OCR intensivo no paint (mais escalas e configurações PSM)
    Ativado apenas quando há evidência de código parcial (≥6 dígitos detectados).

  Estágio 3 — OCR de texto na etiqueta (~15s budget):
    • OCR completo com múltiplas orientações e escalas
    Ativado apenas com sinal útil (evita desperdício em imagens sem etiqueta).

  Estágio 4 — Fallback:
    • OCR na imagem original completa (regiões prováveis)
    • Nome do arquivo como código (se já for numérico de 10 dígitos)

Cada estágio tem deadline próprio + deadline global por item (CODE_READ_TIMEOUT_ITEM_S).
O cache OCR (SHA256) evita reprocessar o mesmo arquivo em reruns.
"""
import re
import os
import time
import hashlib
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pytesseract

# Adiciona scripts ao path para importação
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

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
OCR_ETIQUETA_ADAPTIVE = os.getenv("OCR_ETIQUETA_ADAPTIVE", "1").strip().lower() in {"1", "true", "yes", "on"}
LER_CODIGO_CANONICAL_ONLY = os.getenv("LER_CODIGO_CANONICAL_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
CODE_READ_TIMEOUT_SIMPLE_S = float((os.getenv("CODE_READ_TIMEOUT_SIMPLE_S") or "5.0").strip() or "5.0")
CODE_READ_TIMEOUT_INTENSIVO_S = float((os.getenv("CODE_READ_TIMEOUT_INTENSIVO_S") or "12.0").strip() or "12.0")
CODE_READ_TIMEOUT_OCR_S = float((os.getenv("CODE_READ_TIMEOUT_OCR_S") or "25.0").strip() or "25.0")
CODE_READ_TIMEOUT_ITEM_S = float((os.getenv("CODE_READ_TIMEOUT_ITEM_S") or "45.0").strip() or "45.0")

# ===== OCR PREPROCESSING & ENHANCEMENT =====
ENABLE_ADAPTIVE_PREPROCESSING = os.getenv("ENABLE_ADAPTIVE_PREPROCESSING", "1").strip().lower() in {"1", "true", "yes", "on"}
CLAHE_CLIP_LIMIT = float(os.getenv("CLAHE_CLIP_LIMIT", "2.0"))
CLAHE_TILE_SIZE = int(os.getenv("CLAHE_TILE_SIZE", "8"))

# ===== OCR ZOOM ADAPTATIVO =====
ENABLE_OCR_ADAPTIVE_ZOOM = os.getenv("ENABLE_OCR_ADAPTIVE_ZOOM", "1").strip().lower() in {"1", "true", "yes", "on"}
OCR_ZOOM_THRESHOLD_SMALL = int(os.getenv("OCR_ZOOM_THRESHOLD_SMALL", "100"))  # px
OCR_ZOOM_THRESHOLD_MEDIUM = int(os.getenv("OCR_ZOOM_THRESHOLD_MEDIUM", "200"))  # px
OCR_ZOOM_MULTIPLIER_SMALL = float(os.getenv("OCR_ZOOM_MULTIPLIER_SMALL", "2.0"))
OCR_ZOOM_MULTIPLIER_MEDIUM = float(os.getenv("OCR_ZOOM_MULTIPLIER_MEDIUM", "1.5"))

# ===== OCR CACHE CONFIG =====
OCR_CACHE_ENABLED = os.getenv("OCR_CACHE_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
OCR_CACHE_DIR = Path("output/cache_ocr")
OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _get_file_hash(file_path: Path) -> str | None:
    """Calcula SHA256 do arquivo para usar como chave de cache"""
    try:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]
    except Exception:
        return None

def _ocr_result_from_cache(cache_key: str | None) -> str | None:
    """Recupera resultado do cache"""
    if not OCR_CACHE_ENABLED or not cache_key:
        return None

    cache_file = OCR_CACHE_DIR / f"{cache_key}.ocr"
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return None

def _ocr_result_to_cache(cache_key: str | None, resultado: str) -> None:
    """Salva resultado no cache"""
    if not OCR_CACHE_ENABLED or not cache_key or not resultado:
        return

    cache_file = OCR_CACHE_DIR / f"{cache_key}.ocr"
    try:
        cache_file.write_text(resultado, encoding="utf-8")
    except Exception:
        pass  # Log silencioso, não interrompe execução


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
    # Rejeita EAN-13/EAN-8 (códigos de barras de preço/produto, não de joia)
    if codigo.isdigit() and len(codigo) in (8, 12, 13):
        return False
    if codigo.isdigit() and len(codigo) == CODIGO_LEN_ALVO:
        return True
    # Alfanumérico: prefixo de 1-3 letras + 4-9 dígitos (ex: BR1204039, CR3984506)
    if re.fullmatch(r"[A-Z]{1,3}[0-9]{4,9}", codigo):
        return True
    # Formato legado: qualquer alnum 7-10 com ≥7 dígitos
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

    # Substitui separadores (newline, tab, |, /) por espaço ANTES de limpar
    # Isso evita que "ATA\nBR1204039" vire "ATABR1204039"
    texto_limpo = texto.strip().upper()
    texto_limpo = re.sub(r"[\n\r\t|/\\]", " ", texto_limpo)
    texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()
    if not texto_limpo:
        return None

    # Prioriza código numérico completo de 10 dígitos
    candidatos_digits = DIGITS_RE.findall(texto_limpo)
    validos_digits = [c for c in candidatos_digits if len(c) == CODIGO_LEN_ALVO]
    if validos_digits:
        contagem = Counter(validos_digits)
        validos_digits.sort(key=lambda c: (-contagem[c], c))
        return validos_digits[0]

    # Fallback para códigos alfanuméricos típicos de paint/etiqueta (ex: CR3904506, BR1204039)
    # Aceita prefixo de 1-3 letras + 4-9 dígitos
    # Usa \b para garantir boundary correto (funciona bem com espaços)
    # Também tenta extrair quando o código está grudado em outra palavra (ex: "UTABR1204039")
    # — procura o padrão mais longo que começa com 1-3 letras seguidas de dígitos
    alnum_candidatos = re.findall(r"\b[A-Z]{1,3}[0-9]{4,9}\b", texto_limpo)
    if not alnum_candidatos:
        # Fallback: extrai qualquer ocorrência de 1-3 letras + 4-9 dígitos, mesmo sem boundary
        # Ordena por comprimento decrescente para pegar o mais específico
        alnum_candidatos = re.findall(r"(?<![0-9])[A-Z]{1,3}[0-9]{4,9}(?![0-9A-Z])", texto_limpo)
    if alnum_candidatos:
        return max(alnum_candidatos, key=len)

    # Fallback legado: qualquer alnum 7-10 com ≥7 dígitos
    alnum_candidatos_legado = re.findall(r"[A-Z0-9]{7,10}", texto_limpo)
    for candidato in alnum_candidatos_legado:
        if sum(ch.isdigit() for ch in candidato) < 7:
            continue
        if candidato.isdigit():
            continue
        return candidato

    return None


def _ocr_digits(img, cfg: str) -> str | None:
    try:
        txt = pytesseract.image_to_string(img, config=cfg, timeout=OCR_TIMEOUT_SECONDS)
    except BaseException:
        return None
    return _normalizar_codigo(txt)


def _selecionar_por_votos(candidatos: list[str], min_votos: int = 2) -> str | None:
    if not candidatos:
        return None

    contagem = Counter(candidatos)
    codigo, votos = contagem.most_common(1)[0]
    if votos >= min_votos:
        return codigo
    return None


def _calcular_zoom_ocr_adaptativo(img: np.ndarray) -> float:
    """
    Calcula zoom adaptativo para OCR baseado no tamanho da imagem.
    Útil para textos muito pequenos que precisam de ampliação.
    """
    if not ENABLE_OCR_ADAPTIVE_ZOOM:
        return 1.0

    h, w = img.shape[:2]
    menor_lado = min(h, w)

    if menor_lado < OCR_ZOOM_THRESHOLD_SMALL:
        return OCR_ZOOM_MULTIPLIER_SMALL
    elif menor_lado < OCR_ZOOM_THRESHOLD_MEDIUM:
        return OCR_ZOOM_MULTIPLIER_MEDIUM
    else:
        return 1.0


def _preprocessar_adaptativo(img: np.ndarray) -> list[np.ndarray]:
    """
    Gera variantes pré-processadas de uma imagem para melhor OCR.
    Inclui CLAHE + sharpening para imagens pequenas.
    """
    if not ENABLE_ADAPTIVE_PREPROCESSING:
        return [img]

    variantes = [img]

    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    # CLAHE básico
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(CLAHE_TILE_SIZE, CLAHE_TILE_SIZE))
    clahe_img = clahe.apply(gray)
    variantes.append(clahe_img)

    # CLAHE + Sharpening (bom para textos pequenos)
    kernel_sharpen = np.array([[-1, -1, -1],
                                [-1,  9, -1],
                                [-1, -1, -1]]) / 1.0
    clahe_sharp = cv2.filter2D(clahe_img, -1, kernel_sharpen)
    variantes.append(clahe_sharp)

    # CLAHE + Morphological closing (bom para caracteres quebrados)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    clahe_close = cv2.morphologyEx(clahe_img, cv2.MORPH_CLOSE, kernel_close, iterations=1)
    variantes.append(clahe_close)

    return variantes


def _ocr_paint(paint_path: Path, deadline: float | None = None) -> str | None:
    # ===== CACHE CHECK =====
    cache_key = _get_file_hash(paint_path)
    cached_result = _ocr_result_from_cache(cache_key)
    if cached_result:
        return cached_result

    img = cv2.imread(str(paint_path))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ===== ZOOM ADAPTATIVO PARA OCR =====
    zoom_factor = _calcular_zoom_ocr_adaptativo(gray)
    if zoom_factor > 1.0:
        h, w = gray.shape
        new_w = int(w * zoom_factor)
        new_h = int(h * zoom_factor)
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

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

    # Adicionar variantes pré-processadas adaptativas
    variantes_adap = _preprocessar_adaptativo(gray)
    candidatos.extend([v for v in variantes_adap if v is not None])

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
                _ocr_result_to_cache(cache_key, codigo)
                return codigo

            cfg_alt = "--psm 6 -c tessedit_char_whitelist=0123456789"
            codigo_alt = _ocr_digits(candidate, cfg_alt)
            chamadas += 1
            if codigo_alt:
                _ocr_result_to_cache(cache_key, codigo_alt)
                return codigo_alt

            if chamadas >= MAX_OCR_CALLS_PAINT:
                return None

    return None


def _ocr_paint_intensivo(paint_path: Path, deadline: float | None = None) -> str | None:
    # ===== CACHE CHECK =====
    cache_key = _get_file_hash(paint_path)
    cached_result = _ocr_result_from_cache(cache_key)
    if cached_result:
        return cached_result

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
                        _ocr_result_to_cache(cache_key, codigo)
                        return codigo

                    if chamadas >= MAX_OCR_CALLS_PAINT_INTENSIVO:
                        return None

    return None


def _ocr_imagem_completa(caminho_img: Path, deadline: float | None = None) -> str | None:
    # ===== CACHE CHECK =====
    cache_key = _get_file_hash(caminho_img)
    cached_result = _ocr_result_from_cache(cache_key)
    if cached_result:
        return cached_result

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
                        _ocr_result_to_cache(cache_key, codigo)
                        return codigo

                    if chamadas >= MAX_OCR_CALLS_IMAGEM_COMPLETA:
                        return None

    return None


def _ocr_etiqueta(caminho_img: Path, nivel_confianca: str = "baixa", deadline: float | None = None) -> str | None:
    # ===== CACHE CHECK =====
    cache_key = _get_file_hash(caminho_img)
    cached_result = _ocr_result_from_cache(cache_key)
    if cached_result:
        return cached_result

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
        "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "--psm 7 -c tessedit_char_whitelist=0123456789",
        "--psm 6 -c tessedit_char_whitelist=0123456789",
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
            escalas = (1.0, 1.8, 2.5, 3.0, 4.0)  # 1.0 primeiro — funciona para etiquetas grandes
            usar_rotacao_180 = False
            usar_rotacao_ccw = True
            limite_chamadas = min(MAX_OCR_CALLS_ETIQUETA, 60)
    else:
        psm_configs = psm_full
        escalas = (1.0, 1.8, 2.5, 3.0, 4.0)
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
                            _ocr_result_to_cache(cache_key, codigo)
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
                    min_digits=7,  # Aceita BR1204039 (9 chars, 7 dígitos) e similares
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
                ler_barcode_imagem(etiqueta, modo="intensivo", min_digits=7, return_meta=True)
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

    # ── ESTÁGIO 1: Simples ──────────────────────────────────────────────────
    # Barcode e OCR de paint são rápidos e têm alta precisão quando funcionam.
    # Tentamos primeiro para evitar gastar tempo nos estágios mais lentos.
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
        # Barcode simples funcionou — retorno imediato, sem gastar mais tempo
        return codigo_eti_s, fonte_eti_s or "etiqueta_raw"

    # OCR no paint: texto pintado diretamente na joia (ex: "1200090006")
    # Mais rápido que OCR de etiqueta porque o crop já é pequeno e focado
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

    # Verifica se o estágio 1 deixou algum sinal parcial (≥6 dígitos detectados).
    # Sem sinal, não vale a pena gastar tempo nos estágios intensivos.
    has_partial_6plus = bool(info_sinal.get("partial_6plus", False))
    has_short_candidate = bool(info_sinal.get("short_promissor", False))
    sinal_util = _has_useful_signal(etiquetas, paints, has_partial_6plus, has_short_candidate)

    # ── ESTÁGIO 2: Intensivo ─────────────────────────────────────────────────
    # Só entra aqui se há evidência de código parcial — evita desperdício em
    # imagens sem etiqueta/paint onde o estágio 1 já confirmou que não há nada.
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

    # ── ESTÁGIO 3: OCR de texto na etiqueta ─────────────────────────────────
    # Mais lento que barcode, mas funciona quando o código de barras está
    # danificado ou ilegível. Usa múltiplas orientações porque etiquetas
    # podem estar rotacionadas na foto.
    # IMPORTANTE: se há etiquetas detectadas, sempre tenta OCR de texto —
    # mesmo sem sinal do barcode, porque o barcode pode ser ilegível mas
    # o texto impresso na etiqueta ainda é legível pelo OCR.
    sinal_util = _has_useful_signal(etiquetas, paints, has_partial_6plus, has_short_candidate)
    tem_etiqueta = bool(etiquetas)
    if (sinal_util or tem_etiqueta) and not _deadline_exceeded(item_deadline):
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

    # ── ESTÁGIO 4: Fallbacks finais ──────────────────────────────────────────
    # OCR na imagem original completa: último recurso quando não há crop de
    # etiqueta/paint, ou quando todos os estágios anteriores falharam.
    # Foca nas regiões inferiores da imagem onde o código costuma aparecer.
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

    # Fallback final: se o nome do arquivo já é um código numérico de 10 dígitos,
    # usa diretamente — acontece quando a foto já foi renomeada anteriormente.
    if base.isdigit() and len(base) == CODIGO_LEN_ALVO:
        return base, "nome"

    return None, "nenhum"
