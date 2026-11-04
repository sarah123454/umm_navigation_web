# qr/resolver.py
def lade_qr_punkte(g):
    """Rückgabe: {qr_id: {"id": knoten_id, "anzeige": text}}"""
    return {
        d["qr"]: {"id": nid, "anzeige": d["anzeige"]}
        for nid, d in g.nodes(data=True)
        if d.get("qr")
    }