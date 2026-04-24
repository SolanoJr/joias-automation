import re
import csv
import shutil
from pathlib import Path

# Pastas
SEG_DIR = Path("output/5_segmentado_rembg")
FINAL_DIR = Path("output/6_final")
CSV_PATH = Path("output/resultados.csv")
LIMPAR_FINAL_ANTES = True

FINAL_DIR.mkdir(parents=True, exist_ok=True)

# Importa leitor unificado de código
from ler_codigo import ler_codigo_unico


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


def normalizar_base_para_nome(base: str) -> str:
    limpo = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")
    return limpo or "imagem"


def sufixo_por_fonte(fonte: str | None) -> str:
    fonte = (fonte or "").lower()
    if "paint" in fonte:
        return "_p"
    if "etiqueta" in fonte or "barcode" in fonte:
        return "_e"
    if "sem_etiqueta" in fonte or "ocr_sem_etiqueta" in fonte:
        return "_se"
    return ""


def main():
    if not SEG_DIR.exists():
        print(f"ERRO: não existe {SEG_DIR}")
        return

    seg_imgs = sorted(SEG_DIR.glob("*.jpg"))
    if not seg_imgs:
        print(f"ERRO: nenhuma imagem em {SEG_DIR}")
        return

    if LIMPAR_FINAL_ANTES and FINAL_DIR.exists():
        shutil.rmtree(FINAL_DIR, ignore_errors=True)
        FINAL_DIR.mkdir(parents=True, exist_ok=True)

    ok = 0
    sem_codigo = 0

    rows = []

    for img in seg_imgs:
        base = stem_base(img.name)  # <<< importante: remove _sem_etiqueta etc  
        codigo, fonte = ler_codigo_unico(base)

        # fallback: se o nome já é número, usa como código
        if not codigo and is_numeric_stem(base):
            codigo = base
            fonte = "NOME_ARQUIVO"

        dest = None
        status = None

        if codigo:
            sufixo = sufixo_por_fonte(fonte)
            codigo_saida = f"{codigo}{sufixo}" if sufixo else codigo

            # sempre vai pra pasta final (entrega)
            if base == codigo_saida:
                # já está correto, mas ainda copiamos para FINAL_DIR com mesmo nome
                out_name = f"{codigo_saida}.jpg"
                dest = FINAL_DIR / out_name

                # não sobrescreve: se já existe, cria sufixo
                if dest.exists():
                    out_name = nome_unico(FINAL_DIR, codigo_saida)
                    dest = FINAL_DIR / out_name

                shutil.copy2(img, dest)
                status = "JA_CORRETO"
                ok += 1
            else:
                out_name = nome_unico(FINAL_DIR, codigo_saida)
                dest = FINAL_DIR / out_name
                shutil.copy2(img, dest)
                status = "RENOMEADO"
                ok += 1
        else:
            base_limpo = normalizar_base_para_nome(base)
            out_name = nome_unico(FINAL_DIR, f"SEMCOD_{base_limpo}")
            dest = FINAL_DIR / out_name
            shutil.copy2(img, dest)
            status = "SEM_CODIGO_COPIADO"
            sem_codigo += 1

        rows.append({
            "arquivo_origem": str(img).replace("\\", "/"),
            "base": base,
            "codigo": codigo or "",
            "fonte": fonte or "",
            "arquivo_final": str(dest).replace("\\", "/") if dest else "",      
            "status": status
        })

    # CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["arquivo_origem", "base", "codigo", "fonte", "arquivo_final", "status"]
        )
        w.writeheader()
        w.writerows(rows)

    esperados = {
        Path(r["arquivo_final"]).name
        for r in rows
        if r.get("arquivo_final")
    }
    for p in FINAL_DIR.glob("*.jpg"):
        if p.name not in esperados:
            try:
                p.unlink()
            except Exception:
                pass

    print(f"Final OK: {ok}")
    print(f"Sem codigo: {sem_codigo}")
    print(f"CSV: {CSV_PATH}")


if __name__ == "__main__":
    main()
