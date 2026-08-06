"""Calcul des périodes de cycle client et agrégation des statistiques d'appel."""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from sqlite3 import Connection
from typing import Optional

from . import db

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]  # 0..5, dimanche exclu

# Bornes d'ouverture : lundi-vendredi 8h-20h (créneaux de 30 min), samedi 8h-12h.
SLOTS_SEMAINE = [(h, m) for h in range(8, 20) for m in (0, 30)]  # 24 créneaux, 8h00 -> 19h30
SLOTS_SAMEDI = [(h, m) for h in range(8, 12) for m in (0, 30)]   # 8 créneaux, 8h00 -> 11h30

TRANCHES = [
    ("8h-12h", 8, 12),
    ("12h-14h", 12, 14),
    ("14h-18h", 14, 18),
    ("18h-20h", 18, 20),
]


def add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _period_start_for(cycle_start_day: int, ref: date) -> date:
    days_in_month = calendar.monthrange(ref.year, ref.month)[1]
    day = min(cycle_start_day, days_in_month)
    candidate = date(ref.year, ref.month, day)
    if ref >= candidate:
        return candidate
    return add_months(candidate, -1)


def get_period(cycle_start_day: int, ref: date, offset: int = 0) -> tuple[date, date]:
    """Période [début, fin] (bornes incluses) contenant `ref`, décalée de `offset` cycles."""
    start = _period_start_for(cycle_start_day, ref)
    if offset:
        start = add_months(start, offset)
    end = add_months(start, 1) - timedelta(days=1)
    return start, end


@dataclass
class GridCell:
    count: int = 0
    total_seconds: int = 0

    @property
    def avg_seconds(self) -> float:
        return self.total_seconds / self.count if self.count else 0.0


@dataclass
class ReportData:
    client: Optional[db.Client]
    period_start: date
    period_end: date
    grid: dict  # {(weekday, (h,m)): GridCell}
    recap: dict  # {(weekday, tranche_label): int}
    total_calls: int
    total_seconds: int


def build_report_data(
    conn: Connection, numero_appele: Optional[str], period_start: date, period_end: date
) -> ReportData:
    client = db.get_client(conn, numero_appele) if numero_appele else None
    start_iso = datetime.combine(period_start, datetime.min.time()).isoformat()
    end_iso = datetime.combine(period_end, datetime.max.time()).isoformat()
    rows = db.calls_for_client_range(conn, numero_appele, start_iso, end_iso)

    grid: dict = {}
    recap: dict = {}
    total_calls = 0
    total_seconds = 0

    for row in rows:
        dt = datetime.fromisoformat(row["date_heure"])
        weekday = dt.weekday()  # 0=lundi ... 6=dimanche
        if weekday > 5:
            continue  # dimanche : hors périmètre (pas de permanence)

        seconds = row["comm_seconds"]
        total_calls += 1
        total_seconds += seconds

        slot_minute = (dt.minute // 30) * 30
        slot = (dt.hour, slot_minute)
        valid_slots = SLOTS_SAMEDI if weekday == 5 else SLOTS_SEMAINE
        if slot in valid_slots:
            key = (weekday, slot)
            cell = grid.setdefault(key, GridCell())
            cell.count += 1
            cell.total_seconds += seconds

        for label, start_h, end_h in TRANCHES:
            if start_h <= dt.hour < end_h:
                rkey = (weekday, label)
                recap[rkey] = recap.get(rkey, 0) + 1
                break

    return ReportData(
        client=client,
        period_start=period_start,
        period_end=period_end,
        grid=grid,
        recap=recap,
        total_calls=total_calls,
        total_seconds=total_seconds,
    )
