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
    comm_seconds    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appels_client_date ON appels(numero_appele, date_heure);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes introduites après la création initiale des bases existantes."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(clients)")}
    if "display_name" not in columns:
        conn.execute("ALTER TABLE clients ADD COLUMN display_name TEXT")
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
) -> bool:
    """Insère un appel ; retourne False si déjà présent (dédoublonnage par call_id)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO appels (call_id, numero_appele, numero_appelant, date_heure, comm_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (call_id, numero_appele, numero_appelant, date_heure.isoformat(), comm_seconds),
    )
    return cur.rowcount > 0


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
