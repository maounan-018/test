"""Confronte les scores MyBestSim stockés (editorial_sources.MYBESTSIM_SCORES, saisis à la
main) à la page publique mybestsim.com/en/best-esim-providers/.

Deux contrôles, dans les deux sens :

1. **Dérive** : un score stocké qui ne correspond plus à celui publié, ou qui a disparu de
   la page.
2. **Découverte** : un fournisseur de notre catalogue qui est noté sur leur page sans que
   nous ayons son score. C'est le cas d'un nouveau fournisseur ajouté au catalogue : son
   score n'est pas « indisponible », il est simplement pas encore relevé — le script va le
   chercher et affiche la ligne à coller dans editorial_sources.py.

Sans `--apply`, le script signale sans jamais écrire. Avec `--apply` (ce que fait la CI), il
réécrit les valeurs de MYBESTSIM_SCORES et la date MYBESTSIM_CAPTURED, pour que le workflow
en fasse une pull request : la décision reste humaine, elle se prend sur le diff au lieu de
se prendre sur un rappel. Deux cas ne sont jamais écrits automatiquement, parce qu'ils
demandent un arbitrage et non une recopie : un score stocké qui a disparu de leur page, et
une ressemblance de noms partielle (« Maya » vs « Maya Mobile »).

Codes de sortie :
  0 — rien à faire ;
  3 — dérive recopiable (avec `--apply`, les fichiers ont été réécrits) ;
  1 — page illisible (structure changée) ou arbitrage humain nécessaire.
Trustpilot n'est pas vérifié ici : son robots.txt interdit tout le site aux robots et ses
pages répondent 403 — voir check_freshness.py, qui surveille l'âge du relevé manuel et
signale les fournisseurs jamais relevés.
"""
import argparse
import ast
import datetime
import html
import io
import os
import re
import sys
import urllib.request

from catalog_providers import DATA_JSON, match, near_matches, read_catalog_providers
from editorial_sources import MYBESTSIM_SCORES

URL = "https://mybestsim.com/en/best-esim-providers/"
SOURCES_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editorial_sources.py")

# Garde-fou de structure : leur page note une dizaine de fournisseurs. Si on en lit moins que
# ça, c'est plus vraisemblablement le balisage qui a changé qu'un classement qui a fondu —
# dans le doute on refuse d'écrire et on fait échouer le contrôle.
MIN_SCORES_PAGE = 5

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


def derives(stored: dict, live: dict) -> tuple:
    """Même constat que compare(), mais exploitable par --apply.

    Renvoie (recopiables, arbitrages) :
    - recopiables : [(fournisseur, stocké, publié)] — même fournisseur, score différent
    - arbitrages  : [fournisseur] — stocké chez nous, plus noté chez eux : à trancher
    """
    recopiables, arbitrages = [], []
    for provider, value in sorted(stored.items()):
        if provider not in live:
            arbitrages.append(provider)
        elif live[provider] != value:
            recopiables.append((provider, value, live[provider]))
    return recopiables, arbitrages


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


def _valide(score) -> bool:
    return isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 100


def appliquer(texte: str, changements: list, releve: str) -> tuple:
    """Réécrit MYBESTSIM_SCORES et MYBESTSIM_CAPTURED dans le source d'editorial_sources.

    `changements` : [(fournisseur, stocké ou None, publié)] — None = fournisseur ajouté.
    Renvoie (nouveau_texte, journal). Lève ValueError si le résultat ne relit pas exactement
    les valeurs attendues : mieux vaut un contrôle rouge qu'un fichier à moitié réécrit.
    """
    attendu = dict(_lire_scores(texte))
    journal = []

    for provider, ancien, nouveau in changements:
        if not _valide(nouveau):
            raise ValueError(f"score hors bornes pour {provider} : {nouveau!r}")
        if ancien is None:
            texte = _inserer(texte, provider, nouveau)
            journal.append(f"{provider} : ajouté à {nouveau}")
        else:
            texte = _remplacer(texte, provider, ancien, nouveau)
            journal.append(f"{provider} : {ancien} -> {nouveau}")
        attendu[provider] = nouveau

    texte, change = re.subn(r'(MYBESTSIM_CAPTURED\s*=\s*")\d{4}-\d{2}-\d{2}(")',
                            r"\g<1>" + releve + r"\g<2>", texte, count=1)
    if change != 1:
        raise ValueError("MYBESTSIM_CAPTURED introuvable dans editorial_sources.py")
    journal.append(f"MYBESTSIM_CAPTURED : {releve}")

    relu = _lire_scores(texte)
    if relu != attendu:
        raise ValueError(f"relecture incohérente : {relu} au lieu de {attendu}")
    return texte, journal


def _lire_scores(texte: str) -> dict:
    """Relit MYBESTSIM_SCORES depuis le source, sans l'exécuter."""
    for noeud in ast.walk(ast.parse(texte)):
        if isinstance(noeud, ast.Assign) and any(
            isinstance(c, ast.Name) and c.id == "MYBESTSIM_SCORES" for c in noeud.targets
        ):
            return ast.literal_eval(noeud.value)
    raise ValueError("MYBESTSIM_SCORES introuvable dans editorial_sources.py")


def _remplacer(texte: str, provider: str, ancien: int, nouveau: int) -> str:
    motif = re.compile(r'^(\s*"' + re.escape(provider) + r'":\s*)' + str(ancien) + r'(\s*,)',
                       re.M)
    texte, change = motif.subn(r"\g<1>" + str(nouveau) + r"\g<2>", texte, count=1)
    if change != 1:
        raise ValueError(f"ligne de {provider} introuvable (attendu : {ancien})")
    return texte


def _inserer(texte: str, provider: str, score: int) -> str:
    bloc = re.compile(r"(MYBESTSIM_SCORES = \{.*?\n)(\})", re.S)
    if not bloc.search(texte):
        raise ValueError("bloc MYBESTSIM_SCORES introuvable")
    return bloc.sub(r'\g<1>    "' + provider + r'": ' + str(score) + r",\n\g<2>", texte,
                    count=1)


def fetch_page(url: str = URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mybestsim-dashboard)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default=DATA_JSON, metavar="DATA_JSON",
                        help="data.json d'où lire la liste des fournisseurs du catalogue")
    parser.add_argument("--apply", action="store_true",
                        help="réécrit les scores recopiables dans editorial_sources.py")
    args = parser.parse_args(argv)

    live = parse_scores(fetch_page())
    if len(live) < MIN_SCORES_PAGE:
        print(f"ERREUR — {len(live)} score(s) lu(s) sur la page, moins que les "
              f"{MIN_SCORES_PAGE} attendus : sa structure HTML a probablement changé, le "
              f"script doit être adapté. Rien n'a été écrit.")
        return 1

    recopiables, arbitrages = derives(MYBESTSIM_SCORES, live)
    catalog = read_catalog_providers(args.catalog)
    trouves, a_verifier, sans_trace = discover(catalog, MYBESTSIM_SCORES, live)

    if recopiables:
        print(f"Écart avec {URL} :")
        for provider, ancien, nouveau in recopiables:
            print(f"- {provider} : stocké {ancien}, publié {nouveau}")
        print()

    if arbitrages:
        print("Stockés chez nous mais plus notés sur leur page — à trancher à la main "
              "(retirer le score, ou garder la dernière valeur connue en la datant) :")
        for provider in arbitrages:
            print(f"- {provider} (stocké : {MYBESTSIM_SCORES[provider]})")
        print()

    if trouves:
        print("Fournisseurs du catalogue notés sur leur page mais absents de nos données :")
        for provider, nom_publie, score in trouves:
            vu = "" if nom_publie == provider else f"  (publié sous « {nom_publie} »)"
            print(f"- {provider} : {score}{vu}")
        print()

    if a_verifier:
        print("Noms proches, à trancher à la main (rien n'a été retenu automatiquement) :")
        for provider, proches in a_verifier:
            print(f"- catalogue « {provider} » ressemble à {proches} sur leur page")
        print()

    changements = [(p, a, n) for p, a, n in recopiables]
    changements += [(p, None, s) for p, _, s in trouves]

    if arbitrages or a_verifier:
        print("Arbitrage humain nécessaire : rien n'a été écrit, pas de pull request.")
        return 1

    if not changements:
        print(f"OK — les {len(MYBESTSIM_SCORES)} scores stockés correspondent à la page "
              f"publique ({len(live)} fournisseurs notés).")
        if sans_trace:
            print(f"{len(sans_trace)} fournisseur(s) du catalogue ne figurent pas à leur "
                  f"classement : {', '.join(sans_trace)}.")
            print("Leur score A reste indisponible — c'est un constat vérifié, pas un oubli.")
        return 0

    if not args.apply:
        print("Mettre à jour scripts/editorial_sources.py (valeurs ET date de capture), "
              "ou relancer ce script avec --apply.")
        return 3

    source = io.open(SOURCES_PY, encoding="utf-8").read()
    nouveau_source, journal = appliquer(source, changements,
                                        datetime.date.today().isoformat())
    io.open(SOURCES_PY, "w", encoding="utf-8", newline="\n").write(nouveau_source)
    print("editorial_sources.py réécrit :")
    for ligne in journal:
        print(f"- {ligne}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
