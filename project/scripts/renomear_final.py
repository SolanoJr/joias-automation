"""
renomear_final.py — Etapa 6: renomeia imagens segmentadas pelo código lido.

Melhorias:
  - HTML com imagem antes/depois lado a lado, nome inicial e final
  - Log da 2ª passagem rembg no CSV e HTML (white% antes/depois)
  - Cache SHA256 da 2ª passagem (evita reprocessar em reruns)
  - Paralelização com ThreadPoolExecutor (REMBG_WORKERS workers)
  - Validação de pré-condições (avisa se etapas anteriores não rodaram)
  - Detecção de regressão (compara com CSV anterior)
"""
import re
import csv
import os
import shutil
import base64
import hashlib
import json
import time
import numpy as np
import cv2
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== PASTAS =====
SEG_DIR       = Path("output/5_segmentado_rembg")
FINAL_DIR     = Path("output/6_final")
CSV_PATH      = Path("output/resultados.csv")
HTML_PATH     = Path("output/relatorio.html")
CACHE_PATH    = Path("output/rembg2_cache.json")
ORIGINAIS_DIR = Path("input_raw/fotos_originais")

LIMPAR_FINAL_ANTES = True

RENOMEAR_FINAL_CANONICAL_ONLY = os.getenv("RENOMEAR_FINAL_CANONICAL_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}

# ===== SEGUNDA PASSAGEM REMBG =====
REMBG_SEGUNDA_PASSAGEM           = os.getenv("REMBG_SEGUNDA_PASSAGEM", "1").strip().lower() in {"1", "true", "yes", "on"}
REMBG_SEGUNDA_PASSAGEM_THRESHOLD = float(os.getenv("REMBG_SEGUNDA_PASSAGEM_THRESHOLD", "0.15"))
REMBG_WORKERS                    = int(os.getenv("REMBG_WORKERS", "2"))

# ===== POS-PROCESSAMENTO: ZOOM + CENTRALIZAÇÃO + LIMPEZA DE PAPEL =====
# Detecta a joia real (pixels < JOIA_THRESH), recorta, centraliza e aplica zoom.
# Limpa papel residual (tons cinza que o rembg deixou) de forma conservadora.
# Desabilite com POS_PROC_ZOOM=0 se quiser manter o comportamento anterior.
POS_PROC_ZOOM    = os.getenv("POS_PROC_ZOOM", "1").strip().lower() in {"1", "true", "yes", "on"}
POS_PROC_SIZE    = 1024
POS_PROC_MAX_SCALE = 0.88   # joia ocupa no maximo 88% do canvas
POS_PROC_MARGIN  = 30       # margem minima ao redor da joia (px)
POS_PROC_JOIA_T  = 100      # threshold para detectar joia real (metal/pedra < 100)


def _pos_proc_limpar_papel(img_bgr: np.ndarray) -> np.ndarray:
    """
    Limpeza conservadora de papel residual.
    Sempre limpa >= 220. Tenta 190/180 so se nao apagar joia (<100)
    e houver papel suficiente nessa faixa (>3% dos pixels).
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resultado = img_bgr.copy()
    total = gray.size
    mask_joia = gray < POS_PROC_JOIA_T

    # Sempre seguro
    resultado[gray >= 220] = [255, 255, 255]

    # Tenta mais agressivo se seguro e com volume suficiente
    for t in [190, 180]:
        mask_limpar = (gray >= t) & (gray < 220)
        if (mask_joia & mask_limpar).sum() > 0:
            break  # apagaria joia — para
        if mask_limpar.sum() / total < 0.03:
            break  # pouco papel — nao vale
        resultado[gray >= t] = [255, 255, 255]

    return resultado


def _pos_proc_zoom_centralizar(img_bgr: np.ndarray) -> np.ndarray:
    """
    Detecta a joia real (thresh < 100), recorta com margem,
    aplica zoom adaptativo e centraliza no canvas branco.
    Retorna a imagem processada (mesmo tamanho: 1024x1024).
    """
    from PIL import Image as PILImage

    SIZE    = POS_PROC_SIZE
    max_px  = int(SIZE * POS_PROC_MAX_SCALE)

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    mask = (gray < POS_PROC_JOIA_T).astype(np.uint8)

    # Remove ruido pontual
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    mask_limpa = np.zeros_like(mask)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] > 50:
            mask_limpa[labels == i] = 1

    ys, xs = np.where(mask_limpa > 0)
    if not len(ys):
        # Fallback: threshold mais alto
        mask2 = (gray < 150).astype(np.uint8)
        ys, xs = np.where(mask2 > 0)
        if not len(ys):
            return img_bgr  # nao detectou joia — retorna original

    x1, y1 = int(xs.min()), int(ys.min())
    x2, y2 = int(xs.max()), int(ys.max())
    h, w = img_bgr.shape[:2]

    joia_w_real = x2 - x1
    joia_h_real = y2 - y1

    # Margem proporcional
    cx_pre = (x1 + x2) / 2
    cy_pre = (y1 + y2) / 2
    offset_pre = ((cx_pre - SIZE/2)**2 + (cy_pre - SIZE/2)**2) ** 0.5
    margem_base = max(POS_PROC_MARGIN, int(max(joia_w_real, joia_h_real) * 0.10))
    margem_extra = int(offset_pre * 0.08) if (offset_pre > 150 and joia_w_real < 300) else 0
    margem = margem_base + margem_extra

    x1 = max(0, x1 - margem)
    y1 = max(0, y1 - margem)
    x2 = min(w, x2 + margem)
    y2 = min(h, y2 + margem)

    joia_w = x2 - x1
    joia_h = y2 - y1
    maior_dim = max(joia_w, joia_h)
    ocup_atual = maior_dim / SIZE

    cx_joia = (x1 + x2) / 2
    cy_joia = (y1 + y2) / 2
    offset = ((cx_joia - SIZE/2)**2 + (cy_joia - SIZE/2)**2) ** 0.5

    # Joia centrada e tamanho razoavel: nao amplia
    ja_ok = (ocup_atual >= 0.30 and offset < 80)

    if ja_ok:
        target_px = maior_dim  # mantém tamanho
    elif offset < 80:
        target_px = int(SIZE * 0.65)   # centrada mas pequena
    elif ocup_atual < 0.25:
        target_px = int(SIZE * 0.75)   # pequena e deslocada
    else:
        target_px = int(SIZE * 0.85)   # media/grande e deslocada

    # Crop
    crop = img_bgr[y1:y2, x1:x2]
    crop_pil = PILImage.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    cw, ch = crop_pil.size

    if not ja_ok and maior_dim < target_px:
        zoom = min(target_px / maior_dim, max_px / maior_dim)
        novo_w = min(int(cw * zoom), max_px)
        novo_h = min(int(ch * zoom), max_px)
        if cw > 0 and ch > 0:
            if novo_w / cw < novo_h / ch:
                novo_h = int(ch * novo_w / cw)
            else:
                novo_w = int(cw * novo_h / ch)
        crop_pil = crop_pil.resize((max(1, novo_w), max(1, novo_h)), PILImage.Resampling.LANCZOS)
    elif maior_dim > max_px:
        scale = max_px / maior_dim
        crop_pil = crop_pil.resize((max(1, int(cw * scale)), max(1, int(ch * scale))), PILImage.Resampling.LANCZOS)

    # Centraliza no canvas branco
    canvas = PILImage.new("RGB", (SIZE, SIZE), (255, 255, 255))
    x = (SIZE - crop_pil.width) // 2
    y = (SIZE - crop_pil.height) // 2
    canvas.paste(crop_pil, (x, y))

    return cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)


def _aplicar_pos_processamento(img_bgr: np.ndarray) -> np.ndarray:
    """Aplica limpeza de papel + zoom/centralização na imagem segmentada."""
    if not POS_PROC_ZOOM:
        return img_bgr
    img_limpa = _pos_proc_limpar_papel(img_bgr)
    return _pos_proc_zoom_centralizar(img_limpa)


# ─────────────────────────────────────────────
# Cache SHA256 para segunda passagem
# ─────────────────────────────────────────────
def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


# ─────────────────────────────────────────────
# Segunda passagem rembg
# ─────────────────────────────────────────────
def _white_ratio(img_rgb: np.ndarray) -> float:
    """Fracao de pixels quase-brancos (>245) — proxy de fundo limpo."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY) if img_rgb.ndim == 3 else img_rgb
    return float((gray > 245).mean())


def _aplicar_segunda_passagem_rembg(img_pil, cache: dict, file_hash: str):
    """
    Aplica rembg segunda vez. Retorna (imagem_resultado, white_antes, white_depois, melhorou).
    Usa cache para evitar reprocessar.
    """
    from PIL import Image
    from io import BytesIO

    arr_antes  = np.array(img_pil)
    white_antes = _white_ratio(arr_antes)

    # Ja esta limpo
    if white_antes >= 0.90:
        return img_pil, white_antes, white_antes, False

    # Verifica cache
    if file_hash in cache:
        cached = cache[file_hash]
        if not cached.get("melhorou", False):
            return img_pil, white_antes, cached.get("white_depois", white_antes), False

    try:
        from rembg import new_session, remove

        session   = new_session("isnet-general-use")
        rembg_out = remove(img_pil.convert("RGBA"), session=session)

        if isinstance(rembg_out, (bytes, bytearray)):
            sem_fundo = Image.open(BytesIO(rembg_out)).convert("RGBA")
        elif isinstance(rembg_out, Image.Image):
            sem_fundo = rembg_out.convert("RGBA")
        else:
            sem_fundo = Image.fromarray(np.array(rembg_out)).convert("RGBA")

        arr_sf = np.array(sem_fundo)
        if (arr_sf[:, :, 3] > 10).sum() == 0:
            cache[file_hash] = {"melhorou": False, "white_antes": white_antes, "white_depois": white_antes}
            return img_pil, white_antes, white_antes, False

        w_orig, h_orig = img_pil.size
        fundo = Image.new("RGBA", (w_orig, h_orig), (255, 255, 255, 255))
        fundo.paste(sem_fundo, (0, 0), sem_fundo)
        resultado = fundo.convert("RGB")

        white_depois = _white_ratio(np.array(resultado))
        melhorou     = (white_depois - white_antes) >= REMBG_SEGUNDA_PASSAGEM_THRESHOLD

        cache[file_hash] = {
            "melhorou":    melhorou,
            "white_antes": round(white_antes, 4),
            "white_depois": round(white_depois, 4),
        }

        return (resultado if melhorou else img_pil), white_antes, white_depois, melhorou

    except Exception as e:
        cache[file_hash] = {"melhorou": False, "white_antes": white_antes, "white_depois": white_antes, "erro": str(e)}
        return img_pil, white_antes, white_antes, False


# ─────────────────────────────────────────────
# Validacao de pre-condicoes
# ─────────────────────────────────────────────
def _validar_precondicoes() -> None:
    if not SEG_DIR.exists() or not list(SEG_DIR.glob("*.jpg")):
        print(f"[AVISO] Etapa 5 nao foi rodada — {SEG_DIR} vazia ou inexistente.")
    etiquetas_dir = Path("output/1_etiquetas")
    paints_dir    = Path("output/2_paints")
    if not etiquetas_dir.exists() and not paints_dir.exists():
        print("[AVISO] Etapas 1/2 nao foram rodadas — pastas de etiquetas e paints ausentes.")


# ─────────────────────────────────────────────
# Deteccao de regressao
# ─────────────────────────────────────────────
def _detectar_regressao(rows_novos: list[dict]) -> None:
    if not CSV_PATH.exists():
        return
    try:
        with open(CSV_PATH, encoding="utf-8") as f:
            rows_ant = {r["base"]: r for r in csv.DictReader(f)}
    except Exception:
        return

    regressoes = []
    for r in rows_novos:
        ant = rows_ant.get(r["base"])
        if not ant:
            continue
        if ant.get("codigo") and not r.get("codigo"):
            regressoes.append(f"  REGRESSAO: {r['base']} tinha '{ant['codigo']}', agora sem codigo")

    if regressoes:
        print("\n[AVISO] REGRESSOES DETECTADAS:")
        for msg in regressoes:
            print(msg)
        print()
    else:
        print("Sem regressoes em relacao ao CSV anterior.")


# ─────────────────────────────────────────────
# Helpers de imagem para HTML
# ─────────────────────────────────────────────
def _img_base64(img_path: Path, max_px: int = 200) -> str:
    """Gera imagem redimensionada em base64 para embutir no HTML."""
    try:
        img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if img is None:
            return ""
        h, w = img.shape[:2]
        if max(h, w) > max_px:
            scale = max_px / max(h, w)
            img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return ""
        result = base64.b64encode(buf.tobytes()).decode("ascii")
        del img, buf
        return result
    except Exception:
        return ""


def _buscar_antes(base: str, seg_path: Path) -> Path | None:
    """
    Busca a melhor imagem 'antes' disponivel para comparacao no HTML.
    Ordem de preferencia:
      1. input_raw/fotos_originais — match por timestamp no stem
      2. output/3_sem_etiqueta — joia sem fundo antes do rembg final
      3. A propria imagem segmentada (fallback)
    """
    import re as _re

    # 1. Original por timestamp
    if ORIGINAIS_DIR.exists():
        m = _re.match(r"^(\d{8}_\d{6})", base)
        if m:
            ts = m.group(1)
            for ext in (".jpg", ".jpeg", ".png"):
                p = ORIGINAIS_DIR / f"{ts}{ext}"
                if p.exists():
                    return p
            matches = list(ORIGINAIS_DIR.glob(f"{ts}*"))
            if matches:
                return matches[0]
        for ext in (".jpg", ".jpeg", ".png"):
            p = ORIGINAIS_DIR / f"{base}{ext}"
            if p.exists():
                return p

    # 2. sem_etiqueta
    se_dir = Path("output/3_sem_etiqueta")
    if se_dir.exists():
        for suffix in ("_se", "_sem_etiqueta", ""):
            p = se_dir / f"{base}{suffix}.jpg"
            if p.exists():
                return p

    # 3. Fallback: a propria segmentada
    return seg_path if seg_path.exists() else None


# ─────────────────────────────────────────────
# HTML antes/depois
# ─────────────────────────────────────────────
def _gerar_relatorio_html(rows: list[dict], total_ok: int, total_sem: int) -> None:
    total = len(rows)

    STATUS_COR = {
        "RENOMEADO":          "#d4edda",
        "JA_CORRETO":         "#d4edda",
        "SEM_CODIGO_COPIADO": "#fff3cd",
    }

    linhas_html = []
    for r in rows:
        status        = r.get("status", "")
        cor           = STATUS_COR.get(status, "#ffffff")
        codigo        = r.get("codigo") or "—"
        fonte         = r.get("fonte") or "—"
        base          = r.get("base", "")
        nome_inicial  = r.get("nome_inicial", base)
        nome_final    = r.get("nome_final", "")
        arquivo_final = r.get("arquivo_final", "")
        seg_path      = Path(r.get("arquivo_origem", ""))

        # Info da segunda passagem
        white_antes  = r.get("white_antes")
        white_depois = r.get("white_depois")
        rembg2_ok    = r.get("rembg2_melhorou", False)

        rembg2_badge = ""
        if white_antes is not None:
            pct_antes  = f"{white_antes*100:.1f}%"
            pct_depois = f"{white_depois*100:.1f}%" if white_depois is not None else "—"
            cor_badge  = "#28a745" if rembg2_ok else "#6c757d"
            label      = "2a pass OK" if rembg2_ok else "2a pass —"
            rembg2_badge = (
                f'<br><span style="font-size:10px;color:{cor_badge}">'
                f'{label} {pct_antes}->{pct_depois}</span>'
            )

        # Imagem antes
        antes_path = _buscar_antes(base, seg_path)
        if antes_path and antes_path.exists():
            antes_b64 = _img_base64(antes_path, max_px=180)
            antes_label = antes_path.name
            antes_tag = (
                f'<img src="data:image/jpeg;base64,{antes_b64}" '
                f'style="max-width:180px;max-height:180px;object-fit:contain;border-radius:4px;" '
                f'title="{antes_label}">'
                if antes_b64 else '<span style="color:#aaa;font-size:10px;">sem imagem</span>'
            )
        else:
            antes_tag   = '<span style="color:#aaa;font-size:10px;">sem original</span>'
            antes_label = nome_inicial

        # Imagem final
        if arquivo_final and Path(arquivo_final).exists():
            final_b64 = _img_base64(Path(arquivo_final), max_px=180)
            final_tag = (
                f'<img src="data:image/jpeg;base64,{final_b64}" '
                f'style="max-width:180px;max-height:180px;object-fit:contain;border-radius:4px;" '
                f'title="{nome_final}">'
                if final_b64 else '<span style="color:#aaa;font-size:10px;">sem final</span>'
            )
        else:
            final_tag = '<span style="color:#aaa;font-size:10px;">sem final</span>'

        status_badge = (
            f'<span style="padding:2px 6px;border-radius:3px;font-size:11px;'
            f'background:{"#28a745" if "RENOMEADO" in status or "CORRETO" in status else "#ffc107"};'
            f'color:{"white" if "RENOMEADO" in status or "CORRETO" in status else "#333"}">'
            f'{status}</span>'
        )

        linhas_html.append(
            f'<tr style="background:{cor}">'
            f'<td style="text-align:center;padding:8px;vertical-align:top">'
            f'{antes_tag}'
            f'<div style="font-size:10px;color:#888;margin-top:4px;word-break:break-all">{antes_label}</div>'
            f'</td>'
            f'<td style="text-align:center;padding:8px;vertical-align:middle;font-size:20px;color:#aaa">-></td>'
            f'<td style="text-align:center;padding:8px;vertical-align:top">'
            f'{final_tag}'
            f'<div style="font-size:10px;color:#333;margin-top:4px;font-weight:bold;word-break:break-all">{nome_final}</div>'
            f'</td>'
            f'<td style="padding:8px;vertical-align:top">'
            f'<b style="font-family:monospace">{codigo}</b><br>'
            f'<span style="font-size:11px;color:#555">fonte: {fonte}</span><br>'
            f'{status_badge}'
            f'{rembg2_badge}'
            f'</td>'
            f'</tr>'
        )

    tabela = "\n".join(linhas_html)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatorio joias-automation</title>
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
  table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 6px;
           overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  th {{ background: #343a40; color: white; padding: 10px 8px; text-align: left; font-size: 13px; }}
  td {{ border-bottom: 1px solid #dee2e6; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ filter: brightness(0.97); }}
</style>
</head>
<body>
<h1>Relatorio joias-automation</h1>
<div class="stats">
  <div class="stat total"><div class="num">{total}</div><div class="lbl">Total</div></div>
  <div class="stat ok"><div class="num">{total_ok}</div><div class="lbl">Com codigo</div></div>
  <div class="stat warn"><div class="num">{total_sem}</div><div class="lbl">Sem codigo</div></div>
</div>
<table>
  <thead>
    <tr>
      <th style="width:200px">Antes</th>
      <th style="width:30px"></th>
      <th style="width:200px">Final</th>
      <th>Codigo / Status</th>
    </tr>
  </thead>
  <tbody>
{tabela}
  </tbody>
</table>
</body>
</html>
"""

    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Relatorio HTML: {HTML_PATH}")


# ─────────────────────────────────────────────
# Helpers de nome
# ─────────────────────────────────────────────
def stem_base(nome_arquivo: str) -> str:
    """
    Normaliza nomes para bater "foto base".
    Remove:
      - _sr  (sufixo adicionado por renomear_intermediarios.py na etapa 5)
      - _etiqueta_0, _etiqueta_1, etc
      - _warp
      - _sem_etiqueta
    """
    s = Path(nome_arquivo).stem
    s = re.sub(r"_sr$", "", s)
    s = re.sub(r"_etiqueta_\d+.*$", "", s)
    s = re.sub(r"_warp$", "", s)
    s = re.sub(r"_sem_etiqueta$", "", s)
    return s


def is_numeric_stem(stem: str) -> bool:
    return stem.isdigit()


def nome_unico(dest_dir: Path, nome_base: str) -> str:
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
    """Retorna sufixo vazio — o nome final e apenas o codigo."""
    return ""


# ─────────────────────────────────────────────
# Worker para paralelizacao
# ─────────────────────────────────────────────
def _processar_imagem(img: Path, cache: dict) -> dict:
    """Processa uma imagem: le codigo, aplica 2a passagem, retorna row."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from ler_codigo import ler_codigo_unico

    base   = stem_base(img.name)
    codigo, fonte = ler_codigo_unico(base)

    if not codigo and is_numeric_stem(base):
        codigo = base
        fonte  = "NOME_ARQUIVO"

    dest         = None
    status       = None
    white_antes  = None
    white_depois = None
    rembg2_ok    = False

    if codigo:
        codigo_saida = codigo
        out_name = nome_unico(FINAL_DIR, codigo_saida)
        dest = FINAL_DIR / out_name

        if REMBG_SEGUNDA_PASSAGEM:
            try:
                from PIL import Image

                # 1. Pós-processamento: zoom + centralização + limpeza de papel
                img_bgr = cv2.imread(str(img))
                if img_bgr is not None and POS_PROC_ZOOM:
                    img_bgr = _aplicar_pos_processamento(img_bgr)
                    img_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
                else:
                    img_pil = Image.open(img).convert("RGB")

                # 2. Segunda passagem rembg (remove papel residual restante)
                fhash    = _file_hash(img)
                resultado, white_antes, white_depois, rembg2_ok = _aplicar_segunda_passagem_rembg(img_pil, cache, fhash)
                resultado.save(dest, quality=95)
            except Exception:
                shutil.copy2(img, dest)
        else:
            if POS_PROC_ZOOM:
                try:
                    from PIL import Image
                    img_bgr = cv2.imread(str(img))
                    if img_bgr is not None:
                        img_bgr = _aplicar_pos_processamento(img_bgr)
                        img_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
                        img_pil.save(dest, quality=95)
                    else:
                        shutil.copy2(img, dest)
                except Exception:
                    shutil.copy2(img, dest)
            else:
                shutil.copy2(img, dest)

        status = "RENOMEADO" if base != codigo_saida else "JA_CORRETO"
    else:
        base_limpo = normalizar_base_para_nome(base)
        out_name   = nome_unico(FINAL_DIR, f"SEMCOD_{base_limpo}")
        dest       = FINAL_DIR / out_name
        shutil.copy2(img, dest)
        status = "SEM_CODIGO_COPIADO"

    return {
        "arquivo_origem":  str(img).replace("\\", "/"),
        "base":            base,
        "codigo":          codigo or "",
        "fonte":           fonte or "",
        "arquivo_final":   str(dest).replace("\\", "/") if dest else "",
        "status":          status,
        "nome_inicial":    img.stem,
        "nome_final":      dest.stem if dest else "",
        "white_antes":     round(white_antes, 4) if white_antes is not None else None,
        "white_depois":    round(white_depois, 4) if white_depois is not None else None,
        "rembg2_melhorou": rembg2_ok,
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    _validar_precondicoes()

    if not SEG_DIR.exists():
        print(f"ERRO: nao existe {SEG_DIR}")
        return

    seg_imgs = sorted(SEG_DIR.glob("*.jpg"))
    if not seg_imgs:
        print(f"ERRO: nenhuma imagem em {SEG_DIR}")
        return

    if RENOMEAR_FINAL_CANONICAL_ONLY:
        seg_imgs = [p for p in seg_imgs if not p.stem.endswith("_sr")]

    if LIMPAR_FINAL_ANTES and FINAL_DIR.exists():
        shutil.rmtree(FINAL_DIR, ignore_errors=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    cache = _load_cache()
    t0    = time.perf_counter()
    rows  = []

    print(f"Processando {len(seg_imgs)} imagens com {REMBG_WORKERS} workers...")
    with ThreadPoolExecutor(max_workers=REMBG_WORKERS) as executor:
        futures = {executor.submit(_processar_imagem, img, cache): img for img in seg_imgs}
        for i, future in enumerate(as_completed(futures), 1):
            img = futures[future]
            try:
                row = future.result()
                rows.append(row)
                icon = "OK" if row["status"] != "SEM_CODIGO_COPIADO" else "??"
                rembg_info = ""
                if row.get("white_antes") is not None:
                    rembg_info = (
                        f" | rembg2: {row['white_antes']*100:.0f}%"
                        f"->{row['white_depois']*100:.0f}%"
                        f"{'*' if row['rembg2_melhorou'] else ''}"
                    )
                print(f"  [{i:2d}/{len(seg_imgs)}] {icon} {row['base']:30s} -> {row['codigo'] or 'SEM_CODIGO'}{rembg_info}")
            except Exception as e:
                print(f"  ERRO em {img.name}: {e}")

    rows.sort(key=lambda r: r["arquivo_origem"])
    _save_cache(cache)

    elapsed           = time.perf_counter() - t0
    ok                = sum(1 for r in rows if r["status"] != "SEM_CODIGO_COPIADO")
    sem_codigo        = sum(1 for r in rows if r["status"] == "SEM_CODIGO_COPIADO")
    rembg2_melhoradas = sum(1 for r in rows if r.get("rembg2_melhorou"))

    # CSV com colunas extras de rembg2
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "arquivo_origem", "base", "codigo", "fonte",
            "arquivo_final", "status",
            "white_antes", "white_depois", "rembg2_melhorou",
        ])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})

    # Limpa arquivos orfaos em 6_final
    esperados = {Path(r["arquivo_final"]).name for r in rows if r.get("arquivo_final")}
    for p in FINAL_DIR.glob("*.jpg"):
        if p.name not in esperados:
            try:
                p.unlink()
            except Exception:
                pass

    _detectar_regressao(rows)

    print(f"\nFinal OK:          {ok}/{len(rows)}")
    print(f"Sem codigo:        {sem_codigo}")
    print(f"2a passagem rembg: {rembg2_melhoradas} imagens melhoradas")
    print(f"Tempo total:       {elapsed:.1f}s")
    print(f"CSV:               {CSV_PATH}")

    try:
        _gerar_relatorio_html(rows, ok, sem_codigo)
    except Exception as e:
        print(f"Aviso: falha ao gerar relatorio.html — {e}")


if __name__ == "__main__":
    main()
