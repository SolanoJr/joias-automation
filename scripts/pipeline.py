import sys
import subprocess

def run(cmd, msg):
    print(msg)
    subprocess.run(cmd, check=True)

def main():
    run([sys.executable, "scripts/detect_etiqueta.py"], "Rodando detecção de etiquetas...")
    run([sys.executable, "scripts/segment_rembg.py"], "Rodando segmentação (rembg/isnet)...")
    run([sys.executable, "scripts/renomear_final.py"], "Renomeando e gerando CSV...")

    print("Pipeline finalizado.")

if __name__ == "__main__":
    main()
