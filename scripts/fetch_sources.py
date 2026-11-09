"""Télécharge les CSV fournisseurs depuis Google Drive, d'après data_sources.csv.

Usage: python fetch_sources.py [--manifest data_sources.csv] [--out dossier]

Chaque ligne du manifeste (nom,url) pointe vers UN fichier Drive partagé en « Tous les
utilisateurs disposant du lien ». Le fichier est enregistré sous <out>/<nom>.csv, prêt à
être lu par compute_metrics.py --source <out>.

Codes de sortie : 0 = tout téléchargé ; 1 = au moins un fichier en échec ; 3 = manifeste
vide (rien n'est configuré — l'appelant peut alors retomber sur le dossier data/ du dépôt).
"""
import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request

EXIT_FAILED = 1
EXIT_NOTHING_CONFIGURED = 3

# Colonnes réellement lues par compute_metrics.py : un fichier qui ne les a pas n'est pas
# un catalogue exploitable, même si le téléchargement a réussi.
REQUIRED_COLUMNS = {"provider", "country_code", "country_name", "data_gb",
                    "validity_days", "price", "network", "top_up"}

ID_PATTERNS = (
    re.compile(r"/file/d/([A-Za-z0-9_-]{10,})"),   # drive.google.com/file/d/<id>/view
    re.compile(r"[?&]id=([A-Za-z0-9_-]{10,})"),    # open?id=<id> ou uc?id=<id>
)
DOWNLOAD_URL = "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t"


class SourceError(Exception):
    pass


def extract_drive_id(url: str) -> str:
    for pattern in ID_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1)
    raise ValueError(f"identifiant Drive introuvable dans : {url!r}")


def read_manifest(path: str) -> list:
    """Lignes « nom,url ». Les lignes vides et celles qui commencent par # sont ignorées,
    ainsi que l'en-tête « name,url »."""
    entries = []
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            name, _, url = line.partition(",")
            name, url = name.strip(), url.strip()
            if name.lower() == "name" and url.lower() == "url":
                continue
            if not name or not url:
                raise ValueError(f"ligne de manifeste invalide : {raw!r} (attendu : nom,url)")
            entries.append((name, url))
    return entries


def looks_like_catalog_csv(content: bytes) -> bool:
    """Drive répond par une page HTML (connexion, accès refusé, quota) avec un code 200 :
    un téléchargement « réussi » peut donc ne pas être un CSV. On vérifie l'en-tête."""
    text = content.decode("utf-8-sig", errors="replace")
    first_line = text.splitlines()[0] if text.strip() else ""
    columns = {c.strip().strip('"') for c in first_line.split(",")}
    return REQUIRED_COLUMNS <= columns


def download(file_id: str, retries: int = 3, timeout: int = 60) -> bytes:
    request = urllib.request.Request(DOWNLOAD_URL.format(id=file_id),
                                     headers={"User-Agent": "mybestsim-dashboard-fetch"})
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            time.sleep(2 * attempt)
    raise SourceError(f"téléchargement impossible après {retries} essais : {last_error}")


def fetch_all(entries: list, out_dir: str, downloader=download) -> list:
    """Télécharge tous les fichiers puis lève UNE erreur listant tous les échecs, plutôt
    que de s'arrêter au premier : avec 18 fichiers, corriger un partage à la fois et
    relancer 18 fois serait pénible."""
    os.makedirs(out_dir, exist_ok=True)
    written, errors = [], []
    for name, url in entries:
        try:
            content = downloader(extract_drive_id(url))
            if not looks_like_catalog_csv(content):
                raise SourceError("la réponse n'est pas un CSV de catalogue — le fichier est-il "
                                  "bien partagé en « Tous les utilisateurs disposant du lien » ?")
            path = os.path.join(out_dir, f"{name}.csv")
            with open(path, "wb") as f:
                f.write(content)
            written.append(path)
        except (SourceError, ValueError) as e:
            errors.append(f"  - {name} : {e}")
    if errors:
        raise SourceError("échec sur {} fichier(s) sur {} :\n{}".format(
            len(errors), len(entries), "\n".join(errors)))
    return written


def main() -> int:
    root = os.path.join(os.path.dirname(__file__), "..")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=os.path.join(root, "data_sources.csv"))
    parser.add_argument("--out", default=os.path.join(root, "build", "data"))
    args = parser.parse_args()

    entries = read_manifest(args.manifest) if os.path.exists(args.manifest) else []
    if not entries:
        print(f"Aucune source configurée dans {args.manifest}.", file=sys.stderr)
        return EXIT_NOTHING_CONFIGURED
    try:
        written = fetch_all(entries, args.out)
    except SourceError as e:
        print(f"ERREUR — {e}", file=sys.stderr)
        return EXIT_FAILED
    print(f"OK — {len(written)} fichier(s) téléchargé(s) dans {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
