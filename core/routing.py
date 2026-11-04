# core/routing.py
import networkx as nx

# Aufschlag in "gefühlten Metern" pro Stockwerkwechsel.
# Wirkt nur auf die Routenwahl, die angezeigten Meter bleiben echt.
AUFZUG_STRAFE = 60
TREPPE_STRAFE = 40


def _kantengewicht(g):
    """Gewichtsfunktion: echte Meter + Strafe, wenn sich die Etage ändert."""
    def gewicht(u, v, daten):
        meter = daten["meter"]
        von, nach = g.nodes[u], g.nodes[v]
        if von.get("etage") != nach.get("etage"):
            if von.get("typ") == "treppe" or nach.get("typ") == "treppe":
                return meter + TREPPE_STRAFE
            return meter + AUFZUG_STRAFE
        return meter
    return gewicht


def berechne_route(g, start_id, ziel_id, barrierefrei=False):
    """Kürzester Weg nach Meter (+ Strafe für Etagenwechsel).
    Bei barrierefrei=True werden Treppen-Kanten ignoriert."""
    if barrierefrei:
        erlaubt = [(u, v) for u, v, d in g.edges(data=True) if d["barrierefrei"]]
        graph = g.edge_subgraph(erlaubt)
    else:
        graph = g

    if start_id not in graph or ziel_id not in graph:
        return None
    try:
        pfad = nx.shortest_path(graph, start_id, ziel_id, weight=_kantengewicht(graph))
    except nx.NetworkXNoPath:
        return None

    # Anzeige mit echten Metern, ohne Strafe
    meter = nx.path_weight(graph, pfad, weight="meter")
    return {"knoten": pfad, "meter": round(meter, 1)}