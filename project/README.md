# joias_automation project package

Este diretório contém o pacote mínimo necessário para rodar o pipeline.

Passos:
1. Crie o ambiente virtual:
   python -m venv venv
2. Ative o venv:
   .\venv\Scripts\Activate.ps1
3. Instale dependências:
   pip install -r requirements.txt
4. Coloque imagens em input_raw\fotos_originais
5. Execute:
   python pipeline.py
