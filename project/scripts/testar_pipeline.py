"""
testar_pipeline.py — Suite de testes rápidos do pipeline joias-automation

Roda em segundos usando os crops já existentes em output/1_etiquetas/ e output/2_paints/.
NÃO precisa rodar o pipeline completo para detectar problemas.

Uso:
    python scripts/testar_pipeline.py              # todos os testes
    python scripts/testar_pipeline.py --ambiente   # só verificações de ambiente
    python scripts/testar_pipeline.py --etiquetas  # só leitura de etiquetas
    python scripts/testar_pipeline.py --paints     # só leitura de paints
    python scripts/testar_pipeline.py --logica     # só lógica interna (sem I/O)
    python scripts/testar_pipeline.py --csv        # só integridade do CSV
    python scripts/testar_pipeline.py --deteccao   # roda YOLO nas 2 primeiras imagens (~30s)
    python scripts/testar_pipeline.py --verbose    # mostra detalhes de cada item
"""

import sys
import os
import time
import argparse
from pathlib import Path

# Garante que scripts/ está no path e cwd = project/
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))
os.chdir(scripts_dir.parent)

# ─────────────────────────────────────────────
# Cores ANSI
# ─────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def _ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def _fail(msg): print(f"  {RED}✗{RESET} {msg}")
def _warn(msg): print(f"  {YELLOW}⚠{RESET} {msg}")
def _info(msg): print(f"  {CYAN}→{RESET} {msg}")

# ─────────────────────────────────────────────
# Contadores (dict para evitar problemas de escopo)
# ─────────────────────────────────────────────
R = {"passed": 0, "failed": 0, "warned": 0}

def _assert(cond: bool, msg_ok: str, msg_fail: str) -> bool:
    if cond:
        _ok(msg_ok)
        R["passed"] += 1
    else:
        _fail(msg_fail)
        R["failed"] += 1
    return cond

def _add_warn(msg: str):
    _warn(msg)
    R["warned"] += 1


# ══════════════════════════════════════════════
# BLOCO 0 — Verificações de ambiente (~1s)
# ══════════════════════════════════════════════
def testar_ambiente():
    print(f"\n{BOLD}[0/4] Verificações de ambiente{RESET}")

    # Modelo YOLO
    model_path = Path("models/best.pt")
    _assert(
        model_path.exists(),
        f"Modelo YOLO encontrado: {model_path}",
        f"Modelo YOLO NÃO encontrado: {model_path} — necessário para detecção"
    )

    # Tesseract
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        _ok(f"Tesseract acessível: versão {version}")
        R["passed"] += 1
    except Exception as e:
        _fail(f"Tesseract não acessível: {e}")
        R["failed"] += 1

    # pyzbar
    try:
        import pyzbar  # noqa: F401
        _ok("pyzbar importável")
        R["passed"] += 1
    except ImportError:
        _warn("pyzbar não instalado — leitura de barcode usará apenas OpenCV (menor taxa)")
        R["warned"] += 1

    # Pasta de entrada
    input_dir = Path("input_raw/fotos_originais")
    _assert(
        input_dir.exists(),
        f"Pasta de entrada existe: {input_dir}",
        f"Pasta de entrada NÃO existe: {input_dir}"
    )

    # Contagem de imagens
    if input_dir.exists():
        imgs = sorted([
            *input_dir.glob("*.jpg"),
            *input_dir.glob("*.jpeg"),
            *input_dir.glob("*.png"),
        ])
        if imgs:
            _ok(f"Imagens na pasta de entrada: {len(imgs)}")
            R["passed"] += 1
        else:
            _warn(f"Nenhuma imagem encontrada em {input_dir}")
            R["warned"] += 1


# ══════════════════════════════════════════════
# BLOCO EXTRA — Detecção YOLO (~30s)
# ══════════════════════════════════════════════
def testar_deteccao(verbose: bool = False):
    print(f"\n{BOLD}[extra] Detecção YOLO nas primeiras 2 imagens (~30s){RESET}")

    input_dir = Path("input_raw/fotos_originais")
    model_path = Path("models/best.pt")

    if not input_dir.exists():
        _add_warn(f"Pasta {input_dir} não existe — pulando teste de detecção")
        return

    if not model_path.exists():
        _add_warn(f"Modelo {model_path} não encontrado — pulando teste de detecção")
        return

    imgs = sorted([
        *input_dir.glob("*.jpg"),
        *input_dir.glob("*.jpeg"),
        *input_dir.glob("*.png"),
    ])[:2]

    if not imgs:
        _add_warn(f"Nenhuma imagem em {input_dir} — pulando teste de detecção")
        return

    try:
        from ultralytics import YOLO
    except ImportError:
        _fail("ultralytics não instalado — não é possível testar detecção")
        R["failed"] += 1
        return

    _info(f"Carregando modelo {model_path}...")
    t0 = time.perf_counter()
    try:
        model = YOLO(str(model_path))
    except Exception as e:
        _fail(f"Erro ao carregar modelo: {e}")
        R["failed"] += 1
        return

    total_deteccoes = 0
    classes_encontradas: set[str] = set()

    for img_path in imgs:
        _info(f"Rodando YOLO em {img_path.name}...")
        try:
            results = model(str(img_path), verbose=False)
            for r in results:
                n = len(r.boxes) if r.boxes is not None else 0
                total_deteccoes += n
                if r.boxes is not None and r.names:
                    for cls_id in r.boxes.cls.tolist():
                        classes_encontradas.add(r.names[int(cls_id)])
                if verbose:
                    _info(f"  {img_path.name}: {n} detecção(ões) — {list(classes_encontradas)}")
        except Exception as e:
            _fail(f"Erro ao rodar YOLO em {img_path.name}: {e}")
            R["failed"] += 1
            return

    dt = time.perf_counter() - t0
    clases_alvo = {"etiqueta", "paint"}
    encontrou_alvo = bool(classes_encontradas & clases_alvo)

    _assert(
        total_deteccoes > 0,
        f"YOLO detectou {total_deteccoes} objeto(s) em {len(imgs)} imagem(ns) ({dt:.1f}s)",
        f"YOLO não detectou nada em {len(imgs)} imagem(ns) — verifique o modelo e as imagens"
    )
    _assert(
        encontrou_alvo,
        f"Classes alvo detectadas: {classes_encontradas & clases_alvo}",
        f"Nenhuma classe alvo (etiqueta/paint) detectada — classes encontradas: {classes_encontradas or 'nenhuma'}"
    )


# ══════════════════════════════════════════════
# BLOCO 1 — Lógica pura (sem I/O, ~1s)
# ══════════════════════════════════════════════
def testar_logica():
    print(f"\n{BOLD}[1/4] Lógica interna (sem I/O){RESET}")

    from ler_codigo import _is_valid_candidate, _normalizar_codigo

    # ── _is_valid_candidate ──
    casos_validos = [
        "BR1204039",   # 2 letras + 7 dígitos
        "CR3984506",
        "PL2401606",
        "CJ0244526",
        "BR1209084",
        "1200090006",  # 10 dígitos numéricos
        "1201280006",
    ]
    casos_invalidos = [
        None, "", "BR", "123",
        "ABCDEFGHIJ",   # sem dígitos
        "12345",        # muito curto
        "12345678901",  # 11 dígitos
    ]

    erros_validos = [c for c in casos_validos if not _is_valid_candidate(c)]
    erros_invalidos = [c for c in casos_invalidos if _is_valid_candidate(c)]

    _assert(
        len(erros_validos) == 0,
        f"_is_valid_candidate: {len(casos_validos)} válidos aceitos",
        f"_is_valid_candidate rejeitou indevidamente: {erros_validos}"
    )
    _assert(
        len(erros_invalidos) == 0,
        f"_is_valid_candidate: {len(casos_invalidos)} inválidos rejeitados",
        f"_is_valid_candidate aceitou indevidamente: {erros_invalidos}"
    )

    # ── _normalizar_codigo ──
    casos_norm = [
        ("BR1204039",                    "BR1204039"),
        ("br1204039",                    "BR1204039"),   # lowercase
        ("  CR3984506  ",                "CR3984506"),   # espaços
        ("TURAL ATA\nBR1204039\n| 63d", "BR1204039"),   # texto sujo OCR (newline separado)
        ("UTA\nBR1204039",              "BR1204039"),   # prefixo grudado antes do newline
        ("1200090006",                   "1200090006"),  # 10 dígitos
        ("texto 1200090006 mais",        "1200090006"),  # dígitos no meio
        (None,                           None),
        ("",                             None),
        ("ABCDE",                        None),
    ]
    erros_norm = []
    for entrada, esperado in casos_norm:
        resultado = _normalizar_codigo(entrada)
        if resultado != esperado:
            erros_norm.append(f"{entrada!r} → {resultado!r} (esperado {esperado!r})")

    _assert(
        len(erros_norm) == 0,
        f"_normalizar_codigo: {len(casos_norm)} casos corretos",
        f"_normalizar_codigo com erros:\n    " + "\n    ".join(erros_norm)
    )


# ══════════════════════════════════════════════
# BLOCO 2 — Leitura de paints (~10-60s)
# ══════════════════════════════════════════════
def testar_paints(verbose: bool = False):
    print(f"\n{BOLD}[2/4] Leitura de paints (output/2_paints/){RESET}")

    paints_dir = Path("output/2_paints")
    if not paints_dir.exists() or not list(paints_dir.glob("*.jpg")):
        _add_warn("output/2_paints/ vazia — rode o pipeline primeiro (etapa 1)")
        return

    from ler_codigo import _ocr_paint, _is_valid_candidate, _normalizar_codigo

    paints = sorted(paints_dir.glob("*.jpg"))
    _info(f"Testando {len(paints)} crops de paint...")

    lidos, falhos, tempos = 0, [], []

    for p in paints:
        t0 = time.perf_counter()
        resultado = _ocr_paint(p, deadline=None)
        dt = time.perf_counter() - t0
        tempos.append(dt)

        codigo_norm = _normalizar_codigo(resultado)
        valido = _is_valid_candidate(codigo_norm)

        if valido:
            lidos += 1
            if verbose:
                _ok(f"{p.name}: {codigo_norm} ({dt:.2f}s)")
        else:
            falhos.append((p.name, resultado, dt))
            if verbose:
                _fail(f"{p.name}: OCR={resultado!r} → norm={codigo_norm!r} ({dt:.2f}s)")

    taxa = lidos / len(paints) * 100
    media_t = sum(tempos) / len(tempos)

    _assert(
        taxa >= 80,
        f"Paints lidos: {lidos}/{len(paints)} ({taxa:.0f}%) — média {media_t:.2f}s/crop",
        f"Taxa baixa de paints: {lidos}/{len(paints)} ({taxa:.0f}%) — esperado ≥80%"
    )

    if falhos and not verbose:
        _info(f"Falhos ({len(falhos)}): {', '.join(n for n,_,_ in falhos[:5])}" +
              (" ..." if len(falhos) > 5 else ""))

    lentos = [(n, t) for n, _, t in falhos if t > 3.0]
    if lentos:
        _add_warn(f"{len(lentos)} paints demoraram >3s (timeout): {[n for n,_ in lentos[:3]]}")


# ══════════════════════════════════════════════
# BLOCO 3 — Leitura de etiquetas (~30-120s)
# ══════════════════════════════════════════════
def testar_etiquetas(verbose: bool = False):
    print(f"\n{BOLD}[3/4] Leitura de etiquetas (output/1_etiquetas/){RESET}")

    eti_dir = Path("output/1_etiquetas")
    if not eti_dir.exists() or not list(eti_dir.glob("*.jpg")):
        _add_warn("output/1_etiquetas/ vazia — rode o pipeline primeiro (etapa 1)")
        return

    from barcode_etiqueta import ler_barcode_imagem
    from ler_codigo import _ocr_etiqueta, _is_valid_candidate, _normalizar_codigo

    etiquetas = sorted(eti_dir.glob("*.jpg"))
    _info(f"Testando {len(etiquetas)} crops de etiqueta...")

    barcode_ok, ocr_ok, falhos = 0, 0, []

    for e in etiquetas:
        # 1) Tenta barcode (rápido)
        t0 = time.perf_counter()
        bc_raw, meta = ler_barcode_imagem(e, return_meta=True, min_digits=7)
        bc_norm = _normalizar_codigo(bc_raw)
        bc_valido = _is_valid_candidate(bc_norm)
        dt_bc = time.perf_counter() - t0

        if bc_valido:
            barcode_ok += 1
            if verbose:
                _ok(f"{e.name}: barcode={bc_norm} ({dt_bc:.2f}s)")
            continue

        # 2) Tenta OCR de texto (mais lento) — com deadline de 8s por etiqueta
        t1 = time.perf_counter()
        deadline_ocr = t1 + 8.0
        ocr_raw = _ocr_etiqueta(e, nivel_confianca="baixa", deadline=deadline_ocr)
        ocr_norm = _normalizar_codigo(ocr_raw)
        ocr_valido = _is_valid_candidate(ocr_norm)
        dt_ocr = time.perf_counter() - t1

        if ocr_valido:
            ocr_ok += 1
            if verbose:
                _ok(f"{e.name}: ocr_texto={ocr_norm} ({dt_ocr:.2f}s)")
            continue

        falhos.append((e.name, bc_raw, ocr_raw))
        if verbose:
            _fail(f"{e.name}: barcode={bc_raw!r} | ocr={ocr_raw!r}")

    total_lidos = barcode_ok + ocr_ok
    taxa = total_lidos / len(etiquetas) * 100

    _assert(
        taxa >= 50,
        f"Etiquetas lidas: {total_lidos}/{len(etiquetas)} ({taxa:.0f}%) — barcode={barcode_ok} ocr={ocr_ok}",
        f"Taxa baixa de etiquetas: {total_lidos}/{len(etiquetas)} ({taxa:.0f}%) — esperado ≥50%"
    )

    if falhos:
        _info(f"Diagnóstico das {len(falhos)} etiquetas não lidas:")
        for nome, bc, ocr in falhos[:8]:
            bc_p  = repr(bc)[:50]  if bc  else "None"
            ocr_p = repr(ocr)[:60] if ocr else "None"
            _info(f"  {nome}")
            _info(f"    barcode_raw = {bc_p}")
            _info(f"    ocr_raw     = {ocr_p}")
        if len(falhos) > 8:
            _info(f"  ... e mais {len(falhos)-8} etiquetas")


# ══════════════════════════════════════════════
# BLOCO 4 — Integridade do CSV (~1s)
# ══════════════════════════════════════════════
def testar_csv(verbose: bool = False):
    print(f"\n{BOLD}[4/4] Integridade do CSV e saídas{RESET}")

    csv_path = Path("output/resultados.csv")
    if not csv_path.exists():
        _add_warn("output/resultados.csv não encontrado — rode o pipeline primeiro")
        return

    import csv as csv_mod

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv_mod.DictReader(f))

    if not rows:
        _assert(False, "", "CSV vazio")
        return

    total      = len(rows)
    renomeados = [r for r in rows if r["status"] == "RENOMEADO"]
    semcod     = [r for r in rows if r["status"] == "SEM_CODIGO_COPIADO"]
    taxa       = len(renomeados) / total * 100

    _assert(total > 0, f"CSV tem {total} linhas", "CSV vazio")
    _assert(
        taxa >= 50,
        f"Taxa de sucesso: {len(renomeados)}/{total} ({taxa:.0f}%) renomeados",
        f"Taxa baixa: {len(renomeados)}/{total} ({taxa:.0f}%) — esperado ≥50%"
    )

    # Arquivos finais existem?
    faltando = [r["arquivo_final"] for r in rows
                if r.get("arquivo_final") and not Path(r["arquivo_final"]).exists()]
    _assert(
        len(faltando) == 0,
        f"Todos os {total} arquivos finais existem",
        f"{len(faltando)} arquivos finais no CSV não existem no disco"
    )

    # Duplicatas de código
    codigos = [r["codigo"] for r in renomeados if r["codigo"]]
    duplicatas = sorted({c for c in codigos if codigos.count(c) > 1})
    _assert(
        len(duplicatas) == 0,
        "Sem códigos duplicados",
        f"Códigos duplicados: {duplicatas[:5]}"
    )

    # Diagnóstico dos SEMCOD
    if semcod:
        _info(f"{len(semcod)} imagens sem código — classificando causas...")
        eti_dir = Path("output/1_etiquetas")
        pnt_dir = Path("output/2_paints")

        tem_eti, tem_pnt, sem_nada = [], [], []
        for r in semcod:
            base = r["base"]
            has_e = eti_dir.exists() and bool(list(eti_dir.glob(f"*{base}*")))
            has_p = pnt_dir.exists() and bool(list(pnt_dir.glob(f"*{base}*")))
            if has_e:
                tem_eti.append(base)
            elif has_p:
                tem_pnt.append(base)
            else:
                sem_nada.append(base)

        if tem_eti:
            _add_warn(f"  {len(tem_eti)} têm etiqueta mas leitura falhou → investigar OCR/barcode: {tem_eti[:3]}")
        if tem_pnt:
            _add_warn(f"  {len(tem_pnt)} têm paint mas OCR falhou → investigar _ocr_paint: {tem_pnt[:3]}")
        if sem_nada:
            _info(f"  {len(sem_nada)} sem detecção (YOLO não detectou nada): {sem_nada[:3]}")


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Testes rápidos do pipeline joias-automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python scripts/testar_pipeline.py                  # tudo
  python scripts/testar_pipeline.py --ambiente       # só ambiente (~1s)
  python scripts/testar_pipeline.py --logica         # só lógica (~1s)
  python scripts/testar_pipeline.py --csv            # só CSV (~1s)
  python scripts/testar_pipeline.py --deteccao       # YOLO nas 2 primeiras imagens (~30s)
  python scripts/testar_pipeline.py --paints --verbose
  python scripts/testar_pipeline.py --etiquetas --verbose
        """
    )
    parser.add_argument("--ambiente",  action="store_true")
    parser.add_argument("--logica",    action="store_true")
    parser.add_argument("--paints",    action="store_true")
    parser.add_argument("--etiquetas", action="store_true")
    parser.add_argument("--csv",       action="store_true")
    parser.add_argument("--deteccao",  action="store_true", help="Roda YOLO nas 2 primeiras imagens (~30s)")
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    rodar_tudo = not any([args.ambiente, args.logica, args.paints, args.etiquetas, args.csv, args.deteccao])

    print(f"\n{BOLD}{CYAN}══════════════════════════════════════════{RESET}")
    print(f"{BOLD}{CYAN}  joias-automation — Testes Rápidos{RESET}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════{RESET}")

    t0 = time.perf_counter()

    # Ambiente sempre roda primeiro (quando tudo ou --ambiente explícito)
    if rodar_tudo or args.ambiente:  testar_ambiente()
    if rodar_tudo or args.logica:    testar_logica()
    if rodar_tudo or args.paints:    testar_paints(verbose=args.verbose)
    if rodar_tudo or args.etiquetas: testar_etiquetas(verbose=args.verbose)
    if rodar_tudo or args.csv:       testar_csv(verbose=args.verbose)
    if args.deteccao:                testar_deteccao(verbose=args.verbose)

    dt = time.perf_counter() - t0
    cor = GREEN if R["failed"] == 0 else RED

    print(f"\n{BOLD}{'═'*42}{RESET}")
    print(f"{BOLD}{cor}  {R['passed']} OK  |  {R['failed']} FALHAS  |  {R['warned']} AVISOS{RESET}")
    print(f"  Tempo: {dt:.1f}s")
    print(f"{BOLD}{'═'*42}{RESET}\n")

    sys.exit(0 if R["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
