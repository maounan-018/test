"""Données éditoriales externes sourcées, utilisées pour les scores composites A et B.

Ces valeurs ne sont PAS calculables depuis le catalogue CSV — elles proviennent de
recherches web ciblées (voir research_notes/). Chaque entrée est datée et sourcée pour
rester vérifiable et ne pas être présentée comme un fait établi sans origine.

Capturé le 2026-11-05/06.
"""

# Score MyBestSim officiel (/100), publié sur leur page de comparaison publique.
# Source : https://mybestsim.com/en/best-esim-providers/
# Seuls 10 fournisseurs sont notés sur leur site ; 5 recoupent notre catalogue de 18.
MYBESTSIM_SCORES = {
    "Airalo": 72,
    "Saily": 72,
    "Holafly": 67,
    "Yesim": 75,
    "Roamic": 80,
}

# Score Trustpilot (/5), retenu uniquement pour les fournisseurs avec >2 500 avis
# (seuil fixé pour exclure les échantillons trop petits pour être représentatifs).
# Sources : pages trustpilot.com/review/<domaine> de chaque fournisseur.
TRUSTPILOT_SCORES = {
    "Airalo": 4.2,       # trustpilot.com/review/airalo.com
    "Saily": 4.7,        # trustpilot.com/review/saily.com
    "Holafly": 4.7,      # trustpilot.com/review/esim.holafly.com (~96 800 avis)
    "Yesim": 4.3,        # trustpilot.com/review/yesim.app
    "Roamic": 4.7,       # trustpilot.com/review/roamic.com (~17 000 avis)
    "Ubigi": 4.1,         # trustpilot.com/review/cellulardata.ubigi.com (50 918 avis)
    "Nomad": 4.3,         # trustpilot.com/review/www.nomadesim.com (48 073 avis)
    "GigSky": 4.3,        # trustpilot.com/review/gigsky.com (8 777 avis)
    "aloSIM": 4.0,        # trustpilot.com/review/alosim.com (2 676 avis)
    "Jetpac": 4.7,        # trustpilot.com/review/jetpacglobal.com (3 618 avis)
    "Flexiroam": 4.7,     # trustpilot.com/review/flexiroam.com (2 878 avis)
    "Maya Mobile": 4.5,   # trustpilot.com/review/maya.net (12 914 avis)
}

# Exclus du score éditorial : page Trustpilot avec <2 500 avis (échantillon jugé non
# représentatif), ou match fournisseur non confirmé avec certitude suffisante.
EDITORIAL_EXCLUDED = {
    "eSIMX": "Trustpilot : 35 avis (<2500)",
    "Instabridge": "Trustpilot : 17 avis (<2500) — match produit confirmé mais échantillon trop faible",
    "Truphone": "Trustpilot : 182 avis (<2500), score très négatif (1.0-1.5) non confirmé par un volume suffisant",
    "JamboSIM": "Trustpilot : 6-20 avis selon la période (<2500)",
    "Yatelo": "Trustpilot : 9 avis (<2500)",
    "4S eSIM": "Trustpilot : 4-5 avis (<2500)",
}
