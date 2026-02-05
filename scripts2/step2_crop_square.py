import cv2
import numpy as np
from pathlib import Path

# Diretórios de entrada e saída
INPUT_DIR = Path("temp/passo a passo/2. aqui eu renomeio as imagens com o codigo da etiqueta")
OUTPUT_DIR = Path("scripts2/output2/recortadas")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def centralizar_e_quadrar(imagem):
    # Obter dimensões da imagem
    altura, largura = imagem.shape[:2]

    # Determinar o tamanho do lado do quadrado
    lado = max(altura, largura)

    # Criar um fundo branco quadrado
    fundo_branco = np.ones((lado, lado, 3), dtype=np.uint8) * 255

    # Calcular deslocamento para centralizar a imagem
    y_offset = (lado - altura) // 2
    x_offset = (lado - largura) // 2

    # Inserir a imagem original no centro do fundo branco
    fundo_branco[y_offset:y_offset + altura, x_offset:x_offset + largura] = imagem

    return fundo_branco

def processar_imagens():
    for img_path in sorted(INPUT_DIR.glob("*.jpg")):
        print(f"Processando: {img_path.name}")

        # Ler a imagem
        imagem = cv2.imread(str(img_path))
        if imagem is None:
            print(f"Erro ao carregar a imagem: {img_path.name}")
            continue

        # Centralizar e ajustar para formato quadrado
        imagem_quadrada = centralizar_e_quadrar(imagem)

        # Salvar a imagem processada
        output_path = OUTPUT_DIR / img_path.name
        cv2.imwrite(str(output_path), imagem_quadrada)
        print(f"Imagem salva em: {output_path}")

if __name__ == "__main__":
    processar_imagens()