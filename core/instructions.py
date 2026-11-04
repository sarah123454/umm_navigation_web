# core/instructions.py – macht aus einer Route eine kurze, verständliche Wegbeschreibung
#
# Neu gegenüber der alten Version:
#   1. Lesbare Namen   – "Eingangbeihaus01" wird "Eingang bei Haus 1" (Tabelle SCHOENE_NAMEN)
#   2. Zusammenfassen  – Geradeaus-Stücke werden zu EINEM Schritt mit Meterangabe
#   3. Orientierung    – Startsatz nennt die Richtung, Aufzüge/Eingänge unterwegs als "vorbei an"
#   4. Kreuzungen      – werden nie mit ihrem Label genannt, nur als "an der Kreuzung"

import math
import re

# ---------------------------------------------------------------------------
# 1) Einstellungen
# ---------------------------------------------------------------------------
GERADEAUS_BIS = 30      # Grad: kleinere Knicke gelten als "geradeaus"
HALB_BIS = 60           # Grad: 30–60° = "halb links/rechts"
KEHRTWENDE_AB = 150     # Grad: ab hier "umdrehen"
MAX_VORBEI = 2          # höchstens so viele Orientierungspunkte pro Schritt nennen

# Knotentypen, die man unterwegs sieht und nennen darf ("vorbei an Aufzug 3")
ORIENTIERUNG_TYPEN = ("eingang", "haus", "station", "aufzug", "treppe")

# Labels -> Name für Besucher. Hier trägst du alle "hässlichen" Labels ein.
# Nicht eingetragene Labels werden automatisch lesbarer gemacht (siehe _lesbar).
SCHOENE_NAMEN = {
    "Eingangbeihaus01": "Eingang Haus 1",
    "SeiteneinganginHaus2": "Seiteneingang Haus 2",
    "EingangWest": "Eingang West",
    "Brückezu03": "Brücke zu Haus 3",
    "Rezeption03": "Rezeption Haus 3",
    # "KreuzungzwischEingang01undRTWzufahrt": wird als Kreuzung erkannt, braucht keinen Namen
}

# Zusatzhinweise: erscheinen, wenn die Route an diesem Ort vorbeiführt
HINWEISE = {
    "Aufzug04": "Der Aufzug befindet sich xxxxxx.",
    "Rezeption03": "_________",
    "Brückezu03": "Die Brücke ist überdacht.",
}
# ---------------------------------------------------------------------------
# 2) Namen
# ---------------------------------------------------------------------------
def _lesbar(label):
    """'Aufzug04' -> 'Aufzug 4', 'EingangWest' -> 'Eingang West'."""
    s = re.sub(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", " ", label)   # CamelCase trennen
    s = re.sub(r"(?<=[A-Za-zäöüß])(?=\d)", " ", s)           # Buchstabe|Zahl trennen
    s = re.sub(r"\b0+(\d)", r"\1", s)                          # führende Nullen weg
    return s.replace("_", " ").strip()


def _ist_kreuzung(g, nid):
    d = g.nodes[nid]
    return d.get("typ") in ("kreuzung", "hilfspunkt") or "kreuzung" in d.get("name", "").lower()


def name_fuer_besucher(g, nid):
    """Name, wie er in der Wegbeschreibung erscheint."""
    d = g.nodes[nid]
    label = d.get("name", str(nid))
    if label in SCHOENE_NAMEN:
        return SCHOENE_NAMEN[label]
    anzeige = d.get("anzeige")
    if anzeige and anzeige != label:
        return anzeige
    return _lesbar(label)


def _ort(g, nid):
    """Ortsangabe für Abbiegehinweise: Kreuzungen ohne Label."""
    if _ist_kreuzung(g, nid):
        return "an der Kreuzung" if g.nodes[nid].get("typ") == "kreuzung" or \
            "kreuzung" in g.nodes[nid].get("name", "").lower() else "an der Abzweigung"
    return f"bei {name_fuer_besucher(g, nid)}"


def _ist_orientierung(g, nid):
    return g.nodes[nid].get("typ") in ORIENTIERUNG_TYPEN and not _ist_kreuzung(g, nid)


# ---------------------------------------------------------------------------
# 3) Geometrie
# ---------------------------------------------------------------------------
def _xy(g, nid):
    d = g.nodes[nid]
    return float(d["x"]), float(d["y"])


def _abstand(g, a, b):
    (x1, y1), (x2, y2) = _xy(g, a), _xy(g, b)
    return math.hypot(x2 - x1, y2 - y1)


def _winkel(g, vorher, jetzt, nachher):
    """Abbiegewinkel in Grad (-180..180). Positiv = rechts (y wächst nach unten)."""
    (ax, ay), (bx, by), (cx, cy) = _xy(g, vorher), _xy(g, jetzt), _xy(g, nachher)
    v1 = (bx - ax, by - ay)
    v2 = (cx - bx, cy - by)
    kreuz = v1[0] * v2[1] - v1[1] * v2[0]
    skalar = v1[0] * v2[0] + v1[1] * v2[1]
    return math.degrees(math.atan2(kreuz, skalar))


def _richtung(winkel):
    """None = geradeaus, sonst Text wie 'rechts', 'halb links', 'umdrehen'."""
    w = abs(winkel)
    if w <= GERADEAUS_BIS:
        return None
    if w >= KEHRTWENDE_AB:
        return "umdrehen"
    seite = "rechts" if winkel > 0 else "links"   # bei vertauschten Seiten hier tauschen
    return f"halb {seite}" if w <= HALB_BIS else seite


def _meter_text(m):
    if m is None:
        return ""
    if m < 8:
        return "wenige Meter "
    gerundet = int(round(m / 5.0) * 5) if m < 100 else int(round(m / 10.0) * 10)
    return f"ca. {gerundet} m "


def _vorbei_text(orte):
    if not orte:
        return ""
    orte = orte[:MAX_VORBEI]
    liste = orte[0] if len(orte) == 1 else ", ".join(orte[:-1]) + " und " + orte[-1]
    return f" (vorbei an {liste})"


# ---------------------------------------------------------------------------
# 4) Hauptfunktion
# ---------------------------------------------------------------------------
def _pfad_aus(route):
    if isinstance(route, dict):
        for key in ("pfad", "knoten", "path", "route"):
            if key in route:
                return list(route[key])
        raise KeyError("Route enthält keine Knotenliste (erwartet z. B. route['pfad']).")
    return list(route)


def erzeuge_anweisungen(g, route):
    pfad = _pfad_aus(route)
    if len(pfad) < 2:
        return ["Sie befinden sich bereits am Ziel."]

    # Maßstab: Koordinaten-Länge -> Meter (aus route['meter'], falls vorhanden)
    gesamt_einheiten = sum(_abstand(g, a, b) for a, b in zip(pfad, pfad[1:]))
    meter_gesamt = route.get("meter") if isinstance(route, dict) else None
    faktor = (meter_gesamt / gesamt_einheiten) if meter_gesamt and gesamt_einheiten else None

    def meter(einheiten):
        return einheiten * faktor if faktor else None

    start, ziel = pfad[0], pfad[-1]
    ziel_name = name_fuer_besucher(g, ziel)

    # Startsatz mit Blickrichtung: erster sichtbarer Orientierungspunkt auf der Route
    richtung_ort = next((n for n in pfad[1:] if _ist_orientierung(g, n)), None)
    if richtung_ort and richtung_ort != ziel:
        schritte = [f"Sie starten bei {name_fuer_besucher(g, start)}. "
                    f"Gehen Sie in Richtung {name_fuer_besucher(g, richtung_ort)}."]
    else:
        schritte = [f"Sie starten bei {name_fuer_besucher(g, start)}. "
                    f"Gehen Sie in Richtung {ziel_name}."]

    strecke = 0.0          # gesammelte Strecke seit dem letzten Hinweis
    vorbei = []            # gesammelte Orientierungspunkte seit dem letzten Hinweis

    for i in range(1, len(pfad) - 1):
        vorher, jetzt, nachher = pfad[i - 1], pfad[i], pfad[i + 1]
        strecke += _abstand(g, vorher, jetzt)

        # Etagenwechsel
        e_jetzt, e_nach = g.nodes[jetzt].get("etage"), g.nodes[nachher].get("etage")
        if e_jetzt is not None and e_nach is not None and e_jetzt != e_nach:
            schritte.append(f"Gehen Sie {_meter_text(meter(strecke))}bis {name_fuer_besucher(g, jetzt)}"
                            f"{_vorbei_text(vorbei)} und fahren Sie mit dem Aufzug ins {e_nach}.")
            strecke, vorbei = 0.0, []
            continue

        richtung = _richtung(_winkel(g, vorher, jetzt, nachher))
        if richtung is None:
            # geradeaus: nur merken, keinen eigenen Schritt erzeugen
            if _ist_orientierung(g, jetzt):
                vorbei.append(name_fuer_besucher(g, jetzt))
            continue

        anfang = f"Gehen Sie {_meter_text(meter(strecke))}geradeaus{_vorbei_text(vorbei)}"
        if richtung == "umdrehen":
            schritte.append(f"{anfang} und drehen Sie {_ort(g, jetzt)} um.")
        else:
            schritte.append(f"{anfang} und biegen Sie {_ort(g, jetzt)} {richtung} ab.")
        strecke, vorbei = 0.0, []

    # letztes Stück bis zum Ziel
    strecke += _abstand(g, pfad[-2], ziel)
    schritte.append(f"Nach {_meter_text(meter(strecke)) or 'kurzer Strecke '}"
                    f"{('(vorbei an ' + ', '.join(vorbei[:MAX_VORBEI]) + ') ') if vorbei else ''}"
                    f"erreichen Sie Ihr Ziel: {ziel_name}.")
    return schritte