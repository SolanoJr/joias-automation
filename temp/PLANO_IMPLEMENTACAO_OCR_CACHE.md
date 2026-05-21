# 🚀 PLANO DE IMPLEMENTAÇÃO: OCR Cache (Etapa 1 - 2h)

## 🎯 Objetivo

Implementar cache não-determinístico para OCR de etiquetas/paints.

**Resultado esperado:**
- Run novo: sem ganho (baseline)
- Run 2+: **2-3x speedup** (88-94% mais rápido)

---

## 📋 Mudanças Necessárias

### 1️⃣ Arquivo: `scripts/ler_codigo.py`

#### Adicionar após imports (linha ~20):

```python
import hashlib
from pathlib import Path

# ===== OCR CACHE CONFIG =====
OCR_CACHE_ENABLED = os.getenv("OCR_CACHE_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
OCR_CACHE_DIR = Path("output/cache_ocr")
OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _get_file_hash(file_path: Path) -> str:
    """Calcula SHA256 do arquivo para usar como chave de cache"""
    try:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]  # 16 chars suficientes
    except Exception:
        return None

def _ocr_result_from_cache(cache_key: str) -> str | None:
    """Recupera resultado do cache"""
    if not OCR_CACHE_ENABLED or not cache_key:
        return None
    
    cache_file = OCR_CACHE_DIR / f"{cache_key}.ocr"
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return None

def _ocr_result_to_cache(cache_key: str, resultado: str) -> None:
    """Salva resultado no cache"""
    if not OCR_CACHE_ENABLED or not cache_key or not resultado:
        return
    
    cache_file = OCR_CACHE_DIR / f"{cache_key}.ocr"
    try:
        cache_file.write_text(resultado, encoding="utf-8")
    except Exception as e:
        logging.debug(f"Aviso: Não conseguiu salvar cache: {e}")
```

#### Modificar função `_ocr_paint()` (~linha 156):

**ANTES:**
```python
def _ocr_paint(paint_path: Path, deadline: float | None = None) -> str | None:
    img = cv2.imread(str(paint_path))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # ... resto do código OCR
```

**DEPOIS:**
```python
def _ocr_paint(paint_path: Path, deadline: float | None = None) -> str | None:
    # ===== CACHE CHECK =====
    cache_key = _get_file_hash(paint_path)
    cached_result = _ocr_result_from_cache(cache_key)
    if cached_result:
        return cached_result
    
    img = cv2.imread(str(paint_path))
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # ... resto do código OCR ...
    
    # ===== ANTES DE RETORNAR =====
    if codigo:
        _ocr_result_to_cache(cache_key, codigo)
    
    return codigo
```

#### Modificar função `_ocr_etiqueta_strategy()` (~linha 400):

**Adicionar cache check no início:**
```python
def _ocr_etiqueta_strategy(
    etiquetas: list[Path],
    paints: list[Path],
    # ... outros params
) -> str | None:
    
    # ===== CACHE POOLING =====
    # Tentar cache de QUALQUER etiqueta antes de OCR
    for eta_path in etiquetas:
        cache_key = _get_file_hash(eta_path)
        cached = _ocr_result_from_cache(cache_key)
        if cached:
            return cached
    
    # Se nenhuma hits, prosseguir com OCR normal
    # ... resto do código
```

#### Adicionar função utilitária para relatório (~linha 600):

```python
def _report_cache_stats(perfil_rows):
    """Reporta estatísticas de cache hits/misses"""
    if not perfil_rows or not OCR_CACHE_ENABLED:
        return
    
    cache_hits = sum(1 for r in perfil_rows if "cache_hit" in str(r.get("modo_adaptive", "")))
    total = len(perfil_rows)
    
    hit_rate = (cache_hits / total * 100) if total > 0 else 0
    print(f"\n📊 Cache Statistics:")
    print(f"   Hits: {cache_hits}/{total} ({hit_rate:.1f}%)")
    print(f"   Cache dir: {OCR_CACHE_DIR}")
```

### 2️⃣ Arquivo: `scripts/pipeline.py`

#### Modificar main() para adicionar flag (~linha 120):

```python
def main(
    modo_full: bool = False,
    limite_teste: int = TEST_LIMIT_PADRAO,
    mode: str = "auto",
    inprocess_threshold: int = INPROCESS_THRESHOLD_PADRAO,
    incremental: bool = False,
    use_cache: bool = True,  # ← NOVO
):
    # ... código existente ...
    
    seg_env = {}
    if not modo_full and limite_teste > 0:
        detect_env["PROCESS_LIMIT"] = str(limite_teste)
        print(f"Modo teste rápido: limitando entrada para {limite_teste} arquivo(s)")
    else:
        print("Modo completo: processando todos os arquivos")
    
    # ===== NOVO: Cache Control =====
    if use_cache:
        seg_env["OCR_CACHE_ENABLED"] = "1"
        print("✅ OCR Cache: ATIVADO")
    else:
        seg_env["OCR_CACHE_ENABLED"] = "0"
        print("⚠️  OCR Cache: DESATIVADO (benchmark apenas)")
```

#### Adicionar argumento ao parser (~linha 230):

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Processa todos os arquivos")
    parser.add_argument("--limit", type=int, default=TEST_LIMIT_PADRAO, help=f"Limite teste (padrão: {TEST_LIMIT_PADRAO})")
    parser.add_argument("--mode", choices=["auto", "subprocess", "inprocess"], default="auto")
    parser.add_argument("--inprocess-threshold", type=int, default=INPROCESS_THRESHOLD_PADRAO)
    parser.add_argument("--incremental", action="store_true", help="Preserva saídas e ativa cache")
    
    # ===== NOVO =====
    parser.add_argument("--no-cache", action="store_true", help="Desativa OCR cache (benchmark)")
    
    args = parser.parse_args()

    main(
        modo_full=args.full,
        limite_teste=args.limit,
        mode=args.mode,
        inprocess_threshold=args.inprocess_threshold,
        incremental=args.incremental,
        use_cache=not args.no_cache,  # ← NOVO
    )
```

---

## 🧪 Testes Manuais

### Test 1: Verificar Cache Creation

```bash
cd d:\Desktop\SolanoJr\Programas\joias_automation

# Run 1: Cria cache
python scripts/pipeline.py --limit 5 --mode inprocess

# Verificar cache foi criado
ls -la output/cache_ocr/
# Expect: vários arquivos .ocr

# Ver dentro do cache
cat output/cache_ocr/abc123.ocr
# Should show: "1200145629" ou similar
```

### Test 2: Benchmark Compare

```bash
# Setup: Prepare test set
PROCESS_LIMIT=10 python scripts/1_detect_etiqueta.py

# Run 1: SEM cache (baseline)
python scripts/pipeline.py --limit 10 --no-cache 2>&1 | tee bench_nocache.log
# Expected: ~5-10s OCR

# Run 2: COM cache (hot cache)
python scripts/pipeline.py --limit 10 2>&1 | tee bench_cache.log
# Expected: ~0.5-1s OCR (80-90% mais rápido)

# Comparar
grep "Concluído em" bench_nocache.log
grep "Concluído em" bench_cache.log
```

### Test 3: Incremental Mode

```bash
# Run 1: normal
python scripts/pipeline.py --full 2>&1 | tee run1.log

# Run 2: incremental com cache
python scripts/pipeline.py --incremental 2>&1 | tee run2.log

# Compare timings
# Expect: run2 muito mais rápido
```

---

## 📊 Métricas de Sucesso

| **Métrica** | **Baseline** | **Com Cache** | **Target** |
|-----------|------------|------------|----------|
| 1º run (50 imgs) | 15.4s | 15.4s | 15.4s ✅ |
| 2º run (cache quente) | 15.4s | 1.8s | <3s ✅ |
| 3º run (cache quente) | 15.4s | 1.2s | <2s ✅ |
| Cache hit rate | 0% | 70-90% | >80% ✅ |

---

## 🔧 Troubleshooting

### Problema: Cache não está sendo usado

**Debug:**
```bash
# Ativar logging detalhado
python scripts/ler_codigo.py --debug 2>&1 | grep -i cache

# Verificar arquivo existe
ls output/cache_ocr/ | wc -l
# Should be > 0
```

**Solução:** Verificar se `OCR_CACHE_ENABLED` está sendo propagado corretamente

### Problema: Cache corrompido

**Reset:**
```bash
# Limpar tudo
rm -r output/cache_ocr/

# Rebuild
python scripts/pipeline.py --full
```

### Problema: Performance não melhorou

**Verificar:**
```python
# Em ler_codigo.py, adicionar debug
if cached_result:
    print(f"  💾 Cache hit: {paint_path.name}")
    _append_profile(perfil_rows, base, "ocr_paint", 0.001, 
                    "cache_hit", "cache")
```

---

## 📅 Próximos Passos (Após Cache)

### Phase 2a: Lazy Reshape (1h)
```python
# Em _ocr_paint(), modificar loop:

FOR base IN candidatos:
    # Tenta apenas resize 1x primeiro
    codigo = _ocr_digits(base, cfg)
    if codigo and CONFIANCA > 0.85:
        return codigo  # Early exit!
    
    # Se falhou, tenta outras escalas
    FOR escala IN [1.8, 2.2, 2.8]:
        # ... resto
```

### Phase 2b: Parallelizar Rembg (1.5h)
```python
# Em segment_rembg.py

from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(processar_imagem, img_path): img_path 
        for img_path in imagens
    }
    for future in as_completed(futures):
        resultado = future.result()
```

---

## 📝 Checklist de Implementação

- [ ] Adicionar imports no `ler_codigo.py`
- [ ] Implementar `_get_file_hash()`
- [ ] Implementar `_ocr_result_from_cache()`
- [ ] Implementar `_ocr_result_to_cache()`
- [ ] Modificar `_ocr_paint()` com cache check
- [ ] Modificar `_ocr_etiqueta_strategy()` com cache check
- [ ] Adicionar argumento `--no-cache` em `pipeline.py`
- [ ] Test 1: Verificar cache creation
- [ ] Test 2: Benchmark compare
- [ ] Test 3: Incremental mode
- [ ] Documentar em `OUTPUT_CHANGELOG.md`
- [ ] Commit e push

---

## 💾 Impacto Estimado

```
Linha de código: ~80 novas linhas (net)
Tempo implementação: 1-2 horas
Speedup 2º run: 2-3x (80-90%)
Risco: BAIXO (determinístico, com fallback)
Reversibilidade: ALTA (basta rm output/cache_ocr/)
```
