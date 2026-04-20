import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "project" / "scripts" / "detect_etiqueta.py"
    runpy.run_path(str(target), run_name="__main__")
