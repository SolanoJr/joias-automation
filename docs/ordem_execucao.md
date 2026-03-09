# Ordem de Execução (Numerada)

## Scripts principais (ordem)
- 1) [scripts/1_detect_etiqueta.py](scripts/1_detect_etiqueta.py) -> chama [scripts/detect_etiqueta.py](scripts/detect_etiqueta.py)
- 2) [scripts/2_preparar_quadrado_manual.py](scripts/2_preparar_quadrado_manual.py) -> chama [scripts/preparar_quadrado_manual.py](scripts/preparar_quadrado_manual.py)
- 3) [scripts/3_segment_rembg.py](scripts/3_segment_rembg.py) -> chama [scripts/segment_rembg.py](scripts/segment_rembg.py)
- 4) [scripts/4_renomear_final.py](scripts/4_renomear_final.py) -> chama [scripts/renomear_final.py](scripts/renomear_final.py)
- 5) [scripts/5_renomear_intermediarios.py](scripts/5_renomear_intermediarios.py) -> chama [scripts/renomear_intermediarios.py](scripts/renomear_intermediarios.py)
- 6) [scripts/6_validar_saidas.py](scripts/6_validar_saidas.py) -> chama [scripts/validar_saidas.py](scripts/validar_saidas.py)

## Pastas de saída numeradas (espelho)
Geradas automaticamente pelo script [scripts/organizar_pastas_numeradas.py](scripts/organizar_pastas_numeradas.py):

- [output/1_etiquetas](output/1_etiquetas)  <- [output/etiquetas](output/etiquetas)
- [output/2_paints](output/2_paints)  <- [output/paints](output/paints)
- [output/3_sem_etiqueta](output/3_sem_etiqueta)  <- [output/sem_etiqueta](output/sem_etiqueta)
- [output/4_quadrado_manual](output/4_quadrado_manual)  <- [output/quadrado_manual](output/quadrado_manual)
- [output/5_segmentado_rembg](output/5_segmentado_rembg)  <- [output/segmentado_rembg](output/segmentado_rembg)
- [output/6_final](output/6_final)  <- [output/final](output/final)

## Observação
- O pipeline continua usando os caminhos canônicos (`output/etiquetas`, `output/paints`, etc.) para manter compatibilidade.
- As pastas numeradas são uma visualização organizada da mesma saída final.
