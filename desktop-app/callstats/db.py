"""Accès à la base SQLite locale : clients, appels, réglages de publication."""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    numero_appele   TEXT PRIMARY KEY,
    nom_appele      TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    cycle_start_day INTEGER NOT NULL DEFAULT 1,
    display_name    TEXT
);

CREATE TABLE IF NOT EXISTS appels (
    call_id         TEXT PRIMARY KEY,
    numero_appele   TEXT NOT NULL REFERENCES clients(numero_appele),
    numero_appelant TEXT,
    date_heure      TEXT NOT NULL,
    comm_seconds    INTEGER NOT NULL,
    tag             TEXT
);
CREATE INDEX IF NOT EXISTS idx_appels_client_date ON appels(numero_appele, date_heure);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS appels_sortants (
    call_id         TEXT PRIMARY KEY,
    numero_appele   TEXT NOT NULL REFERENCES clients(numero_appele),
    numero_appelant TEXT,
    date_heure      TEXT NOT NULL,
    comm_seconds    INTEGER NOT NULL,
    is_sortant      INTEGER NOT NULL DEFAULT 0,
    sortant_type    TEXT,
    is_aboutement   INTEGER NOT NULL DEFAULT 0,
    aboutement_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_appels_sortants_client_date ON appels_sortants(numero_appele, date_heure);

CREATE TABLE IF NOT EXISTS sms_manuels (
    numero_appele TEXT NOT NULL REFERENCES clients(numero_appele),
    period_start  TEXT NOT NULL,
    sms_rappel    INTEGER NOT NULL DEFAULT 0,
    sms_contact   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (numero_appele, period_start)
);
"""

# Tarifs dédiés connus pour certain(e)s client(e)s (appliqués une seule fois, à la création du
# client ou lors de la migration d'une base existante — jamais réappliqués ensuite pour ne pas
# écraser une modification manuelle ultérieure dans Réglages > Tarifs).
SPECIAL_TARIFS = {
    "0973030903": {  # BERTRAND
        "tarif_aboutement_fixe": 0.15,
        "tarif_aboutement_portable": 0.52,
        "tarif_sortant_fixe": 0.35,
        "tarif_sortant_portable": 0.56,
    },
}

DEFAULT_TARIF_ABOUTEMENT_FIXE = 0.15
DEFAULT_TARIF_ABOUTEMENT_PORTABLE = 0.56
DEFAULT_TARIF_SORTANT_FIXE = 0.56
DEFAULT_TARIF_SORTANT_PORTABLE = 0.98


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes introduites après la création initiale des bases existantes."""
    client_columns = {row["name"] for row in conn.execute("PRAGMA table_info(clients)")}
    if "display_name" not in client_columns:
        conn.execute("ALTER TABLE clients ADD COLUMN display_name TEXT")
        conn.commit()
        client_columns.add("display_name")

    for col in ("tarif_aboutement_fixe", "tarif_aboutement_portable", "tarif_sortant_fixe", "tarif_sortant_portable"):
        if col not in client_columns:
            conn.execute(f"ALTER TABLE clients ADD COLUMN {col} REAL")
            conn.commit()

    appel_columns = {row["name"] for row in conn.execute("PRAGMA table_info(appels)")}
    if "tag" not in appel_columns:
        conn.execute("ALTER TABLE appels ADD COLUMN tag TEXT")
        conn.commit()

    _apply_special_tarifs(conn)


def _apply_special_tarifs(conn: sqlite3.Connection) -> None:
    """Applique les tarifs dédiés connus aux client(e)s déjà présent(e)s en base dont les tarifs
    n'ont encore jamais été personnalisés (les 4 colonnes sont NULL)."""
    for numero, tarifs in SPECIAL_TARIFS.items():
        row = conn.execute(
            "SELECT tarif_aboutement_fixe, tarif_aboutement_portable, tarif_sortant_fixe, tarif_sortant_portable "
            "FROM clients WHERE numero_appele = ?",
            (numero,),
        ).fetchone()
        if row is None or any(row[k] is not None for k in tarifs):
            continue
        conn.execute(
            "UPDATE clients SET tarif_aboutement_fixe = ?, tarif_aboutement_portable = ?, "
            "tarif_sortant_fixe = ?, tarif_sortant_portable = ? WHERE numero_appele = ?",
            (
                tarifs["tarif_aboutement_fixe"],
                tarifs["tarif_aboutement_portable"],
                tarifs["tarif_sortant_fixe"],
                tarifs["tarif_sortant_portable"],
                numero,
            ),
        )
        conn.commit()


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "client"


def unique_slug(conn: sqlite3.Connection, base_slug: str) -> str:
    slug = base_slug
    suffix = 2
    while conn.execute("SELECT 1 FROM clients WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


@dataclass
class Client:
    numero_appele: str
    nom_appele: str
    slug: str
    cycle_start_day: int
    display_name: Optional[str] = None

    @property
    def label(self) -> str:
        """Nom affiché à l'écran et dans les rapports (personnalisable, sinon le nom du fichier importé)."""
        return self.display_name if self.display_name else self.nom_appele


def _client_from_row(row: sqlite3.Row) -> Client:
    return Client(
        row["numero_appele"], row["nom_appele"], row["slug"], row["cycle_start_day"], row["display_name"]
    )


def get_or_create_client(conn: sqlite3.Connection, numero_appele: str, nom_appele: str) -> Client:
    row = conn.execute("SELECT * FROM clients WHERE numero_appele = ?", (numero_appele,)).fetchone()
    if row:
        # Le nom peut légèrement varier d'un export à l'autre (espaces...) ; on garde le premier connu.
        return _client_from_row(row)
    slug = unique_slug(conn, slugify(nom_appele))
    conn.execute(
        "INSERT INTO clients (numero_appele, nom_appele, slug, cycle_start_day) VALUES (?, ?, ?, 1)",
        (numero_appele, nom_appele, slug),
    )
    if numero_appele in SPECIAL_TARIFS:
        tarifs = SPECIAL_TARIFS[numero_appele]
        conn.execute(
            "UPDATE clients SET tarif_aboutement_fixe = ?, tarif_aboutement_portable = ?, "
            "tarif_sortant_fixe = ?, tarif_sortant_portable = ? WHERE numero_appele = ?",
            (
                tarifs["tarif_aboutement_fixe"],
                tarifs["tarif_aboutement_portable"],
                tarifs["tarif_sortant_fixe"],
                tarifs["tarif_sortant_portable"],
                numero_appele,
            ),
        )
    return Client(numero_appele, nom_appele, slug, 1)


def list_clients(conn: sqlite3.Connection) -> list[Client]:
    rows = conn.execute(
        "SELECT * FROM clients ORDER BY COALESCE(display_name, nom_appele) COLLATE NOCASE"
    ).fetchall()
    return [_client_from_row(r) for r in rows]


def get_client(conn: sqlite3.Connection, numero_appele: str) -> Optional[Client]:
    row = conn.execute("SELECT * FROM clients WHERE numero_appele = ?", (numero_appele,)).fetchone()
    if not row:
        return None
    return _client_from_row(row)


def update_client(
    conn: sqlite3.Connection, numero_appele: str, slug: str, cycle_start_day: int, display_name: str = ""
) -> None:
    conn.execute(
        "UPDATE clients SET slug = ?, cycle_start_day = ?, display_name = ? WHERE numero_appele = ?",
        (slug, cycle_start_day, display_name.strip() or None, numero_appele),
    )


def insert_call(
    conn: sqlite3.Connection,
    call_id: str,
    numero_appele: str,
    numero_appelant: str,
    date_heure: datetime,
    comm_seconds: int,
    tag: str = "",
) -> bool:
    """Insère un appel ; retourne False si déjà présent (dédoublonnage par call_id).

    Si l'appel existe déjà mais que son Tag diffère (ex: base créée avant l'ajout de
    cette colonne), le Tag est mis à jour rétroactivement lors d'un ré-import.
    """
    existing = conn.execute("SELECT tag FROM appels WHERE call_id = ?", (call_id,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO appels (call_id, numero_appele, numero_appelant, date_heure, comm_seconds, tag) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (call_id, numero_appele, numero_appelant, date_heure.isoformat(), comm_seconds, tag or None),
        )
        return True
    if (existing["tag"] or "") != (tag or ""):
        conn.execute("UPDATE appels SET tag = ? WHERE call_id = ?", (tag or None, call_id))
    return False


def calls_for_client_range(conn: sqlite3.Connection, numero_appele: Optional[str], start_iso: str, end_iso: str):
    if numero_appele is None:
        return conn.execute(
            "SELECT * FROM appels WHERE date_heure >= ? AND date_heure <= ? ORDER BY date_heure",
            (start_iso, end_iso),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM appels WHERE numero_appele = ? AND date_heure >= ? AND date_heure <= ? ORDER BY date_heure",
        (numero_appele, start_iso, end_iso),
    ).fetchall()


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# -- Appels sortants / aboutements -----------------------------------------------


def insert_call_sortant(
    conn: sqlite3.Connection,
    call_id: str,
    numero_appele: str,
    numero_appelant: str,
    date_heure: datetime,
    comm_seconds: int,
    is_sortant: bool,
    sortant_type: Optional[str],
    is_aboutement: bool,
    aboutement_type: Optional[str],
) -> bool:
    """Insère un appel sortant/aboutement ; retourne False si déjà présent (dédoublonnage par call_id)."""
    existing = conn.execute("SELECT 1 FROM appels_sortants WHERE call_id = ?", (call_id,)).fetchone()
    if existing is not None:
        return False
    conn.execute(
        "INSERT INTO appels_sortants "
        "(call_id, numero_appele, numero_appelant, date_heure, comm_seconds, "
        " is_sortant, sortant_type, is_aboutement, aboutement_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            call_id, numero_appele, numero_appelant, date_heure.isoformat(), comm_seconds,
            1 if is_sortant else 0, sortant_type, 1 if is_aboutement else 0, aboutement_type,
        ),
    )
    return True


def sortants_for_client_range(conn: sqlite3.Connection, numero_appele: Optional[str], start_iso: str, end_iso: str):
    if numero_appele is None:
        return conn.execute(
            "SELECT * FROM appels_sortants WHERE date_heure >= ? AND date_heure <= ?",
            (start_iso, end_iso),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM appels_sortants WHERE numero_appele = ? AND date_heure >= ? AND date_heure <= ?",
        (numero_appele, start_iso, end_iso),
    ).fetchall()


# -- Tarifs -------------------------------------------------------------------


def get_global_tarifs(conn: sqlite3.Connection) -> dict:
    return {
        "aboutement_fixe": float(get_setting(conn, "tarif_aboutement_fixe", str(DEFAULT_TARIF_ABOUTEMENT_FIXE))),
        "aboutement_portable": float(
            get_setting(conn, "tarif_aboutement_portable", str(DEFAULT_TARIF_ABOUTEMENT_PORTABLE))
        ),
        "sortant_fixe": float(get_setting(conn, "tarif_sortant_fixe", str(DEFAULT_TARIF_SORTANT_FIXE))),
        "sortant_portable": float(get_setting(conn, "tarif_sortant_portable", str(DEFAULT_TARIF_SORTANT_PORTABLE))),
    }


def set_global_tarifs(
    conn: sqlite3.Connection, aboutement_fixe: float, aboutement_portable: float,
    sortant_fixe: float, sortant_portable: float,
) -> None:
    set_setting(conn, "tarif_aboutement_fixe", str(aboutement_fixe))
    set_setting(conn, "tarif_aboutement_portable", str(aboutement_portable))
    set_setting(conn, "tarif_sortant_fixe", str(sortant_fixe))
    set_setting(conn, "tarif_sortant_portable", str(sortant_portable))


def get_client_tarifs_override(conn: sqlite3.Connection, numero_appele: str) -> dict:
    """Tarifs personnalisés du client (valeurs à None si non personnalisées, càd tarif global utilisé)."""
    row = conn.execute(
        "SELECT tarif_aboutement_fixe, tarif_aboutement_portable, tarif_sortant_fixe, tarif_sortant_portable "
        "FROM clients WHERE numero_appele = ?",
        (numero_appele,),
    ).fetchone()
    if not row:
        return {"aboutement_fixe": None, "aboutement_portable": None, "sortant_fixe": None, "sortant_portable": None}
    return {
        "aboutement_fixe": row["tarif_aboutement_fixe"],
        "aboutement_portable": row["tarif_aboutement_portable"],
        "sortant_fixe": row["tarif_sortant_fixe"],
        "sortant_portable": row["tarif_sortant_portable"],
    }


def set_client_tarifs_override(
    conn: sqlite3.Connection, numero_appele: str,
    aboutement_fixe: Optional[float], aboutement_portable: Optional[float],
    sortant_fixe: Optional[float], sortant_portable: Optional[float],
) -> None:
    """Enregistre les tarifs personnalisés du client (None = utiliser le tarif global)."""
    conn.execute(
        "UPDATE clients SET tarif_aboutement_fixe = ?, tarif_aboutement_portable = ?, "
        "tarif_sortant_fixe = ?, tarif_sortant_portable = ? WHERE numero_appele = ?",
        (aboutement_fixe, aboutement_portable, sortant_fixe, sortant_portable, numero_appele),
    )


def get_effective_tarifs(conn: sqlite3.Connection, numero_appele: Optional[str]) -> dict:
    """Tarifs applicables au client (tarif personnalisé si défini, sinon tarif global)."""
    globaux = get_global_tarifs(conn)
    if not numero_appele:
        return globaux
    override = get_client_tarifs_override(conn, numero_appele)
    return {key: (override[key] if override[key] is not None else globaux[key]) for key in globaux}


# -- SMS (saisie manuelle) -----------------------------------------------------


def get_sms_manuels(conn: sqlite3.Connection, numero_appele: str, period_start_iso: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT sms_rappel, sms_contact FROM sms_manuels WHERE numero_appele = ? AND period_start = ?",
        (numero_appele, period_start_iso),
    ).fetchone()
    return (row["sms_rappel"], row["sms_contact"]) if row else (0, 0)


def set_sms_manuels(
    conn: sqlite3.Connection, numero_appele: str, period_start_iso: str, sms_rappel: int, sms_contact: int
) -> None:
    conn.execute(
        "INSERT INTO sms_manuels (numero_appele, period_start, sms_rappel, sms_contact) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(numero_appele, period_start) DO UPDATE SET "
        "sms_rappel = excluded.sms_rappel, sms_contact = excluded.sms_contact",
        (numero_appele, period_start_iso, sms_rappel, sms_contact),
    )
