# Log de Melhorias Visuais — Pasta Final vs Objetivo

Registrado em: 2026-05-08
Fonte: análise manual do usuário comparando `output/6_final/` com `output/6_final/objetivo/`

---

## Legenda
- **Zoom**: aumentar a joia na imagem sem perder qualidade
- **Centralizar**: ajustar posição da joia no canvas
- **Papel residual**: fundo branco com manchas/sombras de papel ainda visíveis

---

## Por imagem

### Perfeito (100%) — sem alterações necessárias
- BR1175026
- BR1185006
- BR1207007
- CJ0254512
- CR3964506
- CR3984506

### Quase perfeito — só falta zoom sem perder qualidade
- BR1197006
- BR1208039 *(aparece em duas categorias)*
- CR5014508
- CR5024510
- CR5034539
- CR5054532

### Faltou zoom sem perder qualidade
- BR1166006
- BR1176006 *(+ talvez remover um pouco mais de papel residual)*
- BR1208039
- BR1209084
- CR3784206
- CR3804206 *(+ talvez remover um pouco mais de papel residual)*

### Faltou zoom + centralização específica
- **CR3974506** — centralizar colar (descer um pouco); pode cortar pontinha de cima
- **BR1165006** — centralizar brinco (descer um pouco)
- **BR1174026** — zoom nos brincos + centralizar (mover para baixo-direita)
- **BR1179006** — centralizar brincos (subir um pouco) + zoom
- **BR1186006** — zoom + centralizar (cima-direita)
- **CR3954526** — zoom + centralizar (mais para baixo, pode cortar um pouco em cima)
- **CR4044506** — zoom + centralizar (mover para direita, pode cortar um pouco em cima)
- **CR4054510** — zoom + centralizar (mover para direita, pode cortar um pouco em cima)
- **CR4064506** — zoom + centralizar (mover para direita, pode cortar um pouco em cima)
- **CR5044539** — zoom + centralizar (mover para direita, pode cortar um pouco em cima)

### Faltou zoom + remoção de papel residual
- BR1167006
- BR1168026
- BR1169012
- BR1171012
- BR1172026
- BR1173012
- BR1177006
- BR1178000
- BR1181006
- BR1182006
- BR1183026
- BR1184026
- BR1187006
- BR1188006
- BR1189006
- BR1198006
- BR1202006
- BR1202014
- BR1203008
- BR1204039
- BR1205007
- BR1206039
- CJ0244526
- PL2401606
- PL2441606
- PL2462006

---

## Ideia de melhoria no pipeline (sugestão do usuário)

Para o grupo "zoom + remoção de papel", testar nova ordem de processamento:
1. Pegar imagem original
2. Aplicar zoom/centralização (sem perder qualidade)
3. Usar removedor de fundo (rembg)
4. Remover etiqueta/paint se ainda visível
5. Continuar o resto do processo normal

Testar com ~5 imagens antes de aplicar em todas.

---

## Observação geral
O principal gap entre `final/` e `objetivo/` é:
1. **Zoom insuficiente** — a joia ocupa menos espaço no canvas do que deveria
2. **Centralização imperfeita** — a joia não está perfeitamente centrada no quadrado
3. **Papel residual** — manchas/sombras de papel ainda visíveis em algumas imagens

Esses três pontos são interdependentes: um zoom maior + melhor centralização
automaticamente reduz a proporção de papel visível no resultado final.


---

## Rodada de testes — pós-processamento (testar_pos_seg.py)
Data: 2026-05-08

### Resultados por imagem (ATUAL | TESTE | OBJETIVO)

**BR1166006** — qualidade melhor que o objetivo, brincos maiores que atual e objetivo (tamanho perfeito), mas deixou fundo de papel residual. Precisa remover papel.

**BR1167006** — qualidade e tamanho ótimos, mas ainda tem muito papel e está cortando o brinco em cima. Precisa: remover papel + não cortar topo.

**BR1174026** — EXCELENTE. Passou o atual e o objetivo, ficou mais que perfeito.

**BR1175026** — permaneceu igual ao atual (perfeito). Não regrediu.

**BR1179006** — tinha tudo pra ultrapassar atual e objetivo, mas está cortando parte do brinco. Precisa: não cortar brinco.

**BR1197006** — piorou. Ficou menor e com papel. Precisa: mais zoom + remover papel.

**CR3784206** — qualidade boa, mas está cortando a parte esquerda do colar. Precisa: não cortar laterais.

**CR5024510** — PERFEITO.

**CR5034539** — PERFEITO.

**PL2401606** — qualidade melhor que o objetivo, mas ainda pequeno e com papel. Precisa: mais zoom + remover papel.

### Problemas identificados para próxima iteração
1. **Papel residual** — BR1166006, BR1197006, PL2401606: limpeza de papel insuficiente
2. **Corte de joia** — BR1167006 (topo), BR1179006 (brinco), CR3784206 (esquerda): margem insuficiente ou zoom excessivo
3. **Zoom insuficiente** — BR1197006, PL2401606: ainda pequenos
4. **BR1174026** — referência de resultado excelente, não mexer

### Observação do usuário
"sinto q estamos chegando em um nivel muuuito bom, melhor do q eu esperava, mesmo com essa minha maquina fraquinha"


---

## Rodada 2 — margem proporcional + PAPEL_MIN=210

**BR1166006** — sem mudança visível. Papel ainda presente. Zoom e tamanho perfeitos.
**BR1197006** — sem mudança. Continua pequeno e com papel. Joia centralizada.
**BR1179006** — PERFEITO. Parou de cortar, zoom bom, qualidade excelente.
**BR1167006** — parou de cortar o brinco, mas ainda tem papel. Quase perfeito.
**BR1175026** — continuou perfeito.
**CR5024510** — perfeito.
**CR5034539** — perfeito.
**BR1174026** — continuou perfeito.
**CR3784206** — corte diminuiu muito, quase perfeito, usável do jeito que ficou (corta só um pinguinho na esquerda).
**PL2401606** — sem mudança. Continua com papel e pequeno. Manteve qualidade e centralização.

### Problemas restantes para próxima iteração
1. **Papel residual persistente** — BR1166006, BR1197006, BR1167006, PL2401606: PAPEL_MIN=210 não foi suficiente. Precisa de limpeza mais agressiva ou abordagem diferente.
2. **Zoom insuficiente** — BR1197006, PL2401606: `ja_ok=True` está bloqueando o zoom neles.
3. **Corte mínimo** — CR3784206: corta um pinguinho na esquerda. Margem ainda insuficiente para esse caso.


---

## Rodada 3 — limpeza adaptativa PAPEL_MIN=160 (muito agressiva)

**BR1166006, BR1167006, PL2401606** — apagou papel MAS apagou joia junto. Tamanho, qualidade e centralização chegaram perto da perfeição. Precisa reduzir agressividade.
**BR1197006** — tanta agressão que apagou a joia e deixou o papel (joia continua minúscula).
**BR1174026, BR1175026, BR1179006** — muita agressão pegou joia.
**CR5024510, CR5034539** — muita agressão pegou joia.
**CR3784206** — agressão deixou colar estranho + ainda corta um pinguinho na esquerda.

### Conclusão
Threshold 160 é muito agressivo para joias com metal claro (tons 100-160).
Threshold ideal por tipo: ~190 para a maioria, 160 só para casos com muito papel cinza-claro.
Usuário aceita deixar os casos difíceis (BR1166006, BR1167006, PL2401606) para ajuste manual após aplicar configuração mais conservadora.


---

## Rodada 4 — limpeza conservadora (>=220 sempre, 190/180 só se seguro)

**BR1166006** — ficou estranha mas não perdeu pixel de joia. Usuário vai editar manualmente.
**BR1167006** — só precisa remover papel manualmente.
**BR1197006** — continua horrível, caso especial, deixar como está.
**PL2401606** — voltou como era. Usuário vai remover papel manualmente.
**Demais** — mantidos os resultados bons das rodadas anteriores.

### Decisão final
- Casos difíceis (BR1166006, BR1167006, PL2401606) serão editados manualmente pelo usuário.
- BR1197006 é caso especial — aceito como está.
- Configuração atual aprovada para aplicar em todas as imagens.

### Ideia do usuário para próxima iteração
Em vez de remover o papel cinza, **preencher o resto da imagem com mais papel** (escala cinzenta).
Raciocínio: se o fundo já tem papel cinza residual, uniformizar esse cinza em toda a imagem
pode ser mais seguro que tentar remover — e visualmente mais consistente.


---

## Rodada 5 — limpeza conservadora (protege <150) + fundo cinza

**BR1166006** — nunca mais voltou ao estado perfeito da rodada 1. Melhor deixar com papel completo (sem limpeza). Não tentar mais.
**BR1174026** — continua perfeita.
**BR1175026** — continua perfeita.
**BR1181006** — precisa diminuir agressividade + preencher fundo com cinza/papel.
**BR1197006** — nada muda ela. Só preencher com cinza/papel. Não testar mais.
**BR1205007** — diminuir agressão + preencher completamente com cinza/papel (não só uma tirinha).
**PL2401606** — desistir de limpar. Só preencher espaço em branco com cinza/papel.
**PL2441606** — horrível: agressão + não centralizada. Coração deve ficar no meio + preencher resto com cinza/papel.

### Decisão final sobre estratégia
- **Limpeza**: só >= 220 (sem tentar 190/180). Não arriscar mais.
- **Fundo cinza**: aplicar em TODAS as imagens com papel residual (>8% em 150-220).
  O cinza deve preencher TODO o fundo, não só partes.
- **Centralização**: garantir que a joia detectada fique no centro antes de preencher.
- **BR1166006, BR1197006, PL2401606**: desistir de limpar, só preencher com cinza.


---

## Rodada 6 — detecção dois estágios + fundo cinza

**BR1166006** — DESISTIR. Cada tentativa piora. Deixar com papel original, sem pós-processamento.
**BR1174026** — continua perfeita.
**BR1175026** — continua perfeita.
**BR1181006** — ainda precisa diminuir agressividade + centralizar (ir mais pra baixo-direita).
**BR1197006** — DESISTIR de melhorar. Só cortar quadrada, centralizar joia e preencher com cinza/papel. Manual.
**BR1205007** — diminuir agressão + centralizar como estava antes.
**PL2401606** — DESISTIR. Só preencher espaço branco com cinza/papel. Sem limpeza.
**PL2441606** — ao redor ficou branco bom. Se deixar esse branco pro resto da imagem, joia centralizada com zoom, talvez fique perfeito.

### Decisão final consolidada
- **BR1166006, BR1197006, PL2401606**: sem pós-processamento de limpeza. Só fundo cinza/papel se sobrar papel.
- **PL2441606**: manter o branco ao redor, centralizar joia, zoom leve.
- **Limpeza**: APENAS >= 220. Nada mais agressivo.
- **Fundo cinza**: aplicar em todas com papel residual, preenchendo TODO o fundo uniformemente.
- **Pergunta do usuário**: "essas imagens q ainda sobrou muito papel, ainda vai ser cortada pra ficar quadrada e COMPLETAMENTE com cinza/papel, né?" — SIM, esse é o objetivo.


---

## Rodada 7 — fundo cinza artificial (errado)

**BR1166006** — só precisa de zoom, o papel já está lá, não precisa de cinza artificial
**BR1174026** — perfeito (joia ficou um pouco menor mas aceitável)
**BR1175026** — perfeito
**BR1181006** — cortou joia em cima, nada centralizado, cinza desnecessário. Quer: papel original + joia centralizada com zoom
**BR1197006** — mesma coisa: deixar o papel, dar zoom na joia, centralizar
**BR1205007** — ficou muito bom, faltou só zoom (joia ficou pequena)
**PL2401606** — dar zoom e deixar com o papel mesmo
**PL2441606** — deixar só a joia e o papel, coração no centro igual ao objetivo

### Decisão final — abordagem correta
NÃO recortar e colar em canvas novo.
NÃO usar cinza artificial.
Abordagem: ampliar a região da joia (zoom) mantendo o papel ao redor,
centralizar a joia no canvas 1024x1024, substituir só o branco puro (>=240)
pelo tom do papel da própria imagem.


---

## Rodada 8 — zoom na imagem inteira + recorte centrado (abordagem correta)

**BR1166006** — no caminho certo. Mais zoom + mais centralização.
**BR1174026** — não mencionada = mantida como está (perfeita).
**BR1175026** — não mencionada = mantida como está (perfeita).
**BR1181006** — continua cortando joia e descentralizada. Quase desistindo, deixar quadrada.
**BR1197006** — no caminho certo. Mais zoom + mais centralização.
**BR1205007** — tamanho ideal, ficou boa.
**PL2401606** — mais zoom. Pode cortar um pouco a pontinha da pulseira.
**PL2441606** — sem salvação. Deixar a foto original mesmo.

### Ações
- Aumentar POS_PROC_TARGET de 0.75 para 0.88 (mais zoom)
- BR1181006: investigar por que corta e descentraliza
- PL2441606: excluir do pós-processamento (usar original)


---

## Rodada 9 — análise pós-processamento nas 55 imagens

### Mais zoom + centralização necessários
BR1165006, BR1166006, BR1171012, BR1172026, BR1173012, BR1177006, BR1178000,
BR1181006, BR1187006, BR1188006, BR1189006, BR1197006, BR1198006, BR1209084,
CJ0244526, PL2401606, PL2441606, PL2452006, PL2462006
→ Identificar dourado para zoom/centralização melhor

### Zoom excessivo — diminuir
BR1167006, BR1176006, BR1185006, BR1183026, BR1184026, BR1207007

### Branco forte residual (pintar com tom do papel)
BR1168026, BR1169012 — ainda tem branco forte, mais zoom e centralização pra baixo

### Pioraram — voltar com mais zoom e centralização
BR1174026, BR1179006

### Cortando joia — diminuir zoom levemente
BR1182006, BR1183026, BR1184026

### Muito mais zoom e centralização
BR1186006, BR1208039

### Só centralização (identificar dourado)
BR1202006, BR1202014, BR1203008, BR1204039, BR1206039

### Quase perfeito — mais zoom e centralização
CR3784206, CR3794206, CR3964506, CR5044539, CR5034539, CR5024510,
CR4064506, CR5054532, CR3974506

### Decisão: criar tabela de configuração por imagem
Usuário sugeriu criar tabela/Excel com ajustes individuais por imagem:
- zoom_target (porcentagem da joia no canvas)
- offset_x, offset_y (centralização)
- pode_cortar_pontas (bool)
- foco (joia inteira / pingente / etc)
- modo (zoom / sem_zoom / original)


---

## Sessão 2026-06-16 — Diagnóstico e correções no novo batch (21 imagens)

### Contexto
Novo batch com 21 imagens (formato `20260529_*.jpg`, resolução 1836x4080). 
Executado em Windows, venv Python, Tesseract 5.5, pyzbar disponível.

### Bugs corrigidos

#### 1. `renomear_intermediarios.py` — CSV com campos extras
**Problema:** `DictWriter` hardcoded com 6 campos, mas `renomear_final.py` adicionou `white_antes`, `white_depois`, `rembg2_melhorou`.
**Correção:** Detecta campos do CSV em runtime e inclui todos automaticamente.

#### 2. `ler_codigo.py` — `_ocr_imagem_completa` causava timeout
**Problema:** Imagens 1836x4080 + escala 1.5/2.2 criavam imagens ~2700x6120 que travavam o Tesseract (timeout 1s).
**Correção:**
- Adicionado downscale para `OCR_IMAGEM_COMPLETA_MAX_SIDE=900px` antes de qualquer escala
- Priorizou regiões inferiores (código está sempre na parte baixa)
- Adicionado `ABCDEFGHIJKLMNOPQRSTUVWXYZ` no whitelist (para capturar `BR...`, `CR...`, etc.)
- **Impacto:** taxa de sucesso OCR subiu de **33% para 90%** (7/21 → 19/21 imagens com código)

#### 3. `renomear_final.py` — `_bbox_joia` causava descentralização
**Problema:** Detector dourado (HSV hue 15-35) pegava apenas pixels de reflexo pequenos, não a joia inteira, gerando bbox incorreto e descentralização pós-processamento (23-27% de offset).
**Correção:** Substituído por detector baseado em **pixels não-brancos** (fundo branco = >= 240), que usa o canvas do rembg diretamente. Inclui filtro de componentes pequenos e agrupamento de componentes relevantes.
**Impacto:** `BR1214006` corrigida de 23.2% → 0.6% offset; `CR2047000` de 27.3% → 0.1% offset.

### Resultado final
- 19/21 imagens com código correto (90%) — era 7/21 (33%)
- 2 SEMCOD (`20260529_092238` e `20260529_103420`) — código não visível nem com OCR agressivo
- Todas as 19 imagens: 1024×1024, fundo branco, joia centralizada (offset <1%), código no nome do arquivo
- Validação de regressão: PASSOU
- Testes da suite: 13 OK, 0 FALHAS, 2 AVISOS (esperados)

### Laboratório de segmentação
- Rodado com `--seed 42`, 10 imagens, concluiu 10/10 OK
- Tempo médio: 32.5s/imagem (GrabCut pesado)
- Relatório disponível em `temp/Laboratorio/resultados/relatorio_lab.html`
- Filtros de máscara removendo em média 51.7% de pixels (agressivo para joias com metal claro)

### Observações para próxima iteração
1. `20260529_092238` e `20260529_103420` — sem código detectável; considerar revisão manual ou retreino do modelo YOLO
2. `R3586000` — código lido incompleto (deveria ser `CR3586000`); OCR cortou o `C` na borda da região
3. `BR1238006_p.jpg` — paint com timeout de OCR; considerar aumentar timeout ou pré-processamento específico para esse tipo de fonte
4. Lab GrabCut muito lento (~32s/img) — considerar desabilitar `ENABLE_GRABCUT` nas iterações rápidas
