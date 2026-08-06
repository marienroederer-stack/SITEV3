"""Archivage (export CSV) et purge des appels par mois civil."""

import calendar
import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS archive_months (
    year_month  TEXT PRIMARY KEY,  -- format 'YYYY-MM'
    exported_at TEXT,
    purged_at   TEXT
);
"""


def ensure_schema(conn: Connection) -> None:
    conn.executescript(SCHEMA)


def month_bounds(year_month: str) -> tuple[date, date]:
    year, month = (int(p) for p in year_month.split("-"))
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def month_label(year_month: str) -> str:
    mois = [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ]
    year, month = (int(p) for p in year_month.split("-"))
    return f"{mois[month - 1].capitalize()} {year}"


@dataclass
class MonthStatus:
    year_month: str
    call_count: int
    exported_at: Optional[str]
    purged_at: Optional[str]


def list_months(conn: Connection) -> list[MonthStatus]:
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT strftime('%Y-%m', date_heure) AS ym, COUNT(*) AS n "
        "FROM appels GROUP BY ym ORDER BY ym DESC"
    ).fetchall()
    statuses = []
    for row in rows:
        arch = conn.execute(
            "SELECT exported_at, purged_at FROM archive_months WHERE year_month = ?", (row["ym"],)
        ).fetchone()
        statuses.append(
            MonthStatus(
                year_month=row["ym"],
                call_count=row["n"],
                exported_at=arch["exported_at"] if arch else None,
                purged_at=arch["purged_at"] if arch else None,
            )
        )
    return statuses


def export_csv(conn: Connection, year_month: str, path: Path) -> int:
    """Exporte les appels du mois en CSV et marque le mois comme archivé. Retourne le nombre de lignes."""
    ensure_schema(conn)
    start, end = month_bounds(year_month)
    start_iso = datetime.combine(start, datetime.min.time()).isoformat()
    end_iso = datetime.combine(end, datetime.max.time()).isoformat()

    rows = conn.execute(
        "SELECT a.date_heure, a.numero_appelant, a.numero_appele, c.nom_appele, c.display_name, "
        "a.comm_seconds, a.call_id "
        "FROM appels a JOIN clients c ON c.numero_appele = a.numero_appele "
        "WHERE a.date_heure >= ? AND a.date_heure <= ? ORDER BY a.date_heure",
        (start_iso, end_iso),
    ).fetchall()

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            ["Date", "Heure", "Numéro Appelant", "Numéro Appelé", "Nom (fichier)", "Nom affiché",
             "Durée (secondes)", "Call Id"]
        )
        for row in rows:
            dt = datetime.fromisoformat(row["date_heure"])
            writer.writerow(
                [
                    dt.strftime("%d/%m/%Y"),
                    dt.strftime("%H:%M:%S"),
                    row["numero_appelant"],
                    row["numero_appele"],
                    row["nom_appele"],
                    row["display_name"] or "",
                    row["comm_seconds"],
                    row["call_id"],
                ]
            )

    conn.execute(
        "INSERT INTO archive_months (year_month, exported_at) VALUES (?, ?) "
        "ON CONFLICT(year_month) DO UPDATE SET exported_at = excluded.exported_at",
        (year_month, datetime.now().isoformat()),
    )
    conn.commit()
    return len(rows)


def list_purgeable(conn: Connection) -> list[str]:
    """Mois archivés (exportés) mais pas encore purgés."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT year_month FROM archive_months WHERE exported_at IS NOT NULL AND purged_at IS NULL "
        "ORDER BY year_month"
    ).fetchall()
    return [r["year_month"] for r in rows]


@dataclass
class PurgeResult:
    months: list
    rows_deleted: int


def purge_archived(conn: Connection) -> PurgeResult:
    """Supprime les appels de tous les mois archivés non encore purgés."""
    months = list_purgeable(conn)
    rows_deleted = 0
    for year_month in months:
        start, end = month_bounds(year_month)
        start_iso = datetime.combine(start, datetime.min.time()).isoformat()
        end_iso = datetime.combine(end, datetime.max.time()).isoformat()
        cur = conn.execute(
            "DELETE FROM appels WHERE date_heure >= ? AND date_heure <= ?", (start_iso, end_iso)
        )
        rows_deleted += cur.rowcount
        conn.execute(
            "UPDATE archive_months SET purged_at = ? WHERE year_month = ?",
            (datetime.now().isoformat(), year_month),
        )
    conn.commit()
    return PurgeResult(months=months, rows_deleted=rows_deleted)
