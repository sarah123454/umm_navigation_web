# app.py
import sys
from pathlib import Path

# Projektordner in den Suchpfad, damit "core" und "config" gefunden werden
ROOT = Path(__file__).resolve().parent
if not (ROOT / "core").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from core.graph import lade_graph
from core.routing import berechne_route
from core.instructions import erzeuge_anweisungen
from core.ziele import (startpunkte, haeuser, stationen, alle_orte, ordne_stationen_zu,
                        standort_beschreibung, naechster_punkt_im_haus, start_im_haus,
                        alle_auswaehlbaren)
from config import AUSWAHL_MODUS
from core.suche import suche
from core.wegkarte_ui import zeige_wegkarte

st.set_page_config(page_title="UMM Campus-Navigation", page_icon="🏥")


@st.cache_resource            # Graph nur einmal laden, nicht bei jedem Klick
def hole_graph():
    return lade_graph()


@st.cache_resource            # Station->Haus-Zuordnung nur einmal berechnen
def hole_zuordnung(_g):
    zuordnung, warnungen = ordne_stationen_zu(_g)
    for w in warnungen:
        print("WARNUNG:", w)             # einmalig im Terminal, nicht für Besucher sichtbar
    return zuordnung


g = hole_graph()
zuordnung = hole_zuordnung(g)

# Neue Daten (svg_to_graph.py mit 'waehlbar'): nur echte Ziele, keine Knotenpunkte
NEUE_DATEN = any("waehlbar" in d for _, d in g.nodes(data=True))

start_optionen = startpunkte(g)          # nur Häuser, Stationen, Eingänge
haus_optionen = haeuser(g)
if AUSWAHL_MODUS == "alle" and not NEUE_DATEN:
    station_optionen = alle_orte(g)      # alter Übergangsmodus: jeder Knoten als Ziel
else:
    station_optionen = stationen(g, zuordnung)   # nur Stationen/Einrichtungen, mit Haus in Klammern

if NEUE_DATEN:
    # Start und Ziel: exakt dieselbe Liste (Stationen, Eingänge, Häuser)
    start_optionen = alle_auswaehlbaren(g, zuordnung)
    station_optionen = start_optionen


def such_auswahl(was, optionen, key):
    """Suchfeld mit Tippfehler-Toleranz; gibt die Liste für das Dropdown zurück."""
    suchtext = st.text_input(f"🔎 {was} eintippen (Tippfehler sind kein Problem):", key=key)
    if suchtext:
        treffer = suche(suchtext, optionen)
        if treffer:
            st.caption(f"✅ Beste Treffer für „{suchtext}“ – bitte unten bestätigen.")
            return treffer
        st.warning("Nichts Passendes gefunden. Bitte wählen Sie aus der Liste.")
    return list(optionen)


st.title("🏥 UMM Campus-Navigation (Prototyp)")
st.write("Willkommen! Navigieren Sie zu den verschiedenen Häusern und Stationen.")

# 1. Einschränkungen
einschraenkung = st.selectbox(
    "Bitte wählen Sie Ihre Einschränkungen aus:",
    ["Keine", "Rollstuhlzugänglichkeit", "Sehbehindert", "Überdacht"],
)
barrierefrei = einschraenkung == "Rollstuhlzugänglichkeit"

# 2. Startpunkt: per QR-Code (?start=<ID>, darf JEDER Knoten sein) oder manuell
qr_start = st.query_params.get("start")
if qr_start in g.nodes:
    start_id = qr_start
    st.info(f"📍 Ihr Standort (per QR-Code erkannt): **{standort_beschreibung(g, start_id)}**")
    if st.button("Anderen Startpunkt wählen"):
        st.query_params.clear()
        st.rerun()
else:
    if qr_start:
        st.warning("Der QR-Code ist unbekannt. Bitte wählen Sie Ihren Standort manuell.")
    start_name = st.selectbox("Ihr aktueller Standort:", list(start_optionen))
    start_id = start_optionen[start_name]

# 3. Ziel: nach Station ODER nach Haus (mit anschließender Stationsauswahl)
if not haus_optionen and not station_optionen:
    vorhandene_typen = sorted({d["typ"] for _, d in g.nodes(data=True)})
    st.error(
        "Keine Ziele gefunden. Prüfen Sie PRAEFIXE / ZIEL_KATEGORIEN in config.py "
        "und starten Sie die App neu.\n\n"
        f"Knotentypen in locations.json: {', '.join(vorhandene_typen)}"
    )
    st.stop()

if haus_optionen:
    modus = st.radio("Wie möchten Sie Ihr Ziel finden?",
                     ["📍 Nach Ort / Station", "🏢 Nach Haus"], horizontal=True)
else:
    modus = "🩺"                          # noch keine Häuser markiert -> Haus-Suche ausblenden

if modus.startswith("🏢"):
    if not haus_optionen:
        st.warning("Es sind noch keine Häuser hinterlegt. Bitte suchen Sie nach Station.")
        st.stop()
    haus_name = st.selectbox("Welches Haus?", such_auswahl("Haus", haus_optionen, "suche_haus"))
    haus_id = haus_optionen[haus_name]

    stationen_im_haus = stationen(g, zuordnung, haus_id)
    if stationen_im_haus:
        NUR_HAUS = f"– Nur zum Eingang von {haus_name} –"
        wahl = st.selectbox(f"Stationen in {haus_name} ({len(stationen_im_haus)}):",
                            [NUR_HAUS] + list(stationen_im_haus))
        if wahl == NUR_HAUS:
            # schnellster erreichbarer Punkt dieses Hauses (z. B. der nächste Eingang)
            ziel_id = naechster_punkt_im_haus(g, start_id, haus_id, barrierefrei)
            ziel_name = haus_name
        else:
            ziel_id, ziel_name = stationen_im_haus[wahl], f"{wahl} ({haus_name})"
    else:
        st.caption("Für dieses Haus sind keine Stationen hinterlegt.")
        ziel_id = naechster_punkt_im_haus(g, start_id, haus_id, barrierefrei)
        ziel_name = haus_name
    if ziel_name == haus_name and start_im_haus(g, start_id, haus_id):
        st.info(f"📍 Sie befinden sich bereits in {haus_name}.")
else:
    if not station_optionen:
        st.warning("Es sind noch keine Stationen hinterlegt. Bitte suchen Sie nach Haus.")
        st.stop()
    ziel_name = st.selectbox("Wohin möchten Sie?",
                             such_auswahl("Ziel", station_optionen, "suche_station"))
    ziel_id = station_optionen[ziel_name]

# 4. Route berechnen
# Die Route wird in st.session_state gespeichert, damit sie bei "Weiter ▶" (= Neuladen der Seite)
# nicht verschwindet. Ändert sich Start, Ziel oder Einschränkung, wird sie verworfen.
auswahl = (start_id, ziel_id, barrierefrei)
if st.session_state.get("auswahl") != auswahl:
    st.session_state.auswahl = auswahl
    st.session_state.route = None

if st.button("Route berechnen", type="primary"):
    route = berechne_route(g, start_id, ziel_id, barrierefrei=barrierefrei)
    if route is None:
        st.session_state.route = None
        st.error("Keine Route gefunden. Bitte wenden Sie sich an die Information.")
    else:
        st.session_state.route = route

route = st.session_state.get("route")
if route is not None:
    st.success(f"Route zu **{ziel_name}** – ca. {route['meter']:.0f} m")
    anweisungen = erzeuge_anweisungen(g, route)
    zeige_wegkarte(g, route, anweisungen)          # Lageplan + Schritt-für-Schritt
    st.info("💡 Tipp: Achten Sie unterwegs auf die Hinweisschilder der Universitätsmedizin Mannheim.")
    