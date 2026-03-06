from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import cv2
import pytesseract

DIGIT_RE = re.compile(r"\d{6,}")


def ocr_digits_lower_band(gray):
    h, w = gray.shape
    roi = gray[int(h * 0.45):, :]
    up = cv2.resize(roi, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    variants = [up]
    _, otsu = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)
    variants.append(255 - otsu)

    texts = []
    for im in variants:
        for psm in (6, 7, 11):
            cfg = f"--psm {psm} -c tessedit_char_whitelist=0123456789"
            try:
                txt = pytesseract.image_to_string(im, config=cfg, timeout=1)
            except BaseException:
                continue
            txt = txt.replace(" ", "").replace("\n", "")
            if txt:
                texts.append(txt)

    joined = "|".join(texts)
    return bool(DIGIT_RE.search(joined)), joined[:120]


def evaluate(raw_dir: Path, sem_dir: Path):
    raw_files = sorted(raw_dir.glob("*.jpg"))
    results = []

    for raw in raw_files:
        sem = sem_dir / raw.name
        if not sem.exists():
            results.append({
                "arquivo": raw.name,
                "status": "missing_sem",
                "digits_left": "",
                "overerase": "",
                "top_white": "",
                "bottom_white": "",
                "ocr_sample": "",
            })
            continue

        img = cv2.imread(str(sem))
        if img is None:
            results.append({
                "arquivo": raw.name,
                "status": "unreadable_sem",
                "digits_left": "",
                "overerase": "",
                "top_white": "",
                "bottom_white": "",
                "ocr_sample": "",
            })
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, _ = gray.shape
        top = gray[: max(1, int(h * 0.45)), :]
        bottom = gray[int(h * 0.55):, :]

        top_white = float((top > 245).mean())
        bottom_white = float((bottom > 245).mean())

        has_digits, ocr_sample = ocr_digits_lower_band(gray)
        overerase = bottom_white > 0.94 and (bottom_white - top_white) > 0.45

        status = "ok"
        if has_digits:
            status = "digits_left"
        if overerase:
            status = "overerase" if status == "ok" else "digits_and_overerase"

        results.append({
            "arquivo": raw.name,
            "status": status,
            "digits_left": "1" if has_digits else "0",
            "overerase": "1" if overerase else "0",
            "top_white": f"{top_white:.4f}",
            "bottom_white": f"{bottom_white:.4f}",
            "ocr_sample": ocr_sample,
        })

    summary = {
        "total": len(results),
        "missing_sem": sum(r["status"] == "missing_sem" for r in results),
        "unreadable_sem": sum(r["status"] == "unreadable_sem" for r in results),
        "digits_left": sum(r["digits_left"] == "1" for r in results),
        "overerase": sum(r["overerase"] == "1" for r in results),
    }
    summary["score"] = summary["digits_left"] * 2 + summary["overerase"] * 3 + summary["missing_sem"] * 10

    return results, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="input_raw/fotos_originais")
    parser.add_argument("--sem", default="output/sem_etiqueta")
    parser.add_argument("--csv", default="output/analysis/qa_sem_etiqueta.csv")
    parser.add_argument("--summary", default="output/analysis/qa_sem_etiqueta_summary.json")
    args = parser.parse_args()

    raw_dir = Path(args.raw)
    sem_dir = Path(args.sem)
    csv_path = Path(args.csv)
    summary_path = Path(args.summary)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    results, summary = evaluate(raw_dir, sem_dir)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["arquivo", "status", "digits_left", "overerase", "top_white", "bottom_white", "ocr_sample"],
        )
        w.writeheader()
        w.writerows(results)

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("QA total:", summary["total"])
    print("digits_left:", summary["digits_left"])
    print("overerase:", summary["overerase"])
    print("score:", summary["score"])
    print("csv:", csv_path)
    print("summary:", summary_path)


if __name__ == "__main__":
    main()
