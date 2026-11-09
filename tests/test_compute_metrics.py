"""Tests unitaires et d'intégration pour le pipeline de calcul des métriques."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from compute_metrics import (
    base_metrics,
    price_per_gb_by_provider,
    price_per_day_by_provider,
    regional_dispersion,
    network_premium_by_country,
    composite_scores,
    provider_breakdown,
    top_destinations,
    price_by_destination,
    price_by_country,
    load_catalog,
    build_dataset,
    _percentile_scores,
)
from editorial_sources import MYBESTSIM_SCORES

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@pytest.fixture
def small_df():
    """Jeu de données minimal à résultats calculables à la main."""
    return pd.DataFrame([
        {"sku": "a1", "provider": "A", "product_name": "x", "country_code": "FR", "country_name": "France",
         "data_gb": 10, "data_display": "10 Go", "validity_days": 10, "price": 20.0, "currency": "EUR",
         "network": "4G", "top_up": "oui"},
        {"sku": "a2", "provider": "A", "product_name": "x", "country_code": "FR", "country_name": "France",
         "data_gb": 20, "data_display": "20 Go", "validity_days": 10, "price": 30.0, "currency": "EUR",
         "network": "5G", "top_up": "non"},
        {"sku": "b1", "provider": "B", "product_name": "x", "country_code": "DE", "country_name": "Allemagne",
         "data_gb": 5, "data_display": "5 Go", "validity_days": 5, "price": 50.0, "currency": "EUR",
         "network": "4G", "top_up": "oui"},
    ])


class TestBaseMetrics:
    def test_counts_and_ranges(self, small_df):
        m = base_metrics(small_df)
        assert m["total_products"] == 3
        assert m["providers_count"] == 2
        assert m["price_min"] == 20.0
        assert m["price_max"] == 50.0
        assert m["price_avg"] == pytest.approx((20 + 30 + 50) / 3, abs=0.01)

    def test_over_100_threshold(self, small_df):
        m = base_metrics(small_df)
        assert m["over_100_eur"] == 0  # aucune ligne > 100€ dans le fixture


class TestPriceRatios:
    def test_price_per_gb(self, small_df):
        """Ratio d'agrégats (somme prix / somme Go), pas moyenne des ratios par offre :
        une moyenne pondérerait un forfait 1 Go autant qu'un forfait 20 Go."""
        result = {r["provider"]: r["price_per_gb"] for r in price_per_gb_by_provider(small_df)}
        # A : (20+30) / (10+20) = 50/30 = 1.667
        assert result["A"] == pytest.approx(1.67, abs=0.01)
        # B : 50/5 = 10.0
        assert result["B"] == pytest.approx(10.0, abs=0.01)

    def test_price_per_gb_is_aggregate_ratio_not_mean_of_ratios(self):
        """Régression : avec une moyenne de ratios par offre, un fournisseur qui vend
        surtout de petits forfaits chers au Go paraît moins compétitif qu'il ne l'est
        réellement une fois le volume pris en compte."""
        df = pd.DataFrame([
            {"provider": "X", "price": 10.0, "data_gb": 1},    # 10 €/Go
            {"provider": "X", "price": 10.0, "data_gb": 100},  # 0.1 €/Go
        ])
        result = {r["provider"]: r["price_per_gb"] for r in price_per_gb_by_provider(df)}
        # moyenne des ratios : (10 + 0.1) / 2 = 5.05 -- ratio d'agrégats : 20/101 = 0.198
        assert result["X"] == pytest.approx(0.20, abs=0.01)

    def test_price_per_gb_ignores_unlimited(self):
        df = pd.DataFrame([
            {"provider": "C", "price": 40.0, "data_gb": None, "validity_days": 30},
            {"provider": "C", "price": 10.0, "data_gb": 5, "validity_days": 10},
        ])
        result = {r["provider"]: r["price_per_gb"] for r in price_per_gb_by_provider(df)}
        assert result["C"] == pytest.approx(2.0, abs=0.01)  # seule la ligne à 5 Go compte

    def test_price_per_day(self, small_df):
        result = {r["provider"]: r["price_per_day"] for r in price_per_day_by_provider(small_df)}
        # A : (20/10 + 30/10) / 2 = (2.0 + 3.0) / 2 = 2.5
        assert result["A"] == pytest.approx(2.5, abs=0.01)
        assert result["B"] == pytest.approx(10.0, abs=0.01)


class TestRegionalDispersion:
    def test_cv_known_values(self):
        # Région "Europe" : 3 lignes à price/gb = 1, 2, 3 -> moyenne 2, stdev(échantillon) = 1 -> CV = 0.5
        df = pd.DataFrame([
            {"provider": "X", "country_code": "EU", "country_name": "Europe", "price": 1.0, "data_gb": 1},
            {"provider": "X", "country_code": "EU", "country_name": "Europe", "price": 2.0, "data_gb": 1},
            {"provider": "X", "country_code": "EU", "country_name": "Europe", "price": 3.0, "data_gb": 1},
        ])
        out = regional_dispersion(df)
        assert len(out) == 1
        assert out[0]["cv"] == pytest.approx(0.5, abs=0.01)

    def test_ignores_non_region_countries(self, small_df):
        # France/Allemagne ne sont pas des codes région (EU/AS/WW/NA/AF) -> aucune sortie
        assert regional_dispersion(small_df) == []


class TestNetworkPremium:
    def test_controls_for_country(self):
        """Vérifie que la prime est calculée par pays puis moyennée, pas globalement.

        Ici : en France le 5G est 2x plus cher que le 4G (vrai signal),
        mais le 5G n'existe qu'en Allemagne, bien moins chère au global —
        un calcul naïf global sous-estimerait/biaiserait la prime."""
        rows = []
        for i in range(3):
            rows.append({"provider": "X", "country_code": "FR", "country_name": "France",
                         "network": "4G", "price": 10.0, "data_gb": 1})
            rows.append({"provider": "X", "country_code": "FR", "country_name": "France",
                         "network": "5G", "price": 20.0, "data_gb": 1})
            rows.append({"provider": "X", "country_code": "DE", "country_name": "Allemagne",
                         "network": "4G", "price": 5.0, "data_gb": 1})
        df = pd.DataFrame(rows)
        result = network_premium_by_country(df)
        # Seule la France a 4G ET 5G avec >=3 lignes chacun -> prime = (20-10)/10 = 100%
        assert result["premium_pct"] == pytest.approx(100.0, abs=0.1)
        assert result["n_countries"] == 1

    def test_insufficient_data_returns_none(self):
        df = pd.DataFrame([{"provider": "X", "country_code": "FR", "country_name": "France",
                            "network": "4G", "price": 10.0, "data_gb": 1}])
        result = network_premium_by_country(df)
        assert result["premium_pct"] is None

    def test_excludes_multi_country_zones(self):
        """Une zone multi-pays n'est pas une destination : la compter dans n_countries
        contredit le libellé « N pays » affiché à côté du KPI."""
        rows = []
        for _ in range(3):
            rows.append({"provider": "X", "country_code": "EU", "country_name": "Europe",
                         "network": "4G", "price": 10.0, "data_gb": 1})
            rows.append({"provider": "X", "country_code": "EU", "country_name": "Europe",
                         "network": "5G", "price": 20.0, "data_gb": 1})
        result = network_premium_by_country(pd.DataFrame(rows))
        assert result["n_countries"] == 0
        assert result["premium_pct"] is None


class TestPercentileScores:
    """Remplace le min-max : insensible aux valeurs extrêmes, et un petit écart réel ne
    produit plus un grand écart de score."""

    def test_higher_is_better_ranks_ascending(self):
        scores = _percentile_scores({"A": 10, "B": 20, "C": 30})
        assert scores["A"] < scores["B"] < scores["C"]
        assert scores["C"] == pytest.approx(100.0)

    def test_lower_is_better_inverts_ranking(self):
        scores = _percentile_scores({"A": 10, "B": 20, "C": 30}, lower_is_better=True)
        assert scores["A"] > scores["B"] > scores["C"]
        assert scores["A"] == pytest.approx(100.0)

    def test_insensitive_to_extreme_outlier(self):
        """Régression : avec un min-max, retirer/ajouter un extrême change le score de
        TOUS les autres. Avec un rang percentile, seuls les rangs voisins bougent."""
        base = {"A": 10, "B": 11, "C": 12, "D": 13}
        with_outlier = {**base, "E": 1000}
        s_base = _percentile_scores(base)
        s_outlier = _percentile_scores(with_outlier)
        # B, C, D gardent le même rang relatif (2e, 3e, 4e) que l'extrême E soit présent
        # ou non : un min-max aurait au contraire écrasé leurs scores vers 0 à l'ajout de E.
        ranks_base = sorted(base, key=lambda k: s_base[k])
        ranks_outlier = sorted(["A", "B", "C", "D"], key=lambda k: s_outlier[k])
        assert ranks_base == ranks_outlier


class TestCompositeScores:
    def test_three_versions_present(self, small_df):
        scores = composite_scores(small_df)
        assert "version_a_mybestsim" in scores
        assert "version_b_trustpilot" in scores
        assert "version_c_sans_editorial" in scores

    def test_version_c_never_none(self, small_df):
        """La version sans éditorial doit toujours produire un score (aucune dépendance externe)."""
        scores = composite_scores(small_df)
        for row in scores["version_c_sans_editorial"]:
            assert row["score"] is not None

    def test_unknown_provider_marked_unavailable_in_a_and_b(self, small_df):
        """Les fournisseurs A et B (fictifs) ne sont ni dans MyBestSim ni dans Trustpilot."""
        scores = composite_scores(small_df)
        for row in scores["version_a_mybestsim"]:
            assert row["editorial_source"] == "indisponible"
            assert row["score"] is None

    def test_trustpilot_rescaled_by_min_max_not_proportional(self):
        """Régression : Trustpilot ne permet pas de note à 0 étoile (minimum réel = 1
        étoile), donc la composante éditoriale B doit être rescalée par min-max sur
        [1, 5], pas par une règle de trois (× 20) qui valoriserait artificiellement la
        pire note possible (1/5 deviendrait 20/100 au lieu de 0/100)."""
        df = pd.DataFrame([
            {"provider": "Airalo", "country_code": "FR", "price": 10.0, "data_gb": 1,
             "network": "4G", "validity_days": 7},
            {"provider": "Airalo", "country_code": "DE", "price": 10.0, "data_gb": 1,
             "network": "4G", "validity_days": 7},
        ])
        scores = composite_scores(df)
        row = next(r for r in scores["version_b_trustpilot"] if r["provider"] == "Airalo")
        # Airalo = 4.2/5 sur Trustpilot (scripts/editorial_sources.py).
        # Min-max [1,5] : (4.2-1)/4*100 = 80.0, pondéré à 60% = 48.0 ; les 3 sous-scores
        # quantitatifs valent tous 100 (seul fournisseur du jeu de test) pour 40 pts.
        # Règle de trois (x20) aurait donné 84.0*0.6 + 40 = 90.4 à la place de 88.0.
        assert row["score"] == pytest.approx(88.0, abs=0.1)

    def test_version_a_is_published_score_not_recombined(self):
        """Régression : MYBESTSIM_SCORES contient le score FINAL publié par MyBestSim,
        déjà mélangé (60 % éditorial + 40 % bonus data). Le recombiner avec nos propres
        notes prix/couverture/réseau comptait la dimension quantitative deux fois. La
        version A doit être ce score publié, tel quel, quelles que soient nos données."""
        df = pd.DataFrame([
            {"provider": "Airalo", "country_code": "FR", "price": 10.0, "data_gb": 1,
             "network": "4G", "validity_days": 7},
            {"provider": "Roamic", "country_code": "FR", "price": 90.0, "data_gb": 1,
             "network": "5G", "validity_days": 7},
            {"provider": "Roamic", "country_code": "DE", "price": 90.0, "data_gb": 1,
             "network": "5G", "validity_days": 7},
        ])
        scores = composite_scores(df)
        by_provider = {r["provider"]: r for r in scores["version_a_mybestsim"]}
        for p in ("Airalo", "Roamic"):
            assert by_provider[p]["score"] == pytest.approx(float(MYBESTSIM_SCORES[p]))
            assert by_provider[p]["editorial_source"] == "mybestsim"

    def test_network_criterion_counts_unlimited_not_only_5g(self):
        """MyBestSim décrit ce critère comme « 5G + unlimited ». Deux fournisseurs
        identiques en prix/Go, couverture et part de 5G (nulle), qui ne diffèrent que par
        la présence d'une offre illimitée : celui qui en propose doit obtenir le meilleur
        score de la version C. Avant correction seule la 5G était mesurée et les deux
        scores étaient égaux."""
        rows = []
        for provider, de_data in (("X", None), ("Y", 1)):  # None = illimité
            rows.append({"provider": provider, "country_code": "FR", "price": 10.0,
                         "data_gb": 1, "network": "4G", "validity_days": 7})
            rows.append({"provider": provider, "country_code": "DE", "price": 10.0,
                         "data_gb": de_data, "network": "4G", "validity_days": 7})
        scores = composite_scores(pd.DataFrame(rows))
        by_provider = {r["provider"]: r["score"] for r in scores["version_c_sans_editorial"]}
        assert by_provider["X"] > by_provider["Y"]


class TestDeterministicOrdering:
    """Régression : value_counts() ne garantit pas d'ordre stable entre valeurs à égalité
    (observé en CI : 'États-Unis' et 'Égypte' à 98 offres changeaient d'ordre entre une
    exécution Windows locale et Ubuntu en CI, faisant échouer le contrôle de
    reproductibilité). Les égalités doivent être départagées alphabétiquement, toujours
    dans le même ordre, peu importe l'OS ou l'ordre d'arrivée des lignes."""

    def test_provider_tie_broken_alphabetically(self):
        df = pd.DataFrame([
            {"provider": "Zebra", "price": 1.0},
            {"provider": "Zebra", "price": 1.0},
            {"provider": "Alpha", "price": 1.0},
            {"provider": "Alpha", "price": 1.0},
        ])
        result = provider_breakdown(df)
        assert result == [{"provider": "Alpha", "count": 2}, {"provider": "Zebra", "count": 2}]

    def test_destination_tie_broken_alphabetically(self):
        df = pd.DataFrame([
            {"country_name": "Zanzibar"}, {"country_name": "Zanzibar"},
            {"country_name": "Albanie"}, {"country_name": "Albanie"},
        ])
        result = top_destinations(df, n=5)
        assert result == [{"destination": "Albanie", "offers": 2}, {"destination": "Zanzibar", "offers": 2}]

    def test_repeated_runs_give_identical_order(self):
        """Même calcul répété sur les mêmes données -> toujours le même ordre."""
        if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
            pytest.skip("dossier data/ non disponible dans cet environnement")
        df1 = load_catalog(DATA_DIR)
        df2 = load_catalog(DATA_DIR)
        assert top_destinations(df1) == top_destinations(df2)
        assert provider_breakdown(df1) == provider_breakdown(df2)


class TestPriceByDestination:
    def test_matches_known_values(self, small_df):
        out = {r["destination"]: r for r in price_by_destination(small_df, n=5)}
        assert out["France"]["price_avg"] == pytest.approx(25.0, abs=0.01)  # (20+30)/2
        assert out["France"]["offers"] == 2
        assert out["France"]["providers"] == 1  # les 2 offres France viennent du fournisseur A
        assert out["Allemagne"]["price_avg"] == pytest.approx(50.0, abs=0.01)
        assert out["Allemagne"]["offers"] == 1

    def test_providers_count_for_multi_country_zone(self):
        """Régression : le nombre de fournisseurs d'une zone multi-pays (Europe, Asie...)
        doit être calculé directement, pas récupéré via price_by_country qui exclut ces
        zones (pas de position unique sur une carte) — sinon la colonne restait vide."""
        df = pd.DataFrame([
            {"provider": "A", "country_code": "EU", "country_name": "Europe", "price": 10.0, "data_gb": 1},
            {"provider": "A", "country_code": "EU", "country_name": "Europe", "price": 12.0, "data_gb": 1},
            {"provider": "B", "country_code": "EU", "country_name": "Europe", "price": 15.0, "data_gb": 1},
        ])
        out = {r["destination"]: r for r in price_by_destination(df, n=5)}
        assert out["Europe"]["providers"] == 2

    def test_price_per_gb_is_not_confounded_by_plan_size_mix(self):
        """Deux destinations au même prix/Go réel (0.5 €/Go) mais avec un mix de
        tailles différent ne doivent pas être départagées par price_avg seul : c'est
        price_per_gb qui doit rester identique, price_avg peut diverger."""
        df = pd.DataFrame([
            # Japon : uniquement de gros forfaits (50 Go) -> price_avg élevé
            {"provider": "X", "country_name": "Japon", "price": 25.0, "data_gb": 50},
            {"provider": "X", "country_name": "Japon", "price": 25.0, "data_gb": 50},
            # Thaïlande : uniquement de petits forfaits (1 Go) -> price_avg faible
            {"provider": "X", "country_name": "Thaïlande", "price": 0.5, "data_gb": 1},
            {"provider": "X", "country_name": "Thaïlande", "price": 0.5, "data_gb": 1},
        ])
        out = {r["destination"]: r for r in price_by_destination(df, n=5)}
        assert out["Japon"]["price_avg"] != pytest.approx(out["Thaïlande"]["price_avg"], abs=0.01)
        assert out["Japon"]["price_per_gb"] == pytest.approx(0.5, abs=0.01)
        assert out["Thaïlande"]["price_per_gb"] == pytest.approx(0.5, abs=0.01)


class TestPriceByCountry:
    def test_has_coordinates_and_values(self, small_df):
        out = {r["code"]: r for r in price_by_country(small_df)}
        assert out["FR"]["price_avg"] == pytest.approx(25.0, abs=0.01)
        assert out["FR"]["offers"] == 2
        assert out["FR"]["lat"] == pytest.approx(46.2276, abs=0.01)

    def test_excludes_non_geographic_codes(self):
        """Les zones multi-pays n'ont pas de position unique : elles ne doivent pas
        apparaître sur la carte plutôt que d'être placées à une coordonnée inventée."""
        df = pd.DataFrame([
            {"provider": "X", "country_code": "EU", "country_name": "Europe",
             "price": 40.0, "data_gb": 5, "validity_days": 10},
            {"provider": "X", "country_code": "FR", "country_name": "France",
             "price": 20.0, "data_gb": 5, "validity_days": 10},
        ])
        codes = [r["code"] for r in price_by_country(df)]
        assert "EU" not in codes
        assert "FR" in codes


class TestCountryCodeNA:
    """Régression : le code pays 'NA' (Amérique du Nord) fait partie des valeurs que
    pandas traite par défaut comme manquantes. Sans keep_default_na=False, les 192 lignes
    'Amérique du Nord' perdaient leur code pays : la zone disparaissait de la dispersion
    régionale (alors que REGION_CODES la prévoit) et n'était comptée dans la couverture
    d'aucun fournisseur, ce qui alimentait les trois scores composites."""

    def test_na_is_read_as_a_country_code(self):
        if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
            pytest.skip("dossier data/ non disponible dans cet environnement")
        df = load_catalog(DATA_DIR)
        assert (df["country_code"] == "NA").sum() == 192
        assert df["country_code"].isna().sum() == 0

    def test_unlimited_plans_still_have_no_data_gb(self):
        """keep_default_na=False ne doit pas transformer les forfaits illimités en 0."""
        if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
            pytest.skip("dossier data/ non disponible dans cet environnement")
        df = load_catalog(DATA_DIR)
        assert df["data_gb"].isna().sum() == 653

    def test_north_america_appears_in_regional_dispersion(self):
        if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
            pytest.skip("dossier data/ non disponible dans cet environnement")
        regions = [r["region"] for r in regional_dispersion(load_catalog(DATA_DIR))]
        assert "Amérique du Nord" in regions


class TestRegionCodesExposed:
    """Le dashboard recalcule la dispersion régionale côté client ; il doit lire la liste
    des zones depuis data.json et non en garder une copie, les deux ayant divergé."""

    def test_region_codes_in_dataset(self):
        if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
            pytest.skip("dossier data/ non disponible dans cet environnement")
        assert set(build_dataset(DATA_DIR)["region_codes"]) == {"EU", "AS", "WW", "NA", "AF"}


class TestFullPipeline:
    """Test d'intégration sur les vraies données du catalogue."""

    def test_real_data_matches_known_reference(self):
        if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
            pytest.skip("dossier data/ non disponible dans cet environnement")
        dataset = build_dataset(DATA_DIR)
        m = dataset["base_metrics"]
        assert m["total_products"] == 5056
        assert m["providers_count"] == 18
        assert m["over_100_eur"] == 56
        assert m["price_min"] == pytest.approx(5.36, abs=0.01)
        assert m["price_max"] == pytest.approx(154.63, abs=0.01)
        assert m["price_avg"] == pytest.approx(29.30, abs=0.05)

    def test_no_missing_values_in_output(self):
        if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
            pytest.skip("dossier data/ non disponible dans cet environnement")
        dataset = build_dataset(DATA_DIR)
        for row in dataset["provider_breakdown"]:
            assert row["count"] > 0
        assert len(dataset["provider_breakdown"]) == 18


class TestInstantaneCommite:
    """docs/data.json est un instantané : il doit correspondre aux CSV du dépôt.

    Le test de parité navigateur portait cette hypothèse en silence — il lisait les CSV de
    data/ pour juger une page alimentée par docs/data.json. Elle est maintenant vérifiée
    ici, explicitement, et le test de parité compare ce que la page reçoit vraiment.
    """

    def test_data_json_correspond_aux_csv(self):
        import json

        racine = os.path.join(os.path.dirname(__file__), "..")
        from compute_metrics import build_dataset

        attendu = build_dataset(os.path.join(racine, "data"))
        with open(os.path.join(racine, "docs", "data.json"), encoding="utf-8") as f:
            commite = json.load(f)
        assert commite == attendu, (
            "docs/data.json ne correspond plus aux CSV de data/ : relancer "
            "python scripts/compute_metrics.py")
