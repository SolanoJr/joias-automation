"""
lab_config.py — Configurações centralizadas do Laboratório de Segmentação.

Todas as variáveis podem ser sobrescritas via variáveis de ambiente LAB_*.
"""
from __future__ import annotations

import os
from pathlib import Path

# ===== RAIZ DO PROJETO =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent / "project"

# ===== PASTAS =====
INPUT_DIR = Path(os.getenv("LAB_INPUT_DIR", str(PROJECT_ROOT / "input_raw/fotos_originais")))
OUTPUT_DIR = Path(os.getenv("LAB_OUTPUT_DIR", str(Path(__file__).resolve().parent / "resultados")))

# ===== CANVAS =====
CANVAS_SIZE = int(os.getenv("LAB_CANVAS_SIZE", "1024"))
TARGET_RATIO = float(os.getenv("LAB_TARGET_RATIO", "0.85"))
ALPHA_THRESHOLD = int(os.getenv("LAB_ALPHA_THRESHOLD", "10"))

# ===== AMOSTRAGEM =====
AMOSTRA_MIN = int(os.getenv("LAB_AMOSTRA_MIN", "5"))
AMOSTRA_MAX = int(os.getenv("LAB_AMOSTRA_MAX", "10"))
AMOSTRA_SEED = os.getenv("LAB_AMOSTRA_SEED", "")  # vazio = aleatório real

# ===== MORFOLOGIA =====
MORPH_OPEN_KSIZE = int(os.getenv("LAB_MORPH_OPEN_KSIZE", "3"))
MORPH_CLOSE_KSIZE = int(os.getenv("LAB_MORPH_CLOSE_KSIZE", "7"))
MIN_COMPONENT_RATIO = float(os.getenv("LAB_MIN_COMPONENT_RATIO", "0.005"))

# ===== GRABCUT =====
ENABLE_GRABCUT = os.getenv("LAB_ENABLE_GRABCUT", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
GRABCUT_ITER = int(os.getenv("LAB_GRABCUT_ITER", "3"))

# ===== REFINAMENTO POR COR =====
ENABLE_COLOR_REFINE = os.getenv("LAB_ENABLE_COLOR_REFINE", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
COLOR_WHITE_V_MIN = int(os.getenv("LAB_COLOR_WHITE_V_MIN", "230"))
COLOR_WHITE_S_MAX = int(os.getenv("LAB_COLOR_WHITE_S_MAX", "30"))

# ===== FILTRO DE ETIQUETAS (verde/branco como fundo garantido) =====
ENABLE_LABEL_FILTER = os.getenv("LAB_ENABLE_LABEL_FILTER", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
LABEL_GREEN_H_MIN = int(os.getenv("LAB_LABEL_GREEN_H_MIN", "30"))
LABEL_GREEN_H_MAX = int(os.getenv("LAB_LABEL_GREEN_H_MAX", "95"))
LABEL_GREEN_S_MIN = int(os.getenv("LAB_LABEL_GREEN_S_MIN", "25"))
LABEL_GREEN_V_MIN = int(os.getenv("LAB_LABEL_GREEN_V_MIN", "40"))
LABEL_DIST_SEPARATE = os.getenv("LAB_LABEL_DIST_SEPARATE", "1").strip().lower() in {
    "1", "true", "yes", "on",
}

# ===== REMOÇÃO DE OBJETOS DE BORDA =====
ENABLE_EDGE_OBJECT_REMOVAL = os.getenv("LAB_ENABLE_EDGE_OBJECT_REMOVAL", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
EDGE_OBJECT_METALLIC_S_MIN = int(os.getenv("LAB_EDGE_OBJECT_METALLIC_S_MIN", "30"))

# ===== REFINAMENTO POR BRILHO METÁLICO =====
ENABLE_SPECULAR_FILTER = os.getenv("LAB_ENABLE_SPECULAR_FILTER", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
SPECULAR_V_MIN = int(os.getenv("LAB_SPECULAR_V_MIN", "245"))
SPECULAR_S_MAX = int(os.getenv("LAB_SPECULAR_S_MAX", "15"))
SPECULAR_NEIGHBOR_KSIZE = int(os.getenv("LAB_SPECULAR_NEIGHBOR_KSIZE", "15"))
SPECULAR_NEIGHBOR_S_MIN = int(os.getenv("LAB_SPECULAR_NEIGHBOR_S_MIN", "20"))
SPECULAR_MIN_CLUSTER_PX = int(os.getenv("LAB_SPECULAR_MIN_CLUSTER_PX", "10"))

# ===== DETECÇÃO DE SILHUETA POR BORDAS =====
ENABLE_EDGE_MASK = os.getenv("LAB_ENABLE_EDGE_MASK", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
EDGE_CANNY_LOW = int(os.getenv("LAB_EDGE_CANNY_LOW", "30"))
EDGE_CANNY_HIGH = int(os.getenv("LAB_EDGE_CANNY_HIGH", "120"))
EDGE_DILATE_ITER = int(os.getenv("LAB_EDGE_DILATE_ITER", "3"))

# ===== ENSEMBLE =====
ENABLE_ENSEMBLE = os.getenv("LAB_ENABLE_ENSEMBLE", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
ENSEMBLE_MODELS = os.getenv("LAB_ENSEMBLE_MODELS", "isnet-general-use,u2net").split(",")
ENSEMBLE_THRESHOLD = float(os.getenv("LAB_ENSEMBLE_THRESHOLD", "0.5"))

# ===== MODELO ÚNICO =====
SINGLE_MODEL = os.getenv("LAB_MODEL", "isnet-general-use")

# ===== ZOOM =====
ZOOM_MAX = float(os.getenv("LAB_ZOOM_MAX", "3.0"))
ZOOM_MIN = float(os.getenv("LAB_ZOOM_MIN", "0.5"))

# ===== PRÉ-DETECÇÃO HEURÍSTICA =====
ENABLE_PRE_DETECT = os.getenv("LAB_ENABLE_PRE_DETECT", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
PRE_DETECT_CONF_MIN = float(os.getenv("LAB_PRE_DETECT_CONF_MIN", "0.15"))

# ===== HULL CONVEXO =====
ENABLE_CONVEX_HULL = os.getenv("LAB_ENABLE_CONVEX_HULL", "0").strip().lower() in {
    "1", "true", "yes", "on",
}

# ===== DIAGNÓSTICO =====
ENABLE_DIAGNOSTICS = os.getenv("LAB_ENABLE_DIAGNOSTICS", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
