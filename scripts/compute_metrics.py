"""Calcule toutes les métriques du dashboard eSIM à partir des CSV fournisseurs.

Usage: python compute_metrics.py [--source CHEMIN_DOSSIER] [--out docs/data.json]
Le dossier source accepte un chemin local, réseau ou un dossier OneDrive/Drive synchronisé
(aucun traitement spécifique requis : pathlib ne distingue pas ces cas).
"""
import argparse
import glob
import json
import os
import statistics as stats

import pandas as pd

from editorial_sources import MYBESTSIM_SCORES, TRUSTPILOT_SCORES, EDITORIAL_EXCLUDED
from country_coords import COUNTRY_COORDS

REGION_CODES = {"EU", "AS", "WW", "NA", "AF"}


def load_catalog(source_dir: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(source_dir, "*.csv")))
    if not files:
        raise FileNotFoundError(f"Aucun CSV trouvé dans {source_dir}")
    # keep_default_na=False est indispensable ici : le code pays "NA" (Amérique du Nord,
    # 192 lignes) fait partie de la liste de valeurs manquantes par défaut de pandas et
    # serait silencieusement converti en NaN. La zone disparaîtrait alors de la dispersion
    # régionale et de la couverture, bien que REGION_CODES la prévoie.
    # Seule la chaîne vide reste une valeur manquante ; data_gb est de toute façon
    # reconverti juste après, les forfaits illimités restent donc bien NaN.
    df = pd.concat(
        [pd.read_csv(f, keep_default_na=False, na_values=[""]) for f in files],
        ignore_index=True,
    )
    df["data_gb"] = pd.to_numeric(df["data_gb"], errors="coerce")
    return df


def base_metrics(df: pd.DataFrame) -> dict:
    return {
        "total_products": int(len(df)),
        "providers_count": int(df["provider"].nunique()),
        "over_100_eur": int((df["price"] > 100).sum()),
        "price_min": round(float(df["price"].min()), 2),
        "price_max": round(float(df["price"].max()), 2),
        "price_avg": round(float(df["price"].mean()), 2),
        "data_gb_avg": round(float(df["data_gb"].dropna().mean()), 2),
        "unlimited_count": int(df["data_gb"].isna().sum()),
    }


def _stable_counts_desc(series: pd.Series) -> pd.Series:
    """value_counts() ne garantit pas d'ordre stable entre valeurs à égalité (l'ordre peut
    varier d'une exécution/OS à l'autre). On trie d'abord par nom (stable), puis par
    comptage décroissant avec un tri stable : les égalités restent alors alphabétiques,
    de façon reproductible partout."""
    return series.value_counts().sort_index().sort_values(ascending=False, kind="stable")


def provider_breakdown(df: pd.DataFrame) -> list:
    counts = _stable_counts_desc(df["provider"])
    return [{"provider": p, "count": int(c)} for p, c in counts.items()]


def network_breakdown(df: pd.DataFrame) -> list:
    counts = _stable_counts_desc(df["network"])
    return [{"network": n, "count": int(c)} for n, c in counts.items()]


def validity_breakdown(df: pd.DataFrame) -> list:
    counts = df["validity_days"].value_counts().sort_index()
    return [{"validity_days": int(v), "count": int(c)} for v, c in counts.items()]


def size_breakdown(df: pd.DataFrame) -> list:
    sized = df.dropna(subset=["data_gb"])
    counts = sized["data_gb"].value_counts().sort_index()
    return [{"data_gb": float(g), "count": int(c)} for g, c in counts.items()]


def price_per_size(df: pd.DataFrame) -> list:
    sized = df.dropna(subset=["data_gb"])
    avg = sized.groupby("data_gb")["price"].mean().sort_index()
    return [{"data_gb": float(g), "price_avg": round(float(p), 2)} for g, p in avg.items()]


def price_per_gb_by_provider(df: pd.DataFrame) -> list:
    """price/Go par fournisseur, en ratio d'agrégats (somme des prix / somme des Go) et
    non en moyenne de ratios individuels.
    Une moyenne de price/Go par offre pondère un forfait 1 Go à 8,59 € (8,59 €/Go) autant
    qu'un forfait 50 Go à 56,67 € (1,13 €/Go) : elle mesure alors autant le mix de tailles
    du catalogue du fournisseur que son niveau de prix réel. Vérifié sur les données :
    les deux formules changent le classement de 18 fournisseurs de jusqu'à 10 rangs
    (Truphone 16e en moyenne de ratios -> 6e en ratio pondéré), alors que cette métrique
    alimente directement le score composite — le podium ne doit pas dépendre d'un choix
    de formule non documenté."""
    sized = df.dropna(subset=["data_gb"])
    sized = sized[sized["data_gb"] > 0].copy()
    agg = sized.groupby("provider").apply(
        lambda g: g["price"].sum() / g["data_gb"].sum(), include_groups=False
    ).sort_values(kind="stable")
    return [{"provider": p, "price_per_gb": round(float(v), 2)} for p, v in agg.items()]


def price_per_day_by_provider(df: pd.DataFrame) -> list:
    tmp = df.copy()
    tmp["price_per_day"] = tmp["price"] / tmp["validity_days"]
    avg = tmp.groupby("provider")["price_per_day"].mean().sort_values(kind="stable")
    return [{"provider": p, "price_per_day": round(float(v), 2)} for p, v in avg.items()]


def usage_intensity_segments(df: pd.DataFrame) -> dict:
    """Segmentation Go/jour, bornes inspirées d'une étude Saily sur l'usage réel en
    roaming (léger <0.1 Go/j, moyen 0.1-0.5, lourd >0.5), recalibrées sur la distribution
    du catalogue plutôt qu'appliquées telles quelles (cf. rapport de recherche)."""
    sized = df.dropna(subset=["data_gb"]).copy()
    sized["gb_per_day"] = sized["data_gb"] / sized["validity_days"]
    light = int((sized["gb_per_day"] < 0.3).sum())
    medium = int(((sized["gb_per_day"] >= 0.3) & (sized["gb_per_day"] < 1.0)).sum())
    heavy = int((sized["gb_per_day"] >= 1.0).sum())
    return {"leger": light, "moyen": medium, "lourd": heavy}


def regional_dispersion(df: pd.DataFrame) -> list:
    """Coefficient de variation (CV = écart-type / moyenne) du prix/Go par région,
    méthode empruntée à la littérature sur la dispersion des prix de détail."""
    sized = df.dropna(subset=["data_gb"])
    sized = sized[sized["data_gb"] > 0].copy()
    sized["price_per_gb"] = sized["price"] / sized["data_gb"]
    regions = sized[sized["country_code"].isin(REGION_CODES)]
    out = []
    for region, grp in regions.groupby("country_name"):
        vals = grp["price_per_gb"].tolist()
        if len(vals) < 2:
            continue
        mean = stats.mean(vals)
        cv = stats.stdev(vals) / mean if mean else 0
        out.append({"region": region, "price_per_gb_avg": round(mean, 2), "cv": round(cv, 3), "n": len(vals)})
    return sorted(out, key=lambda r: (-r["cv"], r["region"]))


def network_premium_by_country(df: pd.DataFrame) -> dict:
    """Prime 5G vs 4G, calculée À DESTINATION ÉGALE (par pays) puis moyennée —
    corrige le biais de la première estimation globale (confondue avec la géographie)."""
    sized = df.dropna(subset=["data_gb"])
    sized = sized[sized["data_gb"] > 0].copy()
    # « À destination égale » suppose une destination : les zones multi-pays (Europe,
    # Asie, Monde, Amérique du Nord) ne sont pas des pays et étaient comptées comme tels
    # dans n_countries, ce que le libellé « N pays » du dashboard contredisait.
    sized = sized[~sized["country_code"].isin(REGION_CODES)]
    sized["price_per_gb"] = sized["price"] / sized["data_gb"]

    premiums = []
    for country, grp in sized.groupby("country_name"):
        p4 = grp.loc[grp["network"] == "4G", "price_per_gb"]
        p5 = grp.loc[grp["network"] == "5G", "price_per_gb"]
        if len(p4) >= 3 and len(p5) >= 3:
            premiums.append((p5.mean() - p4.mean()) / p4.mean())

    if not premiums:
        return {"premium_pct": None, "n_countries": 0, "note": "pas assez de pays avec 4G et 5G comparables"}
    return {
        "premium_pct": round(stats.mean(premiums) * 100, 1),
        "n_countries": len(premiums),
        "note": "moyenne des primes calculées pays par pays (contrôle géographique), pas un agrégat global",
    }


def volume_discount_curve(df: pd.DataFrame) -> list:
    """Courbe prix/Go moyen par tranche de taille, par fournisseur — quantifie
    l'économie d'échelle au lieu de l'estimer globalement."""
    sized = df.dropna(subset=["data_gb"])
    sized = sized[sized["data_gb"] > 0].copy()
    sized["price_per_gb"] = sized["price"] / sized["data_gb"]
    out = []
    for provider, grp in sized.groupby("provider"):
        by_size = grp.groupby("data_gb")["price_per_gb"].mean().sort_index()
        out.append({
            "provider": provider,
            "points": [{"data_gb": float(g), "price_per_gb": round(float(v), 2)} for g, v in by_size.items()],
        })
    return out


def price_by_country(df: pd.DataFrame) -> list:
    """Prix moyen, prix/Go et nombre d'offres par pays réel, avec coordonnées pour la carte.
    Les codes non géographiques (EU/AS/WW, et les lignes sans code pays) sont exclus :
    un forfait multi-pays n'a pas de position unique sur une carte."""
    sized = df.dropna(subset=["data_gb"]).copy()
    sized = sized[sized["data_gb"] > 0]
    sized["price_per_gb"] = sized["price"] / sized["data_gb"]

    out = []
    for code, grp in df.groupby("country_code"):
        if code not in COUNTRY_COORDS:
            continue
        lat, lng = COUNTRY_COORDS[code]
        gb_grp = sized[sized["country_code"] == code]
        out.append({
            "code": code,
            "country": grp["country_name"].iloc[0],
            "lat": lat,
            "lng": lng,
            "offers": int(len(grp)),
            "price_avg": round(float(grp["price"].mean()), 2),
            # Ratio d'agrégats (comme price_per_gb_by_provider), pas moyenne de ratios :
            # c'est la métrique utilisée pour colorer la carte, elle doit rester comparable.
            "price_per_gb": round(float(gb_grp["price"].sum() / gb_grp["data_gb"].sum()), 2) if len(gb_grp) else None,
            "providers": int(grp["provider"].nunique()),
        })
    return sorted(out, key=lambda r: (-r["offers"], r["country"]))


def price_by_destination(df: pd.DataFrame, n: int = 15) -> list:
    """Prix moyen, €/Go et nombre d'offres par destination, pour les destinations les plus
    couvertes (mêmes n que top_destinations, pour cohérence visuelle entre graphiques).
    price_avg n'est pas comparable d'une destination à l'autre : un pays où les
    fournisseurs ne vendent que de gros forfaits paraît "cher" même à prix/Go identique
    (confusion non contrôlée avec le mix de tailles de forfait local). price_per_gb,
    en ratio d'agrégats comme price_per_gb_by_provider, est la métrique réellement
    comparable entre destinations."""
    top = set(d["destination"] for d in top_destinations(df, n))
    sub = df[df["country_name"].isin(top)]
    grp = sub.groupby("country_name").agg(price_avg=("price", "mean"), offers=("price", "size"))
    grp = grp.sort_index().sort_values("offers", ascending=False, kind="stable")

    sized = sub.dropna(subset=["data_gb"])
    sized = sized[sized["data_gb"] > 0]
    pgb = sized.groupby("country_name").apply(
        lambda g: g["price"].sum() / g["data_gb"].sum(), include_groups=False
    )
    # Nombre de fournisseurs calculé ici plutôt que récupéré depuis price_by_country :
    # ce dernier exclut les zones multi-pays (Europe/Asie/Monde/Amérique du Nord, pas de
    # position unique sur une carte), alors qu'elles font partie des destinations les
    # plus couvertes et doivent donc aussi afficher leur nombre de fournisseurs ici.
    providers = sub.groupby("country_name")["provider"].nunique()

    out = []
    for d, r in grp.iterrows():
        out.append({
            "destination": d,
            "price_avg": round(float(r.price_avg), 2),
            "price_per_gb": round(float(pgb[d]), 2) if d in pgb.index else None,
            "offers": int(r.offers),
            "providers": int(providers[d]),
        })
    return out


def top_destinations(df: pd.DataFrame, n: int = 15) -> list:
    counts = _stable_counts_desc(df["country_name"]).head(n)
    return [{"destination": d, "offers": int(c)} for d, c in counts.items()]


def topup_flexibility(df: pd.DataFrame) -> list:
    out = []
    for provider, grp in df.groupby("provider"):
        pct = (grp["top_up"] == "oui").mean() * 100
        out.append({"provider": provider, "topup_pct": round(float(pct), 1)})
    return sorted(out, key=lambda r: (-r["topup_pct"], r["provider"]))


def coverage_breadth(df: pd.DataFrame) -> list:
    counts = df.groupby("provider")["country_code"].nunique().sort_index().sort_values(ascending=False, kind="stable")
    return [{"provider": p, "countries": int(c)} for p, c in counts.items()]


def _percentile_scores(values: dict, lower_is_better: bool = False) -> dict:
    """Score 0-100 par rang percentile, et non par min-max.
    Les écarts réels entre fournisseurs sont faibles (ex. prix/Go : 21,7 % d'étendue
    autour de la moyenne) mais le min-max les étirait sur toute l'échelle 0-100 : un
    écart de prix de 3,1 % entre deux fournisseurs devenait 13 points de score. Le rang
    percentile est en plus insensible aux extrêmes — avec le min-max, retirer le
    fournisseur le moins cher du catalogue aurait changé mécaniquement le score des 17
    autres sans qu'aucune donnée les concernant n'ait changé ; avec un rang, ça ne
    déplace que les scores voisins du rang libéré."""
    s = pd.Series(values, dtype=float)
    ranked = (-s if lower_is_better else s).rank(pct=True, method="average")
    return (ranked * 100).to_dict()


def composite_scores(df: pd.DataFrame) -> dict:
    """Calcule les 3 versions du score composite par fournisseur.
    Version A : score MyBestSim publié tel quel (pas de recombinaison — voir plus bas
                pourquoi), sinon indisponible.
    Version B : pondération Trustpilot comme seule source éditoriale (60/16/14/10),
                fournisseurs sans Trustpilot fiable (<2500 avis) marqués indisponibles.
    Version C : sans éditorial, 3 critères quantitatifs seuls rescalés à 100%
                (40% prix / 35% couverture / 25% réseau 5G + illimité).
    """
    pgb = {r["provider"]: r["price_per_gb"] for r in price_per_gb_by_provider(df)}
    cov = {r["provider"]: r["countries"] for r in coverage_breadth(df)}
    # Critère réseau = moyenne de deux pourcentages du catalogue du fournisseur : offres
    # en 5G et offres en data illimitée. MyBestSim décrit ce critère comme "5G + unlimited
    # : feature availability" (vérifié sur mybestsim.com/en/best-esim-providers/) — avant
    # cette correction, seule la part de 5G était mesurée, l'illimité était ignoré.
    # Moyenne des deux pourcentages plutôt qu'un simple "a au moins une offre illimitée"
    # binaire : reste cohérent avec la façon dont la 5G était déjà mesurée (part du
    # catalogue, pas juste présence/absence).
    pct_5g = df.groupby("provider").apply(lambda g: (g["network"] == "5G").mean() * 100, include_groups=False)
    pct_unlimited = df.groupby("provider").apply(lambda g: g["data_gb"].isna().mean() * 100, include_groups=False)
    net_feat = (pct_5g + pct_unlimited) / 2

    providers = sorted(df["provider"].unique())
    net_feat_dict = net_feat.to_dict()
    price_scores = _percentile_scores(pgb, lower_is_better=True)  # moins cher = mieux
    cov_scores = _percentile_scores(cov)
    net_scores = _percentile_scores(net_feat_dict)

    def quant_subscores(provider):
        return price_scores[provider], cov_scores[provider], net_scores[provider]

    version_a, version_b, version_c = [], [], []
    for p in providers:
        price_score, cov_score, net_score = quant_subscores(p)

        # Version C : sans éditorial, poids 40/35/25 (rescale de 16/14/10 MyBestSim)
        score_c = round(price_score * 0.40 + cov_score * 0.35 + net_score * 0.25, 1)
        version_c.append({"provider": p, "score": score_c})

        # Composante quantitative commune à B, poids MyBestSim bruts 16/14/10 (=40 pts)
        quant_40 = price_score * 0.16 + cov_score * 0.14 + net_score * 0.10

        # Version A : score MyBestSim publié, SANS recombinaison avec nos notes
        # quantitatives. MYBESTSIM_SCORES contient leur score final déjà mélangé (60%
        # éditorial + 40% bonus data — vérifié : nos valeurs matchent exactement les
        # scores affichés sur mybestsim.com/en/best-esim-providers/, ex. Roamic 80/100).
        # Ce n'est PAS une note éditoriale isolée : ils ne publient jamais ce sous-score
        # séparément. Le recombiner avec quant_40 comptait deux fois la dimension
        # quantitative (une fois dans leur score déjà mélangé, une fois en plus ici).
        if p in MYBESTSIM_SCORES:
            score_a = round(float(MYBESTSIM_SCORES[p]), 1)
            version_a.append({"provider": p, "score": score_a, "editorial_source": "mybestsim"})
        else:
            version_a.append({"provider": p, "score": None, "editorial_source": "indisponible"})

        # Version B : éditorial = Trustpilot (/5 rescalé /100) si fiable (>2500 avis).
        # Min-max sur [1, 5] et non x20 : Trustpilot ne permet pas de note à 0 étoile, le
        # minimum réel de l'échelle est 1 étoile. Une simple proportionnalité (x20)
        # traiterait 1/5 comme 20/100 alors que c'est la pire note possible sur la
        # plateforme — elle devrait valoir 0/100 pour rester comparable à l'échelle des
        # autres composantes, elles aussi bornées à leur minimum réel observé.
        if p in TRUSTPILOT_SCORES:
            editorial = (TRUSTPILOT_SCORES[p] - 1) / (5 - 1) * 100
            score_b = round(editorial * 0.60 + quant_40, 1)
            version_b.append({"provider": p, "score": score_b, "editorial_source": "trustpilot"})
        else:
            version_b.append({"provider": p, "score": None, "editorial_source": "indisponible"})

    return {
        "version_a_mybestsim": sorted(version_a, key=lambda r: (r["score"] is None, -(r["score"] or 0), r["provider"])),
        "version_b_trustpilot": sorted(version_b, key=lambda r: (r["score"] is None, -(r["score"] or 0), r["provider"])),
        "version_c_sans_editorial": sorted(version_c, key=lambda r: (-r["score"], r["provider"])),
        "excluded_from_editorial": EDITORIAL_EXCLUDED,
    }


def compact_rows(df: pd.DataFrame) -> list:
    """Lignes compactes embarquées pour permettre le filtrage/recalcul côté navigateur.
    Colonnes utiles aux filtres et graphiques uniquement (currency omise : uniforme EUR).
    data_gb NaN (forfaits illimités) converti explicitement en None : pandas réinsère NaN
    lors d'une simple affectation sur colonne float64, ce qui casse le JSON (NaN interdit
    par la norme JSON, contrairement à json.dumps qui l'accepte par défaut en Python)."""
    out = []
    cols = ["provider", "country_code", "country_name", "data_gb", "validity_days", "price", "network", "top_up"]
    for row in df[cols].itertuples(index=False):
        gb = row.data_gb
        code = row.country_code
        out.append({
            "provider": row.provider,
            "country_code": None if pd.isna(code) else code,
            "country_name": row.country_name,
            "data_gb": None if pd.isna(gb) else float(gb),
            "validity_days": int(row.validity_days),
            "price": float(row.price),
            "network": row.network,
            "top_up": row.top_up,
        })
    return out


def build_dataset(source_dir: str) -> dict:
    df = load_catalog(source_dir)
    return {
        "generated_from": f"{df['provider'].nunique()} fournisseurs, {len(df)} lignes",
        # Exposé pour que le dashboard n'ait pas sa propre copie de cette liste : le JS
        # recalcule la dispersion régionale côté client et les deux définitions avaient
        # divergé (le client ignorait NA et AF).
        "region_codes": sorted(REGION_CODES),
        "rows": compact_rows(df),
        "base_metrics": base_metrics(df),
        "provider_breakdown": provider_breakdown(df),
        "network_breakdown": network_breakdown(df),
        "validity_breakdown": validity_breakdown(df),
        "size_breakdown": size_breakdown(df),
        "price_per_size": price_per_size(df),
        "price_per_gb_by_provider": price_per_gb_by_provider(df),
        "price_per_day_by_provider": price_per_day_by_provider(df),
        "usage_intensity_segments": usage_intensity_segments(df),
        "regional_dispersion": regional_dispersion(df),
        "network_premium": network_premium_by_country(df),
        "volume_discount_curve": volume_discount_curve(df),
        "top_destinations": top_destinations(df),
        "price_by_destination": price_by_destination(df),
        "price_by_country": price_by_country(df),
        # Table de coordonnées exposée au navigateur : la carte est recalculée côté client
        # à chaque changement de filtre, elle a donc besoin des centroïdes.
        "country_coords": {code: {"lat": lat, "lng": lng} for code, (lat, lng) in COUNTRY_COORDS.items()},
        "topup_flexibility": topup_flexibility(df),
        "coverage_breadth": coverage_breadth(df),
        "composite_scores": composite_scores(df),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "docs", "data.json"))
    args = parser.parse_args()

    dataset = build_dataset(args.source)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"OK — {dataset['generated_from']} -> {args.out}")


if __name__ == "__main__":
    main()
