# core/routing.py
import networkx as nx


def berechne_route(g, start_id, ziel_id, barrierefrei=False):
    """Kürzester Weg nach Meter. Bei barrierefrei=True werden Treppen-Kanten ignoriert."""
    if barrierefrei:
        erlaubt = [(u, v) for u, v, d in g.edges(data=True) if d["barrierefrei"]]
        graph = g.edge_subgraph(erlaubt)
    else:
        graph = g

    if start_id not in graph or ziel_id not in graph:
        return None
    try:
        pfad = nx.shortest_path(graph, start_id, ziel_id, weight="meter")
    except nx.NetworkXNoPath:
        return None

    meter = nx.path_weight(graph, pfad, weight="meter")
    return {"knoten": pfad, "meter": round(meter, 1)}