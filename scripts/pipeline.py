import sys
import subprocess
from pathlib import Path


LIMPAR_SAIDAS = True
PASTAS_SAIDA = [
    Path("output/etiquetas"),
    Path("output/paints"),
    Path("output/sem_etiqueta"),
    Path("output/segmentado_rembg"),
    Path("output/final"),
]
CSV_SAIDA = Path("output/resultados.csv")

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
    run([sys.executable, "scripts/segment_rembg.py"], "Rodando segmentação (rembg/isnet)...")
    run([sys.executable, "scripts/renomear_final.py"], "Renomeando e gerando CSV...")

    print("Pipeline finalizado.")

if __name__ == "__main__":
    main()
