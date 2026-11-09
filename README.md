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
data/                   18 CSV fournisseurs (données de repli et de test)
data_sources.csv        liens Google Drive des CSV (un fichier par ligne : nom,lien)
scripts/
  compute_metrics.py    lit les CSV, calcule toutes les métriques, génère docs/data.json
  fetch_sources.py      télécharge les CSV listés dans data_sources.csv depuis Google Drive
  editorial_sources.py  scores éditoriaux externes (MyBestSim, Trustpilot), sourcés et datés
  check_editorial.py    compare les scores MyBestSim stockés à leur page, et y cherche
                        le score des fournisseurs qu'on n'a pas encore relevés
  check_freshness.py    surveille l'âge des notes Trustpilot relevées à la main
  catalog_providers.py  liste les fournisseurs du catalogue et rapproche leurs noms
  country_coords.py     centroïdes des pays, pour la carte
docs/                    site statique (GitHub Pages)
  index.html             dashboard : une page unique (HTML, CSS, JavaScript), thème
                         clair par défaut, bascule vers le thème sombre dans la sidebar
  data.json               généré par compute_metrics.py, ne pas éditer à la main
  internet-en-croisiere-esim.html   article SEO (partie 2 du test)
  assets/                 logo et images de l'article
tests/                    89 tests (calculs, récupération Drive, dérive éditoriale, parité
                          Python/navigateur)
.github/workflows/ci.yml  tests, parité, déploiement quotidien et alerte de dérive
requirements-dev.txt      dépendances + Playwright (test de parité navigateur)
```

## Utiliser

```bash
pip install -r requirements-dev.txt && playwright install chromium   # une fois
pytest tests/                                 # 58 tests (le test navigateur est ignoré
                                              # sans Playwright)
python scripts/compute_metrics.py             # régénère docs/data.json depuis data/
python scripts/fetch_sources.py               # (option) télécharge les CSV depuis Drive
python scripts/check_editorial.py             # compare les scores MyBestSim stockés au site
python -m http.server 8600 --directory docs   # prévisualiser en local
```

`compute_metrics.py` accepte `--source <dossier>` pour pointer vers n'importe quel dossier
de CSV — chemin local, réseau ou dossier synchronisé. Pour intégrer un nouveau fournisseur,
voir « Ajouter un fournisseur » plus bas.

## Architecture

Le pipeline a deux étapes distinctes, pour que le dashboard reste consultable sans les CSV :

1. **Construction** (`compute_metrics.py`, exécuté en local ou en CI) : lit les CSV,
   calcule toutes les statistiques, écrit un unique `docs/data.json`.
2. **Consultation** (`docs/index.html`) : page statique autonome. Les lignes du catalogue
   sont embarquées dans `data.json`, et les filtres (fournisseur, réseau, durée) recalculent
   les graphiques et la carte directement dans le navigateur, sans second appel serveur.

## Automatisation

Le workflow GitHub Actions (`.github/workflows/ci.yml`) tourne à chaque push sur `main`, à
chaque pull request, **tous les jours à 05:00 UTC** et à la demande (onglet Actions) :

- **test** : les 89 tests.
- **parity** : charge le dashboard dans Chromium et compare les chiffres recalculés en
  JavaScript à chaque filtre (KPI, prix au Go par fournisseur, dispersion par zone, prime
  5G/4G) à ceux de Python sur les mêmes lignes. Ces calculs existent en double ; sans ce
  test, l'un pourrait dériver de l'autre sans que rien ne le signale.
- **deploy** (hors pull request) : récupère les CSV depuis Google Drive, génère `data.json`
  et publie le site sur GitHub Pages. Si `data_sources.csv` est vide, il utilise le dossier
  `data/` du dépôt. Tout autre échec (fichier non partagé, réseau) arrête le déploiement
  plutôt que de publier des données périmées sans le dire. `docs/data.json` commité n'est
  donc qu'un instantané : la version publiée est régénérée à chaque exécution.
- **editorial-drift** (quotidien uniquement) : compare `MYBESTSIM_SCORES` à la page
  publique de MyBestSim et échoue si un score a changé. Les notes Trustpilot, elles, ne
  peuvent pas être vérifiées automatiquement : leur `robots.txt` interdit tout le site aux
  robots (`User-agent: *` puis `Disallow: /`), leurs pages comme `api.trustpilot.com`
  répondent 403, et la seule voie officielle (API Data Solutions) passe par un contrat
  commercial. Ce qui est automatisable, c'est de ne pas les laisser vieillir en silence :
  `check_freshness.py` compare la date de relevé de chaque fournisseur à la date du jour et
  fait échouer le job au-delà de 30 jours, avec la liste des pages à ouvrir. La mise à jour
  reste humaine (`--checklist` imprime le relevé à cocher).

## Ajouter un fournisseur

Un CSV de même structure déposé dans le dossier source est intégré **sans toucher au code**.
Aucun nom de fournisseur n'est codé en dur : `compute_metrics.py` fait un `glob("*.csv")` sur
le dossier et lit le nom affiché dans la colonne `provider` du fichier. Toutes les
statistiques, les graphiques, les filtres et les classements se recalculent.

Les deux scores qui dépendent de sources éditoriales externes ne sont pas abandonnés pour
autant : les contrôles vont chercher le nouveau venu sur les deux sites concernés, chaque
jour, à partir du catalogue régénéré (et non d'un instantané commité).

- **Score MyBestSim** : `check_editorial.py` lit tout leur classement publié. Pour chaque
  fournisseur du catalogue dont nous n'avons pas le score, il vérifie s'il y est noté — si
  oui, il affiche la ligne exacte à coller dans `editorial_sources.py` et fait échouer le job
  jusqu'à ce que ce soit fait. Le rapprochement des noms se fait à la casse et à la
  ponctuation près (« aloSIM » = « AloSim ») ; une ressemblance seulement partielle
  (« Maya » / « Maya Mobile ») est signalée à trancher à la main, jamais retenue
  automatiquement.
- **Note Trustpilot** : leur site ne peut pas être interrogé (voir plus haut), donc ce qui
  est automatisé, c'est la détection, pas le relevé. `check_freshness.py` signale tout
  fournisseur du catalogue qui n'a ni note stockée ni mention dans `EDITORIAL_EXCLUDED` — la
  liste des fournisseurs déjà vérifiés et écartés, avec la raison (échantillon sous les 2 500
  avis, identification incertaine). Il reste alors à ouvrir la page et à inscrire soit la
  note, soit la raison.

Conséquence : « indisponible » n'apparaît qu'après vérification. Soit le fournisseur est
réellement absent du classement MyBestSim — le script le dit explicitement, c'est un constat
daté et non un oubli —, soit son échantillon Trustpilot est trop faible et la raison est
écrite dans le dépôt. Un nouveau fournisseur ne peut pas rester silencieusement sans score :
le job quotidien passe au rouge tant que personne n'a tranché.

Une seule limite subsiste, et elle est géographique : un pays dont le code n'est pas dans
`country_coords.py` n'apparaît pas sur la carte, tout en restant compté dans toutes les autres
statistiques. Les codes régionaux (`EU`, `AS`, `NA`, `WW`) en sont exclus exprès — un forfait
multi-pays n'a pas de position unique sur une carte.

Trois façons d'alimenter le dossier source, de la plus simple à la plus automatique :

1. **Dossier du dépôt** (`data/`) : déposer le fichier, rien d'autre.
2. **Google Drive** (en place aujourd'hui) : une ligne `nom,lien` dans `data_sources.csv` par
   fichier. C'est le seul geste manuel qui reste — le téléchargement, le contrôle de
   structure, le calcul et la publication sont automatiques.
3. **Lecture du dossier entier** : non implémenté, et c'est un choix. Les deux appels
   nécessaires sont `files.list?q='<ID_DOSSIER>' in parents` pour l'API Google Drive, et
   `/shares/{lien encodé}/driveItem?$expand=children` pour Microsoft Graph (OneDrive,
   SharePoint) — même principe, lister puis télécharger. Côté Drive, une clé d'API suffit pour
   un dossier partagé par lien ; côté Graph, un jeton OAuth est exigé, ce qui demande une
   inscription d'application. Dropbox, S3, R2 ou un partage WebDAV se traitent de la même
   façon.

Ce dernier point coûte peu parce que `fetch_sources.py` est le **seul** module qui sait d'où
viennent les fichiers : tout ce qui est en aval ne demande qu'un dossier local contenant des
`.csv`. Changer d'hébergeur, ou passer de la liste explicite à la lecture d'un dossier, revient
à écrire un adaptateur « lister / télécharger » dans ce fichier, sans rien changer ailleurs.
Le contrôle de structure existant reste commun à tous : un fichier qui n'a pas les colonnes
d'un catalogue est refusé avec un message clair au lieu de polluer le dashboard.

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
