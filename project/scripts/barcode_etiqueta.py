import cv2
from pathlib import Path
import os
import sys
import contextlib
from collections import Counter
from typing import Any
import numpy as np

if os.name == "nt" and hasattr(os, "add_dll_directory"):
    pyzbar_dir = Path(sys.prefix) / "Lib" / "site-packages" / "pyzbar"
    if pyzbar_dir.exists():
        os.add_dll_directory(str(pyzbar_dir))

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_DISPONIVEL = True
except Exception:
    pyzbar_decode = None
    PYZBAR_DISPONIVEL = False

# ===== RAIZ DO PROJETO =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent

PASTA_ETIQUETAS = PROJECT_ROOT / "output/etiquetas"
DEBUG_SALVAR_FALHAS = False
PASTA_DEBUG_FALHAS = PROJECT_ROOT / "output/debug_barcode_falhas"
ESCALAS_BARCODE = [1.5, 2.0]
ESCALAS_BARCODE_INTENSIVO = [2.5, 3.0]
MIN_CODIGO_LEN = 8
MAX_CODIGO_LEN = 16
BARCODE_FAST_PREP = os.getenv("BARCODE_FAST_PREP", "0").strip().lower() in {"1", "true", "yes", "on"}
# Tamanho máximo para pyzbar (imagens muito grandes travam o decoder)
PYZBAR_MAX_SIDE = 1500

@contextlib.contextmanager
def silenciar_stderr():
    old = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = old


def _criar_detector_opencv() -> Any | None:
    barcode_namespace = getattr(cv2, "barcode", None)
    if barcode_namespace is not None:
        detector_cls = getattr(barcode_namespace, "BarcodeDetector", None)
        if detector_cls is not None:
            try:
                return detector_cls()
            except Exception:
                pass

    detector_factory = getattr(cv2, "barcode_BarcodeDetector", None)
    if detector_factory is not None:
        try:
            return detector_factory()
        except Exception:
            pass

    return None


def _extrair_digitos(valor: Any) -> str:
    texto = str(valor).strip()
    return "".join(ch for ch in texto if ch.isdigit())


def _codigo_valido(valor: Any, min_digits: int = MIN_CODIGO_LEN) -> str | None:
    """
    Valida e retorna o código lido pelo barcode reader.
    Preserva o código alfanumérico completo (ex: BR1204039) quando válido.
    """
    texto = str(valor).strip().upper()
    if not texto:
        return None

    # Código alfanumérico tipo BR1204039, CR3984506 — preserva completo
    import re as _re
    alnum_match = _re.fullmatch(r"[A-Z]{1,3}[0-9]{4,9}", texto)
    if alnum_match:
        n_digits = sum(ch.isdigit() for ch in texto)
        if n_digits >= min_digits:
            return texto

    # Código numérico puro — extrai só dígitos
    codigo = _extrair_digitos(texto)
    if MIN_CODIGO_LEN <= len(codigo) <= MAX_CODIGO_LEN and len(codigo) >= min_digits:
        return codigo
    return None


def _iterar_strings(resultado: Any):
    if resultado is None:
        return

    if isinstance(resultado, str):
        yield resultado
        return

    if isinstance(resultado, (list, tuple)):
        for item in resultado:
            yield from _iterar_strings(item)
        return

    if hasattr(resultado, "tolist"):
        try:
            convertido = resultado.tolist()
            yield from _iterar_strings(convertido)
        except Exception:
            return

def _coletar_codigos_array(img_array, detector=None, tentar_multi=False, min_digits: int = MIN_CODIGO_LEN):
    codigos: list[str] = []

    if pyzbar_decode is not None:
        with silenciar_stderr():
            resultados = pyzbar_decode(img_array)
        for r in resultados:
            codigo = _codigo_valido(r.data.decode("utf-8", errors="ignore"), min_digits=min_digits)
            if codigo:
                codigos.append(codigo)

    if detector is None:
        detector = _criar_detector_opencv()
    if detector is not None:
        if hasattr(detector, "detectAndDecode"):
            retorno = detector.detectAndDecode(img_array)
            for texto in _iterar_strings(retorno):
                codigo = _codigo_valido(texto, min_digits=min_digits)
                if codigo:
                    codigos.append(codigo)

        if hasattr(detector, "detectAndDecodeWithType"):
            retorno = detector.detectAndDecodeWithType(img_array)
            for texto in _iterar_strings(retorno):
                codigo = _codigo_valido(texto, min_digits=min_digits)
                if codigo:
                    codigos.append(codigo)

        if tentar_multi:
            if hasattr(detector, "detectAndDecodeMulti"):
                retorno = detector.detectAndDecodeMulti(img_array)
                for texto in _iterar_strings(retorno):
                    codigo = _codigo_valido(texto, min_digits=min_digits)
                    if codigo:
                        codigos.append(codigo)

            if hasattr(detector, "detectAndDecodeMultiWithType"):
                retorno = detector.detectAndDecodeMultiWithType(img_array)
                for texto in _iterar_strings(retorno):
                    codigo = _codigo_valido(texto, min_digits=min_digits)
                    if codigo:
                        codigos.append(codigo)

    return codigos


def _tentar_ler_array(img_array, detector=None, tentar_multi=False):
    codigos = _coletar_codigos_array(
        img_array,
        detector=detector,
        tentar_multi=tentar_multi,
        min_digits=MIN_CODIGO_LEN,
    )
    if codigos:
        return codigos[0]

    return None


def _primeiro_codigo_array(img_array, detector=None, tentar_multi=False, min_digits: int = 10):
    codigos = _coletar_codigos_array(
        img_array,
        detector=detector,
        tentar_multi=tentar_multi,
        min_digits=min_digits,
    )
    if codigos:
        return codigos[0]
    return None

def _rotacoes(img):
    # img pode ser 2D (gray) ou 3D (BGR)
    yield img
    yield cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    yield cv2.rotate(img, cv2.ROTATE_180)
    yield cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)


def _variantes_rapidas(img_bgr, gray):
    yield img_bgr
    yield gray
    adapt = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    yield adapt


def _limitar_tamanho_pyzbar(img: np.ndarray, max_side: int = None) -> np.ndarray:
    """Limita tamanho da imagem para evitar travamento do pyzbar em imagens grandes."""
    if max_side is None:
        max_side = PYZBAR_MAX_SIDE
    h, w = img.shape[:2]
    maior = max(h, w)
    if maior <= max_side:
        return img
    scale = max_side / float(maior)
    novo_w = max(1, int(w * scale))
    novo_h = max(1, int(h * scale))
    return cv2.resize(img, (novo_w, novo_h), interpolation=cv2.INTER_AREA)


def _primeiro_codigo_pyzbar(img_array, min_digits: int = 10):
    if pyzbar_decode is None:
        return None

    # Limita tamanho para evitar travamento
    img_safe = _limitar_tamanho_pyzbar(img_array)

    with silenciar_stderr():
        resultados = pyzbar_decode(img_safe)

    for r in resultados:
        codigo = _codigo_valido(r.data.decode("utf-8", errors="ignore"), min_digits=min_digits)
        if codigo:
            return codigo

    return None


def _pyzbar_variantes(img_gray: np.ndarray, min_digits: int = 10):
    """
    Tenta ler barcode com pyzbar usando múltiplas variantes de pré-processamento.
    Estratégia otimizada para CODE128 em etiquetas de joias.
    Retorna (codigo, variante_usada) ou (None, "").
    """
    if pyzbar_decode is None:
        return None, ""

    h, w = img_gray.shape[:2]

    # Variantes em ordem de custo crescente
    def _tentar(arr, nome):
        safe = _limitar_tamanho_pyzbar(arr)
        with silenciar_stderr():
            resultados = pyzbar_decode(safe)
        for r in resultados:
            codigo = _codigo_valido(r.data.decode("utf-8", errors="ignore"), min_digits=min_digits)
            if codigo:
                return codigo, nome
        return None, ""

    # 1. Original com padding (mais comum que funciona)
    pad = cv2.copyMakeBorder(img_gray, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    c, n = _tentar(pad, "pad_orig")
    if c: return c, n

    # 2. Otsu com padding
    _, otsu = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    pad_otsu = cv2.copyMakeBorder(otsu, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    c, n = _tentar(pad_otsu, "pad_otsu")
    if c: return c, n

    # 3. Scale 2x com padding (para imagens pequenas)
    if max(h, w) < 800:
        up2 = cv2.resize(img_gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        pad_up2 = cv2.copyMakeBorder(up2, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
        c, n = _tentar(pad_up2, "pad_2x")
        if c: return c, n

        _, otsu_up2 = cv2.threshold(up2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        pad_otsu_up2 = cv2.copyMakeBorder(otsu_up2, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
        c, n = _tentar(pad_otsu_up2, "pad_otsu_2x")
        if c: return c, n

    # 4. CLAHE com padding
    clahe_img = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(img_gray)
    pad_clahe = cv2.copyMakeBorder(clahe_img, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
    c, n = _tentar(pad_clahe, "pad_clahe")
    if c: return c, n

    # 5. Sem padding (fallback)
    c, n = _tentar(img_gray, "raw")
    if c: return c, n

    c, n = _tentar(otsu, "otsu")
    if c: return c, n

    return None, ""


def ler_barcode_crop_simples(caminho_img: Path, min_digits: int = 10, return_stage: bool = False):
    img = cv2.imread(str(caminho_img))
    if img is None:
        return (None, "") if return_stage else None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Usa a estratégia otimizada com pyzbar (variantes + padding)
    if pyzbar_decode is not None:
        codigo, variante = _pyzbar_variantes(gray, min_digits=min_digits)
        if codigo:
            return (codigo, variante) if return_stage else codigo

    # Fallback: pyzbar simples nas variantes básicas (compatibilidade)
    up2 = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thr = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    tentativas = [
        ("raw", img),
        ("resize2x", up2),
        ("threshold", thr),
    ]

    for etapa, arr in tentativas:
        codigo = _primeiro_codigo_pyzbar(arr, min_digits=min_digits)
        if codigo:
            return (codigo, etapa) if return_stage else codigo

    return (None, "") if return_stage else None


def _iterar_tentativas_v2(img_bgr, gray):
    up2 = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    pad_lr16 = cv2.copyMakeBorder(gray, 0, 0, 16, 16, cv2.BORDER_CONSTANT, value=255)
    pad_lr16_up2 = cv2.resize(pad_lr16, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    pad_all12 = cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    pad_all12_up2 = cv2.resize(pad_all12, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_up2 = cv2.resize(otsu, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    yield "orig_bgr", img_bgr
    yield "gray", gray
    yield "gray_up2", up2
    yield "gray_pad_lr16_up2", pad_lr16_up2
    yield "gray_pad_all12_up2", pad_all12_up2
    yield "otsu_up2", otsu_up2
    yield "gray_pad_lr16_up2_rot90", cv2.rotate(pad_lr16_up2, cv2.ROTATE_90_CLOCKWISE)
    yield "gray_pad_lr16_up2_rot270", cv2.rotate(pad_lr16_up2, cv2.ROTATE_90_COUNTERCLOCKWISE)


def ler_barcode_imagem_v2(caminho_img: Path, min_digits: int = 10, return_variant: bool = False):
    img = cv2.imread(str(caminho_img))
    if img is None:
        if return_variant:
            return None, {"variant": "", "attempts": 0}
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    tentativas = 0
    for nome, variante in _iterar_tentativas_v2(img, gray):
        tentativas += 1
        codigo = _primeiro_codigo_pyzbar(variante, min_digits=min_digits)
        if codigo:
            if return_variant:
                return codigo, {"variant": nome, "attempts": tentativas}
            return codigo

    if return_variant:
        return None, {"variant": "", "attempts": tentativas}
    return None

def _gerar_variantes(gray):
    variantes = [("gray", gray)]

    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    variantes.append(("blur", blur))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    variantes.append(("clahe", contrast))

    _, otsu = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variantes.append(("otsu", otsu))

    adapt = cv2.adaptiveThreshold(
        contrast,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )
    variantes.append(("adapt", adapt))

    nitida = cv2.addWeighted(contrast, 1.5, blur, -0.5, 0)
    variantes.append(("nitida", nitida))

    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1))
    variantes.append(("close_h", cv2.morphologyEx(contrast, cv2.MORPH_CLOSE, kernel_h, iterations=1)))
    variantes.append(("open_h", cv2.morphologyEx(contrast, cv2.MORPH_OPEN, kernel_h, iterations=1)))

    escalas = ESCALAS_BARCODE
    base_para_escala = [
        ("gray", gray),
        ("clahe", contrast),
        ("otsu", otsu),
        ("adapt", adapt),
        ("nitida", nitida),
    ]
    for nome_base, base in base_para_escala:
        for escala in escalas:
            up = cv2.resize(base, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
            variantes.append((f"{nome_base}_x{str(escala).replace('.', '_')}", up))

    return variantes


def _salvar_debug_falha(caminho_img: Path, variantes):
    pasta_imagem = PASTA_DEBUG_FALHAS / caminho_img.stem
    pasta_imagem.mkdir(parents=True, exist_ok=True)

    for i, (nome, img_variante) in enumerate(variantes):
        saida = pasta_imagem / f"{i:02d}_{nome}.jpg"
        cv2.imwrite(str(saida), img_variante)

def ler_barcode_imagem(
    caminho_img: Path,
    modo: str = "normal",
    min_digits: int = 10,
    return_meta: bool = False,
    simple_only: bool = False,
):
    codigo_simples, etapa_simples = ler_barcode_crop_simples(caminho_img, min_digits=min_digits, return_stage=True)
    if codigo_simples:
        if return_meta:
            return codigo_simples, {
                "candidates": [codigo_simples],
                "best_count": 1,
                "all_counts": {codigo_simples: 1},
                "simple_stage": etapa_simples,
            }
        return codigo_simples

    if simple_only:
        meta_vazio = {
            "candidates": [],
            "best_count": 0,
            "all_counts": {},
            "simple_stage": "",
        }
        return (None, meta_vazio) if return_meta else None

    img = cv2.imread(str(caminho_img))
    if img is None:
        return (None, {}) if return_meta else None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    variantes = _gerar_variantes(gray)
    detector = _criar_detector_opencv()
    candidatos: list[str] = []

    modo_normal = modo != "intensivo"

    if not return_meta:
        if BARCODE_FAST_PREP and modo_normal:
            for base in _variantes_rapidas(img, gray):
                codigo = _primeiro_codigo_array(base, detector=detector, tentar_multi=False, min_digits=min_digits)
                if codigo:
                    return codigo

        if modo_normal:
            variantes_rapidas = variantes[:8]
            for _, v in variantes_rapidas:
                for vr in _rotacoes(v):
                    codigo = _primeiro_codigo_array(vr, detector=detector, tentar_multi=False, min_digits=min_digits)
                    if codigo:
                        return codigo

            for _, v in variantes[8:]:
                codigo = _primeiro_codigo_array(v, detector=detector, tentar_multi=True, min_digits=min_digits)
                if codigo:
                    return codigo
        else:
            for _, v in variantes:
                for vr in _rotacoes(v):
                    codigo = _primeiro_codigo_array(vr, detector=detector, tentar_multi=True, min_digits=min_digits)
                    if codigo:
                        return codigo

            for escala in ESCALAS_BARCODE_INTENSIVO:
                up = cv2.resize(gray, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
                for vr in _rotacoes(up):
                    codigo = _primeiro_codigo_array(vr, detector=detector, tentar_multi=True, min_digits=min_digits)
                    if codigo:
                        return codigo

        if DEBUG_SALVAR_FALHAS:
            _salvar_debug_falha(caminho_img, variantes)
        return None

    if modo_normal:
        # fase rápida: variantes base em todas as rotações, sem métodos multi
        variantes_rapidas = variantes[:8]
        for _, v in variantes_rapidas:
            for vr in _rotacoes(v):
                codigos = _coletar_codigos_array(vr, detector=detector, tentar_multi=False)
                if codigos:
                    candidatos.extend(codigos)

        # fase de resgate: variantes restantes sem rotação, com métodos multi
        for _, v in variantes[8:]:
            codigos = _coletar_codigos_array(v, detector=detector, tentar_multi=True)
            if codigos:
                candidatos.extend(codigos)
    else:
        # modo intensivo: testa todas variantes + rotações + métodos multi
        for _, v in variantes:
            for vr in _rotacoes(v):
                codigos = _coletar_codigos_array(vr, detector=detector, tentar_multi=True)
                if codigos:
                    candidatos.extend(codigos)

        # último resgate: escalas fortes da imagem cinza base
        for escala in ESCALAS_BARCODE_INTENSIVO:
            up = cv2.resize(gray, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
            for vr in _rotacoes(up):
                codigos = _coletar_codigos_array(vr, detector=detector, tentar_multi=True)
                if codigos:
                    candidatos.extend(codigos)

    contagem = Counter(c for c in candidatos if len(c) >= MIN_CODIGO_LEN)
    longos = [(cod, qtd) for cod, qtd in contagem.items() if len(cod) >= min_digits]
    melhor = None
    melhor_qtd = 0

    if longos:
        melhor, melhor_qtd = sorted(longos, key=lambda x: (x[1], len(x[0])), reverse=True)[0]

    if melhor is not None:
        meta = {
            "candidates": candidatos,
            "best_count": melhor_qtd,
            "all_counts": dict(contagem),
            "simple_stage": "",
        }
        return (melhor, meta) if return_meta else melhor

    if DEBUG_SALVAR_FALHAS:
        _salvar_debug_falha(caminho_img, variantes)

    meta = {
        "candidates": candidatos,
        "best_count": max(contagem.values()) if contagem else 0,
        "all_counts": dict(contagem),
        "simple_stage": "",
    }
    return (None, meta) if return_meta else None

def ler_codigos_da_pasta(pasta: Path = PASTA_ETIQUETAS):
    resultados = {}
    for img_path in sorted(pasta.glob("*.jpg")):
        resultados[img_path.name] = ler_barcode_imagem(img_path)
    return resultados

if __name__ == "__main__":
    print("Iniciando leitura de código de barras (simples)...\n")
    if not PYZBAR_DISPONIVEL:
        print("Aviso: pyzbar indisponível; usando fallback OpenCV BarcodeDetector.\n")
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
