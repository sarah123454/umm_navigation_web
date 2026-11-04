# core/wegkarte_ui.py – Streamlit-Baustein: Lageplan mit Schritt-für-Schritt-Navigation
#
# Einbinden in app.py (nachdem route und anweisungen berechnet wurden):
#     from core.wegkarte_ui import zeige_wegkarte
#     zeige_wegkarte(g, route, anweisungen)
import streamlit as st

from config import BASE_DIR
from core import wegkarte
from core.lageplan import lade_lageplan
from core.wegkarte import lageplan_als_base64, pfad_aus, route_svg, schritt_abschnitte

# Lageplan: bevorzugt DIREKT die Inkscape-SVG (kein Export nötig), sonst ein exportiertes PNG
LAGEPLAN_SVG = BASE_DIR / "tools" / "Lageplan.svg"
LAGEPLAN_PNG = BASE_DIR / "daten" / "lageplan.png"
AUSBLENDEN = None          # None = Graph-Ebenen automatisch erkennen; sonst z. B. ["EG", "UG"]

KREISZAHLEN = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


@st.cache_data
def _svg_laden(pfad_text, geaendert, ausblenden):
    return lade_lageplan(pfad_text, list(ausblenden) if ausblenden else None)


@st.cache_data
def _png_laden(pfad_text, geaendert):
    return lageplan_als_base64(pfad_text)


def _lageplan():
    """Lädt den Lageplan. Fehlt er, Hinweis anzeigen und ohne Hintergrund weitermachen."""
    if LAGEPLAN_SVG.exists():
        aus = tuple(AUSBLENDEN) if AUSBLENDEN else None
        bild, breite, hoehe, info = _svg_laden(str(LAGEPLAN_SVG), LAGEPLAN_SVG.stat().st_mtime, aus)
        wegkarte.setze_masse(breite, hoehe)       # Maße direkt aus der SVG -> Route liegt exakt darüber
        if info["fehlende_bilder"]:
            st.warning("Im Lageplan sind verknüpfte Bilder, die nicht gefunden wurden: "
                       + ", ".join(info["fehlende_bilder"])
                       + ". Tipp: In Inkscape das Bild auswählen → Rechtsklick → „Bild einbetten“.")
        return bild
    if LAGEPLAN_PNG.exists():
        return _png_laden(str(LAGEPLAN_PNG), LAGEPLAN_PNG.stat().st_mtime)
    st.warning(f"🗺️ Lageplan nicht gefunden (erwartet: `{LAGEPLAN_SVG}`). "
               "Die Route wird ohne Hintergrund gezeigt.")
    return None


def _nummer(i):
    return KREISZAHLEN[i - 1] if i <= len(KREISZAHLEN) else f"{i}."


def zeige_wegkarte(g, route, anweisungen):
    """
    g           : Graph
    route       : Ergebnis aus dem Routing (Liste oder dict mit 'pfad')
    anweisungen : Liste der Textschritte aus erzeuge_anweisungen()
    """
    plan = _lageplan()                     # setzt auch die Maße für die Karte
    abschnitte = schritt_abschnitte(g, route)
    anzahl = len(abschnitte)

    if len(anweisungen) != anzahl:
        st.warning(f"Hinweis: {len(anweisungen)} Textschritte, aber {anzahl} Kartenabschnitte – "
                   "die Nummern passen evtl. nicht genau.")

    # Bei neuer Route wieder bei der Gesamtübersicht anfangen
    schluessel = tuple(pfad_aus(route))
    if st.session_state.get("wk_route") != schluessel:
        st.session_state.wk_route = schluessel
        st.session_state.wk_schritt = 0          # 0 = Gesamtübersicht

    schritt = st.session_state.wk_schritt

    # --- Karte ---
    svg = route_svg(g, route, plan, aktiv=schritt or None, zoom=True)
    st.markdown(svg, unsafe_allow_html=True)

    # --- Aktueller Schritt groß ---
    if schritt == 0:
        st.markdown(f"#### 🗺️ Gesamte Route – {anzahl} Schritte")
        st.caption("Tippen Sie auf „Los geht's“, um Schritt für Schritt geführt zu werden.")
    else:
        text = anweisungen[schritt - 1] if schritt - 1 < len(anweisungen) else ""
        st.markdown(
            f"<div style='font-size:1.35rem;line-height:1.5;padding:0.6rem 0'>"
            f"<b style='color:#d62828'>{_nummer(schritt)}</b> {text}</div>",
            unsafe_allow_html=True,
        )

    # --- Buttons (groß, gut mit dem Daumen erreichbar) ---
    links, mitte, rechts = st.columns([1, 1, 1])
    with links:
        if st.button("◀ Zurück", use_container_width=True, disabled=schritt == 0, key="wk_zurueck"):
            st.session_state.wk_schritt -= 1
            st.rerun()
    with mitte:
        if st.button("🗺️ Gesamt", use_container_width=True, disabled=schritt == 0, key="wk_gesamt"):
            st.session_state.wk_schritt = 0
            st.rerun()
    with rechts:
        beschriftung = "Los geht's ▶" if schritt == 0 else "Weiter ▶"
        if st.button(beschriftung, use_container_width=True, type="primary",
                     disabled=schritt >= anzahl, key="wk_weiter"):
            st.session_state.wk_schritt += 1
            st.rerun()

    if schritt:
        st.progress(schritt / anzahl, text=f"Schritt {schritt} von {anzahl}")
    if schritt == anzahl:
        st.success("🏁 Sie haben Ihr Ziel erreicht.")

    # --- Komplette Liste zum Nachlesen ---
    with st.expander("📋 Alle Schritte anzeigen"):
        for i, text in enumerate(anweisungen, 1):
            fett = "**" if i == schritt else ""
            st.markdown(f"{fett}{_nummer(i)} {text}{fett}")