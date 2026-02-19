import re
import csv
import shutil
from pathlib import Path

# Pastas
SEG_DIR = Path("output/segmentado_rembg")
ETI_DIR = Path("output/etiquetas")
FINAL_DIR = Path("output/final")
CSV_PATH = Path("output/resultados.csv")

FINAL_DIR.mkdir(parents=True, exist_ok=True)

# Importa do seu barcode_etiqueta.py
from barcode_etiqueta import ler_barcode_imagem

def stem_base(nome_arquivo: str) -> str:
    """
    Remove sufixos tipo _etiqueta_0, _warp etc e devolve o "id" da foto original.
    Ex:
      20260107_132828_etiqueta_0_warp.jpg -> 20260107_132828
      1200910006_etiqueta_1.jpg -> 1200910006
    """
    s = Path(nome_arquivo).stem
    s = re.sub(r"_etiqueta_\d+.*$", "", s)
    return s

def is_numeric_stem(stem: str) -> bool:
    return stem.isdigit()

def mapear_codigos_por_imagem() -> dict:
    """
    Lê todas as etiquetas e devolve:
      { base_stem_da_foto: codigo_ou_None }
    Se existir mais de uma etiqueta, pega o primeiro código válido.
    """
    mapa = {}
    for p in sorted(ETI_DIR.glob("*.jpg")):
        base = stem_base(p.name)
        if base in mapa and mapa[base]:
            continue  # já temos código
        codigo = ler_barcode_imagem(p)
        if codigo:
            mapa[base] = codigo
        else:
            mapa.setdefault(base, None)
    return mapa

def main():
    if not SEG_DIR.exists():
        print(f"ERRO: não existe {SEG_DIR}")
        return

    seg_imgs = sorted(SEG_DIR.glob("*.jpg"))
    if not seg_imgs:
        print(f"ERRO: nenhuma imagem em {SEG_DIR}")
        return

    mapa = mapear_codigos_por_imagem()

    ok = 0
    sem_codigo = 0

    rows = []
    usados = set()

    for img in seg_imgs:
        base = img.stem  # aqui é o nome da foto (sem _sem_etiqueta)
        codigo = mapa.get(base)

        # fallback: se o nome já é número, usa como código
        if not codigo and is_numeric_stem(base):
            codigo = base

        if codigo:
            if img.stem == codigo:
                status = "JA_CORRETO"
            else:
                # evita sobrescrever se repetir
                out_name = f"{codigo}.jpg"
                i = 2
                while out_name in usados or (FINAL_DIR / out_name).exists():
                    out_name = f"{codigo}_{i}.jpg"
                    i += 1

                usados.add(out_name)
                dest = FINAL_DIR / out_name
                shutil.copy2(img, dest)
                status = "RENOMEADO"
                ok += 1
        else:
            dest = None
            status = "SEM_CODIGO"
            sem_codigo += 1

        rows.append({
            "arquivo_origem": str(img).replace("\\", "/"),
            "base": base,
            "codigo": codigo or "",
            "arquivo_final": str(dest).replace("\\", "/") if dest else "",
            "status": status
        })

    # CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["arquivo_origem", "base", "codigo", "arquivo_final", "status"])
        w.writeheader()
        w.writerows(rows)

    print(f"Final OK: {ok}")
    print(f"Sem codigo: {sem_codigo}")
    print(f"CSV: {CSV_PATH}")

if __name__ == "__main__":
    main()
