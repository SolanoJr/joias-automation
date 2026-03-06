# Ideias V2 (backlog)

Objetivo final: imagem quadrada com joia centralizada em fundo branco e nome correto do código.

## 1) Leitura de código (mudar estratégia)
- Trocar foco de barcode puro para OCR de etiqueta dedicado.
- Detectar primeiro a região do código da etiqueta (modelo leve de detecção).
- OCR por ensemble (Tesseract + EasyOCR/PaddleOCR) e votação.
- Normalizar para 10 dígitos e validar por regras do negócio.
- Marcar confiança por leitura (`alta`, `media`, `baixa`) e só renomear automático em confiança alta.

## 2) Segmentação de joia
- Modo produção: priorizar preservar joia (fallback para original em caso de dúvida).
- Criar score de presença de joia e flag de revisão para casos críticos.
- Treinar modelo específico de segmentação para joias (dataset próprio), reduzindo dependência do rembg genérico.

## 3) Avaliação e treino
- Criar base verdade-terreno: `imagem_base -> codigo_correto`.
- Medir acurácia por fonte (`paint`, `etiqueta_ocr`, etc.).
- Salvar dataset de erros para retreino incremental.

## 4) Fluxo operacional
- Dois modos:
  - `modo_rapido`: mais cobertura, aceita mais leituras.
  - `modo_confiavel`: mais conservador, evita nome errado.
- Sempre gerar relatório de revisão para casos `SEM_CODIGO` e baixa confiança.
