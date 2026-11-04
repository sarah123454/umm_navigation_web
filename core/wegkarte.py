# core/wegkarte.py – optische Wegbeschreibung: Route + nummerierte Schritte auf dem Lageplan
#
# Teilt die Route in dieselben Abschnitte wie die Text-Wegbeschreibung (instructions.py)
# und zeichnet sie als SVG über den Lageplan:
#   - gelaufene Abschnitte grau, aktueller Abschnitt kräftig, kommende heller
#   - an jedem Abschnitt eine Nummer (1, 2, 3 …), passend zum Textschritt
#   - Zoom auf den aktuellen Abschnitt UND in der Übersicht auf die ganze Route
#   - Linien und Kreise skalieren mit dem Ausschnitt (nicht mit dem ganzen Plan)
#   - liegen Kreise dicht beieinander, werden sie automatisch kleiner
#   - Lageplan optional in Graustufen und aufgehellt (SVG-Filter)
import base64
import math
from pathlib import Path

from config import SVG_BREITE, SVG_HOEHE

# Ab welchem Winkel (Grad) gilt eine Richtungsänderung als Abbiegen?
# Wird – falls vorhanden – aus instructions.py übernommen, damit Karte und Text gleich zählen.
try:
    from core.instructions import GERADEAUS_BIS
except ImportError:
    GERADEAUS_BIS = 30

# --- Aussehen (bei Bedarf anpassen) ---
PLAN_SAETTIGUNG = 0.3     # 1 = Originalfarben, 0 = komplett grau (0.2–0.4 = "Nebel")
PLAN_AUFHELLEN = 0.35     # 0 = Original, 1 = komplett weiß (0.3–0.5 ist gut)

FARBE_GELAUFEN = "#9ca3af"   # grau
FARBE_AKTUELL = "#e60026"    # knallrot
FARBE_KOMMEND = "#ff8a00"    # leuchtendes Orange
FARBE_MARKER = "#1f2937"     # Zwischenschritte: dunkelgrau
FARBE_AKTIV = "#0057ff"      # kräftiges Blau, hebt sich von der roten Linie ab
FARBE_START = "#00b33c"      # Startpunkt: sattes Grün
FARBE_ZIEL = "#e60026"       # Ziel: knallrot
LEGENDE = True               # kleine Legende unter dem Plan anzeigen

# Größen in Promille der AUSSCHNITTSbreite: Wird gezoomt, bleiben Kreise und Linien
# auf dem Bildschirm gleich groß, statt mitzuwachsen.
LINIENBREITE = 8
MARKER_RADIUS = 14

# --- Zoom ---
ZOOM_UEBERSICHT = True    # auch die Gesamtübersicht auf die Route zoomen (statt ganzer Plan)
ZOOM_RAND = 0.25          # Rand um die Route, Anteil der Routen-Ausdehnung
ZOOM_RAND_MIN = 0.03      # Mindestrand, Anteil der Planbreite
ZOOM_MIN = 0.12           # Ausschnitt nie kleiner als 12 % des Plans (sonst fehlt die Umgebung)

# --- Kreise bei Häufung verkleinern ---
MARKER_ABSTAND = 3.0      # gewünschter Abstand zwischen zwei Kreismitten, in Kreisradien
MARKER_MIN_FAKTOR = 0.45  # Kreise schrumpfen höchstens auf 45 % (Zahl muss lesbar bleiben)


def setze_masse(breite, hoehe):
    """Maße des Lageplans setzen (werden beim Laden der SVG automatisch ermittelt)."""
    global SVG_BREITE, SVG_HOEHE
    SVG_BREITE, SVG_HOEHE = float(breite), float(hoehe)


def _s(breite=None):
    """Skalierungsfaktor für Linien/Marker, bezogen auf die sichtbare Breite."""
    return (breite or SVG_BREITE) / 1000

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def pfad_aus(route):
    """Route kann eine Liste von Knoten-IDs oder ein dict mit 'pfad' sein."""
    if isinstance(route, dict):
        for schluessel in ("pfad", "path", "knoten", "nodes", "route"):
            if schluessel in route:
                return list(route[schluessel])
        raise KeyError(f"Route enthält keinen Pfad. Vorhandene Schlüssel: {list(route)}")
    return list(route)


def _xy(g, n):
    d = g.nodes[n]
    if "x" in d and "y" in d:
        return float(d["x"]), float(d["y"])
    return tuple(map(float, d["pos"]))      # Rückfall, falls die Koordinaten als 'pos' gespeichert sind


def lageplan_als_base64(pfad):
    """Lädt den Lageplan (PNG/JPG/SVG) einmal und gibt (mime, base64) zurück."""
    pfad = Path(pfad)
    mime = _MIME.get(pfad.suffix.lower())
    if mime is None:
        raise ValueError(f"Lageplan '{pfad.name}': bitte als PNG, JPG oder SVG exportieren (kein PDF).")
    return mime, base64.b64encode(pfad.read_bytes()).decode("ascii")


def _winkel(g, a, b, c):
    """Richtungsänderung in Grad am Knoten b (Weg a -> b -> c), Bereich -180 … 180."""
    (ax, ay), (bx, by), (cx, cy) = _xy(g, a), _xy(g, b), _xy(g, c)
    w = math.degrees(math.atan2(cy - by, cx - bx) - math.atan2(by - ay, bx - ax))
    return (w + 180) % 360 - 180


def _biegt_ab(g, a, b, c):
    return abs(_winkel(g, a, b, c)) > GERADEAUS_BIS


# ---------------------------------------------------------------------------
# Route in Abschnitte teilen (gleiche Logik wie erzeuge_anweisungen)
# ---------------------------------------------------------------------------
def schritt_abschnitte(g, route):
    """
    Liefert eine Liste von Abschnitten, einer pro Textschritt:
        {"nr": 1, "marker": Knoten-ID, "von": Index, "bis": Index, "art": "start"|"weg"|"ziel"}
    'von'/'bis' sind Indizes in der Knotenliste der Route.
    """
    pfad = pfad_aus(route)
    if len(pfad) < 2:
        return [{"nr": 1, "marker": pfad[0], "von": 0, "bis": 0, "art": "ziel"}]

    # Wendepunkte: Abbiegungen und Etagenwechsel – genau dort beginnt im Text ein neuer Schritt
    wende = []
    for i in range(1, len(pfad) - 1):
        vorher, jetzt, nachher = pfad[i - 1], pfad[i], pfad[i + 1]
        e1, e2 = g.nodes[jetzt].get("etage"), g.nodes[nachher].get("etage")
        if e1 is not None and e2 is not None and e1 != e2:
            wende.append(i)
        elif _biegt_ab(g, vorher, jetzt, nachher):
            wende.append(i)

    grenzen = [0] + wende + [len(pfad) - 1]
    abschnitte = [{"nr": 1, "marker": pfad[0], "von": 0, "bis": grenzen[1], "art": "start"}]
    for k in range(1, len(grenzen) - 1):
        abschnitte.append({"nr": k + 1, "marker": pfad[grenzen[k]],
                           "von": grenzen[k - 1], "bis": grenzen[k], "art": "weg"})
    abschnitte.append({"nr": len(grenzen), "marker": pfad[-1],
                       "von": grenzen[-2], "bis": grenzen[-1], "art": "ziel"})
    return abschnitte


# ---------------------------------------------------------------------------
# Zoom-Ausschnitt
# ---------------------------------------------------------------------------
def _ausschnitt(g, pfad, von, bis):
    """Ausschnitt (x, y, breite, hoehe) um die Knoten pfad[von..bis], im Seitenverhältnis des Plans."""
    xs, ys = zip(*(_xy(g, n) for n in pfad[von:bis + 1]))
    ausdehnung = max(max(xs) - min(xs), max(ys) - min(ys))
    rand = max(ausdehnung * ZOOM_RAND, SVG_BREITE * ZOOM_RAND_MIN)
    x0, x1 = min(xs) - rand, max(xs) + rand
    y0, y1 = min(ys) - rand, max(ys) + rand

    # Seitenverhältnis des Plans beibehalten, damit das Bild nicht springt
    verh = SVG_BREITE / SVG_HOEHE
    b, h = x1 - x0, y1 - y0
    if b / h < verh:
        neu_b = h * verh
        x0 -= (neu_b - b) / 2
        b = neu_b
    else:
        neu_h = b / verh
        y0 -= (neu_h - h) / 2
        h = neu_h

    # Mindestgröße (Umgebung bleibt sichtbar), höchstens der ganze Plan
    if b < SVG_BREITE * ZOOM_MIN:
        x0 -= (SVG_BREITE * ZOOM_MIN - b) / 2
        y0 -= (SVG_HOEHE * ZOOM_MIN - h) / 2
        b, h = SVG_BREITE * ZOOM_MIN, SVG_HOEHE * ZOOM_MIN
    b, h = min(b, SVG_BREITE), min(h, SVG_HOEHE)
    x0 = min(max(x0, 0), SVG_BREITE - b)
    y0 = min(max(y0, 0), SVG_HOEHE - h)
    return x0, y0, b, h


def _viewbox(g, pfad, von, bis):
    """Wie _ausschnitt, aber als viewBox-Text (für ältere Aufrufe)."""
    return "{:.1f} {:.1f} {:.1f} {:.1f}".format(*_ausschnitt(g, pfad, von, bis))


def _marker_faktor(punkte, r_basis):
    """Verkleinert alle Kreise, wenn zwei davon zu dicht beieinanderliegen."""
    min_abstand = None
    for i in range(len(punkte)):
        for j in range(i + 1, len(punkte)):
            d = math.dist(punkte[i], punkte[j])
            if d > 1e-6 and (min_abstand is None or d < min_abstand):
                min_abstand = d
    if min_abstand is None:
        return 1.0
    return max(MARKER_MIN_FAKTOR, min(1.0, min_abstand / (MARKER_ABSTAND * r_basis)))


# ---------------------------------------------------------------------------
# SVG zeichnen
# ---------------------------------------------------------------------------
def _linie(g, knoten, farbe, breite, deckkraft=1.0, skala=None):
    if len(knoten) < 2:
        return ""
    skala = skala or _s()
    punkte = " ".join(f"{x:.1f},{y:.1f}" for x, y in (_xy(g, n) for n in knoten))
    return (f'<polyline points="{punkte}" fill="none" stroke="{farbe}" stroke-width="{breite * skala:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="{deckkraft}"/>')


def _plan_filter():
    """SVG-Filter für den Lageplan: Sättigung reduzieren + aufhellen (Nebel-Effekt)."""
    teile = []
    if PLAN_SAETTIGUNG < 1:
        teile.append(f'<feColorMatrix type="saturate" values="{PLAN_SAETTIGUNG:.2f}"/>')
    if PLAN_AUFHELLEN > 0:
        s, i = 1 - PLAN_AUFHELLEN, PLAN_AUFHELLEN
        kanal = f'type="linear" slope="{s:.2f}" intercept="{i:.2f}"'
        teile.append(f'<feComponentTransfer><feFuncR {kanal}/><feFuncG {kanal}/>'
                     f'<feFuncB {kanal}/></feComponentTransfer>')
    if not teile:
        return "", ""
    defs = f'<defs><filter id="planfilter">{"".join(teile)}</filter></defs>'
    return defs, ' filter="url(#planfilter)"'


def route_svg(g, route, lageplan, aktiv=None, zoom=True):
    """
    g        : networkx-Graph
    route    : Route (Liste oder dict mit 'pfad')
    lageplan : (mime, base64) aus lageplan_als_base64() oder None (dann ohne Hintergrundbild)
    aktiv    : Nummer des aktuellen Schritts (1 …) oder None = Gesamtübersicht
    zoom     : auf den Abschnitt bzw. (Übersicht) auf die ganze Route zoomen
    """
    pfad = pfad_aus(route)
    abschnitte = schritt_abschnitte(g, route)
    ganzer_plan = (0.0, 0.0, SVG_BREITE, SVG_HOEHE)

    # 1) Ausschnitt bestimmen – davon hängen Linien- und Kreisgröße ab
    if aktiv is None:
        vb = _ausschnitt(g, pfad, 0, len(pfad) - 1) if (zoom and ZOOM_UEBERSICHT) else ganzer_plan
    else:
        a = abschnitte[aktiv - 1]
        vb = _ausschnitt(g, pfad, a["von"], a["bis"]) if zoom else ganzer_plan
    skala = _s(vb[2])
    viewbox = "{:.1f} {:.1f} {:.1f} {:.1f}".format(*vb)

    # 2) Linien
    teile = []
    if aktiv is None:
        teile.append(_linie(g, pfad, FARBE_AKTUELL, LINIENBREITE, 1.0, skala))
    else:
        teile.append(_linie(g, pfad[:a["von"] + 1], FARBE_GELAUFEN, LINIENBREITE, skala=skala))
        teile.append(_linie(g, pfad[a["bis"]:], FARBE_KOMMEND, LINIENBREITE, skala=skala))
        teile.append(_linie(g, pfad[a["von"]:a["bis"] + 1], FARBE_AKTUELL, LINIENBREITE + 3, skala=skala))

    # 3) Kreise: bei Häufung im sichtbaren Ausschnitt gemeinsam verkleinern
    x0, y0, b, h = vb
    sichtbar = [_xy(g, s["marker"]) for s in abschnitte]
    sichtbar = [(x, y) for x, y in sichtbar if x0 <= x <= x0 + b and y0 <= y <= y0 + h]
    r_basis = MARKER_RADIUS * skala
    faktor = _marker_faktor(sichtbar, r_basis)

    # aktiver Marker zuletzt, damit er oben liegt
    for s in sorted(abschnitte, key=lambda s: s["nr"] == aktiv):
        x, y = _xy(g, s["marker"])
        if s["nr"] == aktiv:
            farbe, r = FARBE_AKTIV, 1.4
        elif s["art"] == "start":
            farbe, r = FARBE_START, 1.2
        elif s["art"] == "ziel":
            farbe, r = FARBE_ZIEL, 1.2
        elif aktiv is not None and s["nr"] < aktiv:
            farbe, r = FARBE_GELAUFEN, 1.0
        else:
            farbe, r = FARBE_MARKER, 1.0
        r *= r_basis * faktor
        schrift = r * 1.05
        teile.append(
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{farbe}" stroke="white" '
            f'stroke-width="{3 * skala * faktor:.2f}"/>'
            f'<text x="{x:.1f}" y="{y + schrift * 0.36:.1f}" text-anchor="middle" fill="white" '
            f'font-family="Arial, sans-serif" font-size="{schrift:.1f}" font-weight="bold">{s["nr"]}</text></g>'
        )

    # Hintergrundbild (Lageplan) mit Filter – nur das Bild wird grau/heller, Route und Marker nicht
    if lageplan:
        defs, filt = _plan_filter()
        plan = (f'<image href="data:{lageplan[0]};base64,{lageplan[1]}" x="0" y="0" '
                f'width="{SVG_BREITE}" height="{SVG_HOEHE}"{filt}/>')
    else:
        defs, plan = "", ""

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" width="100%" '
        f'style="display:block;background:white" role="img" '
        f'aria-label="Lageplan mit eingezeichneter Route">'
        + defs
        + plan
        + "".join(teile) +
        "</svg>"
    )
    return (
        '<div style="border:1px solid #ccc;border-radius:10px;overflow:hidden;background:white">'
        + svg
        + (_legende(aktiv is not None) if LEGENDE else "")
        + "</div>"
    )


def _legende(mit_aktuell=False):
    """Kleine Legende als Leiste am unteren Bildrand."""
    def punkt(farbe, text):
        return (f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px">'
                f'<span style="width:14px;height:14px;border-radius:50%;background:{farbe};'
                f'border:2px solid white;box-shadow:0 0 0 1px #999"></span>{text}</span>')

    def linie(farbe, text):
        return (f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px">'
                f'<span style="width:22px;height:5px;border-radius:3px;background:{farbe}"></span>{text}</span>')

    eintraege = [punkt(FARBE_START, "Start (Sie sind hier)"),
                 punkt(FARBE_ZIEL, "Ziel"),
                 linie(FARBE_AKTUELL, "Route")]
    if mit_aktuell:
        eintraege.append(punkt(FARBE_AKTIV, "Aktueller Schritt"))
    return ('<div style="display:flex;flex-wrap:wrap;row-gap:4px;padding:8px 12px;'
            'border-top:1px solid #ddd;background:#fafafa;font-family:Arial,sans-serif;'
            'font-size:0.9rem;color:#222">' + "".join(eintraege) + "</div>")