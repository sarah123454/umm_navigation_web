# core/karte.py  (Anfang der Datei)
import functools
import fitz                      # PyMuPDF
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

from config import BASE_DIR, SVG_BREITE, SVG_HOEHE

PLAN_PDF = BASE_DIR / "static" / "lageplan.pdf"
PLAN_PNG = BASE_DIR / "static" / "lageplan.png"


@functools.lru_cache(maxsize=1)
def lade_plan():
    """Liefert den Lageplan als Bild-Array. PDF hat Vorrang, PNG ist der Rückfall."""
    if PLAN_PDF.exists():
        with fitz.open(PLAN_PDF) as doc:
            pix = doc[0].get_pixmap(dpi=200)
            bild = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if abs(pix.width / pix.height - SVG_BREITE / SVG_HOEHE) > 0.01:
                print("WARNUNG: Seitenverhältnis des PDFs weicht von der SVG ab, die Karte wäre verzerrt.")
            return bild
    return mpimg.imread(PLAN_PNG)