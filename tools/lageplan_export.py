# tools/lageplan_export.py – exportiert den UMM-Lageplan als Hintergrundbild für die Wegkarte
#
# Was das Skript macht:
#   1. liest deine Inkscape-Datei (die mit dem Wegegraphen auf dem UMM-Plan)
#   2. blendet in einer KOPIE die Ebenen mit Knoten/Kanten aus (deine Datei bleibt unverändert)
#   3. exportiert die ganze Seite mit Inkscape als PNG nach daten/lageplan.png
#   4. trägt die passenden Maße (SVG_BREITE / SVG_HOEHE) in config.py ein
#
# Aufruf (im Ordner umm_navigation):
#   python tools/lageplan_export.py daten\umm_lageplan.svg
#   python tools/lageplan_export.py daten\umm_lageplan.svg --dpi 144
#   python tools/lageplan_export.py daten\umm_lageplan.svg --ausblenden "Knoten" "Kanten"
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ZIEL_PNG = BASE_DIR / "daten" / "lageplan.png"
CONFIG = BASE_DIR / "config.py"

NS = {
    "svg": "http://www.w3.org/2000/svg",
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
}
INK = "{%s}" % NS["inkscape"]
SVGNS = "{%s}" % NS["svg"]

# Typische Installationsorte von Inkscape unter Windows
INKSCAPE_PFADE = [
    r"C:\Program Files\Inkscape\bin\inkscape.exe",
    r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe",
    str(Path.home() / r"AppData\Local\Programs\Inkscape\bin\inkscape.exe"),
]

# Namespaces beim Speichern beibehalten, sonst schreibt ElementTree "ns0:" usw.
for _p, _uri in NS.items():
    ET.register_namespace("" if _p == "svg" else _p, _uri)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


# ---------------------------------------------------------------------------
def finde_inkscape():
    pfad = shutil.which("inkscape")
    if pfad:
        return pfad
    for p in INKSCAPE_PFADE:
        if Path(p).exists():
            return p
    sys.exit("❌ Inkscape nicht gefunden. Bitte den Pfad zu inkscape.exe oben in INKSCAPE_PFADE eintragen.")


def ebenen(root):
    """Alle Inkscape-Ebenen (auch Unterebenen) mit Namen."""
    return [(g, g.get(INK + "label") or g.get("id"))
            for g in root.iter(SVGNS + "g") if g.get(INK + "groupmode") == "layer"]


def ist_graph_ebene(g):
    """Erkennt Ebenen mit dem Wegegraphen: enthalten Verbinder (Kanten) oder Ellipsen/Kreise (Knoten)."""
    for el in g.iter():
        if el.get(INK + "connector-type") is not None:
            return True
        if el.tag in (SVGNS + "ellipse", SVGNS + "circle"):
            return True
    return False


def masse(root):
    """Maße der Seite in Benutzereinheiten (viewBox) – in genau diesen Einheiten liegen die Knoten-Koordinaten."""
    vb = root.get("viewBox")
    if vb:
        _, _, b, h = (float(v) for v in re.split(r"[ ,]+", vb.strip()))
        return b, h
    zahl = lambda s: float(re.match(r"[\d.]+", s).group())
    return zahl(root.get("width")), zahl(root.get("height"))


def config_aktualisieren(breite, hoehe):
    text = CONFIG.read_text(encoding="utf-8")
    fmt = lambda v: f"{v:g}"
    neu = text
    for name, wert in (("SVG_BREITE", breite), ("SVG_HOEHE", hoehe)):
        muster = rf"^{name}\s*=.*$"
        zeile = f"{name} = {fmt(wert)}"
        if re.search(muster, neu, flags=re.M):
            neu = re.sub(muster, zeile, neu, count=1, flags=re.M)
        else:
            neu += f"\n{zeile}\n"
    if neu != text:
        CONFIG.write_text(neu, encoding="utf-8")
        print(f"✅ config.py aktualisiert: SVG_BREITE = {fmt(breite)}, SVG_HOEHE = {fmt(hoehe)}")
    else:
        print(f"✅ config.py stimmt bereits (SVG_BREITE = {fmt(breite)}, SVG_HOEHE = {fmt(hoehe)})")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="UMM-Lageplan als PNG für die Wegkarte exportieren")
    ap.add_argument("svg", help="deine Inkscape-Datei mit Plan + Wegegraph")
    ap.add_argument("--dpi", type=int, default=192, help="Auflösung (Standard 192 = scharf beim Zoomen)")
    ap.add_argument("--ausblenden", nargs="*", default=None,
                    help="Namen der Ebenen, die ausgeblendet werden (Standard: automatisch erkennen)")
    ap.add_argument("--ziel", default=str(ZIEL_PNG), help="Ausgabedatei (Standard: daten/lageplan.png)")
    args = ap.parse_args()

    quelle = Path(args.svg)
    if not quelle.is_absolute():
        quelle = (Path.cwd() / quelle).resolve()
    if not quelle.exists():
        sys.exit(f"❌ Datei nicht gefunden: {quelle}")
    ziel = Path(args.ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)

    baum = ET.parse(quelle)
    root = baum.getroot()

    # --- 1. Ebenen ausblenden ---
    alle = ebenen(root)
    if not alle:
        print("⚠️  Keine Inkscape-Ebenen gefunden – es wird alles exportiert (inkl. Knoten/Kanten).")
    print("Ebenen in der Datei:")
    ausgeblendet = 0
    for g, name in alle:
        if args.ausblenden is not None:
            weg = name in args.ausblenden
        else:
            weg = ist_graph_ebene(g)
        if weg:
            stil = re.sub(r"display\s*:\s*[^;]+;?", "", g.get("style", ""))
            g.set("style", ("display:none;" + stil).rstrip(";"))
            ausgeblendet += 1
        print(f"   {'🚫 ausgeblendet' if weg else '👁  sichtbar    '}  {name}")

    if ausgeblendet == 0:
        print("⚠️  Keine Ebene ausgeblendet. Falls Knoten/Kanten im Bild sind, die Ebenen-Namen mit\n"
              "    --ausblenden \"Name1\" \"Name2\" angeben.")
    if ausgeblendet == len(alle) and alle:
        sys.exit("❌ Alle Ebenen würden ausgeblendet (dann wäre der Plan leer). Bitte --ausblenden nutzen.")

    # --- 2. Kopie speichern (im selben Ordner, damit verknüpfte Bilder gefunden werden) ---
    with tempfile.NamedTemporaryFile("wb", suffix=".svg", dir=quelle.parent, delete=False) as tmp:
        baum.write(tmp, encoding="utf-8", xml_declaration=True)
        kopie = Path(tmp.name)

    # --- 3. Mit Inkscape exportieren ---
    try:
        inkscape = finde_inkscape()
        print(f"\nExportiere mit {args.dpi} dpi … (kann ein paar Sekunden dauern)")
        erg = subprocess.run(
            [inkscape, str(kopie), "--export-type=png", f"--export-filename={ziel}",
             "--export-area-page", f"--export-dpi={args.dpi}", "--export-background=white",
             "--export-background-opacity=1"],
            capture_output=True, text=True,
        )
        if erg.returncode != 0 or not ziel.exists():
            sys.exit(f"❌ Inkscape-Export fehlgeschlagen:\n{erg.stderr}")
    finally:
        kopie.unlink(missing_ok=True)

    groesse = ziel.stat().st_size / 1_000_000
    print(f"✅ Lageplaln gespeichert: {ziel} ({groesse:.1f} MB)")
    if groesse > 4:
        print("⚠️  Datei ist groß – die Seite lädt evtl. langsam. Tipp: --dpi 120 probieren.")

    # --- 4. Maße in config.py ---
    breite, hoehe = masse(root)
    config_aktualisieren(breite, hoehe)
    print("\nFertig! App neu starten, dann liegt die Route auf dem UMM-Plan.")


if __name__ == "__main__":
    main()