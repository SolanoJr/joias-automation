from pathlib import Path
import cv2
from ultralytics import YOLO

# ===== CONFIG =====
INPUT_DIR = Path("input_raw/fotos_originais")
OUT_ETI = Path("output/etiquetas")
OUT_PNT = Path("output/paints")
OUT_SEM = Path("output/sem_etiqueta")

# coloque o caminho do seu best.pt treinado
MODEL_PATH = Path(r"runs/detect/runs/codigo_v13/weights/best.pt")

# thresholds
CONF_MIN = 0.35

# filtros simples pra evitar caixa absurda
MAX_AREA_RATIO = 0.35   # etiqueta/paint não deveriam ocupar 35% da imagem inteira
MIN_W = 30
MIN_H = 15

# ===================

def clamp_box(x1, y1, x2, y2, w, h):
    x1 = max(0, min(int(x1), w - 1))
    y1 = max(0, min(int(y1), h - 1))
    x2 = max(0, min(int(x2), w - 1))
    y2 = max(0, min(int(y2), h - 1))
    if x2 <= x1: x2 = min(w - 1, x1 + 1)
    if y2 <= y1: y2 = min(h - 1, y1 + 1)
    return x1, y1, x2, y2

def box_ok(x1, y1, x2, y2, img_w, img_h):
    bw = x2 - x1
    bh = y2 - y1
    if bw < MIN_W or bh < MIN_H:
        return False
    area = bw * bh
    if area / (img_w * img_h) > MAX_AREA_RATIO:
        return False
    return True

def main():
    if not MODEL_PATH.exists():
        print(f"ERRO: modelo não encontrado: {MODEL_PATH}")
        return

    OUT_ETI.mkdir(parents=True, exist_ok=True)
    OUT_PNT.mkdir(parents=True, exist_ok=True)
    OUT_SEM.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(MODEL_PATH))

    imgs = sorted([*INPUT_DIR.glob("*.jpg"), *INPUT_DIR.glob("*.jpeg"), *INPUT_DIR.glob("*.png")])
    if not imgs:
        print(f"ERRO: nenhuma imagem em {INPUT_DIR}")
        return

    print("Detectando etiqueta + paint (AABB) e gerando crops + sem_etiqueta...\n")

    for img_path in imgs:
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"Falha ao ler: {img_path.name}")
            continue

        h, w = img.shape[:2]
        base = img_path.stem

        # inferência
        res = model.predict(source=img, conf=CONF_MIN, verbose=False)[0]
        names = res.names  # {0:'etiqueta', 1:'paint'} (esperado)

        # copiar original pra pintar retângulos brancos
        sem = img.copy()

        eti_count = 0
        pnt_count = 0

        if res.boxes is not None and len(res.boxes) > 0:
            for b in res.boxes:
                conf = float(b.conf[0])
                cls = int(b.cls[0])
                label = names.get(cls, str(cls))

                x1, y1, x2, y2 = b.xyxy[0].tolist()
                x1, y1, x2, y2 = clamp_box(x1, y1, x2, y2, w, h)

                if not box_ok(x1, y1, x2, y2, w, h):
                    continue

                crop = img[y1:y2, x1:x2].copy()

                if label == "etiqueta":
                    out = OUT_ETI / f"{base}_etiqueta_{eti_count}.jpg"
                    cv2.imwrite(str(out), crop)
                    eti_count += 1

                elif label == "paint":
                    out = OUT_PNT / f"{base}_paint_{pnt_count}.jpg"
                    cv2.imwrite(str(out), crop)
                    pnt_count += 1

                # remover = retângulo branco sólido (do jeito que você pediu)
                cv2.rectangle(sem, (x1, y1), (x2, y2), (255, 255, 255), thickness=-1)

        # salva sem_etiqueta SEM filtros, SEM clarear imagem toda
        out_sem = OUT_SEM / f"{base}.jpg"
        cv2.imwrite(str(out_sem), sem)

        print(f"{img_path.name} -> etiqueta:{eti_count} paint:{pnt_count} | sem_etiqueta OK")

    print("\nFinalizado.")

if __name__ == "__main__":
    main()