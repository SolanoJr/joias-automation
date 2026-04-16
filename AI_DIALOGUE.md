# AI Dialogue Log (Copilot ↔ GPT)

Objetivo: manter contexto técnico fora do chat longo e acelerar colaboração entre IAs.

## Fluxo recomendado
1. Copilot propõe patch pequeno.
2. GPT revisa arquitetura/risco.
3. Copilot implementa.
4. GPT valida abordagem.

## Modelo de mensagem (sempre curto)
- Arquivo:
- Função:
- Problema:
- Evidência (erro/log):
- Restrição (não pode quebrar):
- Pedido objetivo:

## Registro de troca

### 2026-03-09
**Pergunta para GPT:**

Como reduzir `semcod` no fluxo atual sem quebrar padrão de nomes e sem aumentar falso positivo?

**Resposta do GPT:**

Focar em patch pequeno no leitor (`ler_codigo.py`), priorizando preprocessamento de etiqueta/barcode antes de mudanças arquiteturais.

**Decisão aplicada:**

Aplicar melhorias incrementais e medir sempre no lote rápido de 10 arquivos.

**Patch final (resumo):**

- Ajuste de consenso da etiqueta: quando há só 1 candidato, aceitar com 1 voto.
- Próximo patch em andamento: OCR de etiqueta com variação de rotação para tentar recuperar o último `semcod`.

**Teste executado:**

`python scripts/pipeline.py` (modo rápido de 10 arquivos)

**Resultado:**

`semcod` caiu de 2 para 1 (restante: base `20260108_142143`).

---

## Regras do projeto (fixas)
- Fluxo principal enumerado: `scripts/1_...` até `scripts/6_...`.
- Saídas principais enumeradas: `output/1_*` até `output/6_*`.
- Teste padrão: `python scripts/pipeline.py` (10 arquivos).
- Teste completo: `python scripts/pipeline.py --full`.
- Padrão de nome: `_p`, `_e`, `_se`, `_qm`, `_sr` e final sem sufixo.

## Dica operacional
Nunca mandar arquivo inteiro sem necessidade. Preferir:
- trecho da função problemática
- log curto do erro
- 1 exemplo de entrada que falhou
