import csv
import os
import re
import shutil
from pathlib import Path

CSV_PATH = Path("output/resultados.csv")
ORIGINAIS_DIR = Path("input_raw/fotos_originais")

PAINTS_DIR = Path("output/2_paints")
ETIQUETAS_DIR = Path("output/1_etiquetas")
SEM_ETIQUETA_DIR = Path("output/3_sem_etiqueta")
QUADRADO_DIR = Path("output/4_quadrado_manual")
SEG_DIR = Path("output/5_segmentado_rembg")
KEEP_CANONICAL_INTERMEDIATES = (
    os.getenv("KEEP_CANONICAL_INTERMEDIATES", "0").strip().lower() in {"1", "true", "yes", "on"}
)


def normalizar_para_nome(valor: str) -> str:
    limpo = re.sub(r"[^A-Za-z0-9_-]+", "_", valor).strip("_")
    return limpo or "imagem"


def _stem_from_path_text(path_text: str) -> str:
    if not path_text:
        return ""
    try:
        return Path(path_text).stem.strip()
    except Exception:
        return ""


def _base_from_intermediario_stem(stem: str) -> str:
    s = (stem or "").strip()
    if not s:
        return ""

    if " - " in s:
        left, _ = s.split(" - ", 1)
        if left.strip():
            return left.strip()

    s = re.sub(r"_etiqueta_\d+.*$", "", s)
    s = re.sub(r"_paint_\d+.*$", "", s)
    s = re.sub(r"_(e|p|se|qm|sr)(?:_\d+)?$", "", s)
    s = re.sub(r"_warp$", "", s)
    s = re.sub(r"_sem_etiqueta$", "", s)
    return s.strip()


def resolver_nome_inicial(row: dict, bases_originais: set[str]) -> str:
    base = (row.get("base") or "").strip()
    if base and base in bases_originais:
        return base

    stem_origem = _stem_from_path_text((row.get("arquivo_origem") or "").strip())
    base_origem = _base_from_intermediario_stem(stem_origem)
    if base_origem and base_origem in bases_originais:
        return base_origem

    return base


def nome_unico(dest_dir: Path, stem: str, ext: str = ".jpg") -> Path:
    candidato = dest_dir / f"{stem}{ext}"
    i = 2
    while candidato.exists():
        candidato = dest_dir / f"{stem}_{i}{ext}"
        i += 1
    return candidato


def _listar_arquivos(folder: Path, patterns: list[str]) -> list[Path]:
    vistos: dict[str, Path] = {}
    for pattern in patterns:
        for p in sorted(folder.glob(pattern)):
            vistos[str(p.resolve())] = p
    return sorted(vistos.values(), key=lambda x: x.name)


def _filtrar_fontes_canonicas(arquivos: list[Path], sufixo_tipo: str) -> list[Path]:
    if sufixo_tipo == "e":
        return [p for p in arquivos if " - " not in p.stem and "_etiqueta_" in p.stem]
    if sufixo_tipo == "p":
        return [p for p in arquivos if " - " not in p.stem and "_paint_" in p.stem]
    if sufixo_tipo in {"se", "qm", "sr"}:
        return [p for p in arquivos if " - " not in p.stem]
    return arquivos


def base_stem(codigo: str, base_inicial: str, sufixo: str) -> str:
    inicial = (base_inicial or "").strip()
    if not inicial:
        inicial = "imagem"
    nome_final = codigo if codigo else f"{normalizar_para_nome(inicial)}_semcod"

    inicial_norm = normalizar_para_nome(inicial)
    final_norm = normalizar_para_nome(nome_final)
    if inicial_norm and final_norm and inicial_norm == final_norm:
        return f"{nome_final}{sufixo}"

    return f"{inicial} - {nome_final}{sufixo}"


def renomear_multiplos(folder: Path, patterns: list[str], stem_destino: str, sufixo_tipo: str = "") -> int:
    if not folder.exists():
        return 0

    arquivos = _listar_arquivos(folder, patterns)
    if KEEP_CANONICAL_INTERMEDIATES:
        arquivos = _filtrar_fontes_canonicas(arquivos, sufixo_tipo)
    if not arquivos:
        return 0

    renomeados = 0
    total = len(arquivos)
    for idx, src in enumerate(arquivos, start=1):
        stem_final = stem_destino if total == 1 else f"{stem_destino}_{idx}"
        ext = src.suffix.lower() or ".jpg"
        if KEEP_CANONICAL_INTERMEDIATES:
            dest = folder / f"{stem_final}{ext}"
        else:
            dest = nome_unico(folder, stem_final, ext)
        if src.resolve() == dest.resolve():
            continue
        if KEEP_CANONICAL_INTERMEDIATES:
            shutil.copy2(src, dest)
        else:
            src.rename(dest)
        renomeados += 1

    return renomeados


def renomear_unico(folder: Path, patterns: list[str], stem_destino: str, sufixo_tipo: str = "") -> Path | None:
    if not folder.exists():
        return None

    candidatos = _listar_arquivos(folder, patterns)
    if KEEP_CANONICAL_INTERMEDIATES:
        candidatos = _filtrar_fontes_canonicas(candidatos, sufixo_tipo)
    if not candidatos:
        return None

    src = candidatos[0]

    ext = src.suffix.lower() or ".jpg"
    if KEEP_CANONICAL_INTERMEDIATES:
        dest = folder / f"{stem_destino}{ext}"
    else:
        dest = nome_unico(folder, stem_destino, ext)
    if src.resolve() == dest.resolve():
        return src

    if KEEP_CANONICAL_INTERMEDIATES:
        shutil.copy2(src, dest)
    else:
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

    total_paints = 0
    total_etiquetas = 0
    total_sem = 0
    total_quad = 0
    total_seg = 0

    novo_origem_por_base = {}

    bases_originais = {
        p.stem
        for ext in ("*.jpg", "*.jpeg", "*.png")
        for p in ORIGINAIS_DIR.glob(ext)
    }

    for row in rows:
        base = (row.get("base") or "").strip()
        nome_inicial = resolver_nome_inicial(row, bases_originais)
        codigo = (row.get("codigo") or "").strip()

        if not base:
            continue

        stem_p = base_stem(codigo, nome_inicial, "_p")
        stem_e = base_stem(codigo, nome_inicial, "_e")
        stem_se = base_stem(codigo, nome_inicial, "_se")
        stem_qm = base_stem(codigo, nome_inicial, "_qm")
        stem_sr = base_stem(codigo, nome_inicial, "_sr")

        total_paints += renomear_multiplos(
            PAINTS_DIR,
            [
                f"{base}_paint_*.jpg",
                f"{base} - *_p*.jpg",
                f"{base}_p*.jpg",
            ],
            stem_p,
            sufixo_tipo="p",
        )
        total_etiquetas += renomear_multiplos(
            ETIQUETAS_DIR,
            [
                f"{base}_etiqueta_*.jpg",
                f"{base} - *_e*.jpg",
                f"{base}_e*.jpg",
            ],
            stem_e,
            sufixo_tipo="e",
        )

        dest_sem = renomear_unico(
            SEM_ETIQUETA_DIR,
            [
                f"{base}.jpg",
                f"{base} - *_se*.jpg",
                f"{base}_se*.jpg",
            ],
            stem_se,
            sufixo_tipo="se",
        )
        if dest_sem is not None:
            total_sem += 1

        dest_quad = renomear_unico(
            QUADRADO_DIR,
            [
                f"{base}.jpg",
                f"{base} - *_qm*.jpg",
                f"{base}_qm*.jpg",
            ],
            stem_qm,
            sufixo_tipo="qm",
        )
        if dest_quad is not None:
            total_quad += 1

        dest_seg = renomear_unico(
            SEG_DIR,
            [
                f"{base}.jpg",
                f"{base} - *_sr*.jpg",
                f"{base}_sr*.jpg",
            ],
            stem_sr,
            sufixo_tipo="sr",
        )
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
