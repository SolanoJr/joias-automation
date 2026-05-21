"""
detect_joia.py — Detecção leve da região principal da joia.

Objetivo: encontrar um bounding box aproximado da joia ANTES do rembg,
para melhorar crop, zoom e centralização sem depender da máscara do rembg.

Estratégia (heurísticas leves, sem IA pesada):
  1. Dourado/metal: detecta pixels com hue dourado (HSV 15-35) ou escuros (<80)
  2. Contraste local: regiões com alta variância local (detalhes = joia)
  3. Canny edges: concentração de bordas indica objeto complexo (joia)
  4. Ignora blocos grandes claros (papel/fundo)
  5. Combina os três sinais com votação por grade

Saída:
  DeteccaoJoia com:
    - bbox: (x1, y1, x2, y2) ou None
    - confianca: 0.0-1.0
    - area_util: fração da imagem que é joia
    - offset_cx, offset_cy: deslocamento do centro em pixels
    - proporcao: largura/altura do bbox
    - motivo_fallback: string se usou fallback

Uso:
    from detect_joia import detectar_joia
    det = detectar_joia(img_bgr)
    if det.bbox:
        x1, y1, x2, y2 = det.bbox
"""

from __future__ import annotations
import cv2
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path


# ─── Parâmetros ────────────────────────────────────────────────────────────────
# Tamanho máximo para processar (downscale interno para velocidade)
_PROC_MAX_SIDE = 640

# Grade para votação (NxN células)
_GRID_N = 8

# Thresholds de confiança
_CONF_ALTA   = 0.70
_CONF_MEDIA  = 0.45
_CONF_BAIXA  = 0.25

# Margem ao redor do bbox detectado (fração do tamanho da joia)
_MARGEM_FRAC = 0.12
_MARGEM_MIN  = 20   # px na imagem original


@dataclass
class DeteccaoJoia:
    bbox:             tuple[int, int, int, int] | None = None  # (x1,y1,x2,y2) na imagem original
    confianca:        float = 0.0
    area_util:        float = 0.0   # fração da imagem que é joia
    offset_cx:        float = 0.0   # deslocamento horizontal do centro (px)
    offset_cy:        float = 0.0   # deslocamento vertical do centro (px)
    proporcao:        float = 1.0   # largura/altura do bbox
    motivo_fallback:  str   = ""    # preenchido se usou fallback
    # Métricas internas (para log/auditoria)
    score_dourado:    float = 0.0
    score_contraste:  float = 0.0
    score_bordas:     float = 0.0
    img_w:            int   = 0
    img_h:            int   = 0


def _downscale(img: np.ndarray, max_side: int = _PROC_MAX_SIDE) -> tuple[np.ndarray, float]:
    """Reduz a imagem para processamento rápido. Retorna (img_reduzida, escala)."""
    h, w = img.shape[:2]
    maior = max(h, w)
    if maior <= max_side:
        return img, 1.0
    escala = max_side / maior
    novo_w = max(1, int(w * escala))
    novo_h = max(1, int(h * escala))
    return cv2.resize(img, (novo_w, novo_h), interpolation=cv2.INTER_AREA), escala


def _mapa_dourado(img_bgr: np.ndarray) -> np.ndarray:
    """
    Mapa de pixels com características de joia dourada/metálica.
    Combina:
      - Dourado: hue 10-40, sat>50, val>60
      - Prata/metal claro: sat<40, val>120 (mas não branco puro)
      - Metal escuro: val<80
    Retorna mapa float 0-1.
    """
    hsv  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    h_ch = hsv[:, :, 0]
    s_ch = hsv[:, :, 1]
    v_ch = hsv[:, :, 2]

    # Dourado/amarelo
    mask_dourado = (
        (h_ch >= 10) & (h_ch <= 40) &
        (s_ch >= 50) & (v_ch >= 60)
    ).astype(np.float32)

    # Prata/metal claro (baixa saturação, não branco puro)
    mask_prata = (
        (s_ch < 40) & (v_ch >= 80) & (v_ch < 230)
    ).astype(np.float32)

    # Metal escuro
    mask_escuro = (gray < 80).astype(np.float32)

    # Combina com pesos
    mapa = np.clip(mask_dourado * 1.0 + mask_prata * 0.5 + mask_escuro * 0.8, 0, 1)
    return mapa


def _mapa_contraste(gray: np.ndarray) -> np.ndarray:
    """
    Mapa de contraste local — regiões com alta variância = detalhes = joia.
    Ignora regiões muito claras (papel).
    """
    # Variância local com kernel 15x15
    gray_f = gray.astype(np.float32)
    media  = cv2.blur(gray_f, (15, 15))
    media2 = cv2.blur(gray_f ** 2, (15, 15))
    var    = np.clip(media2 - media ** 2, 0, None)
    std    = np.sqrt(var)

    # Normaliza
    std_max = std.max()
    if std_max < 1e-6:
        return np.zeros_like(gray, dtype=np.float32)
    mapa = std / std_max

    # Penaliza regiões muito claras (papel branco/cinza claro)
    mask_claro = (gray > 200).astype(np.float32)
    mapa = mapa * (1.0 - mask_claro * 0.8)

    return mapa.astype(np.float32)


def _mapa_bordas(gray: np.ndarray) -> np.ndarray:
    """
    Mapa de densidade de bordas (Canny) — joias têm muitas bordas.
    Retorna mapa suavizado float 0-1.
    """
    blur  = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 30, 100)
    # Suaviza para criar mapa de densidade
    mapa  = cv2.GaussianBlur(edges.astype(np.float32), (21, 21), 0)
    m_max = mapa.max()
    if m_max < 1e-6:
        return np.zeros_like(gray, dtype=np.float32)
    return mapa / m_max


def _votar_grade(mapas: list[np.ndarray], pesos: list[float], n: int = _GRID_N) -> np.ndarray:
    """
    Divide a imagem em grade NxN e calcula score médio por célula.
    Retorna grade de scores float.
    """
    h, w = mapas[0].shape
    grade = np.zeros((n, n), dtype=np.float32)
    ch = h // n
    cw = w // n

    for i in range(n):
        for j in range(n):
            y1, y2 = i * ch, min((i + 1) * ch, h)
            x1, x2 = j * cw, min((j + 1) * cw, w)
            score = 0.0
            for mapa, peso in zip(mapas, pesos):
                score += mapa[y1:y2, x1:x2].mean() * peso
            grade[i, j] = score

    return grade


def _bbox_da_grade(grade: np.ndarray, img_shape: tuple, escala: float,
                   threshold_frac: float = 0.35) -> tuple[int, int, int, int] | None:
    """
    Converte grade de scores em bbox na imagem original.
    Seleciona células com score >= threshold_frac * max_score.
    """
    h, w = img_shape[:2]
    n = grade.shape[0]
    ch = h // n
    cw = w // n

    max_score = grade.max()
    if max_score < 1e-6:
        return None

    threshold = max_score * threshold_frac
    mask = grade >= threshold

    rows, cols = np.where(mask)
    if not len(rows):
        return None

    # Bbox em coordenadas da imagem reduzida
    r1, r2 = rows.min(), rows.max()
    c1, c2 = cols.min(), cols.max()

    y1_red = r1 * ch
    y2_red = min((r2 + 1) * ch, h)
    x1_red = c1 * cw
    x2_red = min((c2 + 1) * cw, w)

    # Converte para coordenadas originais
    if escala < 1.0:
        x1 = int(x1_red / escala)
        y1 = int(y1_red / escala)
        x2 = int(x2_red / escala)
        y2 = int(y2_red / escala)
    else:
        x1, y1, x2, y2 = x1_red, y1_red, x2_red, y2_red

    return x1, y1, x2, y2


def _adicionar_margem(bbox: tuple, img_shape: tuple) -> tuple[int, int, int, int]:
    """Adiciona margem proporcional ao bbox, respeitando os limites da imagem."""
    x1, y1, x2, y2 = bbox
    h, w = img_shape[:2]
    joia_w = x2 - x1
    joia_h = y2 - y1
    margem = max(_MARGEM_MIN, int(max(joia_w, joia_h) * _MARGEM_FRAC))
    return (
        max(0, x1 - margem),
        max(0, y1 - margem),
        min(w, x2 + margem),
        min(h, y2 + margem),
    )


def _calcular_metricas(bbox: tuple, img_shape: tuple) -> dict:
    """Calcula métricas do bbox para auditoria."""
    x1, y1, x2, y2 = bbox
    h, w = img_shape[:2]
    joia_w = x2 - x1
    joia_h = y2 - y1
    area_util = (joia_w * joia_h) / (w * h)
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    offset_cx = cx - w / 2
    offset_cy = cy - h / 2
    proporcao = joia_w / joia_h if joia_h > 0 else 1.0
    return {
        "area_util":  area_util,
        "offset_cx":  offset_cx,
        "offset_cy":  offset_cy,
        "proporcao":  proporcao,
    }


def detectar_joia(img_bgr: np.ndarray) -> DeteccaoJoia:
    """
    Detecta a região principal da joia na imagem.

    Args:
        img_bgr: imagem BGR (qualquer tamanho)

    Returns:
        DeteccaoJoia com bbox e métricas
    """
    if img_bgr is None or img_bgr.size == 0:
        return DeteccaoJoia(motivo_fallback="imagem_invalida")

    h_orig, w_orig = img_bgr.shape[:2]

    # Downscale para processamento rápido
    img_small, escala = _downscale(img_bgr)
    h_s, w_s = img_small.shape[:2]
    gray_s = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)

    # Calcula os três mapas de sinal
    mapa_d = _mapa_dourado(img_small)
    mapa_c = _mapa_contraste(gray_s)
    mapa_b = _mapa_bordas(gray_s)

    # Scores médios para auditoria
    score_d = float(mapa_d.mean())
    score_c = float(mapa_c.mean())
    score_b = float(mapa_b.mean())

    # Votação por grade com pesos adaptativos
    # Se há muito dourado, aumenta peso do dourado
    peso_d = 1.5 if score_d > 0.05 else 0.8
    peso_c = 1.0
    peso_b = 1.2

    grade = _votar_grade(
        [mapa_d, mapa_c, mapa_b],
        [peso_d, peso_c, peso_b],
    )

    # Bbox da grade
    bbox_raw = _bbox_da_grade(grade, img_small.shape, escala=1.0)

    if bbox_raw is None:
        return DeteccaoJoia(
            motivo_fallback="grade_vazia",
            score_dourado=score_d,
            score_contraste=score_c,
            score_bordas=score_b,
            img_w=w_orig, img_h=h_orig,
        )

    # Converte para coordenadas originais
    if escala < 1.0:
        x1 = int(bbox_raw[0] / escala)
        y1 = int(bbox_raw[1] / escala)
        x2 = int(bbox_raw[2] / escala)
        y2 = int(bbox_raw[3] / escala)
    else:
        x1, y1, x2, y2 = bbox_raw

    # Clipa nos limites
    x1 = max(0, min(x1, w_orig - 1))
    y1 = max(0, min(y1, h_orig - 1))
    x2 = max(x1 + 1, min(x2, w_orig))
    y2 = max(y1 + 1, min(y2, h_orig))

    # Adiciona margem
    x1, y1, x2, y2 = _adicionar_margem((x1, y1, x2, y2), (h_orig, w_orig))

    bbox = (x1, y1, x2, y2)
    metricas = _calcular_metricas(bbox, (h_orig, w_orig))

    # Calcula confiança baseada nos scores e tamanho do bbox
    area_util = metricas["area_util"]
    # Penaliza bbox muito grande (>80% da imagem = provavelmente pegou tudo)
    penalidade_grande = max(0.0, (area_util - 0.80) * 2.0) if area_util > 0.80 else 0.0
    # Penaliza bbox muito pequeno (<3% da imagem)
    penalidade_pequeno = max(0.0, (0.03 - area_util) * 5.0) if area_util < 0.03 else 0.0

    confianca = (
        score_d * peso_d + score_c * peso_c + score_b * peso_b
    ) / (peso_d + peso_c + peso_b)
    confianca = float(np.clip(confianca - penalidade_grande - penalidade_pequeno, 0.0, 1.0))

    return DeteccaoJoia(
        bbox=bbox,
        confianca=confianca,
        area_util=metricas["area_util"],
        offset_cx=metricas["offset_cx"],
        offset_cy=metricas["offset_cy"],
        proporcao=metricas["proporcao"],
        score_dourado=score_d,
        score_contraste=score_c,
        score_bordas=score_b,
        img_w=w_orig,
        img_h=h_orig,
    )


def detectar_joia_com_fallback(img_bgr: np.ndarray) -> DeteccaoJoia:
    """
    Versão segura com fallback: se a detecção falhar ou tiver baixa confiança,
    retorna bbox = imagem inteira (sem crop).
    """
    try:
        det = detectar_joia(img_bgr)
    except Exception as e:
        h, w = img_bgr.shape[:2]
        return DeteccaoJoia(
            bbox=(0, 0, w, h),
            confianca=0.0,
            motivo_fallback=f"excecao:{e}",
            img_w=w, img_h=h,
        )

    if det.bbox is None or det.confianca < _CONF_BAIXA:
        h, w = img_bgr.shape[:2]
        det.bbox = (0, 0, w, h)
        det.motivo_fallback = det.motivo_fallback or "confianca_baixa"

    return det


# ─── Execução standalone para teste ────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import json

    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    INPUT_DIR = _PROJECT_ROOT / "output/4_quadrado_manual"
    OUT_DIR   = _PROJECT_ROOT / "output/debug_detect_joia"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    imgs = sorted(INPUT_DIR.glob("*.jpg"))[:10]
    if not imgs:
        print(f"Nenhuma imagem em {INPUT_DIR}")
        sys.exit(1)

    resultados = []
    for p in imgs:
        img = cv2.imread(str(p))
        if img is None:
            continue
        det = detectar_joia(img)
        h, w = img.shape[:2]

        r = {
            "arquivo":    p.name,
            "bbox":       det.bbox,
            "confianca":  round(det.confianca, 3),
            "area_util":  round(det.area_util, 3),
            "offset_cx":  round(det.offset_cx, 1),
            "offset_cy":  round(det.offset_cy, 1),
            "proporcao":  round(det.proporcao, 2),
            "score_d":    round(det.score_dourado, 3),
            "score_c":    round(det.score_contraste, 3),
            "score_b":    round(det.score_bordas, 3),
            "fallback":   det.motivo_fallback,
        }
        resultados.append(r)

        # Visualização: desenha bbox na imagem
        if det.bbox:
            x1, y1, x2, y2 = det.bbox
            vis = img.copy()
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 3)
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            cv2.circle(vis, (cx, cy), 8, (0, 0, 255), -1)
            cv2.circle(vis, (w // 2, h // 2), 8, (255, 0, 0), -1)
            label = f"conf={det.confianca:.2f} area={det.area_util:.0%}"
            cv2.putText(vis, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            # Downscale para salvar
            vis_small = cv2.resize(vis, (640, 640))
            cv2.imwrite(str(OUT_DIR / f"{p.stem}_det.jpg"), vis_small)

        print(f"{p.name}: conf={det.confianca:.2f} area={det.area_util:.0%} "
              f"offset=({det.offset_cx:+.0f},{det.offset_cy:+.0f}) "
              f"fallback='{det.motivo_fallback}'")

    # Salva JSON de resultados
    json_path = OUT_DIR / "resultados.json"
    json_path.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados salvos em: {OUT_DIR}")
