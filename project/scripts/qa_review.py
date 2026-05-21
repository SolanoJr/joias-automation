"""
qa_review.py — Review automático de qualidade das imagens finais.

Analisa output/6_final/ e move imagens suspeitas para output/review/
com um relatório explicando o motivo.

Critérios de suspeita:
  - muito_papel:    fundo cinza/papel > 40% da imagem
  - objeto_pequeno: joia ocupa < 15% do canvas
  - objeto_gigante: joia ocupa > 95% do canvas (provavelmente cortou)
  - descentralizado: centro da joia deslocado > 35% do canvas
  - sem_codigo:     nome começa com SEMCOD_
  - branco_residual: pixels brancos puros > 15% (rembg não limpou)

Saída:
  - output/review/  — imagens suspeitas (cópias, não move)
  - output/review/relatorio_qa.json — detalhes por imagem
  - output/review/relatorio_qa.html — relatório visual

Uso standalone:
  python scripts/qa_review.py
  python scripts/qa_review.py --mover   # move em vez de copiar
"""

from __future__ import annotations
import cv2
import numpy as np
import json
import shutil
import base64
import argparse
from pathlib import Path
from dataclasses import dataclass, field


# ===== RAIZ DO PROJETO =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent

FINAL_DIR  = PROJECT_ROOT / "output/6_final"
REVIEW_DIR = PROJECT_ROOT / "output/review"
JSON_PATH  = PROJECT_ROOT / "output/review/relatorio_qa.json"
HTML_PATH  = PROJECT_ROOT / "output/review/relatorio_qa.html"

# Thresholds
TH_PAPEL_MAX      = 0.40   # > 40% de papel (120-220) = suspeito
TH_JOIA_MIN       = 0.10   # < 10% de joia = muito pequena
TH_JOIA_MAX       = 0.98   # > 98% de joia = provavelmente cortou
TH_OFFSET_MAX     = 0.40   # > 40% do canvas de offset = descentralizado
# Branco residual: só suspeito se tem MUITO branco E também tem papel
# (branco puro sem papel = fundo limpo = OK)
TH_BRANCO_COM_PAPEL = 0.10  # branco > 10% quando há papel > 20% = suspeito


@dataclass
class ResultadoQA:
    nome:          str
    motivos:       list[str] = field(default_factory=list)
    area_joia:     float = 0.0
    area_papel:    float = 0.0
    area_branco:   float = 0.0
    offset_px:     float = 0.0
    offset_pct:    float = 0.0
    suspeito:      bool  = False


def analisar_imagem(p: Path) -> ResultadoQA:
    """Analisa uma imagem final e retorna métricas de qualidade."""
    nome = p.name
    r = ResultadoQA(nome=nome)

    img = cv2.imread(str(p))
    if img is None:
        r.motivos.append("erro_leitura")
        r.suspeito = True
        return r

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]
    total = h * w

    # Sem código
    if nome.startswith("SEMCOD_"):
        r.motivos.append("sem_codigo")
        r.suspeito = True

    # Papel/cinza residual (tons 120-220) — calcula primeiro
    papel = ((gray >= 120) & (gray < 220)).sum() / total
    r.area_papel = float(papel)
    if papel > TH_PAPEL_MAX:
        r.motivos.append(f"muito_papel({papel:.0%})")

    # Branco residual: só suspeito se tem branco E papel juntos
    # (branco puro sem papel = fundo limpo do rembg = OK)
    branco = (gray >= 240).sum() / total
    r.area_branco = float(branco)
    if branco > TH_BRANCO_COM_PAPEL and papel > 0.20:
        r.motivos.append(f"branco_com_papel({branco:.0%})")

    # Joia (pixels escuros < 120 ou dourado)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask_joia = (
        (gray < 120) |
        (
            (hsv[:,:,0] >= 10) & (hsv[:,:,0] <= 40) &
            (hsv[:,:,1] >= 50) & (hsv[:,:,2] >= 60)
        )
    )
    ys, xs = np.where(mask_joia)
    if len(ys):
        joia_w = int(xs.max() - xs.min())
        joia_h = int(ys.max() - ys.min())
        area_joia = max(joia_w, joia_h) / max(w, h)
        cx = (xs.min() + xs.max()) / 2
        cy = (ys.min() + ys.max()) / 2
        offset = ((cx - w/2)**2 + (cy - h/2)**2) ** 0.5
        offset_pct = offset / max(w, h)
    else:
        area_joia = 0.0
        offset = 0.0
        offset_pct = 0.0

    r.area_joia   = float(area_joia)
    r.offset_px   = float(offset)
    r.offset_pct  = float(offset_pct)

    if area_joia < TH_JOIA_MIN:
        r.motivos.append(f"objeto_pequeno({area_joia:.0%})")
    if area_joia > TH_JOIA_MAX:
        r.motivos.append(f"objeto_gigante({area_joia:.0%})")
    if offset_pct > TH_OFFSET_MAX:
        r.motivos.append(f"descentralizado({offset_pct:.0%})")

    r.suspeito = len(r.motivos) > 0
    return r


def _thumb_b64(p: Path, size: int = 120) -> str:
    """Gera thumbnail base64 para o HTML."""
    try:
        img = cv2.imread(str(p))
        if img is None:
            return ""
        h, w = img.shape[:2]
        s = size / max(h, w)
        img = cv2.resize(img, (max(1, int(w*s)), max(1, int(h*s))))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return ""
        return base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception:
        return ""


def gerar_html(resultados: list[ResultadoQA], total: int) -> None:
    """Gera relatório HTML visual."""
    suspeitos = [r for r in resultados if r.suspeito]
    linhas = []
    for r in suspeitos:
        p = REVIEW_DIR / r.nome
        if not p.exists():
            p = FINAL_DIR / r.nome
        b64 = _thumb_b64(p)
        img_tag = (
            f'<img src="data:image/jpeg;base64,{b64}" '
            f'style="width:120px;height:120px;object-fit:contain">'
            if b64 else '<span style="color:#aaa">sem img</span>'
        )
        motivos_html = " | ".join(
            f'<span style="background:#f8d7da;padding:2px 5px;border-radius:3px;font-size:11px">{m}</span>'
            for m in r.motivos
        )
        linhas.append(
            f'<tr>'
            f'<td style="padding:6px;text-align:center">{img_tag}</td>'
            f'<td style="padding:6px;font-family:monospace">{r.nome}</td>'
            f'<td style="padding:6px">{motivos_html}</td>'
            f'<td style="padding:6px;font-size:11px;color:#555">'
            f'joia={r.area_joia:.0%} papel={r.area_papel:.0%} '
            f'branco={r.area_branco:.0%} offset={r.offset_pct:.0%}'
            f'</td>'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8">
<title>QA Review — joias-automation</title>
<style>
  body{{font-family:Arial,sans-serif;margin:20px;background:#f8f9fa}}
  h1{{color:#2c3e50}}
  .stats{{display:flex;gap:16px;margin:16px 0}}
  .stat{{background:white;border:1px solid #dee2e6;border-radius:6px;padding:12px 20px;text-align:center}}
  .stat .num{{font-size:28px;font-weight:bold}}
  .stat.ok .num{{color:#28a745}}
  .stat.warn .num{{color:#dc3545}}
  table{{border-collapse:collapse;width:100%;background:white;border-radius:6px;
         box-shadow:0 1px 3px rgba(0,0,0,.1)}}
  th{{background:#343a40;color:white;padding:10px 8px;text-align:left}}
  td{{border-bottom:1px solid #dee2e6;vertical-align:middle}}
  tr:hover{{filter:brightness(0.97)}}
</style>
</head>
<body>
<h1>QA Review — joias-automation</h1>
<div class="stats">
  <div class="stat"><div class="num">{total}</div><div>Total</div></div>
  <div class="stat ok"><div class="num">{total - len(suspeitos)}</div><div>OK</div></div>
  <div class="stat warn"><div class="num">{len(suspeitos)}</div><div>Suspeitas</div></div>
</div>
<table>
<thead><tr>
  <th style="width:130px">Imagem</th>
  <th>Nome</th>
  <th>Motivos</th>
  <th>Métricas</th>
</tr></thead>
<tbody>
{"".join(linhas)}
</tbody>
</table>
</body></html>"""

    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Relatório HTML: {HTML_PATH}")


def main(mover: bool = False) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    imgs = sorted(FINAL_DIR.glob("*.jpg"))
    if not imgs:
        print(f"Nenhuma imagem em {FINAL_DIR}")
        return

    resultados = []
    suspeitos  = 0

    for p in imgs:
        r = analisar_imagem(p)
        resultados.append(r)

        if r.suspeito:
            suspeitos += 1
            dest = REVIEW_DIR / p.name
            if mover:
                shutil.move(str(p), str(dest))
            else:
                shutil.copy2(p, dest)
            motivos_str = ", ".join(r.motivos)
            print(f"  SUSPEITO: {p.name} — {motivos_str}")

    # Salva JSON
    dados_json = [
        {
            "nome":        r.nome,
            "suspeito":    r.suspeito,
            "motivos":     r.motivos,
            "area_joia":   round(r.area_joia, 3),
            "area_papel":  round(r.area_papel, 3),
            "area_branco": round(r.area_branco, 3),
            "offset_px":   round(r.offset_px, 1),
            "offset_pct":  round(r.offset_pct, 3),
        }
        for r in resultados
    ]
    JSON_PATH.write_text(json.dumps(dados_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # Gera HTML
    try:
        gerar_html(resultados, len(imgs))
    except Exception as e:
        print(f"Aviso: falha ao gerar HTML — {e}")

    print(f"\nTotal: {len(imgs)}  |  Suspeitas: {suspeitos}  |  OK: {len(imgs)-suspeitos}")
    print(f"Pasta review: {REVIEW_DIR}")
    print(f"JSON: {JSON_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QA automático das imagens finais")
    parser.add_argument("--mover", action="store_true", help="Move imagens suspeitas (padrão: copia)")
    args = parser.parse_args()
    main(mover=args.mover)
