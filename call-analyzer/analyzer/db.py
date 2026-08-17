"""Accès à la base SQLite locale : clients, opérateurs, appels, imports."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import seed_data
from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    sda            TEXT PRIMARY KEY,
    nom            TEXT NOT NULL DEFAULT '',
    code_affaire   TEXT NOT NULL DEFAULT '',
    auto_detected  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operators (
    login          TEXT PRIMARY KEY,
    poste          TEXT NOT NULL DEFAULT '',
    nom            TEXT NOT NULL DEFAULT '',
    auto_detected  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS imports (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    filename       TEXT NOT NULL,
    imported_at    TEXT NOT NULL,
    rows_total     INTEGER NOT NULL DEFAULT 0,
    rows_inserted  INTEGER NOT NULL DEFAULT 0,
    rows_duplicates INTEGER NOT NULL DEFAULT 0,
    rows_filtered  INTEGER NOT NULL DEFAULT 0,
    rows_invalid   INTEGER NOT NULL DEFAULT 0,
    new_clients    INTEGER NOT NULL DEFAULT 0,
    new_operators  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS calls (
    call_id              TEXT PRIMARY KEY,
    date_heure           TEXT NOT NULL,
    sda                  TEXT NOT NULL REFERENCES clients(sda),
    operateur            TEXT NOT NULL DEFAULT '',
    numero_appelant      TEXT,
    code_affaire_row     TEXT,
    tag                  TEXT,
    priorite             TEXT,
    raison_rejet         TEXT,
    duree_totale_seconds INTEGER NOT NULL DEFAULT 0,
    annonce_seconds      INTEGER NOT NULL DEFAULT 0,
    file_seconds         INTEGER NOT NULL DEFAULT 0,
    sonnerie_seconds     INTEGER NOT NULL DEFAULT 0,
    comm_seconds         INTEGER NOT NULL DEFAULT 0,
    import_id            INTEGER REFERENCES imports(id)
);
CREATE INDEX IF NOT EXISTS idx_calls_date ON calls(date_heure);
CREATE INDEX IF NOT EXISTS idx_calls_sda_date ON calls(sda, date_heure);
CREATE INDEX IF NOT EXISTS idx_calls_operateur_date ON calls(operateur, date_heure);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _seed_if_empty(conn)
    purge_excluded_operators(conn)
    return conn


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS n FROM clients").fetchone()["n"]
    if count == 0:
        now = _now_iso()
        conn.executemany(
            "INSERT INTO clients (sda, nom, code_affaire, auto_detected, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            [(sda, nom, code, now, now) for sda, nom, code in seed_data.SEED_CLIENTS],
        )
    count_op = conn.execute("SELECT COUNT(*) AS n FROM operators").fetchone()["n"]
    if count_op == 0:
        now = _now_iso()
        conn.executemany(
            "INSERT INTO operators (login, poste, nom, auto_detected, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            [(login, poste, nom, now, now) for login, poste, nom in seed_data.SEED_OPERATORS],
        )
    conn.commit()


# -- Clients --------------------------------------------------------------------


@dataclass
class Client:
    sda: str
    nom: str
    code_affaire: str
    auto_detected: bool

    @property
    def label(self) -> str:
        return self.nom if self.nom else self.sda


def _client_from_row(row: sqlite3.Row) -> Client:
    return Client(row["sda"], row["nom"], row["code_affaire"], bool(row["auto_detected"]))


def list_clients(conn: sqlite3.Connection) -> list[Client]:
    rows = conn.execute("SELECT * FROM clients ORDER BY (nom = ''), nom COLLATE NOCASE, sda").fetchall()
    return [_client_from_row(r) for r in rows]


def get_client(conn: sqlite3.Connection, sda: str) -> Optional[Client]:
    row = conn.execute("SELECT * FROM clients WHERE sda = ?", (sda,)).fetchone()
    return _client_from_row(row) if row else None


def get_or_create_client(conn: sqlite3.Connection, sda: str, nom: str, code_affaire: str) -> tuple[Client, bool]:
    """Retourne (client, created). Si le SDA existe déjà et que le fichier apporte un nom ou un
    code affaire différent (changement réel, pas juste une variation de casse/espaces), la fiche
    est mise à jour tout en conservant l'historique des appels (identifié par le SDA, pas par le
    nom)."""
    now = _now_iso()
    row = conn.execute("SELECT * FROM clients WHERE sda = ?", (sda,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO clients (sda, nom, code_affaire, auto_detected, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (sda, nom, code_affaire, now, now),
        )
        return Client(sda, nom, code_affaire, True), True

    client = _client_from_row(row)
    changed = False
    new_nom = client.nom
    new_code = client.code_affaire
    if nom and nom.strip().casefold() != (client.nom or "").strip().casefold():
        new_nom = nom
        changed = True
    elif not client.nom and nom:
        new_nom = nom
        changed = True
    if code_affaire and code_affaire.strip().casefold() != (client.code_affaire or "").strip().casefold():
        new_code = code_affaire
        changed = True
    elif not client.code_affaire and code_affaire:
        new_code = code_affaire
        changed = True
    if changed:
        conn.execute(
            "UPDATE clients SET nom = ?, code_affaire = ?, updated_at = ? WHERE sda = ?",
            (new_nom, new_code, now, sda),
        )
        client = Client(sda, new_nom, new_code, client.auto_detected)
    return client, False


def update_client(conn: sqlite3.Connection, sda: str, nom: str, code_affaire: str) -> None:
    conn.execute(
        "UPDATE clients SET nom = ?, code_affaire = ?, updated_at = ? WHERE sda = ?",
        (nom.strip(), code_affaire.strip(), _now_iso(), sda),
    )


def create_client(conn: sqlite3.Connection, sda: str, nom: str, code_affaire: str) -> None:
    now = _now_iso()
    conn.execute(
        "INSERT INTO clients (sda, nom, code_affaire, auto_detected, created_at, updated_at) "
        "VALUES (?, ?, ?, 0, ?, ?)",
        (sda.strip(), nom.strip(), code_affaire.strip(), now, now),
    )


def list_code_affaires(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT code_affaire FROM clients WHERE code_affaire != '' ORDER BY code_affaire COLLATE NOCASE"
    ).fetchall()
    return [r["code_affaire"] for r in rows]


# -- Opérateurs -------------------------------------------------------------------

# Préfixes de login exclus en permanence du répertoire opérateurs : ce sont des postes
# clients raccordés au standard téléphonique (ex: "2205"), pas de vrais opérateurs
# télésecrétaires. Les appels correspondants restent en base (comptés dans "Tous les
# opérateurs"), seule la fiche répertoire n'est jamais créée/affichée.
EXCLUDED_OPERATOR_LOGIN_PREFIXES = ("22",)


def is_excluded_operator_login(login: str) -> bool:
    return any(login.startswith(p) for p in EXCLUDED_OPERATOR_LOGIN_PREFIXES)


def purge_excluded_operators(conn: sqlite3.Connection) -> int:
    """Supprime du répertoire les opérateurs déjà enregistrés dont le login correspond à
    un préfixe exclu. Idempotent, appelé à chaque connexion pour que l'exclusion reste
    permanente même sur une base où ces fiches auraient été créées avant son ajout."""
    rows = conn.execute("SELECT login FROM operators").fetchall()
    to_delete = [r["login"] for r in rows if is_excluded_operator_login(r["login"])]
    for login in to_delete:
        conn.execute("DELETE FROM operators WHERE login = ?", (login,))
    if to_delete:
        conn.commit()
    return len(to_delete)


@dataclass
class Operator:
    login: str
    poste: str
    nom: str
    auto_detected: bool

    @property
    def label(self) -> str:
        return self.nom if self.nom else self.login


def _operator_from_row(row: sqlite3.Row) -> Operator:
    return Operator(row["login"], row["poste"], row["nom"], bool(row["auto_detected"]))


def list_operators(conn: sqlite3.Connection) -> list[Operator]:
    rows = conn.execute("SELECT * FROM operators ORDER BY (nom = ''), nom COLLATE NOCASE, login").fetchall()
    return [_operator_from_row(r) for r in rows if not is_excluded_operator_login(r["login"])]


def get_operator(conn: sqlite3.Connection, login: str) -> Optional[Operator]:
    row = conn.execute("SELECT * FROM operators WHERE login = ?", (login,)).fetchone()
    return _operator_from_row(row) if row else None


def get_or_create_operator(conn: sqlite3.Connection, login: str) -> tuple[Operator, bool]:
    row = conn.execute("SELECT * FROM operators WHERE login = ?", (login,)).fetchone()
    if row is not None:
        return _operator_from_row(row), False
    now = _now_iso()
    conn.execute(
        "INSERT INTO operators (login, poste, nom, auto_detected, created_at, updated_at) "
        "VALUES (?, '', '', 1, ?, ?)",
        (login, now, now),
    )
    return Operator(login, "", "", True), True


def update_operator(conn: sqlite3.Connection, login: str, poste: str, nom: str) -> None:
    conn.execute(
        "UPDATE operators SET poste = ?, nom = ?, updated_at = ? WHERE login = ?",
        (poste.strip(), nom.strip(), _now_iso(), login),
    )


def create_operator(conn: sqlite3.Connection, login: str, poste: str, nom: str) -> None:
    now = _now_iso()
    conn.execute(
        "INSERT INTO operators (login, poste, nom, auto_detected, created_at, updated_at) "
        "VALUES (?, ?, ?, 0, ?, ?)",
        (login.strip(), poste.strip(), nom.strip(), now, now),
    )


# -- Appels -----------------------------------------------------------------------


def insert_call(conn: sqlite3.Connection, **fields) -> bool:
    """Insère un appel ; retourne False si déjà présent (dédoublonnage par call_id)."""
    existing = conn.execute("SELECT 1 FROM calls WHERE call_id = ?", (fields["call_id"],)).fetchone()
    if existing is not None:
        return False
    conn.execute(
        "INSERT INTO calls (call_id, date_heure, sda, operateur, numero_appelant, code_affaire_row, "
        "tag, priorite, raison_rejet, duree_totale_seconds, annonce_seconds, file_seconds, "
        "sonnerie_seconds, comm_seconds, import_id) VALUES "
        "(:call_id, :date_heure, :sda, :operateur, :numero_appelant, :code_affaire_row, "
        ":tag, :priorite, :raison_rejet, :duree_totale_seconds, :annonce_seconds, :file_seconds, "
        ":sonnerie_seconds, :comm_seconds, :import_id)",
        fields,
    )
    return True


def calls_for_dimension(
    conn: sqlite3.Connection,
    dimension: str,
    value: Optional[str],
    start_iso: str,
    end_iso: str,
):
    """dimension: 'client' (value = sda), 'operateur' (value = login),
    'code_affaire' (value = code affaire) ou 'tous' (value ignoré)."""
    base = (
        "SELECT calls.* FROM calls JOIN clients ON clients.sda = calls.sda "
        "WHERE calls.date_heure >= ? AND calls.date_heure <= ?"
    )
    params: list = [start_iso, end_iso]
    if dimension == "client" and value:
        base += " AND calls.sda = ?"
        params.append(value)
    elif dimension == "operateur" and value is not None:
        base += " AND calls.operateur = ?"
        params.append(value)
    elif dimension == "code_affaire" and value is not None:
        base += " AND clients.code_affaire = ?"
        params.append(value)
    base += " ORDER BY calls.date_heure"
    return conn.execute(base, params).fetchall()


def months_with_calls(conn: sqlite3.Connection) -> list[str]:
    """Liste des mois (YYYY-MM) pour lesquels au moins un appel est enregistré, triés."""
    rows = conn.execute("SELECT DISTINCT substr(date_heure, 1, 7) AS ym FROM calls ORDER BY ym").fetchall()
    return [r["ym"] for r in rows]


def count_calls_before(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """Nombre d'appels dont la date est strictement antérieure à `cutoff_iso`."""
    return conn.execute("SELECT COUNT(*) AS n FROM calls WHERE date_heure < ?", (cutoff_iso,)).fetchone()["n"]


def purge_calls_before(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """Supprime définitivement les appels antérieurs à `cutoff_iso`. Les fiches clients et
    opérateurs ne sont pas touchées, et le journal des imports (imports) est conservé tel
    quel comme trace historique. Comme le dédoublonnage se fait par Call Id, réimporter par
    la suite un fichier couvrant la période purgée réinsère normalement les appels effacés
    (ce ne sont plus des doublons)."""
    cur = conn.execute("DELETE FROM calls WHERE date_heure < ?", (cutoff_iso,))
    conn.commit()
    return cur.rowcount


def call_count_for_client(conn: sqlite3.Connection, sda: str) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM calls WHERE sda = ?", (sda,)).fetchone()["n"]


def call_count_for_operator(conn: sqlite3.Connection, login: str) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM calls WHERE operateur = ?", (login,)).fetchone()["n"]


def last_call_date(conn: sqlite3.Connection, sda: str) -> Optional[str]:
    row = conn.execute(
        "SELECT MAX(date_heure) AS d FROM calls WHERE sda = ?", (sda,)
    ).fetchone()
    return row["d"] if row and row["d"] else None


# -- Imports ------------------------------------------------------------------------


def record_import(conn: sqlite3.Connection, filename: str, result) -> int:
    cur = conn.execute(
        "INSERT INTO imports (filename, imported_at, rows_total, rows_inserted, rows_duplicates, "
        "rows_filtered, rows_invalid, new_clients, new_operators) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            filename,
            _now_iso(),
            result.total_rows,
            result.inserted,
            result.duplicates,
            result.filtered_out,
            result.invalid_rows,
            len(result.new_clients),
            len(result.new_operators),
        ),
    )
    return cur.lastrowid


def list_imports(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM imports ORDER BY id DESC").fetchall()


# -- Réglages -------------------------------------------------------------------------


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
