import sys
import subprocess
from pathlib import Path


LIMPAR_SAIDAS = True
PASTAS_SAIDA = [
    Path("output/etiquetas"),
    Path("output/paints"),
    Path("output/sem_etiqueta"),
    Path("output/quadrado_manual"),
    Path("output/segmentado_rembg"),
    Path("output/final"),
]
CSV_SAIDA = Path("output/resultados.csv")
BASELINE_VALIDACAO = Path("output/analysis/baseline_validacao.json")

def run(cmd, msg):
    print(msg)
    subprocess.run(cmd, check=True)


def limpar_saidas():
    for pasta in PASTAS_SAIDA:
        pasta.mkdir(parents=True, exist_ok=True)
        for arquivo in pasta.iterdir():
            if arquivo.is_file():
                arquivo.unlink(missing_ok=True)

    if CSV_SAIDA.exists():
        CSV_SAIDA.unlink(missing_ok=True)

def main():
    if LIMPAR_SAIDAS:
        print("Limpando saídas anteriores...")
        limpar_saidas()

    run([sys.executable, "scripts/detect_etiqueta.py"], "Rodando detecção de etiquetas...")
    run([sys.executable, "scripts/preparar_quadrado_manual.py"], "Preparando pasta quadrada manual...")
    run([sys.executable, "scripts/segment_rembg.py"], "Rodando segmentação (rembg/isnet)...")
    run([sys.executable, "scripts/renomear_final.py"], "Renomeando e gerando CSV...")
    run([sys.executable, "scripts/renomear_intermediarios.py"], "Renomeando pastas intermediárias por código...")
    run([sys.executable, "scripts/organizar_pastas_numeradas.py"], "Gerando pastas numeradas (espelho)...")

    if BASELINE_VALIDACAO.exists():
        run(
            [sys.executable, "scripts/validar_saidas.py", "--mode", "validate"],
            "Validando regressão de saídas...",
        )
    else:
        print(
            "Baseline de validação não encontrado. "
            "Crie com: python scripts/validar_saidas.py --mode create-baseline"
        )

    print("Pipeline finalizado.")

if __name__ == "__main__":
    main()
