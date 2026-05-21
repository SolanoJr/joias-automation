"""
rodar_lab.py — Entry point do Laboratório de Segmentação.

Uso:
    python rodar_lab.py                    # 5-10 imagens aleatórias
    python rodar_lab.py --seed 42          # seed fixa para reprodutibilidade
    python rodar_lab.py --n-min 3 --n-max 5  # 3-5 imagens
    python rodar_lab.py --todas            # todas as imagens (sem amostragem)
    python rodar_lab.py --input /caminho   # pasta de entrada personalizada

Saída: temp/Laboratorio/resultados/
  - lab_*.jpg          — resultado final (1024x1024)
  - diag_*.jpg         — diagnóstico side-by-side
  - etapas_*.jpg       — comparativo antes/depois do refinamento
  - metricas_lab.json  — métricas de cada imagem
  - relatorio_lab.html — relatório visual para auditoria humana
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Garantir que o diretório do lab está no path
_lab_dir = Path(__file__).resolve().parent
if str(_lab_dir) not in sys.path:
    sys.path.insert(0, str(_lab_dir))

from lab_config import OUTPUT_DIR, ENABLE_DIAGNOSTICS, SINGLE_MODEL, ENABLE_ENSEMBLE
from lab_amostragem import selecionar_amostra, listar_imagens
from lab_segmentacao import processar_imagem
from lab_auditoria import (
    gerar_imagem_diagnostico,
    gerar_imagem_etapas,
    salvar_metricas,
    gerar_relatorio_html,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LAB] %(levelname)s - %(message)s",
)
logger = logging.getLogger("lab")


def main():
    parser = argparse.ArgumentParser(description="Laboratório de Segmentação de Joias")
    parser.add_argument("--input", type=str, default=None, help="Pasta de entrada (override)")
    parser.add_argument("--output", type=str, default=None, help="Pasta de saída (override)")
    parser.add_argument("--seed", type=int, default=None, help="Seed para amostragem reprodutível")
    parser.add_argument("--n-min", type=int, default=None, help="Mínimo de imagens na amostra")
    parser.add_argument("--n-max", type=int, default=None, help="Máximo de imagens na amostra")
    parser.add_argument("--todas", action="store_true", help="Processar todas as imagens (sem amostragem)")
    args = parser.parse_args()

    input_dir = Path(args.input) if args.input else None
    output_dir = Path(args.output) if args.output else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Selecionar imagens ---
    if args.todas:
        imgs = listar_imagens(input_dir)
        logger.info(f"Modo --todas: processando {len(imgs)} imagens")
    else:
        imgs = selecionar_amostra(
            pasta=input_dir,
            n_min=args.n_min,
            n_max=args.n_max,
            seed=args.seed,
        )

    if not imgs:
        logger.error("Nenhuma imagem encontrada!")
        return

    logger.info(f"Lab de Segmentação — {len(imgs)} imagens")

    # --- Criar sessão rembg ---
    session = None
    if not ENABLE_ENSEMBLE:
        from rembg import new_session
        session = new_session(SINGLE_MODEL)

    # --- Processar ---
    t_inicio = time.time()
    all_results: list[dict] = []
    all_metrics: list[dict] = []

    for idx, p in enumerate(imgs, start=1):
        logger.info(f"[{idx}/{len(imgs)}] {p.name}")
        result = processar_imagem(p, session, output_dir)
        all_results.append(result)
        all_metrics.append(result["metricas"])

        # Salvar resultado
        if result["resultado"] is not None:
            out_path = output_dir / f"lab_{p.name}"
            result["resultado"].save(out_path, quality=95)
            logger.info(f"  Salvo: {out_path}")

            # Gerar diagnósticos
            if ENABLE_DIAGNOSTICS and result.get("original") is not None:
                if result.get("mask_refined") is not None:
                    diag = gerar_imagem_diagnostico(
                        result["original"],
                        result["mask_refined"],
                        result["resultado"],
                        p.name,
                    )
                    diag_path = output_dir / f"diag_{p.stem}.jpg"
                    diag.save(diag_path, quality=90)

                # Comparativo antes/depois do refinamento
                if result.get("mask_rembg") is not None and result.get("mask_refined") is not None:
                    etapas = gerar_imagem_etapas(
                        result["original"],
                        result["mask_rembg"],
                        result["mask_refined"],
                        p.name,
                    )
                    etapas_path = output_dir / f"etapas_{p.stem}.jpg"
                    etapas.save(etapas_path, quality=90)
        else:
            logger.warning(f"  Falhou: {p.name}")

    # --- Salvar métricas e relatório ---
    salvar_metricas(all_metrics, output_dir)

    if ENABLE_DIAGNOSTICS:
        gerar_relatorio_html(all_results, output_dir)

    # --- Resumo ---
    elapsed = time.time() - t_inicio
    ok = sum(1 for r in all_results if r["resultado"] is not None)
    logger.info(f"Lab concluído: {ok}/{len(imgs)} OK em {elapsed:.1f}s")
    logger.info(f"Resultados em: {output_dir}")
    logger.info(f"Abra {output_dir / 'relatorio_lab.html'} para auditoria visual")


if __name__ == "__main__":
    main()
