"""Emplacements des fichiers de l'application (base de données locale)."""

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home()))
        path = Path(base) / "CaduceaCallAnalyzer"
    else:
        path = Path.home() / ".caducea-call-analyzer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return app_data_dir() / "call_analyzer.db"


def resource_path(relative: str) -> Path:
    """Chemin vers un fichier embarqué (ex: icon.ico), que l'app tourne depuis les
    sources ou depuis l'exécutable PyInstaller (données extraites dans sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def icon_path() -> Path:
    """Chemin vers l'icône de l'application. Réutilise l'icône de marque CADUCEA déjà
    présente dans desktop-app/ (dossier voisin) plutôt que d'en committer une seconde
    copie binaire ici ; le build PyInstaller l'embarque depuis ce même dossier voisin
    (voir packaging/call_analyzer.spec), donc à l'exécution du .exe elle est bien
    trouvée via resource_path (sys._MEIPASS)."""
    bundled = resource_path("icon.ico")
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parent.parent.parent / "desktop-app" / "icon.ico"


def error_log_path() -> Path:
    return app_data_dir() / "erreurs.log"


def log_error(context: str, detail: str) -> None:
    """Ajoute une entrée horodatée au journal d'erreurs local (aide au diagnostic)."""
    import datetime as _datetime

    try:
        with open(error_log_path(), "a", encoding="utf-8") as f:
            f.write(f"[{_datetime.datetime.now().isoformat(timespec='seconds')}] {context}\n{detail}\n\n")
    except OSError:
        pass
