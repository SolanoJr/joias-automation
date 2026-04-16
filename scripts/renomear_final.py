import re
import csv
import shutil
import time
import os
import sys
from pathlib import Path

# Pastas
SEG_DIR = Path("output/5_segmentado_rembg")
FINAL_DIR = Path("output/6_final")
CSV_PATH = Path("output/resultados.csv")
LIMPAR_FINAL_ANTES = True
PROFILE_CSV_PATH = os.getenv("PROFILE_ETAPA4_CSV", "").strip()
RENOMEAR_FINAL_CANONICAL_ONLY = os.getenv("RENOMEAR_FINAL_CANONICAL_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}

FINAL_DIR.mkdir(parents=True, exist_ok=True)

# Adiciona scripts ao path para importação
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

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

    if " - " in s:
        inicial, _ = s.split(" - ", 1)
        inicial = inicial.strip()
        if inicial:
            return inicial

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


def _is_canonical_stem(stem: str) -> bool:
    s = (stem or "").strip()
    if not s:
        return False
    if " - " in s:
        return False
    if s.endswith("_sr"):
        return False
    return True


def main():
    if not SEG_DIR.exists():
        print(f"ERRO: não existe {SEG_DIR}")
        return

    seg_imgs = sorted(SEG_DIR.glob("*.jpg"))
    if RENOMEAR_FINAL_CANONICAL_ONLY:
        seg_imgs = [p for p in seg_imgs if _is_canonical_stem(p.stem)]
    if not seg_imgs:
        print(f"ERRO: nenhuma imagem em {SEG_DIR}")
        return

    if LIMPAR_FINAL_ANTES and FINAL_DIR.exists():
        shutil.rmtree(FINAL_DIR, ignore_errors=True)
        FINAL_DIR.mkdir(parents=True, exist_ok=True)

    ok = 0
    sem_codigo = 0

    rows = []
    perfil_rows: list[dict] = []

    total_imgs = len(seg_imgs)

    for idx, img in enumerate(seg_imgs, start=1):
        if not img.exists():
            rows.append({
                "arquivo_origem": str(img).replace("\\", "/"),
                "base": stem_base(img.name),
                "codigo": "",
                "fonte": "",
                "arquivo_final": "",
                "status": "ORIGEM_NAO_ENCONTRADA",
            })
            print(f"[renomear_final] arquivo ausente, pulando: {img}")
            continue

        base = stem_base(img.name)  # <<< importante: remove _sem_etiqueta etc
        print(f"[renomear_final] lendo codigo {idx}/{total_imgs} | base={base} | arquivo={img.name}")
        t0 = time.perf_counter()
        codigo, fonte = ler_codigo_unico(
            base,
            indice_global=idx,
            total_global=total_imgs,
            perfil_rows=perfil_rows,
        )
        dt_item = time.perf_counter() - t0

        # fallback: se o nome já é número, usa como código
        if not codigo and is_numeric_stem(base):
            codigo = base
            fonte = "NOME_ARQUIVO"

        dest = None
        status = None

        if codigo:
            codigo_saida = codigo

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
            out_name = nome_unico(FINAL_DIR, f"{base_limpo}_semcod")
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

        print(
            f"[renomear_final] concluido {idx}/{total_imgs} | base={base} | "
            f"codigo={(codigo or 'SEM_CODIGO')} | fonte={(fonte or 'nenhum')} | tempo={dt_item:.1f}s"
        )

        perfil_rows.append(
            {
                "base": base,
                "etapa": "ler_codigo_total",
                "tempo_s": f"{dt_item:.4f}",
                "fonte_codigo": fonte or "",
                "status": "ok" if codigo else "sem_codigo",
                "nivel_ocr": "",
                "modo_adaptive": "",
                "early_stop": "",
            }
        )

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

    if PROFILE_CSV_PATH:
        profile_path = Path(PROFILE_CSV_PATH)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with profile_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "base",
                    "etapa",
                    "tempo_s",
                    "fonte_codigo",
                    "status",
                    "nivel_ocr",
                    "modo_adaptive",
                    "early_stop",
                ],
            )
            w.writeheader()
            w.writerows(perfil_rows)
        print(f"Profile CSV: {profile_path}")


if __name__ == "__main__":
    main()
