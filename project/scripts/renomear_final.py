import re
import csv
import os
import shutil
import base64
import io
from pathlib import Path

# Pastas
SEG_DIR = Path("output/5_segmentado_rembg")
FINAL_DIR = Path("output/6_final")
CSV_PATH = Path("output/resultados.csv")
LIMPAR_FINAL_ANTES = True

FINAL_DIR.mkdir(parents=True, exist_ok=True)

# No modo incremental, só processa arquivos com stem canônico (sem sufixos intermediários)
RENOMEAR_FINAL_CANONICAL_ONLY = os.getenv("RENOMEAR_FINAL_CANONICAL_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}

# Importa leitor unificado de código
from ler_codigo import ler_codigo_unico


def _thumb_base64(img_path: Path, size: int = 50) -> str:
    """Gera thumbnail 50x50 em base64 para embutir no HTML."""
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(img_path))
        if img is None:
            return ""
        h, w = img.shape[:2]
        # Redimensiona mantendo proporção
        if h > w:
            new_h, new_w = size, max(1, int(w * size / h))
        else:
            new_w, new_h = size, max(1, int(h * size / w))
        thumb = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        # Centraliza em canvas quadrado
        canvas = np.ones((size, size, 3), dtype=np.uint8) * 240
        y0 = (size - new_h) // 2
        x0 = (size - new_w) // 2
        canvas[y0:y0 + new_h, x0:x0 + new_w] = thumb
        ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return ""
        return base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception:
        return ""


def _gerar_relatorio_html(rows: list[dict], total_ok: int, total_sem: int) -> None:
    """Gera output/relatorio.html com thumbnails e tabela de resultados."""
    html_path = Path("output/relatorio.html")
    total = len(rows)

    # Cores por status
    STATUS_COR = {
        "RENOMEADO":         "#d4edda",  # verde claro
        "JA_CORRETO":        "#d4edda",  # verde claro
        "SEM_CODIGO_COPIADO": "#fff3cd", # amarelo claro
    }

    linhas_html = []
    for r in rows:
        status = r.get("status", "")
        cor = STATUS_COR.get(status, "#ffffff")
        codigo = r.get("codigo") or "<em>—</em>"
        fonte = r.get("fonte") or "—"
        arquivo_final = r.get("arquivo_final", "")

        # Thumbnail da imagem final (em output/6_final/)
        thumb_b64 = ""
        if arquivo_final:
            p = Path(arquivo_final)
            if p.exists():
                thumb_b64 = _thumb_base64(p)

        if thumb_b64:
            img_tag = f'<img src="data:image/jpeg;base64,{thumb_b64}" width="50" height="50" style="object-fit:contain;border-radius:3px;">'
        else:
            img_tag = '<span style="color:#aaa;font-size:10px;">sem img</span>'

        linhas_html.append(
            f'<tr style="background:{cor}">'
            f'<td style="text-align:center;padding:4px">{img_tag}</td>'
            f'<td style="padding:4px;font-family:monospace">{codigo}</td>'
            f'<td style="padding:4px;color:#555">{fonte}</td>'
            f'<td style="padding:4px">'
            f'<span style="padding:2px 6px;border-radius:3px;font-size:11px;'
            f'background:{"#28a745" if "RENOMEADO" in status or "CORRETO" in status else "#ffc107"};'
            f'color:{"white" if "RENOMEADO" in status or "CORRETO" in status else "#333"}">'
            f'{status}</span></td>'
            f'</tr>'
        )

    tabela = "\n".join(linhas_html)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório joias-automation</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; background: #f8f9fa; }}
  h1 {{ color: #2c3e50; border-bottom: 2px solid #dee2e6; padding-bottom: 8px; }}
  .stats {{ display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }}
  .stat {{ background: white; border: 1px solid #dee2e6; border-radius: 6px; padding: 12px 20px; min-width: 120px; text-align: center; }}
  .stat .num {{ font-size: 28px; font-weight: bold; }}
  .stat .lbl {{ font-size: 12px; color: #666; margin-top: 4px; }}
  .stat.ok .num {{ color: #28a745; }}
  .stat.warn .num {{ color: #ffc107; }}
  .stat.total .num {{ color: #007bff; }}
  table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  th {{ background: #343a40; color: white; padding: 10px 8px; text-align: left; font-size: 13px; }}
  td {{ border-bottom: 1px solid #dee2e6; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ filter: brightness(0.97); }}
</style>
</head>
<body>
<h1>Relatório joias-automation</h1>
<div class="stats">
  <div class="stat total"><div class="num">{total}</div><div class="lbl">Total</div></div>
  <div class="stat ok"><div class="num">{total_ok}</div><div class="lbl">Renomeados</div></div>
  <div class="stat warn"><div class="num">{total_sem}</div><div class="lbl">Sem código</div></div>
</div>
<table>
  <thead>
    <tr>
      <th style="width:60px">Thumb</th>
      <th>Código</th>
      <th>Fonte</th>
      <th>Status</th>
    </tr>
  </thead>
  <tbody>
{tabela}
  </tbody>
</table>
</body>
</html>
"""

    html_path.write_text(html, encoding="utf-8")
    print(f"Relatório HTML: {html_path}")


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

    # No modo incremental, filtra apenas arquivos com stem canônico
    if RENOMEAR_FINAL_CANONICAL_ONLY:
        def _is_canonical(p: Path) -> bool:
            s = p.stem
            return " - " not in s and not s.endswith("_sr")
        seg_imgs = [p for p in seg_imgs if _is_canonical(p)]

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

    # Relatório HTML
    try:
        _gerar_relatorio_html(rows, ok, sem_codigo)
    except Exception as e:
        print(f"Aviso: falha ao gerar relatorio.html — {e}")


if __name__ == "__main__":
    main()
