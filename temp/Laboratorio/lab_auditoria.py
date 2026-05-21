"""
lab_auditoria.py — Geração de outputs visuais para auditoria humana.

Gera:
  - Imagens diagnóstico side-by-side (original | máscara overlay | resultado)
  - Relatório HTML com tabela de métricas e preview
  - Métricas JSON
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from lab_config import (
    CANVAS_SIZE,
    TARGET_RATIO,
    ENABLE_GRABCUT,
    ENABLE_COLOR_REFINE,
    ENABLE_ENSEMBLE,
    ENABLE_PRE_DETECT,
    ENABLE_CONVEX_HULL,
    ENABLE_SPECULAR_FILTER,
    ENABLE_EDGE_MASK,
    ENABLE_DIAGNOSTICS,
)

logger = logging.getLogger("lab")


def _pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
    rgb = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def gerar_imagem_diagnostico(
    original: Image.Image,
    mask: np.ndarray,
    resultado: Image.Image,
    nome: str,
) -> Image.Image:
    """Gera imagem 3-em-1: original | máscara overlay colorida | resultado final."""
    size = 512

    orig_thumb = original.copy().convert("RGB")
    orig_thumb.thumbnail((size, size), Image.Resampling.LANCZOS)

    # Overlay colorido: máscara em verde semi-transparente sobre original
    orig_bgr = _pil_to_bgr(original)
    orig_resized = cv2.resize(orig_bgr, (mask.shape[1], mask.shape[0]))

    # Criar overlay colorido (verde para foreground, vermelho para removido)
    overlay = orig_resized.copy()
    mask_bool = mask > 0
    # Verde semi-transparente onde é foreground
    overlay[mask_bool] = (
        overlay[mask_bool] * 0.5 + np.array([0, 180, 0], dtype=np.float64) * 0.5
    ).astype(np.uint8)
    # Vermelho suave onde é background
    overlay[~mask_bool] = (
        overlay[~mask_bool] * 0.7 + np.array([0, 0, 120], dtype=np.float64) * 0.3
    ).astype(np.uint8)

    overlay_pil = Image.fromarray(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
    overlay_pil.thumbnail((size, size), Image.Resampling.LANCZOS)

    res_thumb = resultado.copy()
    res_thumb.thumbnail((size, size), Image.Resampling.LANCZOS)

    panel_w = size * 3 + 20
    panel_h = size + 40
    panel = Image.new("RGB", (panel_w, panel_h), (40, 40, 40))

    y_off = 30
    panel.paste(orig_thumb, (5, y_off))
    panel.paste(overlay_pil, (size + 10, y_off))
    panel.paste(res_thumb, (size * 2 + 15, y_off))

    draw = ImageDraw.Draw(panel)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    labels = ["Original", "Máscara (verde=joia)", "Resultado"]
    for i, label in enumerate(labels):
        draw.text((5 + i * (size + 5), 8), label, fill=(255, 255, 255), font=font)
    draw.text((5, panel_h - 18), nome, fill=(180, 180, 180), font=font)

    return panel


def gerar_imagem_etapas(
    original: Image.Image,
    mask_rembg: np.ndarray,
    mask_refinada: np.ndarray,
    nome: str,
) -> Image.Image:
    """Gera comparativo de máscara antes vs depois do refinamento."""
    size = 400

    orig_bgr = _pil_to_bgr(original)
    h, w = mask_rembg.shape[:2]
    orig_resized = cv2.resize(orig_bgr, (w, h))

    def _overlay(mask_: np.ndarray) -> Image.Image:
        ov = orig_resized.copy()
        ov[mask_ > 0] = (ov[mask_ > 0] * 0.5 + np.array([0, 180, 0], dtype=np.float64) * 0.5).astype(np.uint8)
        ov[mask_ == 0] = (ov[mask_ == 0] * 0.7 + np.array([0, 0, 120], dtype=np.float64) * 0.3).astype(np.uint8)
        pil = Image.fromarray(cv2.cvtColor(ov, cv2.COLOR_BGR2RGB))
        pil.thumbnail((size, size), Image.Resampling.LANCZOS)
        return pil

    antes = _overlay(mask_rembg)
    depois = _overlay(mask_refinada)

    panel_w = size * 2 + 15
    panel_h = size + 40
    panel = Image.new("RGB", (panel_w, panel_h), (30, 30, 50))

    panel.paste(antes, (5, 30))
    panel.paste(depois, (size + 10, 30))

    draw = ImageDraw.Draw(panel)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    except Exception:
        font = ImageFont.load_default()

    draw.text((5, 8), "Antes (rembg puro)", fill=(255, 200, 200), font=font)
    draw.text((size + 10, 8), "Depois (refinada)", fill=(200, 255, 200), font=font)
    draw.text((5, panel_h - 18), nome, fill=(150, 150, 150), font=font)

    return panel


def salvar_metricas(metricas: list[dict], output_dir: Path) -> Path:
    """Salva métricas em JSON."""
    path = output_dir / "metricas_lab.json"
    path.write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Métricas salvas em: {path}")
    return path


def gerar_relatorio_html(resultados: list[dict], output_dir: Path) -> Path:
    """Gera relatório HTML com tabela de métricas, previews e comparativos."""
    html_path = output_dir / "relatorio_lab.html"
    rows = []
    for r in resultados:
        m = r.get("metricas", {})
        nome = m.get("arquivo", "?")
        ok = r.get("resultado") is not None
        zoom = m.get("zoom_factor", "-")
        tempo = m.get("tempo_s", "-")
        area = m.get("area_joia_ratio", "-")
        pre = m.get("pre_detect", {})
        pre_conf = pre.get("confianca", "-")
        pre_usado = pre.get("usado", "-")
        fg_antes = m.get("fg_pixels_antes", "-")
        fg_depois = m.get("fg_pixels_depois", "-")

        stem = Path(nome).stem
        diag_file = f"diag_{stem}.jpg"
        etapas_file = f"etapas_{stem}.jpg"
        result_file = f"lab_{nome}"

        status_class = "ok" if ok else "fail"
        status_text = "OK" if ok else "FALHOU"

        rows.append(f"""
        <tr class="{status_class}">
            <td>{nome}</td>
            <td>{status_text}</td>
            <td>{zoom}</td>
            <td>{area}</td>
            <td>{fg_antes} → {fg_depois}</td>
            <td>{pre_conf}</td>
            <td>{pre_usado}</td>
            <td>{tempo}s</td>
        </tr>
        <tr class="{status_class}">
            <td colspan="8">
                {"<img src='" + diag_file + "' width='800'/>" if ok else "—"}<br/>
                {"<img src='" + etapas_file + "' width='540'/>" if ok else ""}
            </td>
        </tr>""")

    config_str = (
        f"canvas={CANVAS_SIZE}px, target={TARGET_RATIO:.0%}, "
        f"grabcut={'ON' if ENABLE_GRABCUT else 'OFF'}, "
        f"cor={'ON' if ENABLE_COLOR_REFINE else 'OFF'}, "
        f"especular={'ON' if ENABLE_SPECULAR_FILTER else 'OFF'}, "
        f"bordas={'ON' if ENABLE_EDGE_MASK else 'OFF'}, "
        f"ensemble={'ON' if ENABLE_ENSEMBLE else 'OFF'}, "
        f"pre_detect={'ON' if ENABLE_PRE_DETECT else 'OFF'}, "
        f"hull={'ON' if ENABLE_CONVEX_HULL else 'OFF'}"
    )

    total = len(resultados)
    ok_count = sum(1 for r in resultados if r.get("resultado") is not None)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<title>Lab Segmentação — Relatório de Auditoria</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #eee; margin: 20px; }}
h1 {{ color: #e94560; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
th {{ background: #16213e; padding: 10px; text-align: left; }}
td {{ padding: 8px; border-bottom: 1px solid #333; vertical-align: top; }}
tr.ok td:nth-child(2) {{ color: #4ecca3; font-weight: bold; }}
tr.fail td:nth-child(2) {{ color: #e94560; font-weight: bold; }}
img {{ border-radius: 4px; max-width: 100%; }}
.summary {{ background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
.legend {{ background: #0f3460; padding: 10px; border-radius: 6px; margin-bottom: 15px; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>Laboratório de Segmentação — Relatório de Auditoria</h1>
<div class="summary">
<p><strong>Total:</strong> {total} imagens |
<strong>OK:</strong> {ok_count} |
<strong>Falhas:</strong> {total - ok_count}</p>
<p><strong>Configuração:</strong> {config_str}</p>
</div>
<div class="legend">
<strong>Legenda das imagens:</strong><br/>
• <span style="color:#4ecca3">Verde</span> = pixels identificados como joia (foreground)<br/>
• <span style="color:#e94560">Vermelho suave</span> = pixels identificados como fundo (removidos)<br/>
• Comparativo "Antes vs Depois" mostra o efeito do refinamento de máscara
</div>
<table>
<tr>
<th>Arquivo</th><th>Status</th><th>Zoom</th><th>Área Joia</th>
<th>FG Pixels (antes→depois)</th>
<th>Pré-Detect Conf</th><th>Pré-Detect Usado</th><th>Tempo</th>
</tr>
{"".join(rows)}
</table>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    logger.info(f"Relatório HTML: {html_path}")
    return html_path
