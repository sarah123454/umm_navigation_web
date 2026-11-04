# config.py – zentrale Einstellungen
import os
import socket
from pathlib import Path


def _eigene_ip():
    """Ermittelt die IP dieses PCs im WLAN (z. B. 192.168.0.23). Rückfall: localhost."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))          # es wird nichts gesendet, nur die Route bestimmt
            return s.getsockname()[0]
    except OSError:
        return "localhost"


BASE_DIR = Path(__file__).resolve().parent

# --- Ports ---
WEB_PORT = 8501
KIOSK_PORT = 8502
KIOSK_START_ID = None          # feste Knoten-ID des Kiosk-Standorts, z. B. "E01"

# --- QR-Codes ---
# Reihenfolge: Umgebungsvariable UMM_URL > automatisch ermittelte WLAN-IP
WEB_BASE_URL = os.environ.get("UMM_URL", f"http://{_eigene_ip()}:{WEB_PORT}")
QR_DIR = BASE_DIR / "qr" / "codes"
QR_TYPEN = None                # None = QR-Code für JEDEN Knoten; sonst z. B. ("kreuzung", "eingang")

# --- Was erscheint in den Dropdowns? ---
# "alle":    Übergangsmodus für den groben Lageplan – JEDER Knoten ist wählbar
# "wichtig": nur Knoten, deren Label die MARKIERUNG enthält, z. B. "haus_Kopfklinik_wichtig"
#            (die Markierung wird in der App ausgeblendet)
AUSWAHL_MODUS = "alle"
MARKIERUNG = "_wichtig"

# --- Kategorien über Namens-Präfix (Label in Inkscape) ---
# "station_Kardiologie"  -> Kategorie "station", angezeigt als "Kardiologie"
# "haus_Haus_3"          -> Kategorie "haus",    angezeigt als "Haus 3"
# "haus_Kopfklinik"      -> Kategorie "haus",    angezeigt als "Kopfklinik"
# "station_HNO@Kopfklinik" -> Station "HNO", gehört zu Haus "Kopfklinik"
# (Unterstriche im Rest werden zu Leerzeichen; Station ohne "@Haus" wird
#  automatisch dem nächstgelegenen Haus zugeordnet)
PRAEFIXE = {
    "haus_": "haus",
    "station_": "station",
    "eingang_": "eingang",
}
# Rückfall für Knoten OHNE Präfix (nach Knotentyp aus locations.json)
TYP_KATEGORIEN = {
    "eingang": "eingang",
    "ziel": "ziel",            # alte Ziele ohne Präfix; Zeile löschen, wenn alles umbenannt ist
}

START_KATEGORIEN = ("eingang", "haus")             # im Start-Dropdown
ZIEL_KATEGORIEN = ("haus", "station", "ziel")      # alle möglichen Ziele
STATION_KATEGORIEN = ("station", "ziel")           # werden einem Haus zugeordnet

# --- Karte (Maße der Inkscape-SVG, an deine Datei anpassen!) ---
SVG_BREITE = 1000
SVG_HOEHE = 700