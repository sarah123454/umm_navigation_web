# qr/generator.py – erzeugt für jeden Wegpunkt einen QR-Code mit ?start=<ID>
import csv
import re
from urllib.parse import quote

import networkx as nx
import qrcode
from PIL import Image, ImageDraw, ImageFont

from config import WEB_BASE_URL, QR_DIR, QR_TYPEN, ZIEL_TYPEN
from core.graph import lade_graph
from core.ziele import standort_beschreibung


def url_fuer(nid):
    return f"{WEB_BASE_URL}/?start={quote(str(nid))}"


def _dateiname(nid):
    return re.sub(r"[^\w-]", "_", str(nid)) + ".png"


def _qr_mit_beschriftung(url, zeile1, zeile2):
    """QR-Code + zwei Textzeilen darunter (zum Ausdrucken/Aufhängen)."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    bild = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    try:
        schrift = ImageFont.load_default(size=22)      # Pillow >= 10.1
    except TypeError:
        schrift = ImageFont.load_default()

    rand = 70
    gesamt = Image.new("RGB", (bild.width, bild.height + rand), "white")
    gesamt.paste(bild, (0, 0))
    zeichner = ImageDraw.Draw(gesamt)
    for nr, text in enumerate((zeile1, zeile2)):
        breite = zeichner.textlength(text, font=schrift)
        zeichner.text(((bild.width - breite) / 2, bild.height + 5 + nr * 30), text,
                      fill="black", font=schrift)
    return gesamt


def generate_all(nur_typen=QR_TYPEN):
    g = lade_graph()
    QR_DIR.mkdir(parents=True, exist_ok=True)

    ziele = [n for n, d in g.nodes(data=True) if d["typ"] in ZIEL_TYPEN]
    zeilen, warnungen = [], []

    for nid, d in g.nodes(data=True):
        if nur_typen and d["typ"] not in nur_typen:
            continue

        url = url_fuer(nid)
        beschreibung = standort_beschreibung(g, nid)
        bild = _qr_mit_beschriftung(url, "Navigation starten", f"{beschreibung} [{nid}]")
        datei = QR_DIR / _dateiname(nid)
        bild.save(datei)

        # Prüfen: Erreicht man von hier aus wirklich JEDES Haus/jede Station?
        erreichbar = nx.node_connected_component(g, nid)
        fehlend = [g.nodes[z]["name"] for z in ziele if z not in erreichbar]
        if fehlend:
            warnungen.append(f"{nid}: {len(fehlend)} Ziele nicht erreichbar, z. B. {fehlend[:3]}")

        zeilen.append({"id": nid, "typ": d["typ"], "standort": beschreibung,
                       "url": url, "datei": datei.name})

    # Übersicht für den Ausdruck / die Studienarbeit (utf-8-sig -> Umlaute korrekt in Excel)
    with open(QR_DIR / "uebersicht.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=zeilen[0].keys(), delimiter=";")
        w.writeheader()
        w.writerows(zeilen)

    print(f"{len(zeilen)} QR-Codes in {QR_DIR} erzeugt.")
    print(f"Adresse in den Codes: {WEB_BASE_URL}")
    if "localhost" in WEB_BASE_URL:
        print("WARNUNG: 'localhost' funktioniert NICHT auf dem Handy/Tablet!")
    for w in warnungen:
        print("WARNUNG:", w)


if __name__ == "__main__":
    generate_all()