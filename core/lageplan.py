# core/lageplan.py – liest den Lageplan DIREKT aus der Inkscape-SVG (kein Export, kein Inkscape nötig)
#
#   - blendet die Ebenen mit Knoten/Kanten aus (nur im Speicher, die Datei bleibt unverändert)
#   - bettet verknüpfte Bilder ein (z. B. ein importiertes PNG des UMM-Plans),
#     weil der Browser sie sonst nicht laden kann
#   - liefert die Maße der Seite (viewBox), damit die Route exakt darüber liegt
import base64
import mimetypes
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

SVGNS = "{http://www.w3.org/2000/svg}"
INK = "{http://www.inkscape.org/namespaces/inkscape}"
SODI = "{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}"
XLINK = "{http://www.w3.org/1999/xlink}"

for _p, _uri in {"": "http://www.w3.org/2000/svg",
                 "inkscape": "http://www.inkscape.org/namespaces/inkscape",
                 "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
                 "xlink": "http://www.w3.org/1999/xlink"}.items():
    ET.register_namespace(_p, _uri)


def _ist_graph_ebene(g):
    """Ebene mit Wegegraph: enthält Verbinder (Kanten) oder Ellipsen/Kreise (Knoten)."""
    for el in g.iter():
        if el.get(INK + "connector-type") is not None:
            return True
        if el.tag in (SVGNS + "ellipse", SVGNS + "circle"):
            return True
    return False


def _masse(root):
    vb = root.get("viewBox")
    if vb:
        _, _, b, h = (float(v) for v in re.split(r"[ ,]+", vb.strip()))
        return b, h
    zahl = lambda s: float(re.match(r"[\d.]+", s).group())
    return zahl(root.get("width")), zahl(root.get("height"))


def _bild_einbetten(el, ordner):
    """Verknüpftes Bild (Dateipfad) in data:-URI umwandeln, damit der Browser es anzeigt."""
    for attr in ("href", XLINK + "href"):
        ref = el.get(attr)
        if not ref or ref.startswith("data:"):
            continue
        kandidaten = []
        if ref.startswith("file:"):
            kandidaten.append(Path(unquote(urlparse(ref).path).lstrip("/")))
        else:
            kandidaten.append(ordner / unquote(ref))
        if el.get(SODI + "absref"):
            kandidaten.append(Path(el.get(SODI + "absref")))
        for datei in kandidaten:
            if datei.exists():
                mime = mimetypes.guess_type(datei.name)[0] or "image/png"
                daten = base64.b64encode(datei.read_bytes()).decode("ascii")
                el.set(attr, f"data:{mime};base64,{daten}")
                return None
        return ref          # nicht gefunden -> melden
    return None


def lade_lageplan(svg_pfad, ausblenden=None):
    """
    Gibt zurück: ((mime, base64), breite, hoehe, info)
      ausblenden : Liste von Ebenen-Namen; None = Graph-Ebenen automatisch erkennen
      info       : dict mit 'sichtbar', 'ausgeblendet', 'fehlende_bilder'
    """
    svg_pfad = Path(svg_pfad)
    baum = ET.parse(svg_pfad)
    root = baum.getroot()
    info = {"sichtbar": [], "ausgeblendet": [], "fehlende_bilder": []}

    for g in root.iter(SVGNS + "g"):
        if g.get(INK + "groupmode") != "layer":
            continue
        name = g.get(INK + "label") or g.get("id")
        weg = (name in ausblenden) if ausblenden is not None else _ist_graph_ebene(g)
        if weg:
            stil = re.sub(r"display\s*:\s*[^;]+;?", "", g.get("style", ""))
            g.set("style", ("display:none;" + stil).rstrip(";"))
            info["ausgeblendet"].append(name)
        else:
            info["sichtbar"].append(name)

    for el in root.iter(SVGNS + "image"):
        fehlt = _bild_einbetten(el, svg_pfad.parent)
        if fehlt:
            info["fehlende_bilder"].append(fehlt)

    breite, hoehe = _masse(root)
    text = ET.tostring(root, encoding="utf-8")
    return ("image/svg+xml", base64.b64encode(text).decode("ascii")), breite, hoehe, info