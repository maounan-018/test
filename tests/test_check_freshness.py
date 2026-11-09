"""Tests de la surveillance d'âge des notes Trustpilot (aucun accès réseau, par construction).

Le script surveillé ne doit jamais interroger Trustpilot : leur robots.txt interdit tout le
site aux robots et leurs pages répondent 403. Un test vérifie explicitement qu'aucun module
réseau n'y est importé, pour que cette garantie ne puisse pas disparaître par inadvertance.
"""
import datetime as dt
import io
import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)

from check_freshness import DELAI_JOURS, ages, format_avis, main
from editorial_sources import (
    TRUSTPILOT_MIN_REVIEWS,
    TRUSTPILOT_SCORES,
    TRUSTPILOT_SOURCES,
    trustpilot_url,
)

RELEVE = {
    "Ancien": {"score": 4.0, "reviews": 3000, "domain": "ancien.com", "captured": "2026-01-01"},
    "Recent": {"score": 4.5, "reviews": 9000, "domain": "recent.com", "captured": "2026-11-05"},
}
AUJOURDHUI = dt.date(2026, 11, 9)


class TestAges:
    def test_age_en_jours(self):
        lignes = {l["provider"]: l for l in ages(RELEVE, AUJOURDHUI)}
        assert lignes["Recent"]["age"] == 4
        assert lignes["Ancien"]["age"] == 312

    def test_le_plus_ancien_en_premier(self):
        assert [l["provider"] for l in ages(RELEVE, AUJOURDHUI)] == ["Ancien", "Recent"]

    def test_url_reconstruite_depuis_le_domaine(self):
        lignes = ages(RELEVE, AUJOURDHUI)
        assert lignes[0]["url"] == "https://www.trustpilot.com/review/ancien.com"


class TestFormatAvis:
    def test_volume_non_releve(self):
        assert format_avis({"reviews": None, "reviews_approx": False}) == "non relevé"

    def test_separateur_de_milliers_et_approximation(self):
        assert format_avis({"reviews": 50918, "reviews_approx": False}) == "50 918 avis"
        assert format_avis({"reviews": 96800, "reviews_approx": True}) == "~96 800 avis"


class TestCodesDeSortie:
    def test_frais_renvoie_zero(self, capsys):
        assert main(["--today", "2026-11-09"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_perime_renvoie_un_et_liste_les_pages(self, capsys):
        assert main(["--today", "2027-01-10"]) == 1
        sortie = capsys.readouterr().out
        assert "PÉRIMÉ" in sortie
        assert "https://www.trustpilot.com/review/airalo.com" in sortie

    def test_delai_configurable(self, capsys):
        assert main(["--today", "2026-11-09", "--max-age", "2"]) == 1
        assert "PÉRIMÉ" in capsys.readouterr().out

    def test_date_future_est_une_erreur(self, capsys):
        assert main(["--today", "2026-11-01"]) == 1
        assert "postérieure à aujourd'hui" in capsys.readouterr().out

    def test_checklist_liste_toutes_les_pages(self, capsys):
        assert main(["--today", "2026-11-09", "--checklist"]) == 0
        sortie = capsys.readouterr().out
        for nom, entree in TRUSTPILOT_SOURCES.items():
            assert nom in sortie
            assert trustpilot_url(entree["domain"]) in sortie

    def test_volume_manquant_ne_fait_pas_echouer(self, capsys):
        """Lacune connue du relevé initial : signalée, mais ce n'est pas une dérive."""
        assert main(["--today", "2026-11-09"]) == 0
        assert "non relevé" in capsys.readouterr().out


class TestIntegriteDesSources:
    def test_chaque_entree_est_datee_et_sourcee(self):
        for nom, entree in TRUSTPILOT_SOURCES.items():
            assert set(entree) <= {"score", "reviews", "reviews_approx", "domain", "captured"}
            assert dt.datetime.strptime(entree["captured"], "%Y-%m-%d")
            assert entree["domain"] and " " not in entree["domain"], nom

    def test_notes_dans_l_echelle_trustpilot(self):
        for nom, entree in TRUSTPILOT_SOURCES.items():
            assert 1.0 <= entree["score"] <= 5.0, nom

    def test_volume_releve_au_dessus_du_seuil(self):
        """Le seuil de représentativité doit être respecté quand le volume est connu."""
        for nom, entree in TRUSTPILOT_SOURCES.items():
            if entree.get("reviews") is not None:
                assert entree["reviews"] >= TRUSTPILOT_MIN_REVIEWS, nom

    def test_interface_historique_inchangee(self):
        """compute_metrics.py lit TRUSTPILOT_SCORES : {fournisseur: note}."""
        assert TRUSTPILOT_SCORES == {n: e["score"] for n, e in TRUSTPILOT_SOURCES.items()}
        assert all(isinstance(v, float) for v in TRUSTPILOT_SCORES.values())

    def test_delai_par_defaut_raisonnable(self):
        assert 7 <= DELAI_JOURS <= 90


class TestAucunAccesReseau:
    @pytest.mark.parametrize("module", ["urllib", "requests", "http.client", "socket"])
    def test_aucun_module_reseau_importe(self, module):
        source = io.open(os.path.join(SCRIPTS, "check_freshness.py"), encoding="utf-8").read()
        code = "".join(l for l in source.splitlines(True) if not l.lstrip().startswith("#"))
        assert f"import {module}" not in code
