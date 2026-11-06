# Catalogue eSIM — MyBestSim

Dashboard du catalogue eSIM (18 fournisseurs, 5 056 produits) pour le test de recrutement MyBestSim.

## Structure

```
data/                  18 CSV fournisseurs
scripts/
  compute_metrics.py   lit les CSV, calcule toutes les métriques, génère docs/data.json
  editorial_sources.py scores éditoriaux sourcés (MyBestSim, Trustpilot) avec citations
docs/                  dashboard statique (GitHub Pages)
  index.html
  data.json            généré, ne pas éditer à la main
tests/
  test_compute_metrics.py
```

## Utiliser

```bash
pip install -r requirements.txt
pytest tests/                                    # tests
python scripts/compute_metrics.py                # régénère docs/data.json
python -m http.server 8600 --directory docs       # prévisualiser en local
```

`compute_metrics.py` accepte `--source <dossier>` pour pointer vers un autre dossier de CSV
(local, réseau, ou dossier Drive/OneDrive synchronisé).

## Méthodologie

Voir les commentaires de `scripts/editorial_sources.py` pour les sources et dates de capture
des scores éditoriaux, et le rapport de recherche sectorielle pour la justification des
métriques dérivées (prix/Go, dispersion régionale, prime réseau, etc.).

Trois versions du score composite sont calculées (voir dashboard, section "Score de
recommandation") plutôt qu'une seule présentée comme vérité, faute de données éditoriales
complètes sur les 18 fournisseurs.
