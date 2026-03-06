import argparse
import json
import re
from pathlib import Path

import cv2
import pytesseract


ROOT = Path(".")
OUT = ROOT / "output"
PAINTS = OUT / "paints"
ETIQUETAS = OUT / "etiquetas"
SEM_ETIQUETA = OUT / "sem_etiqueta"
BASELINE_PATH = OUT / "analysis" / "baseline_validacao.json"


def _count_images(folder: Path) -> int:
    return len(list(folder.glob("*.jpg")))


def _ocr_digits(img_gray) -> str:
    up = cv2.resize(img_gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    cfg = "--psm 11 -c tessedit_char_whitelist=0123456789"
    try:
        txt = pytesseract.image_to_string(up, config=cfg, timeout=1)
    except BaseException:
        return ""
    return "".join(re.findall(r"\d", txt))


def _paint_quality() -> dict:
    files = sorted(PAINTS.glob("*.jpg"))
    with_digits = 0
    for p in files:
        img = cv2.imread(str(p))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        digits = _ocr_digits(gray)
        if len(digits) >= 8:
            with_digits += 1

    total = len(files)
    ratio = (with_digits / total) if total > 0 else 0.0
    return {
        "count": total,
        "with_digits": with_digits,
        "ratio_with_digits": ratio,
    }


def _sem_etiqueta_quality() -> dict:
    files = sorted(SEM_ETIQUETA.glob("*.jpg"))
    suspeita_meia = 0
    for p in files:
        img = cv2.imread(str(p))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, _ = gray.shape
        top = gray[: max(1, int(h * 0.45)), :]
        bot = gray[int(h * 0.55) :, :]
        top_white = float((top > 245).mean())
        bot_white = float((bot > 245).mean())
        if bot_white > 0.80 and (bot_white - top_white) > 0.35:
            suspeita_meia += 1

    total = len(files)
    return {
        "count": total,
        "suspeita_meia_imagem": suspeita_meia,
    }


def coletar_metricas() -> dict:
    paints = _paint_quality()
    sem = _sem_etiqueta_quality()
    etiquetas_count = _count_images(ETIQUETAS)

    return {
        "counts": {
            "paints": paints["count"],
            "etiquetas": etiquetas_count,
            "sem_etiqueta": sem["count"],
        },
        "paint": paints,
        "sem_etiqueta": sem,
    }


def criar_baseline(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    metricas = coletar_metricas()
    path.write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Baseline salvo em: {path}")
    print(json.dumps(metricas, indent=2, ensure_ascii=False))


def validar(path: Path) -> int:
    if not path.exists():
        print(f"ERRO: baseline não encontrado em {path}")
        return 2

    baseline = json.loads(path.read_text(encoding="utf-8"))
    atual = coletar_metricas()

    erros = []

    # contagens não devem cair
    for chave in ("paints", "etiquetas", "sem_etiqueta"):
        b = int(baseline["counts"].get(chave, 0))
        a = int(atual["counts"].get(chave, 0))
        if a < b:
            erros.append(f"Contagem de {chave} caiu: baseline={b}, atual={a}")

    # qualidade de paint: não pode perder muito OCR útil
    b_ratio = float(baseline["paint"].get("ratio_with_digits", 0.0))
    a_ratio = float(atual["paint"].get("ratio_with_digits", 0.0))
    if a_ratio + 0.10 < b_ratio:
        erros.append(
            f"Qualidade OCR paint piorou além do limite: baseline={b_ratio:.3f}, atual={a_ratio:.3f}"
        )

    # sem_etiqueta: não aumentar casos de meia imagem
    b_meia = int(baseline["sem_etiqueta"].get("suspeita_meia_imagem", 0))
    a_meia = int(atual["sem_etiqueta"].get("suspeita_meia_imagem", 0))
    if a_meia > b_meia:
        erros.append(f"Suspeitas de meia imagem aumentaram: baseline={b_meia}, atual={a_meia}")

    print("\n=== BASELINE ===")
    print(json.dumps(baseline, indent=2, ensure_ascii=False))
    print("\n=== ATUAL ===")
    print(json.dumps(atual, indent=2, ensure_ascii=False))

    if erros:
        print("\nVALIDAÇÃO: FALHOU")
        for e in erros:
            print(f"- {e}")
        return 1

    print("\nVALIDAÇÃO: OK")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["create-baseline", "validate"], required=True)
    parser.add_argument("--baseline", default=str(BASELINE_PATH))
    args = parser.parse_args()

    baseline_path = Path(args.baseline)

    if args.mode == "create-baseline":
        criar_baseline(baseline_path)
        return

    raise SystemExit(validar(baseline_path))


if __name__ == "__main__":
    main()
