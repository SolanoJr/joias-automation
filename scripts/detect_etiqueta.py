from ultralytics import YOLO
import cv2
from pathlib import Path

# caminhos
MODEL_PATH = Path("models/best.pt")
INPUT_DIR = Path("input_raw/fotos_originais")
OUTPUT_DIR = Path("output/etiquetas")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# carregar modelo
model = YOLO(MODEL_PATH)

# rodar em todas as imagens
results = model.predict(
    source=str(INPUT_DIR),
    imgsz=640,
    conf=0.25,
    save=False
)

for r in results:
    img = cv2.imread(r.path)
    if img is None or r.obb is None:
        continue

    for i, box in enumerate(r.obb.xyxy):
        x1, y1, x2, y2 = map(int, box)
        crop = img[y1:y2, x1:x2]

        out_name = Path(r.path).stem
        out_file = OUTPUT_DIR / f"{out_name}_etiqueta_{i}.jpg"

        cv2.imwrite(str(out_file), crop)

print("Etiquetas recortadas com sucesso.")
