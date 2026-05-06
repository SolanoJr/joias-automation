import csv
import re
import os
from pathlib import Path

CSV_PATH = Path("output/resultados.csv")

# No modo incremental, preserva arquivos intermediários já renomeados canonicamente
KEEP_CANONICAL_INTERMEDIATES = os.getenv("KEEP_CANONICAL_INTERMEDIATES", "0").strip().lower() in {"1", "true", "yes", "on"}

PAINTS_DIR = Path("output/2_paints")
ETIQUETAS_DIR = Path("output/1_etiquetas")
SEM_ETIQUETA_DIR = Path("output/3_sem_etiqueta")
QUADRADO_DIR = Path("output/4_quadrado_manual")
SEG_DIR = Path("output/5_segmentado_rembg")


def normalizar_para_nome(valor: str) -> str:
    limpo = re.sub(r"[^A-Za-z0-9_-]+", "_", valor).strip("_")
    return limpo or "imagem"


def nome_unico(dest_dir: Path, stem: str, ext: str = ".jpg") -> Path:
    candidato = dest_dir / f"{stem}{ext}"
    i = 2
    while candidato.exists():
        candidato = dest_dir / f"{stem}_{i}{ext}"
        i += 1
    return candidato


def base_stem(codigo: str, base: str, sufixo: str) -> str:
    if codigo:
        return f"{codigo}{sufixo}"
    return f"{normalizar_para_nome(base)}_semcod{sufixo}"


def renomear_multiplos(folder: Path, pattern: str, stem_destino: str) -> int:   
    if not folder.exists():
        return 0

    arquivos = sorted(folder.glob(pattern))
    if not arquivos:
        return 0

    renomeados = 0
    total = len(arquivos)
    for idx, src in enumerate(arquivos, start=1):
        stem_final = stem_destino if total == 1 else f"{stem_destino}_{idx}"    
        dest = nome_unico(folder, stem_final, src.suffix.lower() or ".jpg")     
        if src.resolve() == dest.resolve():
            continue
        src.rename(dest)
        renomeados += 1

    return renomeados


def renomear_unico(folder: Path, nome_atual: str, stem_destino: str) -> Path | None:
    if not folder.exists():
        return None

    src = folder / nome_atual
    if not src.exists():
        return None

    dest = nome_unico(folder, stem_destino, src.suffix.lower() or ".jpg")       
    if src.resolve() == dest.resolve():
        return src

    src.rename(dest)
    return dest


def main():
    if not CSV_PATH.exists():
        print(f"ERRO: CSV não encontrado em {CSV_PATH}")
        return

    with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV vazio, nada para renomear.")
        return

    if KEEP_CANONICAL_INTERMEDIATES:
        print("Modo KEEP_CANONICAL_INTERMEDIATES: renomeação de intermediários pulada.")
        return

    total_paints = 0
    total_etiquetas = 0
    total_sem = 0
    total_quad = 0
    total_seg = 0

    novo_origem_por_base = {}

    for row in rows:
        base = (row.get("base") or "").strip()
        codigo = (row.get("codigo") or "").strip()

        if not base:
            continue

        stem_p = base_stem(codigo, base, "_p")
        stem_e = base_stem(codigo, base, "_e")
        stem_se = base_stem(codigo, base, "_se")
        stem_qm = base_stem(codigo, base, "_qm")
        stem_sr = base_stem(codigo, base, "_sr")

        total_paints += renomear_multiplos(PAINTS_DIR, f"{base}_paint_*.jpg", stem_p)
        total_etiquetas += renomear_multiplos(ETIQUETAS_DIR, f"{base}_etiqueta_*.jpg", stem_e)

        dest_sem = renomear_unico(SEM_ETIQUETA_DIR, f"{base}.jpg", stem_se)
        if dest_sem is not None:
            total_sem += 1

        dest_quad = renomear_unico(QUADRADO_DIR, f"{base}.jpg", stem_qm)        
        if dest_quad is not None:
            total_quad += 1

        dest_seg = renomear_unico(SEG_DIR, f"{base}.jpg", stem_sr)
        if dest_seg is not None:
            total_seg += 1
            novo_origem_por_base[base] = str(dest_seg).replace("\\", "/")       

    for row in rows:
        base = (row.get("base") or "").strip()
        novo = novo_origem_por_base.get(base)
        if novo:
            row["arquivo_origem"] = novo

    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["arquivo_origem", "base", "codigo", "fonte", "arquivo_final", "status"],
        )
        w.writeheader()
        w.writerows(rows)

    print(
        f"Intermediários renomeados: paints={total_paints}, etiquetas={total_etiquetas}, "
        f"sem_etiqueta={total_sem}, quadrado_manual={total_quad}, segmentado={total_seg}"
    )
    print(f"CSV atualizado: {CSV_PATH}")


if __name__ == "__main__":
    main()
