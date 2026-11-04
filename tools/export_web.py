"""
export_web.py
Bereitet die statische Web-App im Ordner docs/ vor.

Kopiert:   data/locations.json, data/edges.json      -> docs/data/
           assets/umm_logo.png (falls vorhanden)      -> docs/assets/
Erzeugt:   docs/plan.svg    = Lageplan OHNE Wegegraph (Knoten/Verbinder) und OHNE
                              ausgeblendete Ebenen (interne Plaene) -> kleiner + sicherer
           docs/data/plan.json = Koordinatenbereich (viewBox) des Plans

Aufruf (im Ordner umm_navigation), immer NACH svg_to_graph.py:
    python tools\\svg_to_graph.py
    python tools\\export_web.py
"""

import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_HIER = Path(__file__).resolve().parent
BASE_DIR = _HIER.parent if _HIER.name == "tools" else _HIER
DATA = BASE_DIR / "data"
ZIEL = BASE_DIR / "docs"
SVG = BASE_DIR / "tools" / "Lageplan.svg"
LOGO = BASE_DIR / "assets" / "umm_logo.png"

SVG_NS = "http://www.w3.org/2000/svg"
INK_NS = "http://www.inkscape.org/namespaces/inkscape"
SODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
for prefix, uri in [("", SVG_NS), ("inkscape", INK_NS), ("sodipodi", SODI_NS),
                    ("xlink", "http://www.w3.org/1999/xlink")]:
    ET.register_namespace(prefix, uri)

KNOTEN_LABEL = re.compile(r"^(?:H\d+_)?E[^_]+_", re.IGNORECASE)   # wie in svg_to_graph.py


def _ist_versteckt(el):
    stil = (el.get("style") or "").replace(" ", "").lower()
    return "display:none" in stil or el.get("display") == "none"


def bereinige_svg(quelle, ziel):
    baum = ET.parse(quelle)
    wurzel = baum.getroot()
    entfernt = {"knoten": 0, "verbinder": 0, "versteckt": 0}

    def durchlaufen(eltern):
        for kind in list(eltern):
            tag = kind.tag.split("}")[-1]
            label = kind.get(f"{{{INK_NS}}}label") or ""
            if tag == "g" and _ist_versteckt(kind):
                eltern.remove(kind); entfernt["versteckt"] += 1; continue
            if tag in ("circle", "ellipse") and KNOTEN_LABEL.match(label):
                eltern.remove(kind); entfernt["knoten"] += 1; continue
            if tag == "path" and (kind.get(f"{{{INK_NS}}}connection-start")
                                  or kind.get(f"{{{INK_NS}}}connection-end")):
                eltern.remove(kind); entfernt["verbinder"] += 1; continue
            if tag == "namedview":
                eltern.remove(kind); continue
            durchlaufen(kind)

    durchlaufen(wurzel)

    vb = wurzel.get("viewBox")
    if vb:
        x, y, b, h = (float(v) for v in re.split(r"[\s,]+", vb.strip()))
    else:                                     # ohne viewBox: Breite/Hoehe als Einheiten
        zahl = lambda s: float(re.match(r"[\d.]+", s or "1000").group())
        x, y, b, h = 0.0, 0.0, zahl(wurzel.get("width")), zahl(wurzel.get("height"))
        wurzel.set("viewBox", f"0 0 {b} {h}")
    wurzel.set("preserveAspectRatio", "none")
    baum.write(ziel, encoding="utf-8", xml_declaration=True)
    return {"x": x, "y": y, "breite": b, "hoehe": h}, entfernt


def main():
    for datei in ("locations.json", "edges.json"):
        if not (DATA / datei).exists():
            sys.exit(f"Fehlt: {DATA / datei} – zuerst python tools\\svg_to_graph.py ausfuehren")
    if not SVG.exists():
        sys.exit(f"Fehlt: {SVG}")

    (ZIEL / "data").mkdir(parents=True, exist_ok=True)
    for datei in ("locations.json", "edges.json"):
        shutil.copy2(DATA / datei, ZIEL / "data" / datei)

    plan, entfernt = bereinige_svg(SVG, ZIEL / "plan.svg")
    (ZIEL / "data" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    if LOGO.exists():
        (ZIEL / "assets").mkdir(exist_ok=True)
        shutil.copy2(LOGO, ZIEL / "assets" / "umm_logo.png")

    groesse = (ZIEL / "plan.svg").stat().st_size / 1e6
    print(f"Fertig: {ZIEL}")
    print(f"  plan.svg: {groesse:.1f} MB  (entfernt: {entfernt['knoten']} Knoten, "
          f"{entfernt['verbinder']} Verbinder, {entfernt['versteckt']} ausgeblendete Ebenen)")
    print(f"  Planbereich: {plan}")
    print(f"  Logo: {'kopiert' if LOGO.exists() else 'keins gefunden (assets/umm_logo.png)'}")


if __name__ == "__main__":
    main()
