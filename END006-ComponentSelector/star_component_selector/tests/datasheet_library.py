"""Libreria dei datasheet PDF (cartella datasheets/): per scelta non e' nel repository di STAR, si copia a mano (README).

Su una copia senza nessun PDF i controlli sui file vengono saltati, oppure verificano il comportamento documentato senza libreria
(datasheet non esposto, "Not available in the database", conteggio 0); se la libreria c'e', anche solo in parte, valgono tutti
(un PDF registrato che manca e' un errore). 2026-10-19."""
import unittest
from pathlib import Path

DATASHEETS_DIR = Path(__file__).resolve().parent.parent / "datasheets"
PDFS_PRESENT = any(DATASHEETS_DIR.glob("*.pdf"))
REASON = "libreria dei datasheet PDF assente in questa copia (datasheets/ senza PDF: si copiano a mano, vedi README)"
needs_pdfs = unittest.skipUnless(PDFS_PRESENT, REASON)
