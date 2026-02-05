import cv2
from extrair_joia import extrair_mascara_joia, recortar_joia
from padronizar_joia import centralizar_em_fundo_branco

img = cv2.imread("input_raw/fotos_originais/20260107_132828.jpg")

mask, bbox = extrair_mascara_joia(img)

if mask is None:
    print("Falhou extração")
    exit()

joia = recortar_joia(img, mask, bbox)
final = centralizar_em_fundo_branco(joia)

cv2.imwrite("output/teste_final.jpg", final)
print("Imagem salva")
