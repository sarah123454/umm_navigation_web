# test_route.py
from core.graph import lade_graph, finde_id, pruefe_graph
from core.routing import berechne_route
from core.instructions import erzeuge_anweisungen

g = lade_graph()
print(f"{g.number_of_nodes()} Knoten, {g.number_of_edges()} Kanten")

for problem in pruefe_graph(g):
    print("PROBLEM:", problem)

START = "Haupteingang"
ZIEL = "Aufzug03"

start = finde_id(g, START)
ziel = finde_id(g, ZIEL)

route = berechne_route(g, start, ziel)
if route:
    print(f"\nKnotenfolge ({len(route['knoten'])} Knoten):")
    for nid in route["knoten"]:
        print("  ->", g.nodes[nid]["name"])
    print("\nWegbeschreibung:")
    for nr, schritt in enumerate(erzeuge_anweisungen(g, route), start=1):
        print(f"  {nr}. {schritt}")
else:
    print("Keine Route gefunden")