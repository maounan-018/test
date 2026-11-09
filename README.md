# Catalogue eSIM — MyBestSim

Dashboard du catalogue eSIM pour le test de recrutement MyBestSim (Stagiaire Développeur
IA & Automatisation). Lit 18 fichiers CSV fournisseurs, calcule toutes les statistiques
demandées et les publie comme une page web statique, consultable dans un navigateur sans
rien installer ni avoir les fichiers sources en local.

## Chiffres clés du catalogue

| Métrique | Valeur |
|---|---|
| Produits | 5 056 |
| Fournisseurs | 18 |
| Fourchette de prix | 5,36 € – 154,63 € |
| Prix moyen | 29,30 € |
| Produits > 100 € | 56 (1,1 %) |
| Data moyenne (forfaits à volume fini) | 14,49 Go |
| Forfaits illimités | 653 |
| Pays cartographiés | 50 |
| Prime réseau 5G vs 4G (à destination égale) | 0,3 %, sur 50 pays comparables |

Ces chiffres sont recalculés à chaque changement de filtre dans le dashboard ; ici ils
portent sur le catalogue complet.

## Structure du dépôt

```
data/                   18 CSV fournisseurs (données sources)
scripts/
  compute_metrics.py    lit les CSV, calcule toutes les métriques, génère docs/data.json
  editorial_sources.py  scores éditoriaux externes (MyBestSim, Trustpilot), sourcés et datés
  country_coords.py     centroïdes des pays, pour la carte
docs/                    site statique (GitHub Pages)
  index.html             dashboard : une page unique (HTML, CSS, JavaScript), thème
                         clair par défaut, bascule vers le thème sombre dans la sidebar
  data.json               généré par compute_metrics.py, ne pas éditer à la main
  internet-en-croisiere-esim.html   article SEO (partie 2 du test)
  assets/                 logo et images de l'article
tests/
  test_compute_metrics.py 34 tests
.github/workflows/ci.yml  tests + régénération de data.json à chaque push
```

## Utiliser

```bash
pip install -r requirements.txt
pytest tests/                                 # 34 tests
python scripts/compute_metrics.py             # régénère docs/data.json
python -m http.server 8600 --directory docs   # prévisualiser en local
```

`compute_metrics.py` accepte `--source <dossier>` pour pointer vers n'importe quel dossier
de CSV — chemin local, réseau ou dossier Drive/OneDrive synchronisé. Un nouveau fournisseur
est pris en compte automatiquement : il suffit d'ajouter son CSV au dossier source, aucune
modification de code n'est nécessaire.

## Architecture

Le pipeline a deux étapes distinctes, pour que le dashboard reste consultable sans les CSV :

1. **Construction** (`compute_metrics.py`, exécuté en local ou en CI) : lit les CSV,
   calcule toutes les statistiques, écrit un unique `docs/data.json`.
2. **Consultation** (`docs/index.html`) : page statique autonome. Les lignes du catalogue
   sont embarquées dans `data.json`, et les filtres (fournisseur, réseau, durée) recalculent
   les graphiques et la carte directement dans le navigateur, sans second appel serveur.

La CI (GitHub Actions) relance les tests à chaque push, régénère `data.json` et échoue si le
résultat diffère de la version commitée — une garantie que les données publiées sont
reproductibles et à jour avec le code.

## Méthodologie

**Prix au Go.** Calculé en ratio d'agrégats (somme des prix ÷ somme des Go), pas en moyenne
des ratios individuels. Une moyenne de ratios pondère un forfait 1 Go autant qu'un forfait
50 Go et peut inverser un classement : vérifié sur le catalogue, deux fournisseurs changent
de plus de 10 rangs selon la formule choisie.

**Prime réseau 5G.** Comparer un prix 5G global à un prix 4G global confond le réseau avec
la géographie (le 5G n'est pas vendu dans les mêmes pays que le 4G). La prime est donc
calculée pays par pays, puis moyennée — et seulement sur les pays réels, les zones
multi-pays (Europe, Asie, Monde, Amérique du Nord) étant exclues puisque « à destination
égale » suppose une destination.

**Dispersion régionale.** Coefficient de variation (écart-type ÷ moyenne) du prix au Go par
zone multi-pays : il indique si les offres d'une même zone se ressemblent, pas si la zone
est chère.

**Score de recommandation.** La qualité perçue d'un fournisseur n'existe pas dans les CSV
bruts. Plutôt que d'en inventer une seule version présentée comme vérité, trois sont
calculées :

- **Version A** — score MyBestSim publié, tel quel. MyBestSim décrit sa propre méthode
  comme 60 % éditorial + 40 % bonus data (16 % prix, 14 % couverture, 10 % réseau,
  vérifié sur mybestsim.com/en/best-esim-providers/), mais ce score publié est déjà le
  résultat final de ce mélange — ils ne communiquent jamais la part éditoriale isolée.
  On ne le recombine donc pas avec nos propres notes quantitatives (ça compterait deux
  fois la dimension quantitative, une fois dans leur score, une fois dans la nôtre) : on
  l'affiche directement comme référence. Couvre 5 fournisseurs sur 18, les autres restent
  indisponibles plutôt qu'estimés.
- **Version B** — pondération 60 % éditorial / 16 % prix / 14 % couverture / 10 % réseau,
  éditorial = note Trustpilot (fournisseurs à plus de 2 500 avis uniquement). Contrairement
  au score MyBestSim, une note Trustpilot est une mesure de satisfaction isolée — elle ne
  mélange pas déjà prix et couverture — donc la recombiner avec nos notes quantitatives
  n'a pas le même problème. Couvre 12 fournisseurs sur 18.
- **Version C** — sans composante éditoriale, les 3 critères mesurables repondérés à
  100 % (40 % prix, 35 % couverture, 25 % réseau). Couvre les 18 fournisseurs.

Le critère réseau (10 % en B, 25 % en C) mesure la part du catalogue du fournisseur en 5G
**et** en data illimitée (moyenne des deux pourcentages) — MyBestSim définit ce critère
comme "5G + unlimited : feature availability", pas la 5G seule.

Les sous-scores quantitatifs sont normalisés par rang percentile plutôt que par min-max :
les écarts réels entre fournisseurs sont faibles (quelques pour cent) et un min-max les
aurait étirés sur toute l'échelle 0-100, en plus de dépendre entièrement des deux
fournisseurs les plus extrêmes du catalogue.

La note Trustpilot (sur 5) est rescalée sur 100 par min-max entre 1 étoile et 5 étoiles, et
non par une simple règle de trois : Trustpilot ne permet pas de note à 0 étoile, le minimum
réel de l'échelle est 1.

Sources et dates de capture des scores éditoriaux : voir les commentaires de
`scripts/editorial_sources.py`.

## Tests

32 tests couvrant les calculs (formules vérifiées à la main sur des cas simples), les cas
limites (filtre sans résultat, zones multi-pays, forfaits illimités) et plusieurs
régressions trouvées en cours de développement — dont la lecture du code pays « NA »
(Amérique du Nord), que pandas interprète par défaut comme une valeur manquante.
