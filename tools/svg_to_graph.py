"""
svg_to_graph.py
Liest den Wegegraphen aus der Inkscape-SVG und erzeugt locations.json + edges.json.

Knoten:  Kreise/Ellipsen mit Label nach Schema  H<Haus>_E<Ebene>_<Typ><Nr>[_<Name>]
         z.B. H3_E2_AB05, H8_E2_AUF09_AufzugHaus8, H2_E2_AUF06_PRUEFEN
Kanten:  Inkscape-Verbinder (Connector-Werkzeug) zwischen zwei Knoten
Aufzuege/Treppen mit gleicher Nummer auf verschiedenen Ebenen werden automatisch verbunden.

Aufruf (im Ordner umm_navigation):
         python tools\\svg_to_graph.py                    (nimmt tools/Lageplan.svg)
         python tools\\svg_to_graph.py tools\\Lageplan.svg
Ausgabe: data/locations.json + data/edges.json im Format von core/graph.py
         (alte Dateien werden als .bak gesichert)
"""

import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------- Einstellungen
# Ausgabe in umm_navigation/daten/ (dort liest app.py), egal von wo das Skript gestartet wird.
# Liegt das Skript in tools/, ist der Projektordner eine Ebene hoeher.
_HIER = Path(__file__).resolve().parent
BASE_DIR = _HIER.parent if _HIER.name == "tools" else _HIER
AUSGABE = BASE_DIR / "data"                      # hier liest core/graph.py
STANDARD_SVG = BASE_DIR / "tools" / "Lageplan.svg"  # dieselbe Datei wie in core/wegkarte_ui.py

# Massstab: wie viele Meter entspricht 1 SVG-Einheit? (siehe Anleitung zum Kalibrieren)
METER_PRO_EINHEIT = 1.0
# Ersatz-Laenge fuer Ebenenwechsel (Wartezeit/Fahrt), in Metern
METER_AUFZUG = 15
METER_TREPPE = 20

# Kuerzel aus dem Label -> Knotentyp, den die App versteht (instructions.py, ziele.py)
TYP_APP = {"KR": "kreuzung", "AB": "hilfspunkt", "AUF": "aufzug", "TR": "treppe", "QR": "hilfspunkt"}
# Ziele ohne Kuerzel: Typ wird aus dem Namensanfang abgeleitet (sonst "station")
ZIEL_NACH_NAMEN = [("haupteingang", "eingang"), ("eingang", "eingang"), ("ausgang", "eingang"),
                   ("haus", "haus")]
SVG_NS = "http://www.w3.org/2000/svg"
INK_NS = "http://www.inkscape.org/namespaces/inkscape"

# [H<Haus>_]E<Ebene>_[<Typ>[<Nr>]][_<Name>]   - Haus, Typ, Nr und Name sind jeweils optional
MUSTER = re.compile(
    r"^(?:H(\d+)_)?E([^_]+)_"                              # Haus (optional), Ebene
    r"(?:(AB|KR|AUF|TR|ZI|QR)(\d*)(?=_|$)_?)?"              # Typ + Nr (optional)
    r"(.*)$",                                               # Anzeigename (Rest)
    re.IGNORECASE,
)
# Benannte Knoten, die trotzdem NICHT als Ziel auswaehlbar sein sollen (Name wie im Label)
NICHT_ALS_ZIEL = {"Brücke"}

NICHT_WAEHLBAR = {"AB", "AUF", "TR", "KR"}   # Hilfsknoten, nicht als Ziel auswaehlbar
KOSTEN_AUFZUG = 30                      # Wartezeit/Fahrt pro Ebenenwechsel (Pixel-Aequivalent)
KOSTEN_TREPPE = 40
MARKER_PRUEFEN = "PRUEFEN"

# Lesbare Namen fuer Ebenen und Knotentypen (fuer die Anzeige in der App)
EBENEN_NAMEN = {"1": "Erdgeschoss", "2": "Obergeschoss"}   # E1, E2 -> ...
TYP_NAMEN = {"AB": "Abzweig", "KR": "Kreuzung", "AUF": "Aufzug", "TR": "Treppe", "QR": "QR-Punkt"}

# Weg-Art der Verbinder: Unterebene ODER Label des Verbinders enthaelt eines dieser Woerter.
# Nichts davon -> "innen".  Reihenfolge = Vorrang.
# Nicht barrierefreie Einzelwege (Stufen, Schwelle, steile Rampe): Unterebene ODER Label
# des Verbinders enthaelt eines dieser Woerter.  Treppen-Knoten (TR) sind automatisch gesperrt.
NICHT_BARRIEREFREI = ("stufe", "nicht_barrierefrei", "nichtbarrierefrei")
# True: jede Kante an einem Treppen-Knoten (TR) ist nicht barrierefrei.
# Treppen-Knoten daher NEBEN den Flur setzen (Stichweg), nicht mitten in den Flur.
TREPPE_SPERRT_ALLE_KANTEN = True

WEG_BEREICHE = [("ueberdacht", "ueberdacht"), ("überdacht", "ueberdacht"),
                ("aussen", "aussen"), ("außen", "aussen")]


# ---------------------------------------------------------------- Transformationen
def matrix_mal(a, b):
    """Multipliziert zwei affine Matrizen (a, b, c, d, e, f) wie in SVG."""
    a1, b1, c1, d1, e1, f1 = a
    a2, b2, c2, d2, e2, f2 = b
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def parse_transform(text):
    """Unterstuetzt translate, scale, matrix, rotate (das, was Inkscape schreibt)."""
    m = (1, 0, 0, 1, 0, 0)
    if not text:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text):
        w = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        if name == "translate":
            t = (1, 0, 0, 1, w[0], w[1] if len(w) > 1 else 0)
        elif name == "scale":
            t = (w[0], 0, 0, w[1] if len(w) > 1 else w[0], 0, 0)
        elif name == "matrix":
            t = tuple(w)
        elif name == "rotate":
            r = math.radians(w[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(w) == 3:  # rotate(winkel, cx, cy)
                t = matrix_mal(matrix_mal((1, 0, 0, 1, w[1], w[2]), t), (1, 0, 0, 1, -w[1], -w[2]))
        else:
            continue
        m = matrix_mal(m, t)
    return m


def anwenden(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def anzeigename(roh):
    """'AnmeldungNotaufnahme' -> 'Anmeldung Notaufnahme', 'Radiologie_Anmeldung' -> 'Radiologie Anmeldung'."""
    text = roh.replace("_", " ")
    text = re.sub(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", " ", text)
    text = re.sub(r"(?<=[A-Za-zäöüßÄÖÜ])(?=\d)", " ", text)
    return text.strip()


def ebene_lesbar(ebene):
    """'1' -> 'Erdgeschoss', '2' -> 'Obergeschoss', unbekannt -> 'Ebene X'."""
    return EBENEN_NAMEN.get(str(ebene).upper(), f"Ebene {ebene}")


def lesbarer_name(k):
    """Anzeigename fuer die App: H3_E2_AB05 -> 'Haus 3, Obergeschoss, Abzweig 5'."""
    teile = []
    if k["haus"] is not None:
        teile.append(f"Haus {k['haus']}")
    teile.append(ebene_lesbar(k["ebene"]))
    if k["name"]:                                   # eigener Name aus dem Label hat Vorrang
        return k["name"]
    typ = TYP_NAMEN.get(k["typ"])
    if typ:
        teile.append(f"{typ} {k['nr']}" if k["nr"] is not None else typ)
    return ", ".join(teile)


def weg_bereich(texte):
    """'innen', 'aussen' oder 'ueberdacht' - aus Verbinder-Label und umgebenden Ebenen."""
    zusammen = " ".join(texte).lower()
    for wort, bereich in WEG_BEREICHE:
        if wort in zusammen:
            return bereich
    return "innen"


# ---------------------------------------------------------------- Einlesen
def lese_svg(pfad):
    baum = ET.parse(pfad)
    knoten = {}          # name -> Attribute
    xml_id_zu_name = {}  # SVG-id -> Knotenname (fuer die Verbinder)
    verbinder = []       # (start_xml_id, ende_xml_id, verbinder_id)
    warnungen = []

    def durchlaufen(element, matrix, ebenen=()):
        matrix = matrix_mal(matrix, parse_transform(element.get("transform")))
        tag = element.tag.split("}")[-1]
        if tag == "g" and element.get(f"{{{INK_NS}}}groupmode") == "layer":
            ebenen = ebenen + (element.get(f"{{{INK_NS}}}label", ""),)

        if tag in ("circle", "ellipse"):
            label = element.get(f"{{{INK_NS}}}label") or element.get("id", "")
            m = MUSTER.match(label)
            if m:
                haus, ebene, typ, nr, roh = m.groups()
                typ = (typ or "ZI").upper()          # nur Name, kein Typ -> Ziel
                roh = roh or ""
                x, y = anwenden(matrix, float(element.get("cx", 0)), float(element.get("cy", 0)))

                schluessel = label
                if schluessel in knoten:             # doppelte Labels nicht verschmelzen
                    i = 2
                    while f"{label}#{i}" in knoten:
                        i += 1
                    schluessel = f"{label}#{i}"
                    warnungen.append(f"Doppeltes Label: {label} (zweiter Knoten heisst intern {schluessel})")

                pruefen = roh.upper() == MARKER_PRUEFEN
                name = "" if pruefen else anzeigename(roh)
                waehlbar = typ not in NICHT_WAEHLBAR and name != "" and roh not in NICHT_ALS_ZIEL
                if typ == "ZI" and not name:
                    warnungen.append(f"Ziel ohne Anzeigename (nicht auswaehlbar): {label}")

                knoten[schluessel] = {
                    "label": label,
                    "haus": int(haus) if haus else None,
                    "ebene": ebene.upper(), "typ": typ,
                    "nr": int(nr) if nr else None,
                    "name": name, "x": round(x, 1), "y": round(y, 1),
                    "pruefen": pruefen, "waehlbar": waehlbar,
                }
                xml_id_zu_name[element.get("id")] = schluessel
            elif re.match(r"^(H\d+_)?E", label):
                warnungen.append(f"Label passt nicht zum Schema: {label}")

        if tag == "path":
            start = element.get(f"{{{INK_NS}}}connection-start")
            ende = element.get(f"{{{INK_NS}}}connection-end")
            if start or ende:
                texte = [element.get(f"{{{INK_NS}}}label", ""), *ebenen]
                stufen = any(w in " ".join(texte).lower() for w in NICHT_BARRIEREFREI)
                verbinder.append((start, ende, element.get("id"), weg_bereich(texte), stufen))

        for kind in element:
            durchlaufen(kind, matrix, ebenen)

    durchlaufen(baum.getroot(), (1, 0, 0, 1, 0, 0))
    return knoten, xml_id_zu_name, verbinder, warnungen


# ---------------------------------------------------------------- Kanten bauen
def baue_kanten(knoten, xml_id_zu_name, verbinder, warnungen):
    kanten = []
    gesehen = set()

    def hinzufuegen(a, b, distanz, art, bereich="innen", stufen=False):
        schluessel = tuple(sorted((a, b)))
        if a == b or schluessel in gesehen:
            return
        gesehen.add(schluessel)
        kanten.append({"von": a, "nach": b, "distanz": round(distanz, 1), "art": art,
                       "bereich": bereich, "stufen": stufen})

    # 1) Gezeichnete Verbinder
    for start, ende, vid, bereich, stufen in verbinder:
        a = xml_id_zu_name.get((start or "").lstrip("#"))
        b = xml_id_zu_name.get((ende or "").lstrip("#"))
        if not a or not b:
            warnungen.append(f"Verbinder {vid} haengt nicht an zwei Knoten (start={start}, ende={ende})")
            continue
        ka, kb = knoten[a], knoten[b]
        hinzufuegen(a, b, math.dist((ka["x"], ka["y"]), (kb["x"], kb["y"])), "weg", bereich, stufen)

    # 2) Automatische Aufzug- und Treppenkanten zwischen den Ebenen
    gruppen = defaultdict(list)
    haeuser_pro_nr = defaultdict(set)
    for name, k in knoten.items():
        if k["typ"] in ("AUF", "TR") and k["nr"] is not None:
            gruppen[(k["haus"], k["typ"], k["nr"])].append(name)   # nur im selben Haus verbinden
            haeuser_pro_nr[(k["typ"], k["nr"])].add(k["haus"])

    for (typ, nr), haeuser in haeuser_pro_nr.items():
        if len(haeuser) > 1:
            warnungen.append(f"{typ}{nr:02d} kommt in mehreren Haeusern vor: "
                             f"{sorted(haeuser, key=str)} - Nummer doppelt vergeben?")

    for (haus, typ, nr), namen in gruppen.items():
        namen.sort(key=lambda n: knoten[n]["ebene"])
        kosten = KOSTEN_AUFZUG if typ == "AUF" else KOSTEN_TREPPE
        for a, b in zip(namen, namen[1:]):          # nur vorhandene Halte verbinden
            hinzufuegen(a, b, kosten, "aufzug" if typ == "AUF" else "treppe")

    # 3) Knoten ohne Verbindung finden
    verbunden = {k["von"] for k in kanten} | {k["nach"] for k in kanten}
    for name in knoten:
        if name not in verbunden:
            warnungen.append(f"Knoten ohne Kante: {name}")

    return kanten


# ---------------------------------------------------------------- Format fuer die App
def app_typ(k):
    if k["typ"] in TYP_APP:
        return TYP_APP[k["typ"]]
    if k["name"] in NICHT_ALS_ZIEL or not k["waehlbar"]:
        return "durchgang"                              # z.B. Bruecke: kein Ziel, keine Kreuzung
    name = k["name"].lower()
    for anfang, typ in ZIEL_NACH_NAMEN:
        if name.startswith(anfang):
            return typ
    return "station"


def ziel_kategorie(k):
    """Fuer den Filter in der App. Hilfsknoten bekommen None."""
    if not k["waehlbar"]:
        return None
    typ = app_typ(k)
    return typ if typ in ("haus", "eingang") else "station"


def fuer_app(knoten, kanten):
    orte = []
    for nid, k in knoten.items():
        eintrag = {
            "id": nid,
            "name": k["label"],                         # Original-Label (fuer SCHOENE_NAMEN/HINWEISE)
            "anzeige": lesbarer_name(k),                # lesbarer Name fuer Dropdown/Text
            "typ": app_typ(k),
            "x": k["x"], "y": k["y"],
            "etage": k["ebene"],                        # bleibt kurz (1, 2) - wird intern verglichen
            "etage_name": ebene_lesbar(k["ebene"]),     # Erdgeschoss / Obergeschoss
            "waehlbar": k["waehlbar"],                  # nur diese erscheinen in der Zielauswahl
            "kategorie": ziel_kategorie(k),             # "haus" / "station" / "eingang" / None
        }
        if k["haus"] is not None:
            eintrag["haus_name"] = f"Haus {k['haus']}"
        if k["haus"] is not None:
            eintrag["haus_nr"] = k["haus"]
        orte.append(eintrag)

    app_kanten = []
    for e in kanten:
        if e["art"] == "aufzug":
            meter, frei = METER_AUFZUG, True
        elif e["art"] == "treppe":
            meter, frei = METER_TREPPE, False
        else:
            meter, frei = e["distanz"] * METER_PRO_EINHEIT, not e["stufen"]
        # Jede Kante, die eine Treppe (TR) beruehrt, ist nicht barrierefrei –
        # auch der Weg vom Flur zur Treppe und Treppen ohne zweite Etage (Stufen am Eingang).
        if TREPPE_SPERRT_ALLE_KANTEN and "TR" in (knoten[e["von"]]["typ"], knoten[e["nach"]]["typ"]):
            frei = False
        app_kanten.append({"von": e["von"], "nach": e["nach"],
                           "meter": round(meter, 1), "barrierefrei": frei,
                           "bereich": e["bereich"]})          # innen / aussen / ueberdacht
    return orte, app_kanten


# ---------------------------------------------------------------- Hauptprogramm
def main():
    pfad = Path(sys.argv[1]) if len(sys.argv) > 1 else STANDARD_SVG
    if not pfad.exists():
        sys.exit(f"Datei nicht gefunden: {pfad.resolve()}")
    print(f"Lese: {pfad.resolve()}")
    knoten, xml_ids, verbinder, warnungen = lese_svg(pfad)
    kanten = baue_kanten(knoten, xml_ids, verbinder, warnungen)

    orte, app_kanten = fuer_app(knoten, kanten)
    AUSGABE.mkdir(parents=True, exist_ok=True)
    for datei in ("locations.json", "edges.json"):          # alte Version sichern
        alt = AUSGABE / datei
        if alt.exists():
            alt.replace(AUSGABE / (datei + ".bak"))
    with open(AUSGABE / "locations.json", "w", encoding="utf-8") as f:
        json.dump(orte, f, ensure_ascii=False, indent=2)
    with open(AUSGABE / "edges.json", "w", encoding="utf-8") as f:
        json.dump(app_kanten, f, ensure_ascii=False, indent=2)
    print(f"Geschrieben: {AUSGABE / 'locations.json'}")
    print(f"Geschrieben: {AUSGABE / 'edges.json'}")

    print(f"{len(knoten)} Knoten, {len(kanten)} Kanten, "
          f"{sum(k['waehlbar'] for k in knoten.values())} waehlbare Ziele")
    bereiche = defaultdict(int)
    for e in app_kanten:
        bereiche[e["bereich"]] += 1
    print("Wege: " + ", ".join(f"{b}={n}" for b, n in sorted(bereiche.items())))
    print(f"Nicht barrierefrei: {sum(not e['barrierefrei'] for e in app_kanten)} Kanten")
    print("Ziele: " + ", ".join(sorted(o["anzeige"] for o in orte if o["waehlbar"])))
    typen = defaultdict(int)
    for o in orte:
        typen[o["typ"]] += 1
    print("Typen: " + ", ".join(f"{t}={n}" for t, n in sorted(typen.items())))
    for name, k in knoten.items():
        if k["pruefen"]:
            print(f"  ⚠ Noch pruefen: {name}")
    for w in warnungen:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()