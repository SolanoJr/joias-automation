# Progresso do Projeto: Automação de Processamento de Joias

## Objetivo Final
Criar um programa que:
1. Leia imagens de joias.
2. Extraia o código da etiqueta (ou código desenhado no Paint).
3. Renomeie as imagens com base no código extraído.
4. Recorte a joia, centralize-a e coloque-a em um fundo branco quadrado.

## Estrutura do Projeto
- **Entrada:** As imagens originais estão em `temp/passo a passo/1. recebo a imagem dessa forma`.
- **Saída:** Resultados intermediários e finais são salvos em `scripts2/output2`.

## Identidade do Projeto
- Nome do Assistente: GC
- Nome do Usuário: SolanoJr

## Passos Realizados
### Passo 1: Leitura de Código de Barras
- **Script:** `scripts2/step1_barcode_reader.py`
- **Entrada:** `temp/passo a passo/1. recebo a imagem dessa forma`
- **Saída:** Imagens renomeadas com o código da etiqueta em `scripts2/output2/barcodes`.

### Passo 2: Recorte e Centralização
- **Script:** `scripts2/step2_crop_square.py`
- **Entrada:** `temp/passo a passo/2. aqui eu renomeio as imagens com o codigo da etiqueta`
- **Saída:** Imagens centralizadas e ajustadas para formato quadrado em `scripts2/output2/recortadas`.

## Próximos Passos
1. Revisar e lapidar os scripts existentes, se necessário.
2. Implementar o próximo passo do pipeline com base nas pastas e objetivos definidos.

## Observações
- O caminho das pastas foi decorado para facilitar a continuidade: `temp/passo a passo`.
- Dependências instaladas: `opencv-python`, `pyzbar`.

## Como Configurar e Rodar o Projeto em Outro Computador

### Dependências Necessárias
Certifique-se de ter as seguintes dependências instaladas:
- Python 3.8 ou superior
- Bibliotecas Python:
  - `numpy`
  - `Pillow`
  - `rembg`
  - `opencv-python`
  - `pyzbar`

### Passos para Configuração
1. Clone o repositório:
   ```bash
   git clone <URL_DO_REPOSITORIO>
   ```
2. Navegue até o diretório do projeto:
   ```bash
   cd joias_automation
   ```
3. Crie e ative um ambiente virtual (recomendado):
   ```bash
   python -m venv venv
   source venv/bin/activate # No Windows: venv\Scripts\activate
   ```
4. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

### Executando o Projeto
1. Certifique-se de que as imagens de entrada estão na pasta correta (`input_raw/fotos_originais`).
2. Execute o script principal:
   ```bash
   python scripts/pipeline.py
   ```
3. Verifique os resultados na pasta `output`.

### Observação
Se encontrar erros, consulte os logs ou revise os scripts na pasta `scripts` para ajustes.

---

# Joias Automation - Guia de Configuração e Execução

Este documento fornece instruções detalhadas para configurar e executar o projeto em outro computador. Inclui links para downloads necessários e explicações sobre os scripts e fluxos de trabalho.

---

## Requisitos do Sistema

- **Sistema Operacional**: Windows 10 ou superior
- **Python**: Versão 3.10 ou superior
- **Git**: Para controle de versão
- **Git LFS**: Para gerenciar arquivos grandes

---

## Passo 1: Clonar o Repositório

1. Instale o Git: [Download Git](https://git-scm.com/downloads)
2. Instale o Git LFS: [Download Git LFS](https://git-lfs.github.com/)
3. Clone o repositório:
   ```bash
   git clone https://github.com/SolanoJr/joias-automation.git
   cd joias-automation
   git lfs install
   ```

---

## Passo 2: Configurar o Ambiente Python

1. Instale o Python: [Download Python](https://www.python.org/downloads/)
2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

---

## Passo 3: Baixar Modelos Necessários

1. **SAM Model**:
   - Baixe o modelo SAM ViT-B: [sam_vit_b.pth](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth)
   - Salve em `models/sam_vit_b.pth`

2. **YOLO Model**:
   - Baixe o modelo YOLO: [best.pt](https://link-para-o-modelo-yolo)
   - Salve em `models/best.pt`

---

## Passo 4: Estrutura de Pastas

Certifique-se de que a estrutura de pastas esteja conforme abaixo:
```
input_raw/
  fotos_originais/
models/
output/
  etiquetas/
  etiquetas_crop/
  joias_limpa/
  ...
```

---

## Passo 5: Executar o Pipeline

1. Ative o ambiente virtual:
   ```bash
   venv\Scripts\activate
   ```
2. Execute o pipeline principal:
   ```bash
   python scripts/pipeline.py
   ```

---

## Passo 6: Resolver Problemas Comuns

- **Erro de arquivo grande ao fazer push**:
  - Certifique-se de que o Git LFS está configurado corretamente.
  - Adicione arquivos grandes ao Git LFS:
    ```bash
    git lfs track "models/sam_vit_b.pth"
    git add .gitattributes models/sam_vit_b.pth
    git commit -m "Adicionando suporte ao Git LFS"
    ```

- **Dependências ausentes**:
  - Reinstale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

---

## Passo 7: Links Úteis

- Repositório Original do Segment Anything: [segment-anything](https://github.com/facebookresearch/segment-anything)
- Documentação do YOLO: [YOLO Docs](https://github.com/ultralytics/yolov5)
- Git LFS: [Git LFS](https://git-lfs.github.com/)

---

## Contato

Para dúvidas ou problemas, entre em contato com [SolanoJr](mailto:solanojr@example.com).