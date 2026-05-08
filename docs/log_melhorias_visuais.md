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
