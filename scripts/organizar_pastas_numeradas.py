import shutil
from pathlib import Path


MAPEAMENTO = [
    (Path("output/etiquetas"), Path("output/1_etiquetas")),
    (Path("output/paints"), Path("output/2_paints")),
    (Path("output/sem_etiqueta"), Path("output/3_sem_etiqueta")),
    (Path("output/quadrado_manual"), Path("output/4_quadrado_manual")),
    (Path("output/segmentado_rembg"), Path("output/5_segmentado_rembg")),
    (Path("output/final"), Path("output/6_final")),
]


def limpar_dir(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for p in folder.glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)


def espelhar(origem: Path, destino: Path) -> int:
    limpar_dir(destino)
    if not origem.exists():
        return 0

    count = 0
    for arq in sorted(origem.glob("*.jpg")):
        shutil.copy2(arq, destino / arq.name)
        count += 1
    return count


def main():
    for origem, destino in MAPEAMENTO:
        qtd = espelhar(origem, destino)
        print(f"{destino}: {qtd} arquivo(s)")


if __name__ == "__main__":
    main()
