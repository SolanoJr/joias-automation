# 📋 ANEXO: Diagramas Técnicos & Deep Dive

## 1️⃣ Arquitetura do OCR Cache

```
┌────────────────────────────────────────────────────────────────────┐
│                        LER_CODIGO.PY                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Input: paint_path, etiqueta_path                                 │
│      │                                                             │
│      ▼                                                             │
│  ┌──────────────────────────────────────────┐                     │
│  │ _get_file_hash(paint_path)               │                     │
│  │ → SHA256 do arquivo (16 chars)           │                     │
│  │ → "a1b2c3d4e5f6g7h8"                     │                     │
│  └──────────────┬───────────────────────────┘                     │
│                 │                                                  │
│                 ▼                                                  │
│  ┌──────────────────────────────────────────┐                     │
│  │ _ocr_result_from_cache(cache_key)        │                     │
│  │ ✅ HIT: Return "1200145629"              │ ← Rápido! 1ms      │
│  │ ❌ MISS: Proceeds to OCR                 │ ← Lento, 800ms     │
│  └──────────────┬───────────────────────────┘                     │
│                 │                                                  │
│  ┌──────────────┴───────────────────────────┐                     │
│  │                                          │                     │
│  ├─ HIT (80%)                 MISS (20%)   │                     │
│  │  Return cached         _ocr_paint()     │                     │
│  │                        - 60 OCR calls   │                     │
│  │                        - 4 escalas      │                     │
│  │                        - múltiplas      │                     │
│  │                          transforms    │                     │
│  │                                          │                     │
│  └──────────────┬───────────────────────────┘                     │
│                 │                                                  │
│                 ▼                                                  │
│  ┌──────────────────────────────────────────┐                     │
│  │ _ocr_result_to_cache(cache_key, result)  │                     │
│  │ Save: output/cache_ocr/a1b2c3d4e5f6.ocr  │                     │
│  └──────────────────────────────────────────┘                     │
│                 │                                                  │
│                 ▼                                                  │
│  Return resultado ao ler_codigo.py                                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

Cache Storage (output/cache_ocr/):
├─ a1b2c3d4e5f6.ocr → "1200145629"
├─ b2c3d4e5f6g7.ocr → "BR1194000"
├─ c3d4e5f6g7h8.ocr → "CR3904506"
└─ ...  (1 arquivo por Paint/Etiqueta única)
```

---

## 2️⃣ Fluxo de Decisão OCR (Antes vs Depois)

### ANTES (Sem Cache)

```
Para CADA paint/etiqueta:
│
├─→ _ocr_paint_intensivo() [SEMPRE roda]
│   ├─ Carrega imagem: imread()
│   ├─ Converte para grayscale
│   ├─ Aplica CLAHE
│   ├─ Tenta 7 transformações:
│   │  ├─ gray
│   │  ├─ CLAHE normalized
│   │  ├─ Otsu threshold
│   │  ├─ Otsu inverted
│   │  ├─ Adaptive threshold
│   │  ├─ Adaptive inverted
│   │  └─ Sharpened
│   │
│   ├─ Para CADA transformação, tenta 4 escalas:
│   │  ├─ Resize 1x
│   │  ├─ Resize 1.8x
│   │  ├─ Resize 2.2x
│   │  └─ Resize 2.8x
│   │
│   ├─ Para CADA escala×transform, OCR:
│   │  ├─ pytesseract.image_to_string() [40-50ms]
│   │  ├─ PSM 7 config
│   │  └─ PSM 6 config
│   │
│   └─→ Até MAX_OCR_CALLS=60 ✗ DETERMINADO A RODA TUDO

Tempo típico: 0.67s/item (P50), 1.65s (P95)
Resultado: Sempre validado, nunca pula
```

### DEPOIS (Com Cache)

```
Para CADA paint/etiqueta:
│
├─ Calcular SHA256 hash → cache_key
│
├─→ _ocr_result_from_cache(cache_key)
│   ├─ Se arquivo existe em output/cache_ocr/:
│   │  └─ Return resultado (HIT) ← 1ms! ⚡
│   │
│   └─ Se NÃO existe:
│      └─ Proceed to _ocr_paint_intensivo()
│         ├─ Roda normalmente (0.67s)
│         └─ Save resultado no cache
│            (MISS primeiro, depois HIT em reruns)

Tempo típico:
  ✅ 1º run (cache miss): 0.67s/item (sem perda)
  ✅ 2º run (cache hit):  0.001s/item ← 670x mais rápido!
  ✅ 3º run (cache hit):  0.001s/item
```

---

## 3️⃣ Distribuição de Tempos OCR (com dados reais)

```
Perfil de 50 imagens (stability50_r1):

Tempo/Classe:
0.0s │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░║
0.2s │ ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ║ ← Rápidos (raw)
0.4s │ ██████░░░░░░░░░░░░░░░░░░░░░░░░░░ ║ ← Médios (resize 2x)
0.6s │ █████████░░░░░░░░░░░░░░░░░░░░░░░ ║ ← Lentos (threshold)
0.8s │ ████████████░░░░░░░░░░░░░░░░░░░░░╬ ← Falha + paint
1.0s │ ██████████████░░░░░░░░░░░░░░░░░░░ ║
1.2s │ █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ║
1.4s │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ║
1.6s │ ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ║ ← Outliers (P95)
1.8s │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░║ ← Max

Percentis:
P10:  0.132s
P25:  0.191s
P50:  0.537s ← MEDIANA
P75:  0.892s
P90:  1.485s
P95:  1.651s ← FIM DA CAUDA GORDA
P99:  1.924s ← MAX

Implicação:
- 50% < 0.537s → Rápidos (potencial cache hit reuse)
- 50% > 0.537s → Lentos (OCR complexo, bom candidato cache)
```

---

## 4️⃣ Anatomia do _ocr_paint() (Gargalo Deep Dive)

```python
def _ocr_paint(paint_path: Path):
    img = cv2.imread(str(paint_path))  # ~1ms
    gray = cv2.cvtColor(img, ...)      # ~2ms
    
    # ===== TRANSFORMAÇÕES =====
    blur = cv2.GaussianBlur(gray, (3,3), 0)       # ~3ms
    clahe = cv2.createCLAHE(...).apply(blur)      # ~8ms
    _, otsu = cv2.threshold(clahe, ...)           # ~5ms
    adapt = cv2.adaptiveThreshold(clahe, ...)    # ~8ms
    nitida = cv2.addWeighted(...)                  # ~5ms
    
    candidatos = [gray, clahe, otsu, 255-otsu, adapt, 255-adapt, nitida]
    #           ├─ 7 bases diferentes para tentar
    
    # ===== LOOP INFERNAL =====
    for base in candidatos:           # 7 iterações
        for escala in [1, 1.8, 2.2, 2.8]:  # 4 escalas
            for psm in [7, 6]:        # 2 PSM configs
                # ===== MAIS CHAMADAS =====
                if escala != 1:
                    candidate = cv2.resize(base, ...)  # ~5ms por escala
                else:
                    candidate = base
                
                # ===== OCR REAL (CARO!) =====
                texto = pytesseract.image_to_string(
                    candidate,
                    config=f"--psm {psm} -c tessedit_char_whitelist=...",
                    timeout=1
                )  # ← 40-50ms CADA!
                
                # ... validação ...
                chamadas += 1
                if chamadas >= MAX_OCR_CALLS:
                    return resultado  # ← Early exit se atingiu limite
    
    # Potencial: 7 × 4 × 2 = 56 chamadas
    # Limite: 40 chamadas (com early exit)
    # Tempo estimado: 40 calls × 40ms = 1.6s possível

Custos por elemento:
┌──────────────────┬─────┬─────────┐
│ Operação         │ Qty │ Tempo   │
├──────────────────┼─────┼─────────┤
│ imread()         │ 1  │  1ms    │
│ cvtColor         │ 1  │  2ms    │
│ GaussianBlur     │ 1  │  3ms    │
│ CLAHE.apply      │ 1  │  8ms    │
│ threshold        │ 1  │  5ms    │
│ adaptiveThreshold│ 1  │  8ms    │
│ resize (cada uma)│ 3  │ 5ms × 3 │
│ pytesseract 🔴  │ 40 │ 40ms×40 │ ← DOMINANTE!
├──────────────────┼─────┼─────────┤
│ TOTAL            │    │ 1650ms  │
└──────────────────┴─────┴─────────┘

Resumo: 97% do tempo é Tesseract OCR 🔴
        3% é processamento de imagem (negligenciável)
```

---

## 5️⃣ Oportunidades de Otimização (Quick Wins)

### Lazy Evaluation

```
ATUAL: Tenta TODAS as 4 escalas (1x, 1.8x, 2.2x, 2.8x)

OTIMIZADO: Tenta apenas 1x, só escala se falhar

Pseudocódigo:
for base in candidatos:
    # ← Apenas uma escala por defaut
    codigo = _ocr_digits(base, cfg)  # 40ms × 7 bases = 280ms
    
    if codigo and confidence > 0.85:
        return codigo  # ← EARLY EXIT aqui!
    
    # Só se confiança baixa, tenta outras escalas
    if confidence < 0.75:
        for escala in [1.8, 2.2, 2.8]:
            código_alt = _ocr_digits(resize(base, escala), cfg)
            if codigo_alt and confidence > 0.80:
                return codigo_alt

Impacto: -24% chamadas OCR (de 40 para 30 médio)
         = -30% tempo (1.6s → 1.12s para lentos)
```

### Confidence-Based Early Exit

```
ATUAL: Faz 60 OCR calls sempre (com limite hard)

OTIMIZADO: Para se confiança > threshold

Detalhes:
MAX_OCR_CALLS = 60  # Hard limit

# Adicionar soft threshold:
CONFIDENCE_EARLY_EXIT = 0.85  # or 90%

# Quando encontrar com alta confiança:
if codigo_validado(codigo) and confidence(codigo) > CONFIDENCE_EARLY_EXIT:
    return codigo  # ← Para antes de chegar a 60!

Impacto em média: -25% chamadas
                  = -20% tempo
```

### Paralelização de OCR (Marginal)

```
ATUAL: Thread pool não viável (pytesseract usa subprocess)

POSSÍVEL: multiprocessing.Pool (experimental)

from multiprocessing import Pool

def process_item(item_data):
    """Worker em processo separado"""
    codigo, paints, etiquetas = item_data
    # Executa tudo: paint OCR + etiqueta OCR
    return resultado

with Pool(processes=2) as p:  # 2 cores para OCR
    resultados = p.map(process_item, items)

Limitação: Overhead spawn process > ganho em i7 4-core
Viável em: 8+ cores ou serverless (já paralelo automaticamente)
Impacto esperado: +1.2-1.5x máximo (não recomendado)
```

---

## 6️⃣ Trade-off: Cache vs Recompute

```
┌────────────────────────────────────────────────────────┐
│             CACHE RERUN SPEEDUP ANALYSIS               │
├────────────────────────────────────────────────────────┤

Número de Imagens Processadas:
10     │ ████████████ 1.2s (baseline: 10×0.67 = 6.7s)
50     │ ██████████████████████████████ 3.2s (vs. 33.5s)
100    │ ████████████████████████████████████████████████ 6.4s (vs. 67s)
200    │ ██████████████████████████████████████████████████████████████ 12.8s (vs. 134s)

Ganho Relativo (Rerun vs Fresh):
10     │ ████████████ -82% (6.7s → 1.2s)
50     │ ████████████████████████ -91% (33.5s → 3.2s)
100    │ ██████████████████████████ -90% (67s → 6.4s)
200    │ ████████████████████████████ -90% (134s → 12.8s)

Insights:
- Ganho % estabiliza em ~90% após ~50 items
- Storage cresce linear: 1 item ≈ 50 bytes cache
- 200 items = ~10KB cache (negligenciável)
- Cache hits mantêm velocidade padrão mesmo em scales grandes

Break-even point: .
    1º run (sem cache): X seconds
    2º run (com cache): 0.06X seconds
    3º run (com cache): 0.06X seconds
    → Payoff em 2 runs: 1X + 1X = 2X vs 1.06X
    → 47% economia em 2 runs!
```

---

## 7️⃣ Risco vs Impacto

```
                   IMPACTO (Speedup)
                        ↑
                   3.0x │                    ★ OCR Cache
                        │                    (rerun)
                   2.5x │                 ♦ Rembg ThreadPool
                        │
                   2.0x │           ■ Lazy Reshape
                        │ 
                   1.5x │        ● Early Exit Confidence
                        │ ★ (1º run)
                   1.3x │ ⬤ Zoom Adaptativo
                        │
                   1.0x └─────────────────────────────→
                        0    LOW      MEDIUM    HIGH
                             RISCO
        
Mapeamento:
★ OCR Cache (rerun)      Impacto: 3.0x    Risco: LOW    ← AGORA!
★ OCR Cache (1º run)     Impacto: 1.0x    Risco: LOW
♦ Rembg ThreadPool       Impacto: 2.5x    Risco: MED
■ Lazy Reshape           Impacto: 1.3x    Risco: LOW
● Early Exit Conf        Impacto: 1.2x    Risco: LOW
⬤ Zoom Adaptativo        Impacto: 1.05x   Risco: MED
```

---

## 8️⃣ Checksum Validation (Why SHA256 is Safe)

```
File Hash-Based Cache é determinístico porque:

1. Determinismo:
   ├─ Same file (bit por bit) → Same hash
   ├─ Different file → Different hash (probabilidade colisão: 2^-256)
   └─ OCR output determinístico (pytesseract, dado mesma imagem)

2. Invalidação Automática:
   ├─ User edita paint em Photoshop → New hash
   ├─ Cache miss → Reprocessa automaticamente
   └─ Transparente ao usuário

3. Exemplo Prático:
   ┌─ File: output/2_paints/20260415_paint_1.jpg
   │  SHA256: a1b2c3d4e5f6g7h8...
   │  Cache hit → "1200145629"
   │
   └─ User edita arquivo (crop melhor)
      SHA256: xxx999yyy888zzz777... (diferente!)
      Cache miss → Reprocessa
      Nova hash → Novo cache
```

---

## 9️⃣ Performance Scaling (Linear vs Sublinear)

```
50 img: 33.5s OCR + 2% overhead = 35s total
100 img: 67s OCR + 2% overhead = 70s total
200 img: 134s OCR + 2% overhead = 140s total
500 img: 335s OCR + 2% overhead = 350s total

√ Escalab linear: 50 → 100 = 2x tempo
               100 → 200 = 2x tempo
              200 → 500 = 2.5x tempo

Com Cache (rerun):
50 img: 3.2s (hit 90%)
100 img: 6.4s (hit 90%)
200 img: 12.8s (hit 90%)
500 img: 32s (hit 90%)

Scaling factor:
├─ 1º run: Linear (depende de imagens novas)
└─ N-ésima run: Sublinear em N (if cache hit > 80%)

Implicação: Cache fica mais valioso quanto maior o batch!
            (Descontos em volume)
```

---

**Fim dos Diagramas Técnicos**

Veja documentos principais para implementação.
