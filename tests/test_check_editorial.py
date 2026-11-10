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


class TestDerives:
    """Même constat que compare(), mais trié : ce qui se recopie d'un côté, ce qui demande un
    arbitrage de l'autre. C'est ce tri qui décide s'il y a pull request ou échec."""

    def test_separe_recopiable_et_arbitrage(self):
        from check_editorial import derives
        recopiables, arbitrages = derives(
            {"Roamic": 80, "Yesim": 75, "Holafly": 67},
            {"Roamic": 81, "Yesim": 75},
        )
        assert recopiables == [("Roamic", 80, 81)]
        assert arbitrages == ["Holafly"]

    def test_rien_a_signaler(self):
        from check_editorial import derives
        assert derives({"Roamic": 80}, {"Roamic": 80, "Autre": 10}) == ([], [])


SOURCE = '''"""Entête."""

MYBESTSIM_CAPTURED = "2026-11-05"

MYBESTSIM_SCORES = {
    "Airalo": 72,
    "Holafly": 67,
}

TRUSTPILOT_SOURCES = {
    "Holafly": {"score": 4.7, "captured": "2026-11-05"},
}
'''


class TestAppliquer:
    """L'écriture automatique n'a de valeur que si elle est sûre : elle doit toucher la
    valeur visée et rien d'autre, et refuser plutôt que de livrer un fichier douteux."""

    def test_recopie_le_score_et_la_date(self):
        from check_editorial import appliquer
        texte, journal = appliquer(SOURCE, [("Holafly", 67, 75)], "2026-11-10")
        assert '"Holafly": 75,' in texte
        assert 'MYBESTSIM_CAPTURED = "2026-11-10"' in texte
        assert any("67 -> 75" in l for l in journal)

    def test_ne_touche_a_rien_d_autre(self):
        from check_editorial import appliquer
        texte, _ = appliquer(SOURCE, [("Holafly", 67, 75)], "2026-11-10")
        assert '"Airalo": 72,' in texte
        # le relevé Trustpilot porte la même date et le même fournisseur : il ne doit pas
        # être emporté par la réécriture
        assert '"Holafly": {"score": 4.7, "captured": "2026-11-05"},' in texte

    def test_ajoute_un_fournisseur_decouvert(self):
        from check_editorial import appliquer, _lire_scores
        texte, _ = appliquer(SOURCE, [("Simbye", None, 72)], "2026-11-10")
        assert _lire_scores(texte) == {"Airalo": 72, "Holafly": 67, "Simbye": 72}

    def test_refuse_un_score_hors_bornes(self):
        from check_editorial import appliquer
        for absurde in (0, 101, 7.5, True, "75"):
            try:
                appliquer(SOURCE, [("Holafly", 67, absurde)], "2026-11-10")
            except ValueError:
                continue
            raise AssertionError(f"{absurde!r} aurait dû être refusé")

    def test_refuse_si_la_ligne_ne_correspond_pas(self):
        """Garde-fou contre une réécriture à l'aveugle : si la valeur stockée n'est pas celle
        qu'on croit, le fichier a changé entre-temps et on ne touche à rien."""
        from check_editorial import appliquer
        try:
            appliquer(SOURCE, [("Holafly", 99, 75)], "2026-11-10")
        except ValueError:
            return
        raise AssertionError("une valeur de départ fausse aurait dû être refusée")

    def test_refuse_sans_date_de_capture(self):
        from check_editorial import appliquer
        sans_date = SOURCE.replace('MYBESTSIM_CAPTURED = "2026-11-05"\n', "")
        try:
            appliquer(sans_date, [("Holafly", 67, 75)], "2026-11-10")
        except ValueError:
            return
        raise AssertionError("l'absence de MYBESTSIM_CAPTURED aurait dû être refusée")

    def test_le_fichier_reste_du_python_relisible(self):
        from check_editorial import appliquer, _lire_scores
        texte, _ = appliquer(SOURCE, [("Holafly", 67, 75), ("Simbye", None, 66)],
                             "2026-11-10")
        compile(texte, "editorial_sources.py", "exec")
        assert _lire_scores(texte) == {"Airalo": 72, "Holafly": 75, "Simbye": 66}


def _page(scores: dict) -> str:
    return "".join(
        f'<div class="mbshub-nm">{nom}</div>'
        f'<div class="mbshub-val">{score}<span>/100</span></div>'
        for nom, score in scores.items()
    )


class TestMain:
    """Les trois issues du contrôle, sans réseau : rien à faire, pull request, ou échec.
    C'est ce que lit le workflow pour décider d'ouvrir une PR."""

    PUBLIE = {"Airalo": 72, "Holafly": 67, "Roamic": 80, "Yesim": 75, "Saily": 72}

    def _contexte(self, tmp_path, monkeypatch, publie, stocke):
        import json
        import check_editorial as ce

        sources = tmp_path / "editorial_sources.py"
        sources.write_text(SOURCE, encoding="utf-8")
        catalog = tmp_path / "data.json"
        catalog.write_text(json.dumps(
            {"provider_breakdown": [{"provider": p} for p in stocke]}), encoding="utf-8")

        monkeypatch.setattr(ce, "SOURCES_PY", str(sources))
        monkeypatch.setattr(ce, "MYBESTSIM_SCORES", stocke)
        monkeypatch.setattr(ce, "fetch_page", lambda *a, **k: _page(publie))
        return sources, str(catalog)

    def test_rien_a_faire_ne_touche_pas_au_fichier(self, tmp_path, monkeypatch):
        from check_editorial import main
        sources, catalog = self._contexte(tmp_path, monkeypatch, self.PUBLIE,
                                          {"Holafly": 67, "Airalo": 72})
        assert main(["--catalog", catalog, "--apply"]) == 0
        assert sources.read_text(encoding="utf-8") == SOURCE

    def test_derive_recopiable_reecrit_et_sort_en_3(self, tmp_path, monkeypatch):
        from check_editorial import main
        publie = dict(self.PUBLIE, Holafly=75)
        sources, catalog = self._contexte(tmp_path, monkeypatch, publie,
                                          {"Holafly": 67, "Airalo": 72})
        assert main(["--catalog", catalog, "--apply"]) == 3
        ecrit = sources.read_text(encoding="utf-8")
        assert '"Holafly": 75,' in ecrit
        assert 'MYBESTSIM_CAPTURED = "2026-11-05"' not in ecrit

    def test_sans_apply_signale_sans_ecrire(self, tmp_path, monkeypatch):
        from check_editorial import main
        publie = dict(self.PUBLIE, Holafly=75)
        sources, catalog = self._contexte(tmp_path, monkeypatch, publie,
                                          {"Holafly": 67, "Airalo": 72})
        assert main(["--catalog", catalog]) == 3
        assert sources.read_text(encoding="utf-8") == SOURCE

    def test_un_score_disparu_de_leur_page_bloque_la_pr(self, tmp_path, monkeypatch):
        """Un fournisseur qu'ils ont retiré n'est pas une recopie : on échoue sans écrire."""
        from check_editorial import main
        publie = {k: v for k, v in self.PUBLIE.items() if k != "Holafly"}
        sources, catalog = self._contexte(tmp_path, monkeypatch, publie,
                                          {"Holafly": 67, "Airalo": 72})
        assert main(["--catalog", catalog, "--apply"]) == 1
        assert sources.read_text(encoding="utf-8") == SOURCE

    def test_page_illisible_bloque_la_pr(self, tmp_path, monkeypatch):
        """Balisage changé : on lit trop peu de scores, donc on refuse d'écrire quoi que ce
        soit — sinon une PR viderait les scores au premier changement de thème du site."""
        from check_editorial import main
        sources, catalog = self._contexte(tmp_path, monkeypatch, {"Roamic": 80},
                                          {"Holafly": 67, "Airalo": 72})
        assert main(["--catalog", catalog, "--apply"]) == 1
        assert sources.read_text(encoding="utf-8") == SOURCE
