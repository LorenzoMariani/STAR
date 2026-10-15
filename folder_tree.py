from pathlib import Path


def scrivi_struttura(cartella: Path, file_output: Path):
    cartella = cartella.resolve()

    if not cartella.exists():
        raise FileNotFoundError(f"La cartella non esiste: {cartella}")

    if not cartella.is_dir():
        raise NotADirectoryError(f"Il percorso non è una cartella: {cartella}")

    with file_output.open("w", encoding="utf-8") as f:
        f.write(f"Struttura di: {cartella}\n\n")
        f.write(f"{cartella.name}/\n")

        genera_albero(cartella, f)


def genera_albero(cartella: Path, file, prefisso: str = ""):
    elementi = sorted(
        cartella.iterdir(),
        key=lambda x: (x.is_file(), x.name.lower())
    )

    for indice, elemento in enumerate(elementi):
        ultimo = indice == len(elementi) - 1

        ramo = "└── " if ultimo else "├── "
        file.write(
            prefisso
            + ramo
            + elemento.name
            + ("/" if elemento.is_dir() else "")
            + "\n"
        )

        if elemento.is_dir():
            nuovo_prefisso = prefisso + ("    " if ultimo else "│   ")
            genera_albero(elemento, file, nuovo_prefisso)


# ===== IMPOSTA QUI LA CARTELLA =====
cartella_input = "C:/Users/s5oss/Desktop/software_s5lab/STAR"
file_output = "struttura_cartelle.txt"

scrivi_struttura(Path(cartella_input), Path(file_output))

print(f"File creato: {file_output}")