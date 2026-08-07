"""Calcul des périodes de cycle client et agrégation des statistiques d'appel."""

import calendar
import math
from dataclasses import dataclass, field
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

# Seuils de durée de communication mis en avant dans le rapport (fixes, comme l'export actuel).
SEUIL_1_SECONDES = 3 * 60
SEUIL_2_SECONDES = 6 * 60

# Catégories de tags recherchées (sous-chaîne, insensible à la casse) pour le tableau
# "Traitement des appels" : libellé affiché -> terme recherché dans la colonne Tag.
TAG_CATEGORIES = [
    ("Attribution/report de RDV", "RDV"),
    ("Annulation de RDV", "ANNUL"),
    ("Envoi de message", "MESS"),
]

# Marge d'erreur appliquée aux comptages de tags (pointage manuel) : +5 %, arrondi à l'inférieur.
MARGE_ERREUR_TAG = 0.05

# Clients avec une ligne partagée entre plusieurs médecins, distingués par leur nom dans le tag
# (ex: "RDV BUDILLON"). Le premier nom de chaque groupe absorbe l'écart d'arrondi lors de la
# réconciliation avec le total RDV du client. Détection automatique : un client n'affiche la
# subdivision que si des tags contenant ces noms sont présents dans son historique.
SUBDIVISION_GROUPS = [
    ["MAITRE", "RAMBAUD", "BRETONNET"],
    ["BENAS", "BAGOT", "CHABAUD"],
    ["BUDILLON", "RIDAO", "DEMURE"],
]


def _adjust(count: int) -> int:
    """Applique la marge d'erreur de +5 % et arrondit à l'inférieur."""
    return math.floor(count * (1 + MARGE_ERREUR_TAG))


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
class TagCategoryStat:
    label: str
    count: int  # comptage ajusté (+5 %, arrondi à l'inférieur)
    pct: float  # pourcentage sur le total d'appels du mois (1 décimale)


@dataclass
class SubdivisionStat:
    names: list  # les 3 noms du groupe, dans l'ordre (le 1er absorbe l'écart d'arrondi)
    counts: list  # comptages ajustés, dont la somme == count RDV du client
    pcts: list  # pourcentages sur le total RDV du client, dont la somme == 100.0


@dataclass
class ReportData:
    client: Optional[db.Client]
    period_start: date
    period_end: date
    days: list  # toutes les dates civiles de la période, dans l'ordre
    day_grid: dict  # {(date, (h,m)): GridCell} — détail jour par jour
    day_totals: dict  # {date: GridCell} — total de la journée (toutes tranches)
    slot_totals: dict  # {(h,m): GridCell} — total du créneau sur toute la période
    weekday_recap: dict  # {(weekday, tranche_label): GridCell}
    weekday_totals: dict  # {weekday: GridCell}
    weekday_days_with_calls: dict  # {weekday: int}
    moyenne_hors_samedi: float
    count_over_seuil1: int
    count_over_seuil2: int
    total_calls: int
    total_seconds: int
    traitement: list  # [TagCategoryStat, ...] dans l'ordre de TAG_CATEGORIES
    subdivision: Optional[SubdivisionStat]


def build_report_data(
    conn: Connection, numero_appele: Optional[str], period_start: date, period_end: date
) -> ReportData:
    client = db.get_client(conn, numero_appele) if numero_appele else None
    start_iso = datetime.combine(period_start, datetime.min.time()).isoformat()
    end_iso = datetime.combine(period_end, datetime.max.time()).isoformat()
    rows = db.calls_for_client_range(conn, numero_appele, start_iso, end_iso)

    days = []
    d = period_start
    while d <= period_end:
        days.append(d)
        d += timedelta(days=1)

    day_grid: dict = {}
    day_totals = {d: GridCell() for d in days}
    slot_totals: dict = {}
    weekday_recap: dict = {}
    weekday_totals: dict = {}
    total_calls = 0
    total_seconds = 0
    count_over_seuil1 = 0
    count_over_seuil2 = 0
    tag_raw_counts = {label: 0 for label, _ in TAG_CATEGORIES}
    subdivision_raw_counts: dict = {}  # nom -> comptage brut

    for row in rows:
        dt = datetime.fromisoformat(row["date_heure"])
        weekday = dt.weekday()  # 0=lundi ... 6=dimanche
        if weekday > 5:
            continue  # dimanche : hors périmètre (pas de permanence)

        seconds = row["comm_seconds"]
        call_date = dt.date()

        total_calls += 1
        total_seconds += seconds
        if seconds > SEUIL_1_SECONDES:
            count_over_seuil1 += 1
        if seconds > SEUIL_2_SECONDES:
            count_over_seuil2 += 1

        tag_value = (row["tag"] or "").upper()
        if tag_value:
            for label, terme in TAG_CATEGORIES:
                if terme in tag_value:
                    tag_raw_counts[label] += 1
            for groupe in SUBDIVISION_GROUPS:
                for nom in groupe:
                    if nom in tag_value:
                        subdivision_raw_counts[nom] = subdivision_raw_counts.get(nom, 0) + 1

        day_cell = day_totals.setdefault(call_date, GridCell())
        day_cell.count += 1
        day_cell.total_seconds += seconds

        slot_minute = (dt.minute // 30) * 30
        slot = (dt.hour, slot_minute)
        valid_slots = SLOTS_SAMEDI if weekday == 5 else SLOTS_SEMAINE
        if slot in valid_slots:
            cell = day_grid.setdefault((call_date, slot), GridCell())
            cell.count += 1
            cell.total_seconds += seconds

            scell = slot_totals.setdefault(slot, GridCell())
            scell.count += 1
            scell.total_seconds += seconds

        for label, start_h, end_h in TRANCHES:
            if start_h <= dt.hour < end_h:
                rcell = weekday_recap.setdefault((weekday, label), GridCell())
                rcell.count += 1
                rcell.total_seconds += seconds

                wcell = weekday_totals.setdefault(weekday, GridCell())
                wcell.count += 1
                wcell.total_seconds += seconds
                break

    weekday_days_with_calls = {w: 0 for w in range(6)}
    for d in days:
        if d.weekday() > 5:
            continue
        if day_totals.get(d, GridCell()).count > 0:
            weekday_days_with_calls[d.weekday()] += 1

    total_days_lunven = sum(weekday_days_with_calls[w] for w in range(5))
    total_calls_lunven = sum(weekday_totals.get(w, GridCell()).count for w in range(5))
    moyenne_hors_samedi = total_calls_lunven / total_days_lunven if total_days_lunven else 0.0

    traitement = []
    for label, _ in TAG_CATEGORIES:
        count = _adjust(tag_raw_counts[label])
        pct = round(count / total_calls * 100, 1) if total_calls else 0.0
        traitement.append(TagCategoryStat(label=label, count=count, pct=pct))
    total_rdv = traitement[0].count  # "Attribution/report de RDV" est toujours la 1ère catégorie

    subdivision = None
    if numero_appele is not None:
        for groupe in SUBDIVISION_GROUPS:
            if sum(subdivision_raw_counts.get(nom, 0) for nom in groupe) == 0:
                continue
            counts = [_adjust(subdivision_raw_counts.get(nom, 0)) for nom in groupe]
            # Le 1er nom du groupe absorbe l'écart d'arrondi pour que la somme == total RDV.
            counts[0] = total_rdv - counts[1] - counts[2]
            if total_rdv:
                pct2 = round(counts[1] / total_rdv * 100, 1)
                pct3 = round(counts[2] / total_rdv * 100, 1)
                pct1 = round(100.0 - pct2 - pct3, 1)
            else:
                pct1 = pct2 = pct3 = 0.0
            subdivision = SubdivisionStat(names=list(groupe), counts=counts, pcts=[pct1, pct2, pct3])
            break

    return ReportData(
        client=client,
        period_start=period_start,
        period_end=period_end,
        days=days,
        day_grid=day_grid,
        day_totals=day_totals,
        slot_totals=slot_totals,
        weekday_recap=weekday_recap,
        weekday_totals=weekday_totals,
        weekday_days_with_calls=weekday_days_with_calls,
        moyenne_hors_samedi=moyenne_hors_samedi,
        count_over_seuil1=count_over_seuil1,
        count_over_seuil2=count_over_seuil2,
        total_calls=total_calls,
        total_seconds=total_seconds,
        traitement=traitement,
        subdivision=subdivision,
    )
