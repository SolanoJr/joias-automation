import argparse
import csv
import re
import shutil
from pathlib import Path

RESULTADOS_CSV = Path("output/resultados.csv")
REVIEW_CSV = Path("output/analysis/semcod_review.csv")
REVIEW_APLICADO_CSV = Path("output/analysis/semcod_review_aplicado.csv")

TRIAGE_CANDIDATOS = [
    Path("output/analysis/semcod_triagem_50_sugestoes.csv"),
    Path("output/analysis/semcod_triagem_50.csv"),
]

ETI_DIRS = [Path("output/1_etiquetas"), Path("output/etiquetas")]
PAINT_DIRS = [Path("output/2_paints"), Path("output/paints")]
SEG_DIRS = [Path("output/5_segmentado_rembg"), Path("output/segmentado_rembg")]
FINAL_DIR = Path("output/final")


def _norm(s: str) -> str:
    return (s or "").strip()


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _triage_map_por_base() -> dict[str, dict]:
    for p in TRIAGE_CANDIDATOS:
        rows = _read_csv(p)
        if rows:
            out: dict[str, dict] = {}
            for r in rows:
                base = _norm(r.get("base", ""))
                if not base:
                    continue
                out[base] = {
                    "tem_sinal_barcode_original": _norm(r.get("tem_sinal_barcode_original", "")),
                    "codigo_sinal": _norm(r.get("codigo_sinal", "")),
                    "categoria_manual": _norm(r.get("categoria_manual", "")),
                }
            return out
    return {}


def _first_existing_file(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists() and p.is_file():
            return p
    return None


def _buscar_arquivo_por_base(base: str, dirs: list[Path], patterns: list[str]) -> Path | None:
    for d in dirs:
        if not d.exists():
            continue
        for pat in patterns:
            encontrados = sorted(d.glob(pat.format(base=base)))
            if encontrados:
                return encontrados[0]
    return None


def _nome_unico(dest_dir: Path, stem: str, ext: str = ".jpg") -> Path:
    candidato = dest_dir / f"{stem}{ext}"
    idx = 2
    while candidato.exists():
        candidato = dest_dir / f"{stem}_{idx}{ext}"
        idx += 1
    return candidato


def _sanitizar_codigo(valor: str) -> str:
    limpo = re.sub(r"[^A-Za-z0-9_-]+", "", _norm(valor))
    return limpo


def _normalizar_status_revisao(valor: str) -> str:
    v = _norm(valor).upper()
    if v in {"APROVADO", "REJEITADO", "PENDENTE"}:
        return v
    return ""


def _extrair_campos_revisao(row: dict) -> tuple[str, str, str]:
    codigo_override = _sanitizar_codigo(row.get("codigo_override", ""))
    status_revisao = _normalizar_status_revisao(row.get("status_revisao", ""))
    observacao = _norm(row.get("observacao", ""))

    if status_revisao and codigo_override and codigo_override not in {"APROVADO", "REJEITADO", "PENDENTE"}:
        return codigo_override, status_revisao, observacao

    codigo_col = _norm(row.get("codigo_override", "")).upper()
    status_col = _normalizar_status_revisao(codigo_col)
    if status_col:
        codigo_alt = _sanitizar_codigo(row.get("categoria_manual", ""))
        observacao_alt = _norm(row.get("status_revisao", "")) or observacao
        if codigo_alt:
            return codigo_alt, status_col, observacao_alt

    return codigo_override, status_revisao, observacao


def gerar_revisao():
    rows = _read_csv(RESULTADOS_CSV)
    if not rows:
        print(f"ERRO: CSV de resultados não encontrado ou vazio: {RESULTADOS_CSV}")
        return

    triage = _triage_map_por_base()
    saida = []

    for r in rows:
        status = _norm(r.get("status", "")).upper()
        if not status.startswith("SEM_CODIGO"):
            continue

        base = _norm(r.get("base", ""))
        arquivo_origem = _norm(r.get("arquivo_origem", ""))

        origem_path = Path(arquivo_origem) if arquivo_origem else None
        seg_path = _first_existing_file([origem_path] if origem_path else [])
        if seg_path is None:
            seg_path = _buscar_arquivo_por_base(
                base,
                SEG_DIRS,
                ["{base}.jpg", "{base}_sr*.jpg", "{base} - *_sr*.jpg", "{base}*.jpg"],
            )

        crop_etiqueta = _buscar_arquivo_por_base(
            base,
            ETI_DIRS,
            [
                "{base}_etiqueta_*.jpg",
                "{base}_semcod_e*.jpg",
                "{base}_e*.jpg",
                "{base} - *_e*.jpg",
                "{base}*.jpg",
            ],
        )
        crop_paint = _buscar_arquivo_por_base(
            base,
            PAINT_DIRS,
            [
                "{base}_paint_*.jpg",
                "{base}_semcod_p*.jpg",
                "{base}_p*.jpg",
                "{base} - *_p*.jpg",
                "{base}*.jpg",
            ],
        )

        tri = triage.get(base, {})

        saida.append(
            {
                "base": base,
                "arquivo_origem": arquivo_origem,
                "crop_etiqueta_path": str(crop_etiqueta).replace("\\", "/") if crop_etiqueta else "",
                "crop_paint_path": str(crop_paint).replace("\\", "/") if crop_paint else "",
                "segmentado_path": str(seg_path).replace("\\", "/") if seg_path else "",
                "tem_sinal_barcode_original": tri.get("tem_sinal_barcode_original", ""),
                "codigo_sinal": tri.get("codigo_sinal", ""),
                "categoria_manual": tri.get("categoria_manual", ""),
                "codigo_override": "",
                "status_revisao": "PENDENTE",
                "observacao": "",
            }
        )

    fieldnames = [
        "base",
        "arquivo_origem",
        "crop_etiqueta_path",
        "crop_paint_path",
        "segmentado_path",
        "tem_sinal_barcode_original",
        "codigo_sinal",
        "categoria_manual",
        "codigo_override",
        "status_revisao",
        "observacao",
    ]
    _write_csv(REVIEW_CSV, fieldnames, saida)
    print(f"Review gerado: {REVIEW_CSV}")
    print(f"Linhas SEM_CODIGO: {len(saida)}")


def aplicar_overrides():
    rows = _read_csv(REVIEW_CSV)
    if not rows:
        print(f"ERRO: CSV de revisão não encontrado ou vazio: {REVIEW_CSV}")
        return

    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    aplicados = []
    total_aprovados = 0
    total_ok = 0
    total_ajuste_coluna = 0

    for r in rows:
        codigo_override, status_revisao, observacao_extra = _extrair_campos_revisao(r)
        if observacao_extra and not _norm(r.get("observacao", "")):
            r["observacao"] = observacao_extra

        if _norm(r.get("codigo_override", "")).upper() in {"APROVADO", "REJEITADO", "PENDENTE"} and codigo_override:
            total_ajuste_coluna += 1

        base = _norm(r.get("base", ""))

        if not codigo_override or status_revisao != "APROVADO":
            continue

        total_aprovados += 1
        seg_path_texto = _norm(r.get("segmentado_path", ""))
        seg_path = Path(seg_path_texto) if seg_path_texto else None

        origem = _first_existing_file([seg_path] if seg_path else [])
        if origem is None:
            origem = _buscar_arquivo_por_base(
                base,
                SEG_DIRS,
                ["{base}.jpg", "{base}_sr*.jpg", "{base} - *_sr*.jpg", "{base}*.jpg"],
            )

        if origem is None:
            aplicados.append(
                {
                    "base": base,
                    "codigo_override": codigo_override,
                    "arquivo_final": "",
                    "status_apply": "ORIGEM_NAO_ENCONTRADA",
                }
            )
            continue

        destino = _nome_unico(FINAL_DIR, codigo_override, ".jpg")
        shutil.copy2(origem, destino)
        total_ok += 1
        aplicados.append(
            {
                "base": base,
                "codigo_override": codigo_override,
                "arquivo_final": str(destino).replace("\\", "/"),
                "status_apply": "APLICADO",
            }
        )

    _write_csv(
        REVIEW_APLICADO_CSV,
        ["base", "codigo_override", "arquivo_final", "status_apply"],
        aplicados,
    )

    print(f"Aplicação registrada: {REVIEW_APLICADO_CSV}")
    print(f"Linhas APROVADO com override: {total_aprovados}")
    print(f"Overrides aplicados: {total_ok}")
    if total_ajuste_coluna:
        print(f"Linhas com ajuste automático de coluna (Excel): {total_ajuste_coluna}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gerar", action="store_true", help="Gera planilha de revisão dos SEM_CODIGO")
    parser.add_argument("--aplicar", action="store_true", help="Aplica overrides aprovados da revisão")
    args = parser.parse_args()

    if args.gerar and args.aplicar:
        print("ERRO: use apenas um modo por vez (--gerar ou --aplicar).")
        return

    if args.gerar:
        gerar_revisao()
        return

    if args.aplicar:
        aplicar_overrides()
        return

    print("Uso: python scripts/revisao_semcod.py --gerar | --aplicar")


if __name__ == "__main__":
    main()
