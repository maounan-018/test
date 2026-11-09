"""Surveille l'âge des notes Trustpilot relevées à la main dans editorial_sources.py.

Ce script ne fait **aucune requête réseau**, et c'est le cœur de son intérêt : le robots.txt
de Trustpilot interdit tout le site aux robots non autorisés (« User-agent: * » puis
« Disallow: / »), ses pages de notation comme api.trustpilot.com répondent 403, et la seule
voie officiellement automatisable (API Data Solutions) passe par un contrat commercial. Ce
qui est automatisable, en revanche, c'est de ne jamais laisser un relevé vieillir en silence.

Il compare donc la date de relevé de chaque fournisseur à la date du jour, et échoue au-delà
du délai autorisé : le job GitHub passe au rouge, GitHub envoie l'e-mail, et la mise à jour
reste une décision humaine (ouvrir les pages listées, corriger les notes ET les dates).

Les volumes d'avis non relevés sont signalés sans faire échouer la vérification : c'est une
lacune connue du relevé initial, à combler au prochain passage, pas une dérive.

Codes de sortie : 0 = tout est frais ; 1 = au moins un relevé est périmé, ou une date est
illisible ou postérieure à aujourd'hui.
"""
import argparse
import datetime as dt
import sys

from editorial_sources import (
    TRUSTPILOT_MIN_REVIEWS,
    TRUSTPILOT_SOURCES,
    trustpilot_url,
)

DELAI_JOURS = 30

# Seuil affiché avec une espace comme séparateur de milliers (« 2 500 »).
SEUIL_AFFICHE = f"{TRUSTPILOT_MIN_REVIEWS:,}".replace(",", " ")


def parse_date(valeur: str) -> dt.date:
    return dt.datetime.strptime(valeur, "%Y-%m-%d").date()


def ages(sources: dict, aujourdhui: dt.date) -> list:
    """Chaque fournisseur avec l'âge de son relevé, du plus ancien au plus récent."""
    lignes = []
    for nom, entree in sources.items():
        releve = parse_date(entree["captured"])
        lignes.append({
            "provider": nom,
            "captured": releve,
            "age": (aujourdhui - releve).days,
            "score": entree["score"],
            "reviews": entree.get("reviews"),
            "reviews_approx": entree.get("reviews_approx", False),
            "url": trustpilot_url(entree["domain"]),
        })
    return sorted(lignes, key=lambda l: (-l["age"], l["provider"]))


def format_avis(ligne: dict) -> str:
    if ligne["reviews"] is None:
        return "non relevé"
    return f"{'~' if ligne['reviews_approx'] else ''}{ligne['reviews']:,} avis".replace(",", " ")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-age", type=int, default=DELAI_JOURS, metavar="JOURS",
                        help=f"âge maximum toléré d'un relevé (défaut : {DELAI_JOURS})")
    parser.add_argument("--today", metavar="AAAA-MM-JJ",
                        help="date de référence, pour les tests (défaut : aujourd'hui)")
    parser.add_argument("--checklist", action="store_true",
                        help="imprime la liste des pages à ouvrir pour le relevé manuel")
    args = parser.parse_args(argv)

    aujourdhui = parse_date(args.today) if args.today else dt.date.today()

    try:
        lignes = ages(TRUSTPILOT_SOURCES, aujourdhui)
    except ValueError as erreur:
        print(f"ERREUR — date de relevé illisible dans editorial_sources.py : {erreur}")
        return 1

    futures = [l for l in lignes if l["age"] < 0]
    if futures:
        print("ERREUR — date de relevé postérieure à aujourd'hui "
              f"({aujourdhui.isoformat()}), donc fausse :")
        for l in futures:
            print(f"- {l['provider']} : relevé le {l['captured'].isoformat()}")
        return 1

    if args.checklist:
        print(f"Relevé manuel des notes Trustpilot — {len(lignes)} pages à ouvrir "
              f"(seuil de représentativité : {SEUIL_AFFICHE} avis)")
        print("Pour chaque page : noter la note /5 ET le nombre d'avis, puis corriger "
              "editorial_sources.py (valeurs + champ « captured »).\n")
        for l in lignes:
            print(f"[ ] {l['provider']:12} stocké : {l['score']} /5, {format_avis(l)}")
            print(f"    {l['url']}")
        return 0

    perimes = [l for l in lignes if l["age"] > args.max_age]

    print(f"Âge des notes Trustpilot au {aujourdhui.isoformat()} "
          f"(délai toléré : {args.max_age} jours)\n")
    print(f"  {'Fournisseur':12}  {'Note':>5}  {'Volume':>12}  {'Relevé le':>10}  {'Âge':>8}")
    for l in lignes:
        marque = "PÉRIMÉ" if l["age"] > args.max_age else ""
        print(f"  {l['provider']:12}  {l['score']:>5}  {format_avis(l):>12}  "
              f"{l['captured'].isoformat():>10}  {l['age']:>4} j  {marque}")

    sans_volume = [l["provider"] for l in lignes if l["reviews"] is None]
    if sans_volume:
        print()
        print(f"Volume d'avis non relevé pour {', '.join(sans_volume)} : le seuil "
              f"des {SEUIL_AFFICHE} avis n'est pas re-vérifiable pour ces fournisseurs.")
        print("À combler au prochain relevé (n'empêche pas la vérification de passer).")

    if perimes:
        print(f"\n{len(perimes)} relevé(s) de plus de {args.max_age} jours — à re-vérifier "
              "à la main :")
        for l in perimes:
            print(f"- {l['provider']} ({l['age']} j) : {l['url']}")
        print("\nTrustpilot ne peut pas être interrogé par un script (robots.txt : "
              "Disallow: / ; pages en 403). Ouvrir les pages ci-dessus, puis mettre à jour "
              "scripts/editorial_sources.py — notes ET dates de relevé.")
        return 1

    plus_vieux = lignes[0]
    print(f"\nOK — les {len(lignes)} relevés ont moins de {args.max_age} jours "
          f"(le plus ancien : {plus_vieux['provider']}, {plus_vieux['age']} j).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
