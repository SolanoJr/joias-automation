import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('ler_codigo', 'scripts/ler_codigo.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

for base in ['20260415_140608', '20260415_141024', '20260415_141230']:
    orig = sorted(Path('input_raw/fotos_originais').glob(f'{base}.*'))
    print('base', base, 'files', [str(p) for p in orig])
    if orig:
        code = mod._ocr_imagem_completa(orig[0], deadline=None)
        norm = mod._normalizar_codigo(code)
        print(' raw', repr(code), 'norm', repr(norm), 'valid', norm is not None and mod._is_valid_candidate(norm))
