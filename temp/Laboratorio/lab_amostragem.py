"""
lab_amostragem.py — Seleção inteligente de imagens para teste.

Seleciona aleatoriamente entre AMOSTRA_MIN e AMOSTRA_MAX imagens da pasta
de entrada, priorizando diversidade de tamanho e proporção.

Inclui sempre as imagens do golden_set (casos críticos).
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

from PIL import Image

from lab_config import INPUT_DIR, AMOSTRA_MIN, AMOSTRA_MAX, AMOSTRA_SEED, GOLDEN_SET_DIR

logger = logging.getLogger("lab")

EXTENSOES = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff")


def listar_imagens(pasta: Path | None = None) -> list[Path]:
    pasta = pasta or INPUT_DIR
    imgs: list[Path] = []
    for ext in EXTENSOES:
        imgs.extend(pasta.glob(ext))
    return sorted(imgs)


def listar_golden_set() -> list[Path]:
    """Lista todas as imagens do golden_set (casos críticos)."""
    if not GOLDEN_SET_DIR.exists():
        logger.info(f"Golden set não encontrado em {GOLDEN_SET_DIR}")
        return []
    
    imgs: list[Path] = []
    for ext in EXTENSOES:
        imgs.extend(GOLDEN_SET_DIR.glob(ext))
    
    if imgs:
        logger.info(f"Golden set: {len(imgs)} imagens críticas encontradas")
    
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
    
    PRIORIDADE: SEMPRE inclui TODAS as imagens do golden_set (casos críticos).
    Só adiciona imagens aleatórias se houver espaço após o golden set.
    
    Retorna lista de Paths selecionados.
    """
    n_min = n_min or AMOSTRA_MIN
    n_max = n_max or AMOSTRA_MAX

    seed_val = seed if seed is not None else (int(AMOSTRA_SEED) if AMOSTRA_SEED.strip() else None)
    rng = random.Random(seed_val)

    # Primeiro, obter imagens do golden set (casos críticos) - TODAS
    golden_imgs = listar_golden_set()
    
    # Depois, obter imagens da pasta principal
    todas = listar_imagens(pasta)
    
    # Remover duplicatas (caso golden set esteja dentro da pasta principal)
    todas = [img for img in todas if img not in golden_imgs]
    
    if not todas and not golden_imgs:
        logger.warning(f"Nenhuma imagem encontrada em {pasta or INPUT_DIR} nem no golden set")
        return []

    # Calcular espaço disponível para imagens aleatórias após o golden set
    espaco_disponivel = n_max - len(golden_imgs)
    
    # Se o golden set já excede n_max, usar apenas golden set
    if len(golden_imgs) >= n_max:
        logger.info(f"Amostragem: {len(golden_imgs)} do golden set (excede n_max={n_max}, usando apenas golden set)")
        resultado = golden_imgs.copy()
        resultado.sort(key=lambda p: p.name)
        logger.info(
            f"Amostragem final: {len(resultado)} imagens selecionadas "
            f"(seed={'aleatório' if seed_val is None else seed_val})"
        )
        return resultado
    
    # Calcular quantas imagens aleatórias selecionar (respeitando n_min e espaço disponível)
    n_aleatorio_min = max(0, n_min - len(golden_imgs))
    n_aleatorio_max = min(espaco_disponivel, len(todas))
    
    if todas and n_aleatorio_max > 0:
        n_aleatorio = rng.randint(n_aleatorio_min, n_aleatorio_max)
    else:
        n_aleatorio = 0
    
    # Ajustar se já temos imagens do golden set
    if golden_imgs:
        n_total = len(golden_imgs) + n_aleatorio
        logger.info(f"Amostragem: {len(golden_imgs)} do golden set (PRIORIDADE) + {n_aleatorio} aleatórias = {n_total} total")
    else:
        n_total = n_aleatorio
        logger.info(f"Amostragem: {n_total} imagens aleatórias (nenhuma do golden set)")

    # Selecionar imagens aleatórias da pasta principal
    selecionadas: list[Path] = []
    
    if todas and n_aleatorio > 0:
        if len(todas) <= n_aleatorio:
            logger.info(f"Amostragem: usando todas as {len(todas)} imagens (menos que {n_aleatorio})")
            selecionadas = todas.copy()
        else:
            # Classificar por bucket de tamanho para garantir diversidade
            buckets: dict[str, list[Path]] = {}
            for img in todas:
                bucket = _tamanho_bucket(img)
                buckets.setdefault(bucket, []).append(img)

            selecionadas_aleatorias: list[Path] = []
            buckets_disponiveis = list(buckets.keys())

            # Selecionar pelo menos 1 de cada bucket (se possível)
            for bucket_name in buckets_disponiveis:
                bucket_imgs = buckets[bucket_name]
                if bucket_imgs and len(selecionadas_aleatorias) < n_aleatorio:
                    escolha = rng.choice(bucket_imgs)
                    selecionadas_aleatorias.append(escolha)
                    bucket_imgs.remove(escolha)

            # Preencher o restante aleatoriamente
            restantes = [img for imgs in buckets.values() for img in imgs if img not in selecionadas_aleatorias]
            rng.shuffle(restantes)

            while len(selecionadas_aleatorias) < n_aleatorio and restantes:
                selecionadas_aleatorias.append(restantes.pop())

            selecionadas = selecionadas_aleatorias

    # Adicionar golden set ao início da lista (prioridade para análise)
    resultado = golden_imgs + selecionadas
    
    resultado.sort(key=lambda p: p.name)
    logger.info(
        f"Amostragem final: {len(resultado)} imagens selecionadas "
        f"(seed={'aleatório' if seed_val is None else seed_val})"
    )
    return resultado
