import argparse
import csv
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from barcode_etiqueta import _primeiro_codigo_pyzbar

TRIAGE_CSV = Path("output/analysis/semcod_triagem_50_sugestoes.csv")
ETI_DIR = Path("output/1_etiquetas")
ORIG_DIR = Path("input_raw/fotos_originais")
OUT_CSV = Path("output/analysis/diag_estrutural_barcode.csv")
MOSAICO_CSV = Path("output/analysis/mosaico_recuperaveis_13.csv")
MOSAICO_IMG = Path("output/analysis/mosaico_recuperaveis_13.jpg")
OCR_ETIQUETA_CSV = Path("output/analysis/bench_ocr_etiqueta_13.csv")
BATERIA_BARCODE_CSV = Path("output/analysis/bateria_barcode_13.csv")
BARCODE_FAIXA_CSV = Path("output/analysis/barcode_faixa_13.csv")
DIGIT_RE = re.compile(r"\d{8,16}")


def _bases_recuperaveis() -> list[str]:
    if not TRIAGE_CSV.exists():
        return []
    with TRIAGE_CSV.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        (r.get("base") or "").strip()
        for r in rows
        if (r.get("categoria_sugerida") or "").strip() == "barcode_legivel_crop_falhou"
    ]


def _rows_recuperaveis() -> list[dict]:
    if not TRIAGE_CSV.exists():
        return []
    with TRIAGE_CSV.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        r for r in rows
        if (r.get("categoria_sugerida") or "").strip() == "barcode_legivel_crop_falhou"
    ]


def _extrair_numeros(texto: str) -> list[str]:
    if not texto:
        return []
    return DIGIT_RE.findall(texto)


def _rois_ocr(gray: np.ndarray) -> list[tuple[str, np.ndarray]]:
    h, w = gray.shape[:2]
    y0 = int(h * 0.55)
    x1 = int(w * 0.15)
    x2 = int(w * 0.85)

    roi_inferior_central = gray[y0:h, x1:x2] if x2 > x1 else gray[y0:h, :]
    roi_inferior_completa = gray[y0:h, :]
    roi_inteira = gray

    rois: list[tuple[str, np.ndarray]] = []
    if roi_inferior_central.size > 0:
        rois.append(("inferior_central", roi_inferior_central))
    if roi_inferior_completa.size > 0:
        rois.append(("inferior_completa", roi_inferior_completa))
    rois.append(("inteira", roi_inteira))
    return rois


def _preprocess_ocr(roi_gray: np.ndarray) -> list[tuple[str, np.ndarray]]:
    out: list[tuple[str, np.ndarray]] = []
    out.append(("gray", roi_gray))

    up2 = cv2.resize(roi_gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    out.append(("gray_up2", up2))

    _, otsu = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_up2 = cv2.resize(otsu, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    out.append(("gray_otsu_up2", otsu_up2))

    return out


def _rodar_ocr_etiqueta(crop_path: Path, codigo_sinal: str) -> dict:
    inicio = time.perf_counter()
    img = cv2.imread(str(crop_path))
    if img is None:
        return {
            "ocr_candidato": "",
            "comprimento": "0",
            "confianca": "sem_candidato",
            "bate_codigo_sinal": "False",
            "roi_vencedora": "",
            "preprocess_vencedor": "",
            "tempo_s": f"{(time.perf_counter() - inicio):.4f}",
            "status": "crop_invalido",
            "tem_10_digitos": False,
        }

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ocorrencias: dict[str, int] = {}
    primeira_origem: dict[str, tuple[str, str]] = {}

    for roi_nome, roi in _rois_ocr(gray):
        for prep_nome, prep_img in _preprocess_ocr(roi):
            try:
                txt = pytesseract.image_to_string(
                    prep_img,
                    config="--psm 7 -c tessedit_char_whitelist=0123456789",
                    timeout=1,
                )
            except BaseException:
                txt = ""

            for numero in _extrair_numeros(txt):
                ocorrencias[numero] = ocorrencias.get(numero, 0) + 1
                if numero not in primeira_origem:
                    primeira_origem[numero] = (roi_nome, prep_nome)

    if not ocorrencias:
        return {
            "ocr_candidato": "",
            "comprimento": "0",
            "confianca": "sem_candidato",
            "bate_codigo_sinal": "False",
            "roi_vencedora": "",
            "preprocess_vencedor": "",
            "tempo_s": f"{(time.perf_counter() - inicio):.4f}",
            "status": "sem_candidato",
            "tem_10_digitos": False,
        }

    candidato, qtd = sorted(
        ocorrencias.items(),
        key=lambda kv: (len(kv[0]) == 10, kv[1], len(kv[0]), kv[0]),
        reverse=True,
    )[0]

    roi_vencedora, preprocess_vencedor = primeira_origem.get(candidato, ("", ""))
    bate_codigo_sinal = bool(codigo_sinal) and candidato == codigo_sinal
    comprimento = len(candidato)

    if comprimento == 10 and (qtd >= 2 or bate_codigo_sinal):
        confianca = "sucesso_alto"
        status = "ok"
    elif comprimento >= 8:
        confianca = "sucesso_baixo"
        status = "baixo"
    else:
        confianca = "sem_candidato"
        status = "sem_candidato"

    return {
        "ocr_candidato": candidato,
        "comprimento": str(comprimento),
        "confianca": confianca,
        "bate_codigo_sinal": str(bool(bate_codigo_sinal)),
        "roi_vencedora": roi_vencedora,
        "preprocess_vencedor": preprocess_vencedor,
        "tempo_s": f"{(time.perf_counter() - inicio):.4f}",
        "status": status,
        "tem_10_digitos": comprimento == 10,
    }


def rodar_ocr_etiqueta():
    rows = _rows_recuperaveis()
    if not rows:
        print("Nenhum recuperável encontrado no triage para OCR da etiqueta.")
        return

    resultados: list[dict] = []
    processados = 0
    primeiros_tres_10 = 0
    primeiros_tres_alto = 0

    for r in rows:
        base = (r.get("base") or "").strip()
        codigo_sinal = (r.get("codigo_sinal") or "").strip()
        crop = _primeiro_crop(base)

        if crop is None:
            resultados.append(
                {
                    "base": base,
                    "ocr_candidato": "",
                    "comprimento": "0",
                    "confianca": "sem_candidato",
                    "bate_codigo_sinal": "False",
                    "roi_vencedora": "",
                    "preprocess_vencedor": "",
                    "tempo_s": "0.0000",
                    "status": "sem_crop",
                }
            )
            processados += 1
        else:
            saida = _rodar_ocr_etiqueta(crop, codigo_sinal)
            resultados.append(
                {
                    "base": base,
                    "ocr_candidato": saida["ocr_candidato"],
                    "comprimento": saida["comprimento"],
                    "confianca": saida["confianca"],
                    "bate_codigo_sinal": saida["bate_codigo_sinal"],
                    "roi_vencedora": saida["roi_vencedora"],
                    "preprocess_vencedor": saida["preprocess_vencedor"],
                    "tempo_s": saida["tempo_s"],
                    "status": saida["status"],
                }
            )
            processados += 1
            if processados <= 3:
                if saida["tem_10_digitos"]:
                    primeiros_tres_10 += 1
                if saida["confianca"] == "sucesso_alto":
                    primeiros_tres_alto += 1

        if processados == 3:
            if primeiros_tres_10 == 0 or primeiros_tres_alto == 0:
                print("ABORTO_RAPIDO: primeiros 3 sem evidência suficiente (10 dígitos/consistência).")
                break

    OCR_ETIQUETA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OCR_ETIQUETA_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "base",
                "ocr_candidato",
                "comprimento",
                "confianca",
                "bate_codigo_sinal",
                "roi_vencedora",
                "preprocess_vencedor",
                "tempo_s",
                "status",
            ],
        )
        w.writeheader()
        w.writerows(resultados)

    sucesso_alto = sum(1 for r in resultados if r["confianca"] == "sucesso_alto")
    sucesso_baixo = sum(1 for r in resultados if r["confianca"] == "sucesso_baixo")
    total = len(resultados)

    print(f"OCR_ETIQUETA_TOTAL: {total}")
    print(f"sucesso_alto: {sucesso_alto}")
    print(f"sucesso_baixo: {sucesso_baixo}")
    print(f"CSV: {OCR_ETIQUETA_CSV}")


def _listar_crops(base: str) -> list[Path]:
    padroes = [
        f"{base}_etiqueta_*.jpg",
        f"{base}_semcod_e*.jpg",
        f"{base}_e*.jpg",
        f"{base}*.jpg",
    ]
    vistos: list[Path] = []
    for padrao in padroes:
        for arq in sorted(ETI_DIR.glob(padrao)):
            if arq not in vistos:
                vistos.append(arq)
    return vistos


def _primeiro_crop(base: str) -> Path | None:
    crops = _listar_crops(base)
    return crops[0] if crops else None


def _ler_barcode_arquivo(path: Path) -> str | None:
    img = cv2.imread(str(path))
    if img is None:
        return None
    return _primeiro_codigo_pyzbar(img, min_digits=10)


def _dimensoes(path: Path) -> tuple[int, int]:
    img = cv2.imread(str(path))
    if img is None:
        return 0, 0
    h, w = img.shape[:2]
    return w, h


def _is_sucesso_barcode(codigo: str | None) -> bool:
    return bool(codigo) and len(codigo) >= 10


def _clip(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))


def _rotacionar_leve(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _detectar_faixas_barcode(gray: np.ndarray) -> list[tuple[str, np.ndarray, float]]:
    h, w = gray.shape[:2]
    roi = gray[int(h * 0.35):, :]

    gradx = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
    gradx = cv2.convertScaleAbs(gradx)
    _, bw = cv2.threshold(gradx, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 5))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=1)
    bw = cv2.erode(bw, None, iterations=1)
    bw = cv2.dilate(bw, None, iterations=1)

    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidatos: list[tuple[float, str, np.ndarray, float]] = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < int(w * 0.18) or ch < 18:
            continue
        aspect = cw / float(max(ch, 1))
        if aspect < 2.0:
            continue

        cx = _clip(x - int(cw * 0.05), 0, w - 1)
        cy = _clip(y - int(ch * 0.2), 0, roi.shape[0] - 1)
        cxe = _clip(x + cw + int(cw * 0.05), cx + 1, w)
        cye = _clip(y + ch + int(ch * 0.3), cy + 1, roi.shape[0])

        roi_crop = roi[cy:cye, cx:cxe]
        if roi_crop.size == 0:
            continue

        rr = cv2.minAreaRect(c)
        ang = rr[2]
        if ang < -45:
            ang = 90 + ang

        score = float(cw * ch)
        candidatos.append((score, f"faixa_detectada_{len(candidatos)+1}", roi_crop, float(ang)))

    candidatos.sort(key=lambda t: t[0], reverse=True)
    saida = [(nome, crop, ang) for _, nome, crop, ang in candidatos[:2]]

    roi_inferior = gray[int(h * 0.55):, :]
    if roi_inferior.size > 0:
        saida.append(("faixa_inferior_fallback", roi_inferior, 0.0))

    return saida


def rodar_barcode_faixa():
    rows = _rows_recuperaveis()
    if not rows:
        print("Nenhum recuperável encontrado para experimento de faixa barcode.")
        return

    bases = [(_b := (r.get("base") or "").strip()) for r in rows if (r.get("base") or "").strip()]
    csv_rows: list[dict] = []
    recuperadas: set[str] = set()

    for base in bases:
        crop = _primeiro_crop(base)
        if crop is None:
            csv_rows.append(
                {
                    "base": base,
                    "roi_testada": "sem_crop",
                    "transformacao": "nenhuma",
                    "codigo_lido": "",
                    "valido_sim_nao": "NAO",
                    "observacao": "sem crop",
                }
            )
            continue

        img = cv2.imread(str(crop))
        if img is None:
            csv_rows.append(
                {
                    "base": base,
                    "roi_testada": "crop_invalido",
                    "transformacao": "nenhuma",
                    "codigo_lido": "",
                    "valido_sim_nao": "NAO",
                    "observacao": "falha leitura imagem",
                }
            )
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        rois = _detectar_faixas_barcode(gray)
        sucesso_base = False

        for roi_nome, roi_img, ang in rois:
            variantes = [("raw", roi_img)]
            if abs(ang) > 0.8:
                variantes.append(("alinhamento_leve", _rotacionar_leve(roi_img, -ang)))
            else:
                variantes.append(("alinhamento_leve", roi_img))
            variantes.append(
                (
                    "alinhamento_up2",
                    cv2.resize(variantes[-1][1], None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC),
                )
            )

            for trans_nome, trans_img in variantes:
                codigo = _primeiro_codigo_pyzbar(trans_img, min_digits=10)
                valido = _is_sucesso_barcode(codigo)
                if valido:
                    sucesso_base = True
                    recuperadas.add(base)
                csv_rows.append(
                    {
                        "base": base,
                        "roi_testada": roi_nome,
                        "transformacao": trans_nome,
                        "codigo_lido": codigo or "",
                        "valido_sim_nao": "SIM" if valido else "NAO",
                        "observacao": "ok" if valido else "",
                    }
                )
                if valido:
                    break
            if sucesso_base:
                break

    BARCODE_FAIXA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with BARCODE_FAIXA_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["base", "roi_testada", "transformacao", "codigo_lido", "valido_sim_nao", "observacao"],
        )
        w.writeheader()
        w.writerows(csv_rows)

    rec = sorted(recuperadas)
    print(f"CSV_BARCODE_FAIXA: {BARCODE_FAIXA_CSV}")
    print(f"RECUPEROU: {len(rec)}/{len(bases)}")
    print(f"BASES_RECUPERADAS: {rec}")
    print("DIFICULDADE_MANUTENCAO: media")
    if len(rec) < 2:
        print("RECOMENDACAO: encerrar de vez a linha barcode nesses 13 casos")
    elif len(rec) >= 3:
        print("RECOMENDACAO: avaliar fallback leve isolado")
    else:
        print("RECOMENDACAO: limiar intermediario; preferir manter manual assistido")


def _variantes_nivel(img_bgr: np.ndarray, nivel: int) -> list[tuple[str, np.ndarray]]:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    up2 = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thr = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    sharp = cv2.filter2D(gray, -1, np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32))

    if nivel == 0:
        return [("n0_raw", img_bgr)]

    if nivel == 1:
        return [
            ("n1_gray", gray),
            ("n1_resize2x", up2),
            ("n1_threshold", thr),
            ("n1_sharpen", sharp),
        ]

    if nivel == 2:
        _, thr_up2 = cv2.threshold(up2, 127, 255, cv2.THRESH_BINARY)
        return [
            ("n2_gray_resize", up2),
            ("n2_gray_threshold", thr),
            ("n2_resize_threshold", thr_up2),
        ]

    contrast = cv2.convertScaleAbs(gray, alpha=1.2, beta=8)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    return [
        ("n3_rot90", cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)),
        ("n3_rot180", cv2.rotate(gray, cv2.ROTATE_180)),
        ("n3_contraste", contrast),
        ("n3_blur", blur),
    ]


def rodar_bateria_barcode():
    rows = _rows_recuperaveis()
    if not rows:
        print("Nenhum recuperável encontrado para bateria de barcode.")
        return

    bases = [(_norm := (r.get("base") or "").strip()) for r in rows if (r.get("base") or "").strip()]
    csv_rows: list[dict] = []
    cumulativo_recuperados: set[str] = set()

    for nivel in (0, 1, 2, 3):
        recuperados_nivel: set[str] = set()
        for base in bases:
            crop = _primeiro_crop(base)
            if crop is None:
                csv_rows.append(
                    {
                        "base": base,
                        "nivel": nivel,
                        "variante_testada": "sem_crop",
                        "codigo_lido": "",
                        "sucesso_sim_nao": "NAO",
                        "observacao": "sem crop encontrado",
                    }
                )
                continue

            img = cv2.imread(str(crop))
            if img is None:
                csv_rows.append(
                    {
                        "base": base,
                        "nivel": nivel,
                        "variante_testada": "crop_invalido",
                        "codigo_lido": "",
                        "sucesso_sim_nao": "NAO",
                        "observacao": "falha ao ler crop",
                    }
                )
                continue

            for nome, variante in _variantes_nivel(img, nivel):
                codigo = _primeiro_codigo_pyzbar(variante, min_digits=10)
                sucesso = _is_sucesso_barcode(codigo)
                if sucesso:
                    recuperados_nivel.add(base)
                csv_rows.append(
                    {
                        "base": base,
                        "nivel": nivel,
                        "variante_testada": nome,
                        "codigo_lido": codigo or "",
                        "sucesso_sim_nao": "SIM" if sucesso else "NAO",
                        "observacao": "ok" if sucesso else "",
                    }
                )

        novos = sorted(recuperados_nivel - cumulativo_recuperados)
        cumulativo_recuperados.update(recuperados_nivel)
        custo = len(_variantes_nivel(np.zeros((32, 32, 3), dtype=np.uint8), nivel))
        print(f"NIVEL_{nivel}: recuperados={len(recuperados_nivel)}/{len(bases)} | novos={len(novos)} | custo_variantes={custo}")
        if novos:
            print(f"NIVEL_{nivel}_NOVOS: {novos}")

        if len(novos) == 0 and nivel >= 1:
            print(f"PARADA: ganho incremental irrelevante no nível {nivel} (0 novos).")
            break

    BATERIA_BARCODE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with BATERIA_BARCODE_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["base", "nivel", "variante_testada", "codigo_lido", "sucesso_sim_nao", "observacao"],
        )
        w.writeheader()
        w.writerows(csv_rows)

    print(f"CSV_BATERIA: {BATERIA_BARCODE_CSV}")
    print(f"RECUPERADOS_TOTAL: {len(cumulativo_recuperados)}/{len(bases)}")


def _fit_to_box(img: np.ndarray | None, w: int, h: int) -> np.ndarray:
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    if img is None:
        cv2.putText(canvas, "SEM IMAGEM", (20, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
        return canvas

    ih, iw = img.shape[:2]
    if ih <= 0 or iw <= 0:
        cv2.putText(canvas, "IMAGEM INVALIDA", (20, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
        return canvas

    escala = min(w / float(iw), h / float(ih))
    nw = max(1, int(iw * escala))
    nh = max(1, int(ih * escala))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if escala < 1.0 else cv2.INTER_CUBIC)

    x = (w - nw) // 2
    y = (h - nh) // 2
    canvas[y:y + nh, x:x + nw] = resized
    return canvas


def _desenhar_texto_linha(img: np.ndarray, texto: str, y: int, scale: float = 0.55):
    cv2.putText(img, texto, (12, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 20, 20), 1, cv2.LINE_AA)


def gerar_mosaico():
    rows = _rows_recuperaveis()
    if not rows:
        print("Nenhum recuperável encontrado no triage para mosaico.")
        return

    painel_w = 560
    painel_h = 320
    gap = 16
    header_h = 58
    footer_h = 42
    bloco_h = header_h + painel_h + footer_h + gap
    total_w = (painel_w * 2) + (gap * 3)
    total_h = (bloco_h * len(rows)) + gap

    mosaico = np.full((total_h, total_w, 3), 245, dtype=np.uint8)
    csv_rows: list[dict] = []

    y0 = gap
    for r in rows:
        base = (r.get("base") or "").strip()
        codigo_sinal = (r.get("codigo_sinal") or "").strip()
        tem_sinal = (r.get("tem_sinal_barcode_original") or "").strip() or "False"
        categoria_manual = (r.get("categoria_manual") or "").strip()

        original = ORIG_DIR / f"{base}.jpg"
        crop = _primeiro_crop(base)

        img_original = cv2.imread(str(original)) if original.exists() else None
        img_crop = cv2.imread(str(crop)) if crop is not None else None

        painel_original = _fit_to_box(img_original, painel_w, painel_h)
        painel_crop = _fit_to_box(img_crop, painel_w, painel_h)

        x_orig = gap
        x_crop = gap * 2 + painel_w
        y_img = y0 + header_h

        mosaico[y_img:y_img + painel_h, x_orig:x_orig + painel_w] = painel_original
        mosaico[y_img:y_img + painel_h, x_crop:x_crop + painel_w] = painel_crop

        _desenhar_texto_linha(mosaico, f"base: {base}", y0 + 22, 0.60)
        _desenhar_texto_linha(
            mosaico,
            f"codigo_sinal: {codigo_sinal or 'vazio'} | tem_sinal_barcode_original: {tem_sinal}",
            y0 + 44,
            0.52,
        )
        cv2.putText(
            mosaico,
            "ORIGINAL",
            (x_orig + 12, y_img + painel_h + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            mosaico,
            "CROP ETIQUETA",
            (x_crop + 12, y_img + painel_h + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )

        csv_rows.append(
            {
                "base": base,
                "original_path": str(original).replace("\\", "/"),
                "crop_etiqueta_path": str(crop).replace("\\", "/") if crop else "",
                "tem_sinal_barcode_original": tem_sinal,
                "codigo_sinal": codigo_sinal,
                "categoria_manual": categoria_manual,
            }
        )

        y0 += bloco_h

    MOSAICO_IMG.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(MOSAICO_IMG), mosaico)

    with MOSAICO_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "base",
                "original_path",
                "crop_etiqueta_path",
                "tem_sinal_barcode_original",
                "codigo_sinal",
                "categoria_manual",
            ],
        )
        w.writeheader()
        w.writerows(csv_rows)

    print(f"MOSAICO: {MOSAICO_IMG}")
    print(f"MOSAICO_CSV: {MOSAICO_CSV}")
    print(f"TOTAL_BASES_MOSAICO: {len(csv_rows)}")


def _diagnosticar_base(base: str) -> dict:
    original = ORIG_DIR / f"{base}.jpg"
    original_existe = original.exists()
    barcode_original = _ler_barcode_arquivo(original) if original_existe else None

    crops = _listar_crops(base)
    crop_nomes = [c.name for c in crops]
    multiplo_crop = len(crops) > 1

    crop_infos = []
    for crop in crops:
        w, h = _dimensoes(crop)
        codigo = _ler_barcode_arquivo(crop)
        crop_infos.append(
            {
                "nome": crop.name,
                "w": w,
                "h": h,
                "barcode": codigo or "",
            }
        )

    tem_crop_exato = any(
        c.name.startswith(f"{base}_etiqueta_")
        or c.name.startswith(f"{base}_semcod_e")
        or c.name.startswith(f"{base}_e")
        for c in crops
    )
    nomes_batem = all(c.name.startswith(base) for c in crops)
    associacao_ok = bool(crops) and tem_crop_exato and nomes_batem

    return {
        "base": base,
        "original_path": str(original).replace("\\", "/"),
        "original_existe": str(original_existe),
        "barcode_original": barcode_original or "",
        "qtd_crops": str(len(crops)),
        "multiplo_crop": str(multiplo_crop),
        "associacao_ok": str(associacao_ok),
        "crop_nomes": " | ".join(crop_nomes),
        "crop_infos": crop_infos,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bases", nargs="*", help="Lista de bases para diagnosticar")
    parser.add_argument("--mosaico", action="store_true", help="Gera mosaico e CSV dos recuperáveis")
    parser.add_argument("--ocr-etiqueta", action="store_true", help="Benchmark OCR direcionado da etiqueta")
    parser.add_argument("--bateria-barcode", action="store_true", help="Bateria progressiva de barcode por níveis")
    parser.add_argument("--barcode-faixa", action="store_true", help="Experimento de ROI de faixa + alinhamento leve + upscale")
    args = parser.parse_args()

    if args.mosaico:
        gerar_mosaico()
        return

    if args.ocr_etiqueta:
        rodar_ocr_etiqueta()
        return

    if args.bateria_barcode:
        rodar_bateria_barcode()
        return

    if args.barcode_faixa:
        rodar_barcode_faixa()
        return

    bases = args.bases if args.bases else _bases_recuperaveis()
    bases = [b.strip() for b in bases if b and b.strip()]

    if not bases:
        print("Nenhuma base para diagnosticar.")
        return

    resultados = []

    for base in bases:
        r = _diagnosticar_base(base)
        resultados.append(r)

        print(f"BASE: {base}")
        print(f"  original_encontrado: {r['original_existe']}")
        print(f"  caminho_original: {r['original_path']}")
        print(f"  barcode_original: {r['barcode_original'] or 'nenhum'}")
        print(f"  qtd_crops_compativeis: {r['qtd_crops']}")
        print(f"  existe_mais_de_um_crop: {r['multiplo_crop']}")
        print(f"  associacao_base_crop_ok: {r['associacao_ok']}")
        if r["crop_infos"]:
            for ci in r["crop_infos"]:
                print(
                    f"    crop: {ci['nome']} | tamanho: {ci['w']}x{ci['h']} | "
                    f"barcode: {ci['barcode'] or 'nenhum'}"
                )
        else:
            print("    crop: nenhum")
        print("-" * 60)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "base",
                "original_path",
                "original_existe",
                "barcode_original",
                "qtd_crops",
                "multiplo_crop",
                "associacao_ok",
                "crop_nomes",
            ],
        )
        w.writeheader()
        for r in resultados:
            w.writerow(
                {
                    "base": r["base"],
                    "original_path": r["original_path"],
                    "original_existe": r["original_existe"],
                    "barcode_original": r["barcode_original"],
                    "qtd_crops": r["qtd_crops"],
                    "multiplo_crop": r["multiplo_crop"],
                    "associacao_ok": r["associacao_ok"],
                    "crop_nomes": r["crop_nomes"],
                }
            )

    print(f"CSV: {OUT_CSV}")


if __name__ == "__main__":
    main()
