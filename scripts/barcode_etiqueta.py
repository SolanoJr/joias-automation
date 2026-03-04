import cv2
from pathlib import Path
import os
import sys
import contextlib
from typing import Any

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

PASTA_ETIQUETAS = Path("output/etiquetas")
DEBUG_SALVAR_FALHAS = False
PASTA_DEBUG_FALHAS = Path("output/debug_barcode_falhas")
ESCALAS_BARCODE = [1.5, 2.0]
ESCALAS_BARCODE_INTENSIVO = [2.5, 3.0]
MIN_CODIGO_LEN = 8
MAX_CODIGO_LEN = 16

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


def _codigo_valido(valor: Any) -> str | None:
    codigo = str(valor).strip()
    if codigo.isdigit() and MIN_CODIGO_LEN <= len(codigo) <= MAX_CODIGO_LEN:
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

def _tentar_ler_array(img_array, detector=None, tentar_multi=False):
    if pyzbar_decode is not None:
        with silenciar_stderr():
            resultados = pyzbar_decode(img_array)
        for r in resultados:
            codigo = _codigo_valido(r.data.decode("utf-8"))
            if codigo:
                return codigo

    if detector is None:
        detector = _criar_detector_opencv()
    if detector is not None:
        if hasattr(detector, "detectAndDecode"):
            retorno = detector.detectAndDecode(img_array)
            for texto in _iterar_strings(retorno):
                codigo = _codigo_valido(texto)
                if codigo:
                    return codigo

        if hasattr(detector, "detectAndDecodeWithType"):
            retorno = detector.detectAndDecodeWithType(img_array)
            for texto in _iterar_strings(retorno):
                codigo = _codigo_valido(texto)
                if codigo:
                    return codigo

        if tentar_multi:
            if hasattr(detector, "detectAndDecodeMulti"):
                retorno = detector.detectAndDecodeMulti(img_array)
                for texto in _iterar_strings(retorno):
                    codigo = _codigo_valido(texto)
                    if codigo:
                        return codigo

            if hasattr(detector, "detectAndDecodeMultiWithType"):
                retorno = detector.detectAndDecodeMultiWithType(img_array)
                for texto in _iterar_strings(retorno):
                    codigo = _codigo_valido(texto)
                    if codigo:
                        return codigo

    return None

def _rotacoes(img):
    # img pode ser 2D (gray) ou 3D (BGR)
    yield img
    yield cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    yield cv2.rotate(img, cv2.ROTATE_180)
    yield cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

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

def ler_barcode_imagem(caminho_img: Path, modo: str = "normal"):
    img = cv2.imread(str(caminho_img))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    variantes = _gerar_variantes(gray)
    detector = _criar_detector_opencv()

    modo_normal = modo != "intensivo"

    if modo_normal:
        # fase rápida: variantes base em todas as rotações, sem métodos multi
        variantes_rapidas = variantes[:8]
        for _, v in variantes_rapidas:
            for vr in _rotacoes(v):
                codigo = _tentar_ler_array(vr, detector=detector, tentar_multi=False)
                if codigo:
                    return codigo

        # fase de resgate: variantes restantes sem rotação, com métodos multi
        for _, v in variantes[8:]:
            codigo = _tentar_ler_array(v, detector=detector, tentar_multi=True)
            if codigo:
                return codigo
    else:
        # modo intensivo: testa todas variantes + rotações + métodos multi
        for _, v in variantes:
            for vr in _rotacoes(v):
                codigo = _tentar_ler_array(vr, detector=detector, tentar_multi=True)
                if codigo:
                    return codigo

        # último resgate: escalas fortes da imagem cinza base
        for escala in ESCALAS_BARCODE_INTENSIVO:
            up = cv2.resize(gray, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
            for vr in _rotacoes(up):
                codigo = _tentar_ler_array(vr, detector=detector, tentar_multi=True)
                if codigo:
                    return codigo

    if DEBUG_SALVAR_FALHAS:
        _salvar_debug_falha(caminho_img, variantes)

    return None

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
