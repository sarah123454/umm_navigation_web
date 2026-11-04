# core/suche.py – fehlertolerante Zielsuche (nur Standardbibliothek, kein extra Paket nötig)
import re
import unicodedata
from difflib import SequenceMatcher

_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def normalisiere(text):
    """'Kopf-Klinik ü' -> 'kopfklinikue': klein, Umlaute ersetzt, Akzente/Leer-/Sonderzeichen weg."""
    t = text.lower()
    for a, b in _UMLAUTE.items():
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


def _woerter(text):
    return [normalisiere(w) for w in re.split(r"[\s_\-/]+", text) if normalisiere(w)]


def _vergleich(q, n):
    """Ähnlichkeit 0..1 zwischen normalisierter Eingabe q und normalisiertem Namen n."""
    if q == n:
        return 1.0
    if len(q) >= 3 and n.startswith(q):
        return 0.95                                    # "kardio" -> "kardiologie"
    if len(q) >= 3 and q in n:
        return 0.9                                     # "kardio" -> "innerekardiologie"
    voll = SequenceMatcher(None, q, n).ratio()         # Tippfehler im ganzen Wort
    anfang = SequenceMatcher(None, q, n[:len(q)]).ratio() * 0.9   # Tippfehler beim Anfang tippen
    return max(voll, anfang)


def bewerte(eingabe, name):
    """Gesamtpunktzahl: bester Wert aus ganzem Namen und jedem einzelnen Wort."""
    q = normalisiere(eingabe)
    if not q:
        return 0.0
    kandidaten = [normalisiere(name)] + _woerter(name)
    punkte = max(_vergleich(q, n) for n in kandidaten)

    # Zahlen müssen stimmen: "Haus 3" darf nicht "Haus 5" finden
    zahlen_eingabe = re.findall(r"\d+", eingabe)
    if zahlen_eingabe and zahlen_eingabe != re.findall(r"\d+", name):
        punkte *= 0.5
    return punkte


def suche(eingabe, namen, max_treffer=5, schwelle=0.6):
    """Die besten passenden Namen, sortiert nach Ähnlichkeit."""
    treffer = [(bewerte(eingabe, n), n) for n in namen]
    treffer = [t for t in treffer if t[0] >= schwelle]
    treffer.sort(key=lambda t: -t[0])
    return [n for _, n in treffer[:max_treffer]]