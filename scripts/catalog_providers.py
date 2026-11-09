"""Liste des fournisseurs réellement présents dans le catalogue, lue depuis data.json.

Partagée par check_editorial.py et check_freshness.py : les deux doivent répondre à la même
question — « ce fournisseur est-il dans notre catalogue ? » — sans dépendre de pandas ni
relire les 18 CSV.

Le rapprochement des noms se fait sur une forme normalisée (minuscules, sans ponctuation ni
espaces) : « aloSIM » et « AloSim » désignent le même fournisseur, « 4S eSIM » et « 4sesim »
aussi. Aucun rapprochement approximatif n'est appliqué automatiquement — une ressemblance
partielle est signalée à l'humain, jamais retenue à sa place.
"""
import json
import os
import re

DATA_JSON = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")


def normalise(nom: str) -> str:
    return re.sub(r"[^a-z0-9]", "", nom.lower())


def read_catalog_providers(path: str = DATA_JSON) -> list:
    """Noms des fournisseurs tels qu'ils apparaissent dans les CSV, via data.json."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return sorted(r["provider"] for r in data["provider_breakdown"])


def match(nom: str, candidats) -> str:
    """Le candidat dont le nom normalisé est identique, sinon None."""
    cible = normalise(nom)
    for candidat in candidats:
        if normalise(candidat) == cible:
            return candidat
    return None


def near_matches(nom: str, candidats) -> list:
    """Candidats dont le nom normalisé contient l'autre (ressemblance à faire vérifier)."""
    cible = normalise(nom)
    if not cible:
        return []
    proches = []
    for candidat in candidats:
        autre = normalise(candidat)
        if autre != cible and (cible in autre or autre in cible):
            proches.append(candidat)
    return sorted(proches)
