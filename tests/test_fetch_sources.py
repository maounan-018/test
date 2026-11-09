"""Tests de la récupération des CSV depuis Google Drive (aucun accès réseau)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from fetch_sources import (
    SourceError,
    extract_drive_id,
    fetch_all,
    looks_like_catalog_csv,
    read_manifest,
)

VALID_CSV = (
    "sku,provider,product_name,country_code,country_name,data_gb,data_display,"
    "validity_days,price,currency,network,top_up\n"
    "x-1,Airalo,eSIM France 1 Go,FR,France,1,1 Go,7,5.0,EUR,4G,non\n"
).encode("utf-8")
HTML_PAGE = b"<!DOCTYPE html><html><head><title>Google Drive - Acces refuse</title></head></html>"
FILE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"


class TestExtractDriveId:
    @pytest.mark.parametrize("url", [
        f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing",
        f"https://drive.google.com/file/d/{FILE_ID}/view",
        f"https://drive.google.com/open?id={FILE_ID}",
        f"https://drive.google.com/uc?export=download&id={FILE_ID}",
    ])
    def test_supported_link_formats(self, url):
        assert extract_drive_id(url) == FILE_ID

    def test_folder_link_is_rejected_with_clear_message(self):
        """Un lien de DOSSIER ne désigne aucun fichier : mieux vaut un refus net qu'un
        téléchargement qui renverrait une page HTML."""
        with pytest.raises(ValueError, match="identifiant Drive introuvable"):
            extract_drive_id("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345")


class TestReadManifest:
    def test_ignores_comments_blank_lines_and_header(self, tmp_path):
        manifest = tmp_path / "data_sources.csv"
        manifest.write_text(
            "# commentaire\n\nname,url\n"
            f"airalo,https://drive.google.com/file/d/{FILE_ID}/view\n"
            f"saily,https://drive.google.com/open?id={FILE_ID}\n",
            encoding="utf-8")
        assert [name for name, _ in read_manifest(str(manifest))] == ["airalo", "saily"]

    def test_empty_manifest_returns_no_entries(self, tmp_path):
        manifest = tmp_path / "data_sources.csv"
        manifest.write_text("# rien de configuré\nname,url\n", encoding="utf-8")
        assert read_manifest(str(manifest)) == []

    def test_malformed_line_raises(self, tmp_path):
        manifest = tmp_path / "data_sources.csv"
        manifest.write_text("airalo\n", encoding="utf-8")
        with pytest.raises(ValueError, match="ligne de manifeste invalide"):
            read_manifest(str(manifest))


class TestLooksLikeCatalogCsv:
    def test_valid_catalog(self):
        assert looks_like_catalog_csv(VALID_CSV)

    def test_valid_catalog_with_utf8_bom(self):
        """Un CSV enregistré depuis Excel porte souvent un BOM UTF-8 en tête."""
        assert looks_like_catalog_csv(b"\xef\xbb\xbf" + VALID_CSV)

    def test_html_error_page_is_rejected(self):
        assert not looks_like_catalog_csv(HTML_PAGE)

    def test_empty_and_wrong_columns_are_rejected(self):
        assert not looks_like_catalog_csv(b"")
        assert not looks_like_catalog_csv(b"a,b,c\n1,2,3\n")


class TestFetchAll:
    def test_writes_one_csv_per_entry(self, tmp_path):
        entries = [("airalo", f"https://drive.google.com/file/d/{FILE_ID}/view"),
                   ("saily", f"https://drive.google.com/open?id={FILE_ID}")]
        written = fetch_all(entries, str(tmp_path / "out"), downloader=lambda file_id: VALID_CSV)
        assert sorted(os.path.basename(p) for p in written) == ["airalo.csv", "saily.csv"]
        assert (tmp_path / "out" / "airalo.csv").read_bytes() == VALID_CSV

    def test_reports_every_failure_at_once_and_writes_nothing_for_bad_files(self, tmp_path):
        """Avec 18 fichiers, l'utilisateur doit voir TOUS les partages à corriger d'un coup,
        pas un seul par relance. Une page HTML (accès refusé) ne doit jamais être écrite
        comme si c'était un CSV."""
        entries = [("ok", f"https://drive.google.com/file/d/{FILE_ID}/view"),
                   ("prive", f"https://drive.google.com/file/d/{FILE_ID}/view"),
                   ("dossier", "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345")]
        responses = {"ok": VALID_CSV, "prive": HTML_PAGE}
        names = iter(["ok", "prive"])
        with pytest.raises(SourceError) as excinfo:
            fetch_all(entries, str(tmp_path / "out"),
                      downloader=lambda file_id: responses[next(names)])
        message = str(excinfo.value)
        assert "2 fichier(s) sur 3" in message
        assert "prive" in message and "dossier" in message
        assert not (tmp_path / "out" / "prive.csv").exists()


class TestResolveManifest:
    """Les liens de partage ne doivent pas vivre dans le dépôt : le fichier local (ignoré
    par git, écrit en CI depuis le secret DRIVE_SOURCES) a la priorité sur le modèle."""

    def test_option_explicite_gagne(self, tmp_path):
        from fetch_sources import resolve_manifest
        (tmp_path / "data_sources.local.csv").write_text("name,url\n", encoding="utf-8")
        assert resolve_manifest(str(tmp_path), "ailleurs.csv") == "ailleurs.csv"

    def test_fichier_local_prefere_au_modele(self, tmp_path):
        import os
        from fetch_sources import resolve_manifest
        (tmp_path / "data_sources.csv").write_text("name,url\n", encoding="utf-8")
        (tmp_path / "data_sources.local.csv").write_text("name,url\n", encoding="utf-8")
        assert resolve_manifest(str(tmp_path)) == os.path.join(str(tmp_path),
                                                               "data_sources.local.csv")

    def test_modele_utilise_si_pas_de_fichier_local(self, tmp_path):
        import os
        from fetch_sources import resolve_manifest
        (tmp_path / "data_sources.csv").write_text("name,url\n", encoding="utf-8")
        assert resolve_manifest(str(tmp_path)) == os.path.join(str(tmp_path),
                                                               "data_sources.csv")


class TestAucunLienDansLeDepot:
    def test_le_modele_ne_contient_aucun_lien_reel(self):
        """Garde-fou : un lien de partage collé dans data_sources.csv serait publié avec le
        dépôt. Seul l'exemple commenté est toléré."""
        import io
        import os
        chemin = os.path.join(os.path.dirname(__file__), "..", "data_sources.csv")
        for ligne in io.open(chemin, encoding="utf-8"):
            nue = ligne.strip()
            if nue and not nue.startswith("#"):
                assert "drive.google.com" not in nue, (
                    "data_sources.csv contient un lien réel : le mettre dans "
                    "data_sources.local.csv (ignoré par git) ou dans le secret DRIVE_SOURCES")
