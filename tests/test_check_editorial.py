"""Tests du contrôle de dérive des scores éditoriaux (aucun accès réseau)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_editorial import compare, parse_scores

# Extrait fidèle du balisage réel de mybestsim.com/en/best-esim-providers/ (novembre 2026).
PAGE = (
    '<div class="mbshub-nm">Roamic</div><span class="mbshub-stars">★★★★★<small>4.9</small></span>'
    '<div class="mbshub-scorebox"><div class="mbshub-val">80<span>/100</span></div></div>'
    '<div class="mbshub-nm">Yesim</div><span class="mbshub-stars">★★★★★<small>4.8</small></span>'
    '<div class="mbshub-scorebox"><div class="mbshub-val">75<span>/100</span></div></div>'
    '<div class="mbshub-nm">eSIM.DOG &amp; Co</div>'
    '<div class="mbshub-scorebox"><div class="mbshub-val">66<span>/100</span></div></div>'
    # même fournisseur répété dans une 2e vue de la page : la 1re valeur doit gagner
    '<div class="mbshub-nm">Roamic</div><div class="mbshub-val">12<span>/100</span></div>'
)


class TestParseScores:
    def test_reads_names_and_scores(self):
        scores = parse_scores(PAGE)
        assert scores["Roamic"] == 80
        assert scores["Yesim"] == 75

    def test_first_occurrence_wins_and_entities_are_decoded(self):
        scores = parse_scores(PAGE)
        assert scores["Roamic"] == 80          # pas 12
        assert scores["eSIM.DOG & Co"] == 66

    def test_reads_the_mobile_row_markup_too(self):
        """Régression trouvée en lançant le script sur le vrai site : Airalo, Saily et
        Holafly n'y existent que sous le balisage « mobile » (mbshub-sv + <i>), pas sous
        celui des lignes « bureau » (mbshub-val + <span>)."""
        page = ('<div class="mbshub-nm">Airalo</div><span class="mbshub-stars"><small>4.6</small></span>'
                '</div></div><div class="mbshub-mrow-mid"><div class="mbshub-mprice"><b>$4.00</b></div>'
                '<div class="mbshub-mrow-score"><span class="mbshub-sl">Score</span>'
                '<span class="mbshub-sv">72<i>/100</i></span></div></div>')
        assert parse_scores(page) == {"Airalo": 72}

    def test_provider_without_score_does_not_steal_the_next_one(self):
        """Une ligne sans « NN/100 » ne doit pas se voir attribuer le score du fournisseur
        suivant."""
        page = ('<div class="mbshub-nm">SansScore</div><span>—</span>'
                '<div class="mbshub-nm">Yesim</div><div class="mbshub-val">75<span>/100</span></div>')
        scores = parse_scores(page)
        assert "SansScore" not in scores
        assert scores["Yesim"] == 75

    def test_changed_markup_yields_nothing(self):
        """Si le site change ses classes CSS, on doit lire 0 fournisseur (le script
        alerte alors) plutôt que d'inventer des valeurs."""
        assert parse_scores('<div class="autre-classe">Roamic</div><b>80/100</b>') == {}


class TestCompare:
    def test_no_drift(self):
        assert compare({"Roamic": 80, "Yesim": 75}, {"Roamic": 80, "Yesim": 75, "Autre": 10}) == []

    def test_reports_changed_and_missing_providers(self):
        problems = compare({"Roamic": 80, "Yesim": 75, "Holafly": 67}, {"Roamic": 81, "Yesim": 75})
        assert len(problems) == 2
        assert any("Roamic" in p and "81" in p for p in problems)
        assert any("Holafly" in p and "absent" in p for p in problems)


class TestDiscover:
    """Un fournisseur du catalogue noté chez MyBestSim doit être trouvé, pas déclaré
    indisponible. L'inverse aussi : absent de leur page = constat, pas oubli."""

    LIVE = {"Roamic": 80, "Simbye": 72, "Maya Mobile": 65}
    STORED = {"Roamic": 80}

    def test_trouve_un_score_publie_non_stocke(self):
        from check_editorial import discover
        trouves, _, _ = discover(["Roamic", "Simbye"], self.STORED, self.LIVE)
        assert trouves == [("Simbye", "Simbye", 72)]

    def test_rapproche_les_noms_a_la_casse_et_ponctuation_pres(self):
        from check_editorial import discover
        trouves, _, _ = discover(["SIMBYE"], self.STORED, self.LIVE)
        assert trouves == [("SIMBYE", "Simbye", 72)]

    def test_ressemblance_partielle_signalee_jamais_retenue(self):
        from check_editorial import discover
        trouves, a_verifier, sans_trace = discover(["Maya"], self.STORED, self.LIVE)
        assert trouves == []
        assert a_verifier == [("Maya", ["Maya Mobile"])]
        assert sans_trace == []

    def test_absent_de_leur_page_est_un_constat(self):
        from check_editorial import discover
        trouves, a_verifier, sans_trace = discover(["Inconnu"], self.STORED, self.LIVE)
        assert (trouves, a_verifier) == ([], [])
        assert sans_trace == ["Inconnu"]

    def test_deja_stocke_nest_pas_redecouvert(self):
        from check_editorial import discover
        assert discover(["Roamic"], self.STORED, self.LIVE) == ([], [], [])
