"""Emplacements des fichiers de l'application (base de données, clé de chiffrement)."""

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home()))
        path = Path(base) / "DoctelCallStats"
    else:
        path = Path.home() / ".doctel-callstats"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return app_data_dir() / "callstats.db"


def key_path() -> Path:
    return app_data_dir() / "secret.key"
