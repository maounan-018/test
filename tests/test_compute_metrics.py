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
)

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
        result = {r["provider"]: r["price_per_gb"] for r in price_per_gb_by_provider(small_df)}
        # A : (20/10 + 30/20) / 2 = (2.0 + 1.5) / 2 = 1.75
        assert result["A"] == pytest.approx(1.75, abs=0.01)
        # B : 50/5 = 10.0
        assert result["B"] == pytest.approx(10.0, abs=0.01)

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
        assert out["Allemagne"]["price_avg"] == pytest.approx(50.0, abs=0.01)
        assert out["Allemagne"]["offers"] == 1


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
