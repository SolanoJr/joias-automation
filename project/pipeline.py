import sys
import os
import argparse
import subprocess
import time
import runpy
from pathlib import Path


LIMPAR_SAIDAS = True
PASTAS_SAIDA = [
    Path("output/1_etiquetas"),
    Path("output/2_paints"),
    Path("output/3_sem_etiqueta"),
    Path("output/4_quadrado_manual"),
    Path("output/5_segmentado_rembg"),
    Path("output/6_final"),
]
CSV_SAIDA = Path("output/resultados.csv")
BASELINE_VALIDACAO = Path("output/analysis/baseline_validacao.json")
TEST_LIMIT_PADRAO = 10
INPUT_DIR = Path("input_raw/fotos_originais")
LISTA_REPROCESSAR = Path("output/analysis/lista_reprocessar_sem_etiqueta.txt")
INPROCESS_THRESHOLD_PADRAO = 20

def run(cmd, msg, env_extra=None, step_idx: int | None = None, step_total: int | None = None):
    prefixo = ""
    if step_idx is not None and step_total is not None:
        prefixo = f"[{step_idx}/{step_total}] "

    print(f"{prefixo}{msg}")
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, env=env)
    dt = time.perf_counter() - t0
    print(f"{prefixo}Concluído em {dt:.1f}s")


def run_inprocess(script_path: str, msg, env_extra=None, step_idx: int | None = None, step_total: int | None = None):
    prefixo = ""
    if step_idx is not None and step_total is not None:
        prefixo = f"[{step_idx}/{step_total}] "

    print(f"{prefixo}{msg}")
    old_env: dict[str, str | None] = {}
    if env_extra:
        for k, v in env_extra.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v

    script_dir = str(Path(script_path).resolve().parent)
    inseriu_path = False
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
        inseriu_path = True

    t0 = time.perf_counter()
    try:
        runpy.run_path(script_path, run_name="__main__")
    finally:
        if inseriu_path:
            try:
                sys.path.remove(script_dir)
            except ValueError:
                pass
        if env_extra:
            for k in env_extra.keys():
                antigo = old_env.get(k)
                if antigo is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = antigo

    dt = time.perf_counter() - t0
    print(f"{prefixo}Concluído em {dt:.1f}s")


def _estimar_total_entrada(modo_full: bool, limite_teste: int) -> int:
    imgs = sorted([*INPUT_DIR.glob("*.jpg"), *INPUT_DIR.glob("*.jpeg"), *INPUT_DIR.glob("*.png")])

    usar_lista = (os.getenv("USE_LISTA_REPROCESSAR", "0").strip().lower() in {"1", "true", "yes", "on"})
    if usar_lista and LISTA_REPROCESSAR.exists():
        brutos = [ln.strip() for ln in LISTA_REPROCESSAR.read_text(encoding="utf-8").splitlines()]
        lista_nomes = {n for n in brutos if n and not n.startswith("#")}
        if lista_nomes:
            imgs = [p for p in imgs if p.name in lista_nomes]

    if not modo_full and limite_teste > 0:
        imgs = imgs[:limite_teste]

    return len(imgs)


def limpar_saidas():
    for pasta in PASTAS_SAIDA:
        pasta.mkdir(parents=True, exist_ok=True)
        for arquivo in pasta.iterdir():
            if arquivo.is_file():
                arquivo.unlink(missing_ok=True)

    if CSV_SAIDA.exists():
        CSV_SAIDA.unlink(missing_ok=True)

def main(
    modo_full: bool = False,
    limite_teste: int = TEST_LIMIT_PADRAO,
    mode: str = "auto",
    inprocess_threshold: int = INPROCESS_THRESHOLD_PADRAO,
    incremental: bool = False,
):
    t_inicio = time.perf_counter()

    if LIMPAR_SAIDAS and not incremental:
        print("Limpando saídas anteriores...")
        limpar_saidas()
    elif incremental:
        print("Modo incremental: preservando saídas e usando cache por arquivo.")

    detect_env = {}
    seg_env = {}
    if not modo_full and limite_teste > 0:
        detect_env["PROCESS_LIMIT"] = str(limite_teste)
        print(f"Modo teste rápido: limitando entrada para {limite_teste} arquivo(s)")
    else:
        print("Modo completo: processando todos os arquivos")

    if incremental:
        detect_env["DETECT_SKIP_IF_UPTODATE"] = "1"
        detect_env["DETECT_SKIP_BY_EXISTENCE"] = "1"
        seg_env["SEG_SKIP_IF_UPTODATE"] = "1"
        seg_env["SEG_SKIP_BY_EXISTENCE"] = "1"
        seg_env["PREP_SKIP_IF_UPTODATE"] = "1"
        seg_env["PREP_SKIP_BY_EXISTENCE"] = "1"
        seg_env["RENOMEAR_FINAL_CANONICAL_ONLY"] = "1"
        seg_env["LER_CODIGO_CANONICAL_ONLY"] = "1"
        seg_env["KEEP_CANONICAL_INTERMEDIATES"] = "1"

    qtd_estimado = _estimar_total_entrada(modo_full, limite_teste)
    use_inprocess = mode == "inprocess" or (mode == "auto" and qtd_estimado <= inprocess_threshold)
    exec_desc = "in-process" if use_inprocess else "subprocess"
    print(f"Modo de execução: {exec_desc} (itens estimados={qtd_estimado}, threshold={inprocess_threshold})")

    runner = run_inprocess if use_inprocess else run

    runner(
        "scripts/1_detect_etiqueta.py" if use_inprocess else [sys.executable, "scripts/1_detect_etiqueta.py"],
        "Rodando detecção de etiquetas...",
        env_extra=detect_env,
        step_idx=1,
        step_total=5,
    )
    runner(
        "scripts/2_preparar_quadrado_manual.py" if use_inprocess else [sys.executable, "scripts/2_preparar_quadrado_manual.py"],
        "Preparando pasta quadrada manual...",
        env_extra=seg_env if incremental else None,
        step_idx=2,
        step_total=5,
    )
    runner(
        "scripts/3_segment_rembg.py" if use_inprocess else [sys.executable, "scripts/3_segment_rembg.py"],
        "Rodando segmentação (rembg/isnet)...",
        env_extra=seg_env,
        step_idx=3,
        step_total=5,
    )
    runner(
        "scripts/4_renomear_final.py" if use_inprocess else [sys.executable, "scripts/4_renomear_final.py"],
        "Renomeando e gerando CSV...",
        env_extra=seg_env if incremental else None,
        step_idx=4,
        step_total=5,
    )
    runner(
        "scripts/5_renomear_intermediarios.py" if use_inprocess else [sys.executable, "scripts/5_renomear_intermediarios.py"],
        "Renomeando pastas intermediárias por código...",
        env_extra=seg_env if incremental else None,
        step_idx=5,
        step_total=5,
    )

    if modo_full:
        if BASELINE_VALIDACAO.exists():
            run(
                [sys.executable, "scripts/6_validar_saidas.py", "--mode", "validate"],
                "Validando regressão de saídas...",
            )
        else:
            print(
                "Baseline de validação não encontrado. "
                "Crie com: python scripts/validar_saidas.py --mode create-baseline"
            )
    else:
        print("Validação automática pulada no modo teste rápido (use --full para validar baseline).")

    dt_total = time.perf_counter() - t_inicio
    print(f"Pipeline finalizado em {dt_total:.1f}s.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Processa todos os arquivos (sem limite de teste)")
    parser.add_argument("--limit", type=int, default=TEST_LIMIT_PADRAO, help=f"Limite de arquivos no modo teste rápido (padrão: {TEST_LIMIT_PADRAO})")
    parser.add_argument("--mode", choices=["auto", "subprocess", "inprocess"], default="auto", help="Modo de execução do pipeline")
    parser.add_argument("--inprocess-threshold", type=int, default=INPROCESS_THRESHOLD_PADRAO, help=f"Threshold de itens para auto usar in-process (padrão: {INPROCESS_THRESHOLD_PADRAO})")
    parser.add_argument("--incremental", action="store_true", help="Preserva saídas e ativa cache de detecção/segmentação para reruns rápidos")
    args = parser.parse_args()

    main(
        modo_full=args.full,
        limite_teste=args.limit,
        mode=args.mode,
        inprocess_threshold=args.inprocess_threshold,
        incremental=args.incremental,
    )
