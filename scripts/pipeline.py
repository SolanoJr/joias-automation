import os
import csv
import sys
import subprocess
ETIQUETAS_DIR = "output/etiquetas"
CSV_PATH = "output/resultados.csv"

def rodar_detect_etiqueta():
    subprocess.run(
        [sys.executable, "scripts/detect_etiqueta.py"],
        check=True
    )



def rodar_barcode():
    resultados = []

    from barcode_etiqueta import ler_barcode_imagem

    for nome in sorted(os.listdir(ETIQUETAS_DIR)):
        if not nome.lower().endswith(".jpg"):
            continue

        caminho = os.path.join(ETIQUETAS_DIR, nome)
        codigo = ler_barcode_imagem(caminho)

        resultados.append((nome, codigo))

    return resultados


def salvar_csv(resultados):
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["imagem", "codigo"])

        for imagem, codigo in resultados:
            writer.writerow([imagem, codigo])


def main():
    print("Rodando detecção de etiquetas...")
    rodar_detect_etiqueta()

    print("Lendo códigos de barras...")
    resultados = rodar_barcode()

    print("Salvando CSV...")
    salvar_csv(resultados)

    print("Pipeline finalizado.")


if __name__ == "__main__":
    main()
