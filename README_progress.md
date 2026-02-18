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