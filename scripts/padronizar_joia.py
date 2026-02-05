import cv2
import numpy as np

def centralizar_em_fundo_branco(img, margem=20):
    h, w = img.shape[:2]
    lado = max(h, w) + margem * 2

    fundo = np.ones((lado, lado, 3), dtype=np.uint8) * 255
    kernel = np.ones((9, 9), np.uint8)

    y_offset = (lado - h) // 2
    x_offset = (lado - w) // 2

    fundo[
        y_offset:y_offset+h,
        x_offset:x_offset+w
    ] = img

    return fundo
