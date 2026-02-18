import csv
import re
import shutil
from pathlib import Path
from barcode_etiqueta import ler_codigos_pasta

ETIQUETAS_DIR = Path("output/etiquetas")
SEGMENTADO_DIR = Path("output/segmentado_rembg")
FINAL_DIR = Path("output/final")
CSV_PATH = Path("output/resultados.csv")

FINAL_DIR.mkdir(parents=True, exist_ok=True)

def original_from_etiqueta(nome_etiqueta: str) -> str | None:
    """
    Ex: 20260107_132828_etiqueta_0.jpg -> 20260107_132828.jpg
    """
    m = re.match(r"^(.*)_etiqueta_\d+\.jpg$", nome_etiqueta, re.IGNORECASE)
    if not m:
        return None
    return m.group(1) + ".jpg"

def main():
    codigos = ler_codigos_pasta(ETIQUETAS_DIR)

    linhas = []
    ok = 0
    faltou_segmentado = 0
    sem_codigo = 0

    for etiqueta_nome, codigo in codigos.items():
        original_nome = original_from_etiqueta(etiqueta_nome)
        if not original_nome:
            continue

        segmentado_path = SEGMENTADO_DIR / original_nome
        if not segmentado_path.exists():
            faltou_segmentado += 1
            linhas.append([original_nome, etiqueta_nome, codigo, "", "segmentado_nao_encontrado"])
            continue

        # destino final pelo código
        destino = FINAL_DIR / f"{codigo}.jpg"

        # se já existir, não sobrescreve. marca duplicado
        if destino.exists():
            linhas.append([original_nome, etiqueta_nome, codigo, destino.name, "codigo_duplicado"])
            continue

        shutil.copy2(segmentado_path, destino)
        ok += 1
        linhas.append([original_nome, etiqueta_nome, codigo, destino.name, "ok"])

    # Também registrar imagens segmentadas que não tiveram código
    # (opcional, mas útil pra saber o “gap”)
    for seg in sorted(SEGMENTADO_DIR.glob("*.jpg")):
        # se não estiver nas linhas já
        if not any(l[0] == seg.name for l in linhas):
            sem_codigo += 1
            linhas.append([seg.name, "", "", "", "sem_codigo"])

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["original", "etiqueta_crop", "codigo", "arquivo_final", "status"])
        w.writerows(linhas)

    print(f"Final OK: {ok}")
    print(f"Faltou segmentado: {faltou_segmentado}")
    print(f"Sem codigo: {sem_codigo}")
    print(f"CSV: {CSV_PATH}")

if __name__ == "__main__":
    main()
