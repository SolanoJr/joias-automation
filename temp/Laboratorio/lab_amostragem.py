"""
lab_amostragem.py — Seleção inteligente de imagens para teste.

Seleciona aleatoriamente entre AMOSTRA_MIN e AMOSTRA_MAX imagens da pasta
de entrada, priorizando diversidade de tamanho e proporção.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

from PIL import Image

from lab_config import (
    INPUT_DIR,
    AMOSTRA_MIN,
    AMOSTRA_MAX,
    AMOSTRA_SEED,
)

logger = logging.getLogger("lab")

EXTENSOES = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff")


def listar_imagens(pasta: Path | None = None) -> list[Path]:
    pasta = pasta or INPUT_DIR
    imgs: list[Path] = []
    for ext in EXTENSOES:
        imgs.extend(pasta.glob(ext))
    return sorted(imgs)


def _tamanho_bucket(img_path: Path) -> str:
    """Classifica imagem em bucket de tamanho para diversidade."""
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            area = w * h
            if area < 500_000:
                return "pequena"
            elif area < 2_000_000:
                return "media"
            else:
                return "grande"
    except Exception:
        return "desconhecido"


def selecionar_amostra(
    pasta: Path | None = None,
    n_min: int | None = None,
    n_max: int | None = None,
    seed: int | str | None = None,
) -> list[Path]:
    """
    Seleciona entre n_min e n_max imagens aleatórias com diversidade de tamanho.

    Retorna lista de Paths selecionados.
    """
    n_min = n_min or AMOSTRA_MIN
    n_max = n_max or AMOSTRA_MAX

    seed_val = seed if seed is not None else (int(AMOSTRA_SEED) if AMOSTRA_SEED.strip() else None)
    rng = random.Random(seed_val)

    todas = listar_imagens(pasta)
    if not todas:
        logger.warning(f"Nenhuma imagem encontrada em {pasta or INPUT_DIR}")
        return []

    n = rng.randint(n_min, min(n_max, len(todas)))
    n = min(n, len(todas))

    if len(todas) <= n:
        logger.info(f"Amostragem: usando todas as {len(todas)} imagens (menos que {n_min})")
        return todas

    # Classificar por bucket de tamanho para garantir diversidade
    buckets: dict[str, list[Path]] = {}
    for img in todas:
        bucket = _tamanho_bucket(img)
        buckets.setdefault(bucket, []).append(img)

    selecionadas: list[Path] = []
    buckets_disponiveis = list(buckets.keys())

    # Selecionar pelo menos 1 de cada bucket (se possível)
    for bucket_name in buckets_disponiveis:
        bucket_imgs = buckets[bucket_name]
        if bucket_imgs and len(selecionadas) < n:
            escolha = rng.choice(bucket_imgs)
            selecionadas.append(escolha)
            bucket_imgs.remove(escolha)

    # Preencher o restante aleatoriamente
    restantes = [img for imgs in buckets.values() for img in imgs if img not in selecionadas]
    rng.shuffle(restantes)

    while len(selecionadas) < n and restantes:
        selecionadas.append(restantes.pop())

    selecionadas.sort(key=lambda p: p.name)
    logger.info(
        f"Amostragem: {len(selecionadas)}/{len(todas)} imagens selecionadas "
        f"(seed={'aleatório' if seed_val is None else seed_val})"
    )
    return selecionadas
