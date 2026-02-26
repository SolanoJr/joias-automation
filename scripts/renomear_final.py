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
    Normaliza nomes para bater "foto base".
    Remove:
      - _etiqueta_0, _etiqueta_1, etc (e qualquer sufixo depois)
      - _warp
      - _sem_etiqueta
    Ex:
      20260107_132828_etiqueta_0_warp.jpg -> 20260107_132828
      1200910006_etiqueta_1.jpg -> 1200910006
      1200910006_sem_etiqueta.jpg -> 1200910006
    """
    s = Path(nome_arquivo).stem
    s = re.sub(r"_etiqueta_\d+.*$", "", s)
    s = re.sub(r"_warp$", "", s)
    s = re.sub(r"_sem_etiqueta$", "", s)
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

        # já tem código válido, não perde tempo
        if base in mapa and mapa[base]:
            continue

        codigo = ler_barcode_imagem(p)
        if codigo:
            mapa[base] = codigo
        else:
            mapa.setdefault(base, None)

    return mapa


def nome_unico(dest_dir: Path, nome_base: str) -> str:
    """
    Gera nome único tipo:
      1201410006.jpg
      1201410006_2.jpg
      1201410006_3.jpg
    """
    out_name = f"{nome_base}.jpg"
    i = 2
    while (dest_dir / out_name).exists():
        out_name = f"{nome_base}_{i}.jpg"
        i += 1
    return out_name


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

    for img in seg_imgs:
        base = stem_base(img.name)  # <<< importante: remove _sem_etiqueta etc
        codigo = mapa.get(base)

        # fallback: se o nome já é número, usa como código
        if not codigo and is_numeric_stem(base):
            codigo = base

        dest = None
        status = None

        if codigo:
            # sempre vai pra pasta final (entrega)
            if base == codigo:
                # já está correto, mas ainda copiamos para FINAL_DIR com mesmo nome
                out_name = f"{codigo}.jpg"
                dest = FINAL_DIR / out_name

                # não sobrescreve: se já existe, cria sufixo
                if dest.exists():
                    out_name = nome_unico(FINAL_DIR, codigo)
                    dest = FINAL_DIR / out_name

                shutil.copy2(img, dest)
                status = "JA_CORRETO"
                ok += 1
            else:
                out_name = nome_unico(FINAL_DIR, codigo)
                dest = FINAL_DIR / out_name
                shutil.copy2(img, dest)
                status = "RENOMEADO"
                ok += 1
        else:
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
        w = csv.DictWriter(
            f,
            fieldnames=["arquivo_origem", "base", "codigo", "arquivo_final", "status"]
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Final OK: {ok}")
    print(f"Sem codigo: {sem_codigo}")
    print(f"CSV: {CSV_PATH}")


if __name__ == "__main__":
    main()
