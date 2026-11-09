# Catalogue eSIM — MyBestSim

Dashboard du catalogue eSIM pour le test de recrutement MyBestSim (Stagiaire Développeur
IA & Automatisation). Un script lit les 18 fichiers CSV fournisseurs et calcule toutes les
statistiques demandées ; le résultat est publié comme une page autonome, servie telle quelle,
sans serveur applicatif ni base de données. Elle se consulte dans un navigateur sans rien
installer et sans avoir les fichiers sources en local.

« Servie telle quelle » ne veut pas dire figée : la page embarque les lignes du catalogue et
recalcule tous ses chiffres dans le navigateur à chaque changement de filtre. Ce qui est
statique, c'est l'hébergement — pas le contenu.

## Ce que mesure le dashboard

| Métrique | Ce qu'elle mesure |
|---|---|
| Produits | nombre d'offres du catalogue |
| Fournisseurs | nombre de marques distinctes |
| Fourchette de prix | le forfait le moins cher et le plus cher, toutes tailles confondues : une étendue, pas une moyenne |
| Prix moyen | moyenne du prix affiché, sans pondération par le volume — un forfait 1 Go y pèse autant qu'un 50 Go |
| Produits > 100 € | nombre d'offres au-dessus de 100 €, et leur part du catalogue |
| Data moyenne | volume moyen des forfaits à volume fini ; les illimités en sont exclus, n'ayant pas de volume |
| Forfaits illimités | nombre d'offres sans volume fini |
| Médiane €/Go | prix au Go du forfait médian : la moitié des forfaits à volume fini coûtent moins cher au Go |
| Pays cartographiés | pays réels positionnés sur la carte, zones multi-pays exclues |
| Prime réseau 5G vs 4G | écart de prix entre 5G et 4G à destination égale |

Les valeurs changent à chaque mise à jour du catalogue et le dashboard les affiche à jour.
Dans la page, les cartes KPI portent sur la sélection filtrée et se recalculent à chaque
filtre, tandis que la sidebar rappelle en permanence les chiffres du catalogue complet.

## Structure du dépôt

```
data/                   18 CSV fournisseurs (données de repli et de test)
data_sources.csv        modèle commenté : aucun lien réel n'est stocké dans le dépôt
scripts/
  compute_metrics.py    lit les CSV, calcule toutes les métriques, génère docs/data.json
  fetch_sources.py      télécharge les CSV du manifeste depuis Google Drive
  editorial_sources.py  scores éditoriaux externes (MyBestSim, Trustpilot), sourcés et datés
  check_editorial.py    compare les scores MyBestSim stockés à leur page, et y cherche
                        le score des fournisseurs qu'on n'a pas encore relevés
  check_freshness.py    surveille l'âge des relevés Trustpilot et signale les fournisseurs
                        jamais relevés
  catalog_providers.py  liste les fournisseurs du catalogue et rapproche leurs noms
  country_coords.py     centroïdes des pays, pour la carte
docs/                    le site publié
  index.html             dashboard : une page unique (HTML, CSS, JavaScript), thème
                         clair par défaut, bascule vers le thème sombre dans la sidebar
  data.json               généré par compute_metrics.py et régénéré à chaque publication :
                          une retouche à la main serait écrasée au passage suivant
  assets/                 logo MyBestSim
tests/                    94 tests (calculs, récupération des CSV, contrôles éditoriaux,
                          parité Python/navigateur)
.github/workflows/ci.yml  tests, parité, publication quotidienne et alerte de dérive
requirements-dev.txt      dépendances + Playwright (test de parité navigateur)
```

## Utiliser

```bash
pip install -r requirements-dev.txt && playwright install chromium   # une fois
pytest tests/                                 # 94 tests (le test navigateur est ignoré
                                              # sans Playwright)
python scripts/compute_metrics.py             # régénère docs/data.json depuis data/
python scripts/fetch_sources.py               # (option) télécharge les CSV depuis Drive
python scripts/check_editorial.py             # compare les scores MyBestSim stockés au site
python -m http.server 8600 --directory docs   # prévisualiser en local
```

Les liens de partage des CSV ne sont jamais stockés dans le dépôt : un lien donne accès au
fichier à qui le possède. `fetch_sources.py` lit un manifeste fourni à l'exécution et, à
défaut, le pipeline utilise le dossier `data/`. Un test échoue si un lien réel se retrouve
dans un fichier suivi par git.

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

- **test** : les 94 tests.
- **parity** : charge le dashboard dans Chromium et compare les chiffres recalculés en
  JavaScript à chaque filtre (KPI, prix au Go par fournisseur, dispersion par zone, prime
  5G/4G) à ceux de Python sur les mêmes lignes. Ces calculs existent en double ; sans ce
  test, l'un pourrait dériver de l'autre sans que rien ne le signale.
- **deploy** (hors pull request) : récupère les CSV, régénère `data.json` et publie le site.
  Le manifeste des liens est fourni à l'exécution, jamais stocké dans le dépôt ; sans lui,
  le pipeline utilise le dossier `data/`. Tout autre échec — fichier non partagé, réseau —
  arrête la publication plutôt que de mettre en ligne des données périmées sans le dire.
  `docs/data.json` commité n'est donc qu'un instantané : la version publiée est régénérée à
  chaque exécution.
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
2. **Google Drive** (en place aujourd'hui) : une ligne `nom,lien` à ajouter au manifeste.
   C'est le seul geste manuel qui reste — le téléchargement, le contrôle de structure, le
   calcul et la publication sont automatiques.
3. **Lecture du dossier entier** : non implémenté. Les deux appels
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

- **Version A** — le score que MyBestSim publie lui-même, lu sur
  mybestsim.com/en/best-esim-providers/ et affiché sans retraitement, comme référence
  externe. Couvre 5 fournisseurs sur 18 ; les autres restent indisponibles plutôt
  qu'estimés.
- **Version B** — pondération 60 % éditorial / 16 % prix / 14 % couverture / 10 % réseau,
  avec la note Trustpilot comme composante éditoriale (fournisseurs à plus de 2 500 avis
  uniquement). Une note Trustpilot mesure la satisfaction et rien d'autre : elle ne contient
  ni prix ni couverture, on peut donc la combiner à nos notes quantitatives sans compter deux
  fois la même chose. Couvre 12 fournisseurs sur 18.
- **Version C** — sans composante éditoriale, les 3 critères mesurables repondérés à
  100 % (40 % prix, 35 % couverture, 25 % réseau). Couvre les 18 fournisseurs.

Le critère réseau (10 % en B, 25 % en C) mesure la part du catalogue du fournisseur en 5G
**et** en data illimitée (moyenne des deux pourcentages) — MyBestSim définit ce critère
comme "5G + unlimited : feature availability", pas la 5G seule.

Les sous-scores quantitatifs sont normalisés par rang percentile plutôt que par min-max :
les écarts réels entre fournisseurs sont faibles (quelques pour cent) et un min-max les
aurait étirés sur toute l'échelle 0-100, en plus de dépendre entièrement des deux
fournisseurs les plus extrêmes du catalogue.

Conséquence à connaître : un rang percentile est **relatif au catalogue**. Ajouter un
fournisseur déplace les notes de tous les autres. Vérifié en ajoutant un 19e fournisseur :
les 18 scores de la version C bougent et 11 changements de rang apparaissent, alors que la
version A ne bouge pas d'un point, puisqu'elle ne fait que reprendre un score calculé
ailleurs. Deux scores publiés à des dates différentes ne sont donc comparables que si le
catalogue est le même.

La note Trustpilot (sur 5) est rescalée sur 100 par min-max entre 1 étoile et 5 étoiles, et
non par une simple règle de trois : Trustpilot ne permet pas de note à 0 étoile, le minimum
réel de l'échelle est 1.

Sources et dates de capture des scores éditoriaux : voir les commentaires de
`scripts/editorial_sources.py`.

## Tests

94 tests, répartis ainsi :

- **35 sur les calculs** : formules vérifiées à la main sur des cas simples, cas limites
  (filtre sans résultat, zones multi-pays, forfaits illimités), régressions trouvées en cours
  de route — dont la lecture du code pays « NA » (Amérique du Nord), que pandas interprète
  par défaut comme une valeur manquante — et la correspondance entre `docs/data.json` et les
  CSV du dépôt.
- **26 sur la fraîcheur des relevés Trustpilot** : calcul de l'âge, seuil configurable, date
  de relevé incohérente, détection d'un fournisseur jamais relevé, et vérification qu'aucun
  module réseau n'est importé par le script — leurs conditions d'utilisation l'interdisent.
- **18 sur la récupération des CSV** : extraction de l'identifiant d'un lien de partage,
  réponse HTML renvoyée à la place d'un CSV, échecs groupés, choix du manifeste, et garde-fou
  contre un lien réel laissé dans un fichier suivi par git.
- **12 sur la dérive des scores MyBestSim** : lecture de leur page, écart avec les valeurs
  stockées, découverte du score d'un fournisseur non encore relevé, refus des rapprochements
  de noms approximatifs.
- **3 de parité Python / navigateur** : les chiffres recalculés en JavaScript à chaque filtre
  doivent être identiques à ceux de Python sur les mêmes lignes.
