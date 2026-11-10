"""Données éditoriales externes sourcées, utilisées pour les scores composites A et B.

Ces valeurs ne sont PAS calculables depuis le catalogue CSV — elles proviennent de
recherches web ciblées (voir research_notes/). Chaque entrée est datée et sourcée pour
rester vérifiable et ne pas être présentée comme un fait établi sans origine.

Capturé le 2026-11-05/06 ; score Holafly revérifié le 2026-11-10.
"""

# Score MyBestSim officiel (/100), publié sur leur page de comparaison publique.
# Source : https://mybestsim.com/en/best-esim-providers/
# Seuls 10 fournisseurs sont notés sur leur site ; 5 recoupent notre catalogue de 18.
MYBESTSIM_SCORES = {
    "Airalo": 72,
    "Saily": 72,
    "Holafly": 75,
    "Yesim": 75,
    "Roamic": 80,
}

# Notes Trustpilot (/5), retenues uniquement pour les fournisseurs à plus de 2 500 avis
# (seuil fixé pour exclure les échantillons trop petits pour être représentatifs).
#
# Relevé à la main, et c'est un choix assumé : le robots.txt de Trustpilot interdit tout le
# site aux robots non autorisés (« User-agent: * » puis « Disallow: / »), ses pages de
# notation comme api.trustpilot.com répondent 403, et la seule voie officiellement
# automatisable (API Data Solutions) passe par un contrat commercial. Aucun script de ce
# dépôt ne va donc interroger Trustpilot : scripts/check_freshness.py surveille l'âge de ces
# relevés et réclame une vérification humaine quand ils vieillissent.
#
# « captured » : jour du relevé. Le relevé initial s'est étalé sur les 5 et 6 novembre 2026
# sans que le jour exact de chaque fournisseur soit noté — la plus ancienne des deux dates
# est retenue pour tous, afin de surestimer l'âge plutôt que de le sous-estimer.
# « reviews » : nombre d'avis au moment du relevé, None quand il n'a pas été noté (à combler
# au prochain relevé : sans lui, le seuil des 2 500 avis n'est pas re-vérifiable).
# « reviews_approx » : volume lu en valeur arrondie sur la page, pas au chiffre près.
TRUSTPILOT_SOURCES = {
    "Airalo":      {"score": 4.2, "reviews": None,                          "domain": "airalo.com",              "captured": "2026-11-05"},
    "Saily":       {"score": 4.7, "reviews": None,                          "domain": "saily.com",               "captured": "2026-11-05"},
    "Holafly":     {"score": 4.7, "reviews": 96800, "reviews_approx": True, "domain": "esim.holafly.com",        "captured": "2026-11-05"},
    "Yesim":       {"score": 4.3, "reviews": None,                          "domain": "yesim.app",               "captured": "2026-11-05"},
    "Roamic":      {"score": 4.7, "reviews": 17000, "reviews_approx": True, "domain": "roamic.com",              "captured": "2026-11-05"},
    "Ubigi":       {"score": 4.1, "reviews": 50918,                         "domain": "cellulardata.ubigi.com",  "captured": "2026-11-05"},
    "Nomad":       {"score": 4.3, "reviews": 48073,                         "domain": "www.nomadesim.com",       "captured": "2026-11-05"},
    "GigSky":      {"score": 4.3, "reviews": 8777,                          "domain": "gigsky.com",              "captured": "2026-11-05"},
    "aloSIM":      {"score": 4.0, "reviews": 2676,                          "domain": "alosim.com",              "captured": "2026-11-05"},
    "Jetpac":      {"score": 4.7, "reviews": 3618,                          "domain": "jetpacglobal.com",        "captured": "2026-11-05"},
    "Flexiroam":   {"score": 4.7, "reviews": 2878,                          "domain": "flexiroam.com",           "captured": "2026-11-05"},
    "Maya Mobile": {"score": 4.5, "reviews": 12914,                         "domain": "maya.net",                "captured": "2026-11-05"},
}

# Seuil de représentativité appliqué aux notes ci-dessus (voir README, méthodologie du score B).
TRUSTPILOT_MIN_REVIEWS = 2500


def trustpilot_url(domain: str) -> str:
    """Page publique d'où provient la note — à ouvrir à la main pour la re-vérifier."""
    return f"https://www.trustpilot.com/review/{domain}"


# Interface historique utilisée par compute_metrics.py : {fournisseur: note}.
TRUSTPILOT_SCORES = {name: entry["score"] for name, entry in TRUSTPILOT_SOURCES.items()}

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
