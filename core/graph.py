# core/graph.py
import json
from pathlib import Path
import networkx as nx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def lade_graph(locations_file=None, edges_file=None):
    """Liest die beiden JSON-Dateien und baut einen ungerichteten Graphen."""
    locations_file = locations_file or DATA_DIR / "locations.json"
    edges_file = edges_file or DATA_DIR / "edges.json"

    orte = json.loads(Path(locations_file).read_text(encoding="utf-8"))
    kanten = json.loads(Path(edges_file).read_text(encoding="utf-8"))

    g = nx.Graph()
    for o in orte:
        g.add_node(o["id"], **o)
    for k in kanten:
        g.add_edge(
            k["von"], k["nach"],
            meter=k["meter"],
            barrierefrei=k["barrierefrei"],
        )
    return g


def finde_id(g, name):
    """Sucht eine Knoten-ID über den Namen (Label). Gibt None zurück, wenn nichts passt."""
    for nid, daten in g.nodes(data=True):
        if daten["name"].lower() == name.lower():
            return nid
    return None


def pruefe_graph(g):
    """Gibt Probleme als Liste von Texten zurück."""
    probleme = []
    if not nx.is_connected(g):
        teile = list(nx.connected_components(g))
        probleme.append(f"Graph ist in {len(teile)} getrennte Teile zerfallen.")
        for t in teile:
            namen = [g.nodes[n]["name"] for n in list(t)[:4]]
            probleme.append(f"  Teil mit {len(t)} Knoten, z. B.: {', '.join(namen)}")
    return probleme