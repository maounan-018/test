"""Compare les scores MyBestSim stockés (editorial_sources.MYBESTSIM_SCORES, saisis à la
main) à ceux de la page publique mybestsim.com/en/best-esim-providers/.

Signale l'écart sans jamais écraser quoi que ce soit : mettre à jour editorial_sources.py
reste une décision humaine (et la date de capture doit suivre).

Code de sortie : 0 = aucun écart ; 1 = écart détecté, ou page illisible (structure
changée). Trustpilot n'est volontairement pas vérifié ici : son site renvoie un 403 aux
requêtes automatisées et ses conditions d'utilisation interdisent le scraping — ces notes
restent à relever à la main.
"""
import html
import re
import sys
import urllib.request

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


def fetch_page(url: str = URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mybestsim-dashboard)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> int:
    live = parse_scores(fetch_page())
    if not live:
        print("ERREUR — aucun score lu sur la page : sa structure HTML a probablement "
              "changé, le script doit être adapté.")
        return 1
    problems = compare(MYBESTSIM_SCORES, live)
    if problems:
        print(f"Écart avec {URL} :")
        for p in problems:
            print(f"- {p}")
        print("\nMettre à jour scripts/editorial_sources.py (valeurs ET date de capture).")
        return 1
    print(f"OK — les {len(MYBESTSIM_SCORES)} scores stockés correspondent à la page publique "
          f"({len(live)} fournisseurs lus).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
