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

REGION_CODES = {"EU", "AS", "WW", "NA", "AF"}


def load_catalog(source_dir: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(source_dir, "*.csv")))
    if not files:
        raise FileNotFoundError(f"Aucun CSV trouvé dans {source_dir}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
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


def provider_breakdown(df: pd.DataFrame) -> list:
    counts = df["provider"].value_counts()
    return [{"provider": p, "count": int(c)} for p, c in counts.items()]


def network_breakdown(df: pd.DataFrame) -> list:
    counts = df["network"].value_counts()
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
    """price/Go moyen par fournisseur, sur les forfaits à volume fini uniquement."""
    sized = df.dropna(subset=["data_gb"])
    sized = sized[sized["data_gb"] > 0].copy()
    sized["price_per_gb"] = sized["price"] / sized["data_gb"]
    avg = sized.groupby("provider")["price_per_gb"].mean().sort_values()
    return [{"provider": p, "price_per_gb": round(float(v), 2)} for p, v in avg.items()]


def price_per_day_by_provider(df: pd.DataFrame) -> list:
    tmp = df.copy()
    tmp["price_per_day"] = tmp["price"] / tmp["validity_days"]
    avg = tmp.groupby("provider")["price_per_day"].mean().sort_values()
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
    return sorted(out, key=lambda r: r["cv"], reverse=True)


def network_premium_by_country(df: pd.DataFrame) -> dict:
    """Prime 5G vs 4G, calculée À DESTINATION ÉGALE (par pays) puis moyennée —
    corrige le biais de la première estimation globale (confondue avec la géographie)."""
    sized = df.dropna(subset=["data_gb"])
    sized = sized[sized["data_gb"] > 0].copy()
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


def top_destinations(df: pd.DataFrame, n: int = 15) -> list:
    counts = df["country_name"].value_counts().head(n)
    return [{"destination": d, "offers": int(c)} for d, c in counts.items()]


def topup_flexibility(df: pd.DataFrame) -> list:
    out = []
    for provider, grp in df.groupby("provider"):
        pct = (grp["top_up"] == "oui").mean() * 100
        out.append({"provider": provider, "topup_pct": round(float(pct), 1)})
    return sorted(out, key=lambda r: r["topup_pct"], reverse=True)


def coverage_breadth(df: pd.DataFrame) -> list:
    counts = df.groupby("provider")["country_code"].nunique().sort_values(ascending=False)
    return [{"provider": p, "countries": int(c)} for p, c in counts.items()]


def _normalize(value, lo, hi):
    if hi == lo:
        return 50.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100))


def composite_scores(df: pd.DataFrame) -> dict:
    """Calcule les 3 versions du score composite par fournisseur.
    Version A : pondération MyBestSim intégrale (60% éditorial + 16/14/10 quantitatifs),
                éditorial = score MyBestSim réel si connu, sinon Trustpilot, sinon indisponible.
    Version B : pondération Trustpilot comme seule source éditoriale (60/16/14/10),
                fournisseurs sans Trustpilot fiable (<2500 avis) marqués indisponibles.
    Version C : sans éditorial, 3 critères quantitatifs seuls rescalés à 100%
                (40% prix / 35% couverture / 25% réseau 5G).
    """
    pgb = {r["provider"]: r["price_per_gb"] for r in price_per_gb_by_provider(df)}
    cov = {r["provider"]: r["countries"] for r in coverage_breadth(df)}
    net5g = df.groupby("provider").apply(lambda g: (g["network"] == "5G").mean() * 100, include_groups=False)

    providers = sorted(df["provider"].unique())
    price_vals = list(pgb.values())
    cov_vals = list(cov.values())
    net_vals = net5g.tolist()
    p_lo, p_hi = min(price_vals), max(price_vals)
    c_lo, c_hi = min(cov_vals), max(cov_vals)
    n_lo, n_hi = min(net_vals), max(net_vals)

    def quant_subscores(provider):
        price_score = 100 - _normalize(pgb[provider], p_lo, p_hi)  # moins cher = mieux
        cov_score = _normalize(cov[provider], c_lo, c_hi)
        net_score = _normalize(net5g[provider], n_lo, n_hi)
        return price_score, cov_score, net_score

    version_a, version_b, version_c = [], [], []
    for p in providers:
        price_score, cov_score, net_score = quant_subscores(p)

        # Version C : sans éditorial, poids 40/35/25 (rescale de 16/14/10 MyBestSim)
        score_c = round(price_score * 0.40 + cov_score * 0.35 + net_score * 0.25, 1)
        version_c.append({"provider": p, "score": score_c})

        # Composante quantitative commune à A et B, poids MyBestSim bruts 16/14/10 (=40 pts)
        quant_40 = price_score * 0.16 + cov_score * 0.14 + net_score * 0.10

        # Version A : éditorial = MyBestSim réel si connu
        if p in MYBESTSIM_SCORES:
            editorial = MYBESTSIM_SCORES[p]
            score_a = round(editorial * 0.60 + quant_40, 1)
            version_a.append({"provider": p, "score": score_a, "editorial_source": "mybestsim"})
        else:
            version_a.append({"provider": p, "score": None, "editorial_source": "indisponible"})

        # Version B : éditorial = Trustpilot (/5 rescalé /100) si fiable (>2500 avis)
        if p in TRUSTPILOT_SCORES:
            editorial = TRUSTPILOT_SCORES[p] * 20
            score_b = round(editorial * 0.60 + quant_40, 1)
            version_b.append({"provider": p, "score": score_b, "editorial_source": "trustpilot"})
        else:
            version_b.append({"provider": p, "score": None, "editorial_source": "indisponible"})

    return {
        "version_a_mybestsim": sorted(version_a, key=lambda r: (r["score"] is None, -(r["score"] or 0))),
        "version_b_trustpilot": sorted(version_b, key=lambda r: (r["score"] is None, -(r["score"] or 0))),
        "version_c_sans_editorial": sorted(version_c, key=lambda r: -r["score"]),
        "excluded_from_editorial": EDITORIAL_EXCLUDED,
    }


def build_dataset(source_dir: str) -> dict:
    df = load_catalog(source_dir)
    return {
        "generated_from": f"{df['provider'].nunique()} fournisseurs, {len(df)} lignes",
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
