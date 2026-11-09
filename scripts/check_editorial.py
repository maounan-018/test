"""Confronte les scores MyBestSim stockés (editorial_sources.MYBESTSIM_SCORES, saisis à la
main) à la page publique mybestsim.com/en/best-esim-providers/.

Deux contrôles, dans les deux sens :

1. **Dérive** : un score stocké qui ne correspond plus à celui publié, ou qui a disparu de
   la page.
2. **Découverte** : un fournisseur de notre catalogue qui est noté sur leur page sans que
   nous ayons son score. C'est le cas d'un nouveau fournisseur ajouté au catalogue : son
   score n'est pas « indisponible », il est simplement pas encore relevé — le script va le
   chercher et affiche la ligne à coller dans editorial_sources.py.

Le script signale sans jamais écraser : mettre à jour editorial_sources.py reste une
décision humaine (et la date de capture doit suivre). Une ressemblance de noms partielle
(« Maya » vs « Maya Mobile ») est signalée à vérifier, jamais retenue automatiquement.

Code de sortie : 0 = rien à faire ; 1 = écart, score à ajouter, ou page illisible
(structure changée). Trustpilot n'est pas vérifié ici : son robots.txt interdit tout le site
aux robots et ses pages répondent 403 — voir check_freshness.py, qui surveille l'âge du
relevé manuel et signale les fournisseurs jamais relevés.
"""
import argparse
import html
import re
import sys
import urllib.request

from catalog_providers import DATA_JSON, match, near_matches, read_catalog_providers
from editorial_sources import MYBESTSIM_SCORES

URL = "https://mybestsim.com/en/best-esim-providers/"

# Une ligne du classement : nom du fournisseur, puis (avant le fournisseur suivant) son score
# « NN/100 ». Le garde-fou (?!...nm) empêche de rattacher à un fournisseur le score du
# suivant si une ligne n'en avait pas. La page a deux balisages pour le même score : les
# lignes « bureau » (mbshub-val + <span>) et les lignes « mobile » (mbshub-sv + <i>) —
# certains fournisseurs (Airalo, Saily, Holafly…) n'existent que dans le second.
ROW = re.compile(
    r'class="mbshub-nm">([^<]+)</div>'
    r'(?:(?!class="mbshub-nm").)*?'
    r'class="mbshub-(?:val|sv)">(\d+)<(?:span|i)>/100',
    re.S,
)


def parse_scores(page_html: str) -> dict:
    scores = {}
    for name, score in ROW.findall(page_html):
        scores.setdefault(html.unescape(name).strip(), int(score))  # 1re occurrence gagne
    return scores


def compare(stored: dict, live: dict) -> list:
    problems = []
    for provider, value in sorted(stored.items()):
        if provider not in live:
            problems.append(f"{provider} : absent de la page publique (stocké : {value})")
        elif live[provider] != value:
            problems.append(f"{provider} : stocké {value}, publié {live[provider]}")
    return problems


def discover(catalog: list, stored: dict, live: dict) -> tuple:
    """Fournisseurs du catalogue sans score stocké : on cherche s'ils sont notés sur la page.

    Renvoie (trouvés, à_vérifier, sans_trace) :
    - trouvés    : [(fournisseur, nom sur la page, score)] — à ajouter à editorial_sources
    - à_vérifier : [(fournisseur, [noms proches sur la page])] — ressemblance à trancher
    - sans_trace : [fournisseur] — réellement absent de leur classement
    """
    trouves, a_verifier, sans_trace = [], [], []
    for provider in catalog:
        if match(provider, stored):
            continue
        nom_publie = match(provider, live)
        if nom_publie:
            trouves.append((provider, nom_publie, live[nom_publie]))
            continue
        proches = near_matches(provider, live)
        if proches:
            a_verifier.append((provider, proches))
        else:
            sans_trace.append(provider)
    return trouves, a_verifier, sans_trace


def fetch_page(url: str = URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mybestsim-dashboard)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default=DATA_JSON, metavar="DATA_JSON",
                        help="data.json d'où lire la liste des fournisseurs du catalogue")
    args = parser.parse_args(argv)

    live = parse_scores(fetch_page())
    if not live:
        print("ERREUR — aucun score lu sur la page : sa structure HTML a probablement "
              "changé, le script doit être adapté.")
        return 1

    problems = compare(MYBESTSIM_SCORES, live)
    catalog = read_catalog_providers(args.catalog)
    trouves, a_verifier, sans_trace = discover(catalog, MYBESTSIM_SCORES, live)

    if problems:
        print(f"Écart avec {URL} :")
        for p in problems:
            print(f"- {p}")
        print()

    if trouves:
        print("Fournisseurs du catalogue notés sur leur page mais absents de nos données —")
        print("lignes à ajouter dans MYBESTSIM_SCORES (scripts/editorial_sources.py) :")
        for provider, nom_publie, score in trouves:
            vu = "" if nom_publie == provider else f"  # publié sous « {nom_publie} »"
            print(f'    "{provider}": {score},{vu}')
        print()

    if a_verifier:
        print("Noms proches, à trancher à la main (rien n'a été retenu automatiquement) :")
        for provider, proches in a_verifier:
            print(f"- catalogue « {provider} » ressemble à {proches} sur leur page")
        print()

    if problems or trouves:
        print("Mettre à jour scripts/editorial_sources.py (valeurs ET date de capture).")
        return 1

    print(f"OK — les {len(MYBESTSIM_SCORES)} scores stockés correspondent à la page publique "
          f"({len(live)} fournisseurs notés).")
    if sans_trace:
        print(f"{len(sans_trace)} fournisseur(s) du catalogue ne figurent pas à leur "
              f"classement : {', '.join(sans_trace)}.")
        print("Leur score A reste indisponible — c'est un constat vérifié, pas un oubli.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
