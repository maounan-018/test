"""Parité Python / navigateur : les chiffres que le dashboard recalcule en JavaScript à chaque
filtre doivent être identiques à ceux de compute_metrics.py sur les mêmes lignes.

Ces calculs existent en double (prime 5G/4G, dispersion par zone, prix au Go par
fournisseur, médianes) : sans ce test, rien n'empêche l'une des deux versions de dériver
— c'est déjà arrivé (le graphique « Prix au Go par fournisseur » moyennait les ratios
au lieu d'en faire un ratio d'agrégats, contredisant sa propre légende et le Python).

Nécessite playwright + chromium (pip install -r requirements-dev.txt ;
playwright install chromium) et l'accès aux CDN d'ECharts/Leaflet. Sans playwright, le
fichier est ignoré ; sans chromium, il est ignoré en local mais échoue en CI.
"""
import functools
import http.server
import math
import os
import re
import sys
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from compute_metrics import (  # noqa: E402
    load_catalog,
    network_premium_by_country,
    price_per_gb_by_provider,
    regional_dispersion,
)

ROOT = os.path.join(os.path.dirname(__file__), "..")
DOCS_DIR = os.path.join(ROOT, "docs")
DATA_DIR = os.path.join(ROOT, "data")

SCENARIOS = [
    pytest.param("", "", id="sans-filtre"),
    pytest.param("5G", "", id="reseau-5G"),
    pytest.param("4G", "15", id="reseau-4G-15-jours"),
]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    handler = functools.partial(_QuietHandler, directory=DOCS_DIR)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            chromium = p.chromium.launch()
        except Exception as e:  # chromium absent : pas de test possible
            if os.environ.get("CI"):
                raise
            pytest.skip(f"chromium indisponible ({e.__class__.__name__}) : playwright install chromium")
        yield chromium
        chromium.close()


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(DATA_DIR)


@pytest.fixture
def page(browser, base_url):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/index.html")
    page.wait_for_function(
        """() => document.querySelectorAll('#kpi-row .kpi').length === 6
              && window.echarts
              && ['c-pergb', 'c-dispersion'].every(id => {
                   const inst = echarts.getInstanceByDom(document.getElementById(id));
                   return inst && inst.getOption().series && inst.getOption().series.length;
                 })""",
        timeout=30_000,
    )
    yield page
    assert not errors, f"erreurs JavaScript dans la page : {errors}"
    page.close()


def _read_kpis(page):
    return page.eval_on_selector_all(
        "#kpi-row .kpi",
        """els => Object.fromEntries(els.map(e => [
              e.querySelector('.l').textContent,
              {v: e.querySelector('.v').textContent, pill: e.querySelector('.pill').textContent}]))""",
    )


def _settled_kpis(page):
    """Les KPI s'animent ~450 ms d'une valeur à l'autre : on attend deux lectures
    identiques à 200 ms d'écart avant de comparer."""
    previous = None
    for _ in range(25):
        current = _read_kpis(page)
        if current == previous:
            return current
        previous = current
        page.wait_for_timeout(200)
    raise AssertionError("les KPI ne se stabilisent pas")


def _numbers(text):
    return [float(x.replace(",", ".")) for x in re.findall(r"-?\d+(?:[.,]\d+)?", text.replace(" ", "").replace("\xa0", ""))]


def _js_round(x):
    return math.floor(x + 0.5)  # Math.round de JS : arrondi à la hausse sur .5


def _chart_series(page, chart_id):
    """(catégories, valeurs) du graphique à barres horizontales, lues dans l'instance ECharts."""
    return page.evaluate(
        """id => {
              if (document.getElementById(id).closest('.card').hidden) return {cats: [], vals: []};
              const o = echarts.getInstanceByDom(document.getElementById(id)).getOption();
              const axis = o.yAxis[0].type === 'category' ? o.yAxis[0] : o.xAxis[0];
              return {cats: axis.data || [], vals: o.series[0].data || []};
           }""",
        chart_id,
    )


@pytest.mark.parametrize("network, validity", SCENARIOS)
def test_browser_matches_python(page, catalog, network, validity):
    df = catalog
    if network:
        page.select_option("#f-network", network)
        df = df[df["network"] == network]
    if validity:
        page.select_option("#f-validity", validity)
        df = df[df["validity_days"] == int(validity)]
    assert len(df) > 0

    kpi = _settled_kpis(page)

    prices = df["price"]
    sized = df[df["data_gb"] > 0]

    lo, hi = _numbers(kpi["Fourchette de prix globale"]["v"])
    assert (lo, hi) == (_js_round(prices.min()), _js_round(prices.max()))

    assert _numbers(kpi["Prix moyen global"]["v"])[0] == pytest.approx(prices.mean(), abs=0.006)
    assert _numbers(kpi["Prix moyen global"]["pill"])[0] == pytest.approx(prices.median(), abs=0.006)

    per_gb_median = (sized["price"] / sized["data_gb"]).median()
    assert _numbers(kpi["Médiane €/Go"]["v"])[0] == pytest.approx(per_gb_median, abs=0.006)
    assert _numbers(kpi["Médiane €/Go"]["pill"])[0] == len(sized)

    assert _numbers(kpi["Data moyenne par carte"]["v"])[0] == pytest.approx(sized["data_gb"].mean(), abs=0.06)
    assert _numbers(kpi["Produits > 100 €"]["v"])[0] == int((prices > 100).sum())

    premium = network_premium_by_country(df)
    surcharge = kpi["Surcoût 5G vs 4G"]
    if premium["premium_pct"] is None:
        assert surcharge["v"] == "n/d"
    else:
        assert _numbers(surcharge["v"])[0] == pytest.approx(premium["premium_pct"], abs=0.11)
        assert _numbers(surcharge["pill"])[-1] == premium["n_countries"]

    assert _numbers(page.text_content("#sb-filtered"))[0] == len(df)

    # Prix au Go par fournisseur : ratio d'agrégats, identique au Python.
    series = _chart_series(page, "c-pergb")
    expected = {r["provider"]: r["price_per_gb"] for r in price_per_gb_by_provider(df)}
    assert dict(zip(series["cats"], series["vals"])) == pytest.approx(expected, abs=0.011)

    # Dispersion par zone multi-pays : même coefficient de variation.
    series = _chart_series(page, "c-dispersion")
    expected = {r["region"]: r["cv"] for r in regional_dispersion(df)}
    assert dict(zip(series["cats"], series["vals"])) == pytest.approx(expected, abs=0.0011)
