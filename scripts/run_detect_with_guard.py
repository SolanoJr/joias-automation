from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path("output/analysis/qa_sem_etiqueta_baseline.json")
SUMMARY_PATH = Path("output/analysis/qa_sem_etiqueta_summary.json")


def run(cmd: list[str]) -> int:
    p = subprocess.run(cmd)
    return p.returncode


def main():
    py = sys.executable

    if run([py, "scripts/detect_etiqueta.py"]) != 0:
        print("ERRO: detect_etiqueta falhou")
        sys.exit(1)

    if run([py, "scripts/qa_sem_etiqueta.py"]) != 0:
        print("ERRO: qa_sem_etiqueta falhou")
        sys.exit(1)

    if not SUMMARY_PATH.exists():
        print("ERRO: summary QA não gerado")
        sys.exit(1)

    current = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    if not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Baseline criada:", BASELINE_PATH)
        print("Score atual:", current.get("score"))
        return

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    base_score = int(baseline.get("score", 999999))
    cur_score = int(current.get("score", 999999))

    print("Baseline score:", base_score)
    print("Current score:", cur_score)

    if cur_score > base_score:
        print("REGRESSAO detectada: score piorou. Rejeitar esta tentativa.")
        sys.exit(2)

    if cur_score < base_score:
        BASELINE_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Melhoria detectada. Baseline atualizada.")
    else:
        print("Sem regressão.")


if __name__ == "__main__":
    main()
