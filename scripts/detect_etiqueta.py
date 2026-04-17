from pathlib import Path
import cv2
import pytesseract
import re

# ===== CONFIG =====
INPUT_DIR = Path("input_raw/fotos_originais")
OUT_ETI = Path("output/etiquetas")
OUT_PNT = Path("output/paints")
OUT_SEM = Path("output/sem_etiqueta")
USE_LISTA_REPROCESSAR = False
LISTA_REPROCESSAR = Path("output/analysis/lista_reprocessar_sem_etiqueta.txt")

# coloque o caminho do seu best.pt treinado
MODEL_PATH = Path(r"runs/detect/runs/codigo_v13/weights/best.pt")

# thresholds
CONF_MIN = 0.35
DEVICE = "cpu"

# filtros simples pra evitar caixa absurda
MAX_AREA_RATIO = 0.35   # etiqueta/paint não deveriam ocupar 35% da imagem inteira
MIN_W = 30
MIN_H = 15
PAD_CROP_RATIO = 0.10
PAD_ERASE_PX = 8
ENABLE_PAINT_OCR_FALLBACK = True

# ===================

def clamp_box(x1, y1, x2, y2, w, h):
    x1 = max(0, min(int(x1), w - 1))
    y1 = max(0, min(int(y1), h - 1))
    x2 = max(0, min(int(x2), w - 1))
    y2 = max(0, min(int(y2), h - 1))
    if x2 <= x1: x2 = min(w - 1, x1 + 1)
    if y2 <= y1: y2 = min(h - 1, y1 + 1)
    return x1, y1, x2, y2


def expand_box_ratio(x1, y1, x2, y2, w, h, ratio):
    bw = x2 - x1
    bh = y2 - y1
    pad_x = int(bw * ratio)
    pad_y = int(bh * ratio)
    return clamp_box(x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y, w, h)


def expand_box_px(x1, y1, x2, y2, w, h, pad_px):
    return clamp_box(x1 - pad_px, y1 - pad_px, x2 + pad_px, y2 + pad_px, w, h)

def box_ok(x1, y1, x2, y2, img_w, img_h):
    bw = x2 - x1
    bh = y2 - y1
    if bw < MIN_W or bh < MIN_H:
        return False
    area = bw * bh
    if area / (img_w * img_h) > MAX_AREA_RATIO:
        return False
    return True


def _tem_digitos_na_faixa_inferior(img_bgr) -> bool:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, _ = gray.shape
    roi = gray[int(h * 0.45):, :]
    up = cv2.resize(roi, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    for base in (up, cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]):
        for psm in (11, 6):
            cfg = f"--psm {psm} -c tessedit_char_whitelist=0123456789"
            try:
                txt = pytesseract.image_to_string(base, config=cfg, timeout=1)
            except BaseException:
                continue
            txt = txt.replace(" ", "").replace("\n", "")
            if re.search(r"\d{6,}", txt):
                return True

    return False


def _tem_digitos_no_crop(img_bgr) -> bool:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    for base in (up, cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]):
        cfg = "--psm 11 -c tessedit_char_whitelist=0123456789"
        try:
            txt = pytesseract.image_to_string(base, config=cfg, timeout=1)
        except BaseException:
            continue
        txt = txt.replace(" ", "").replace("\n", "")
        if re.search(r"\d{6,}", txt):
            return True
    return False


def _refinar_crop_paint(crop_bgr):
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if h < 20 or w < 20:
        return crop_bgr

    _, bin_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    perfil = bin_inv.mean(axis=1)
    if perfil.max() <= 0:
        return crop_bgr

    limiar = max(12.0, perfil.max() * 0.30)
    ys = [i for i, v in enumerate(perfil) if v >= limiar]
    if not ys:
        return crop_bgr

    y1 = min(ys)
    y2 = max(ys) + 1
    pad = int((y2 - y1) * 0.35)
    y1 = max(int(h * 0.15), y1 - pad)
    y2 = min(h, y2 + pad)
    if y2 - y1 < int(h * 0.20):
        return crop_bgr

    base_crop = crop_bgr[y1:y2, :]

    # micro-ajuste genérico: reduzir um pouco a sobra branca à esquerda em strips largos
    h0, w0 = base_crop.shape[:2]
    if w0 > 0 and h0 > 0 and (w0 / max(h0, 1)) >= 4.0:
        x_cut = max(2, int(w0 * 0.03))
        base_crop = base_crop[:, x_cut:]

    # segundo refinamento: usa boxes OCR para focar na linha numérica
    gray2 = cv2.cvtColor(base_crop, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray2, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    boxes = []
    for psm in (11, 6):
        cfg = f"--psm {psm} -c tessedit_char_whitelist=0123456789"
        try:
            data = pytesseract.image_to_data(up, config=cfg, output_type=pytesseract.Output.DICT, timeout=1)
        except BaseException:
            continue
        for i, txt in enumerate(data.get("text", [])):
            txt = (txt or "").strip()
            if len(re.findall(r"\d", txt)) < 3:
                continue
            try:
                conf = float(data["conf"][i])
            except Exception:
                conf = -1
            if conf < 25:
                continue
            x = int(data["left"][i] / 2.0)
            y = int(data["top"][i] / 2.0)
            w = int(data["width"][i] / 2.0)
            h = int(data["height"][i] / 2.0)
            if w > 0 and h > 0:
                boxes.append((x, y, x + w, y + h))

    if boxes:
        h2, w2 = gray2.shape
        x1b = max(0, min(b[0] for b in boxes))
        y1b = max(0, min(b[1] for b in boxes))
        x2b = min(w2, max(b[2] for b in boxes))
        y2b = min(h2, max(b[3] for b in boxes))

        bw = max(1, x2b - x1b)
        bh = max(1, y2b - y1b)

        # margem pequena em volta dos dígitos (4 direções), com topo um pouco mais generoso
        pad_left = max(4, int(bw * 0.03))
        pad_right = max(6, int(bw * 0.06))
        pad_top = max(6, int(bh * 0.30))
        pad_bottom = max(6, int(bh * 0.45))

        x1b = max(0, x1b - pad_left)
        y1b = max(0, y1b - pad_top)
        x2b = min(w2, x2b + pad_right)
        y2b = min(h2, y2b + pad_bottom)

        if (y2b - y1b) >= max(18, int(h2 * 0.10)) and (x2b - x1b) >= max(40, int(w2 * 0.06)):
            return base_crop[y1b:y2b, x1b:x2b]

    return base_crop


def _crop_paint_valido(crop_bgr) -> bool:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    dark_ratio = float((gray < 230).mean())
    if dark_ratio < 0.01:
        return False
    return _tem_digitos_no_crop(crop_bgr)


def _crop_paint_valido_flex(crop_bgr) -> bool:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    dark_ratio = float((gray < 230).mean())
    aspect = w / float(max(1, h))
    if dark_ratio < 0.015:
        return False
    if aspect < 2.0:
        return False
    return True


def _fallback_paint_por_ocr(img_bgr):
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=2.2, fy=2.2, interpolation=cv2.INTER_CUBIC)

    candidatos = []
    for base in (up, cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]):
        cfg = "--psm 11 -c tessedit_char_whitelist=0123456789"
        try:
            data = pytesseract.image_to_data(base, config=cfg, output_type=pytesseract.Output.DICT, timeout=2)
        except BaseException:
            continue

        for i, txt in enumerate(data.get("text", [])):
            txt = (txt or "").strip()
            n_digits = len(re.findall(r"\d", txt))
            if n_digits < 4:
                continue

            try:
                conf = float(data["conf"][i])
            except Exception:
                conf = -1
            if conf < 25:
                continue

            x = int(data["left"][i] / 2.2)
            y = int(data["top"][i] / 2.2)
            bw = int(data["width"][i] / 2.2)
            bh = int(data["height"][i] / 2.2)

            if bw <= 0 or bh <= 0:
                continue

            y_ratio = y / float(h)
            w_ratio = bw / float(w)
            h_ratio = bh / float(h)
            cx_ratio = (x + bw / 2.0) / float(w)

            if not (0.25 <= y_ratio <= 0.85):
                continue
            if not (0.12 <= w_ratio <= 0.70):
                continue
            if h_ratio > 0.12:
                continue
            if not (0.10 <= cx_ratio <= 0.90):
                continue

            score = conf * n_digits
            candidatos.append((score, x, y, x + bw, y + bh))

    if not candidatos:
        return None

    _, x1, y1, x2, y2 = sorted(candidatos, key=lambda t: t[0], reverse=True)[0]
    return expand_box_ratio(x1, y1, x2, y2, w, h, 0.20)

def main():
    if not MODEL_PATH.exists():
        print(f"ERRO: modelo não encontrado: {MODEL_PATH}")
        return

    OUT_ETI.mkdir(parents=True, exist_ok=True)
    OUT_PNT.mkdir(parents=True, exist_ok=True)
    OUT_SEM.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO
    model = YOLO(str(MODEL_PATH))

    imgs = sorted([*INPUT_DIR.glob("*.jpg"), *INPUT_DIR.glob("*.jpeg"), *INPUT_DIR.glob("*.png")])
    if not imgs:
        print(f"ERRO: nenhuma imagem em {INPUT_DIR}")
        return

    if USE_LISTA_REPROCESSAR and LISTA_REPROCESSAR.exists():
        brutos = [ln.strip() for ln in LISTA_REPROCESSAR.read_text(encoding="utf-8").splitlines()]
        lista_nomes = {n for n in brutos if n and not n.startswith("#")}
        if lista_nomes:
            imgs = [p for p in imgs if p.name in lista_nomes]
            print(f"Modo seletivo ativo: {len(imgs)} imagem(ns) da lista {LISTA_REPROCESSAR}")

    print("Detectando etiqueta + paint (AABB) e gerando crops + sem_etiqueta...\n")

    for img_path in imgs:
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"Falha ao ler: {img_path.name}")
            continue

        h, w = img.shape[:2]
        base = img_path.stem

        # limpa resultados antigos desta imagem para evitar arquivos "stale"
        for antigo in OUT_ETI.glob(f"{base}_etiqueta_*.jpg"):
            try:
                antigo.unlink()
            except Exception:
                pass
        for antigo in OUT_PNT.glob(f"{base}_paint_*.jpg"):
            try:
                antigo.unlink()
            except Exception:
                pass
        for antigo in OUT_PNT.glob(f"{base}_paint_fb_*.jpg"):
            try:
                antigo.unlink()
            except Exception:
                pass

        # inferência
        res = model.predict(source=img, conf=CONF_MIN, verbose=False, device=DEVICE)[0]
        names = res.names  # {0:'etiqueta', 1:'paint'} (esperado)

        # copiar original pra pintar retângulos brancos
        sem = img.copy()

        eti_count = 0
        pnt_count = 0

        candidatos_por_classe = {}

        if res.boxes is not None and len(res.boxes) > 0:
            for b in res.boxes:
                conf = float(b.conf[0])
                cls = int(b.cls[0])
                label = names.get(cls, str(cls))

                x1, y1, x2, y2 = b.xyxy[0].tolist()
                x1, y1, x2, y2 = clamp_box(x1, y1, x2, y2, w, h)

                if not box_ok(x1, y1, x2, y2, w, h):
                    continue

                atual = candidatos_por_classe.get(label)
                if atual is None or conf > atual["conf"]:
                    candidatos_por_classe[label] = {
                        "conf": conf,
                        "box": (x1, y1, x2, y2),
                    }

        for label, cand in candidatos_por_classe.items():
            x1, y1, x2, y2 = cand["box"]
            conf = cand["conf"]

            cx1, cy1, cx2, cy2 = expand_box_ratio(x1, y1, x2, y2, w, h, PAD_CROP_RATIO)
            crop = img[cy1:cy2, cx1:cx2].copy()

            ex1, ey1, ex2, ey2 = expand_box_px(x1, y1, x2, y2, w, h, PAD_ERASE_PX)

            if label == "etiqueta":
                out = OUT_ETI / f"{base}_etiqueta_{eti_count}.jpg"
                cv2.imwrite(str(out), crop)
                eti_count += 1

            elif label == "paint":
                crop_ref = _refinar_crop_paint(crop)
                if _crop_paint_valido(crop_ref):
                    out = OUT_PNT / f"{base}_paint_{pnt_count}.jpg"
                    cv2.imwrite(str(out), crop_ref)
                    pnt_count += 1
                elif _crop_paint_valido_flex(crop):
                    out = OUT_PNT / f"{base}_paint_{pnt_count}.jpg"
                    cv2.imwrite(str(out), crop)
                    pnt_count += 1
                else:
                    print(f"  - paint ignorado (crop sem dígitos válidos): {base}")
                    continue

            cv2.rectangle(sem, (ex1, ey1), (ex2, ey2), (255, 255, 255), thickness=-1)

            print(
                f"  - {label} conf={conf:.3f} box=({x1},{y1},{x2},{y2}) "
                f"crop_pad=({cx1},{cy1},{cx2},{cy2}) erase_pad=({ex1},{ey1},{ex2},{ey2})"
            )

        if ENABLE_PAINT_OCR_FALLBACK and pnt_count == 0 and _tem_digitos_na_faixa_inferior(sem):
            box_fb = _fallback_paint_por_ocr(img)
            if box_fb is not None:
                fx1, fy1, fx2, fy2 = box_fb
                crop_fb = img[fy1:fy2, fx1:fx2].copy()
                crop_fb = _refinar_crop_paint(crop_fb)
                if _crop_paint_valido(crop_fb):
                    out_fb = OUT_PNT / f"{base}_paint_{pnt_count}.jpg"
                    cv2.imwrite(str(out_fb), crop_fb)
                    pnt_count += 1
                elif _crop_paint_valido_flex(img[fy1:fy2, fx1:fx2].copy()):
                    out_fb = OUT_PNT / f"{base}_paint_{pnt_count}.jpg"
                    cv2.imwrite(str(out_fb), img[fy1:fy2, fx1:fx2].copy())
                    pnt_count += 1
                else:
                    print(f"  - paint_fallback ignorado (sem dígitos válidos): {base}")
                    crop_fb = None

                if crop_fb is not None:
                    ex1, ey1, ex2, ey2 = expand_box_px(fx1, fy1, fx2, fy2, w, h, PAD_ERASE_PX)
                    cv2.rectangle(sem, (ex1, ey1), (ex2, ey2), (255, 255, 255), thickness=-1)
                    print(f"  - paint_fallback_ocr box=({fx1},{fy1},{fx2},{fy2}) erase=({ex1},{ey1},{ex2},{ey2})")

        # salva sem_etiqueta SEM filtros, SEM clarear imagem toda
        out_sem = OUT_SEM / f"{base}.jpg"
        cv2.imwrite(str(out_sem), sem)

        print(f"{img_path.name} -> etiqueta:{eti_count} paint:{pnt_count} | sem_etiqueta OK")

    print("\nFinalizado.")

if __name__ == "__main__":
    main()