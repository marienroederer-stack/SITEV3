"""Moteur d'analyse : périodes, grille créneaux/jours et indicateurs, pour n'importe
quelle dimension (client, opérateur, code affaire) et n'importe quelle granularité."""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from sqlite3 import Connection
from typing import Optional

from . import db

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
JOURS_ABBR = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]

# Horaires d'ouverture du standard : lundi-vendredi 8h-20h, samedi 8h-12h, dimanche fermé.
OUVERTURE_SEMAINE = (8, 20)
OUVERTURE_SAMEDI = (8, 12)

GRANULARITES = [15, 30, 60]
TYPES_PERIODE = ["jour", "semaine", "mois"]

# Seuils (en minutes) de durée d'appel (colonne "Comm" — durée de communication réelle,
# cohérent avec la durée moyenne de traitement) mis en avant dans le rapport.
SEUILS_MINUTES = [3, 4, 5, 6]

# Catégories de tag recherchées (sous-chaîne, insensible à la casse) pour le tableau de
# traitement des appels.
TAG_CATEGORIES = [
    ("Rendez-vous (RDV)", "RDV"),
    ("Annulation", "ANNUL"),
    ("Message", "MESS"),
    ("Confirmation (CONF)", "CONF"),
    ("Urgence/pro (PRO)", "PRO"),
]


def slots_for_weekday(weekday: int, granularity: int) -> list[tuple[int, int]]:
    """Créneaux (h, m) ouverts pour ce jour de semaine (0=lundi..6=dimanche), à la
    granularité demandée (minutes)."""
    if weekday == 6:
        return []
    start_h, end_h = OUVERTURE_SAMEDI if weekday == 5 else OUVERTURE_SEMAINE
    slots = []
    total_minutes = (end_h - start_h) * 60
    for offset in range(0, total_minutes, granularity):
        h = start_h + offset // 60
        m = offset % 60
        slots.append((h, m))
    return slots


def all_slots(granularity: int) -> list[tuple[int, int]]:
    """Union des créneaux lundi-vendredi (l'amplitude la plus large) — utilisée pour
    les lignes de la grille."""
    return slots_for_weekday(0, granularity)


def slot_label(h: int, m: int, granularity: int) -> str:
    end_minutes = h * 60 + m + granularity
    end_h, end_m = divmod(end_minutes, 60)
    return f"{h:02d}h{m:02d}-{end_h:02d}h{end_m:02d}"


def add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_period(period_type: str, ref: date, offset: int = 0) -> tuple[date, date]:
    """Période [début, fin] (bornes incluses) contenant `ref`, décalée de `offset` périodes."""
    if period_type == "jour":
        d = ref + timedelta(days=offset)
        return d, d
    if period_type == "semaine":
        monday = ref - timedelta(days=ref.weekday())
        monday += timedelta(weeks=offset)
        return monday, monday + timedelta(days=6)
    if period_type == "mois":
        start = date(ref.year, ref.month, 1)
        start = add_months(start, offset)
        end = add_months(start, 1) - timedelta(days=1)
        return start, end
    raise ValueError(f"Type de période inconnu : {period_type}")


@dataclass
class GridCell:
    count: int = 0
    comm_seconds: int = 0

    @property
    def avg_comm(self) -> float:
        return self.comm_seconds / self.count if self.count else 0.0


@dataclass
class TagCategoryStat:
    label: str
    count: int
    pct: float


@dataclass
class Summary:
    total_calls: int = 0
    avg_comm_seconds: float = 0.0
    avg_wait_global_seconds: float = 0.0
    avg_wait_sonnerie_seconds: float = 0.0
    ratios: dict = field(default_factory=dict)  # {minutes: pct}
    tag_rate_pct: float = 0.0
    tag_breakdown: list = field(default_factory=list)  # [TagCategoryStat, ...]


@dataclass
class ReportData:
    dimension: str
    value: Optional[str]
    label: str
    period_type: str
    period_start: date
    period_end: date
    granularity: int
    days: list
    grid: dict  # {(date, (h,m)): GridCell}
    day_totals: dict  # {date: GridCell}
    slot_totals: dict  # {(h,m): GridCell}
    grand_total: GridCell
    summary: Summary


def _label_for(conn: Connection, dimension: str, value: Optional[str]) -> str:
    if value is None:
        return {"client": "Tous les clients", "operateur": "Tous les opérateurs", "code_affaire": "Tous les codes affaire"}[
            dimension
        ]
    if dimension == "client":
        c = db.get_client(conn, value)
        return c.label if c else value
    if dimension == "operateur":
        if value == "":
            return "Non attribué"
        o = db.get_operator(conn, value)
        return o.label if o else value
    if dimension == "code_affaire":
        return value if value else "Non classé"
    return value or ""


def build_summary(rows) -> Summary:
    total = len(rows)
    sum_comm = 0
    sum_wait_global = 0
    sum_wait_sonnerie = 0
    over = {m: 0 for m in SEUILS_MINUTES}
    tagged = 0
    tag_raw_counts: dict = {}

    for row in rows:
        sum_comm += row["comm_seconds"]
        sum_wait_global += row["annonce_seconds"] + row["file_seconds"] + row["sonnerie_seconds"]
        sum_wait_sonnerie += row["sonnerie_seconds"]
        comm_duree = row["comm_seconds"]
        for m in SEUILS_MINUTES:
            if comm_duree > m * 60:
                over[m] += 1
        tag_value = (row["tag"] or "").strip()
        if tag_value:
            tagged += 1
            tag_raw_counts[tag_value] = tag_raw_counts.get(tag_value, 0) + 1

    summary = Summary()
    summary.total_calls = total
    summary.avg_comm_seconds = sum_comm / total if total else 0.0
    summary.avg_wait_global_seconds = sum_wait_global / total if total else 0.0
    summary.avg_wait_sonnerie_seconds = sum_wait_sonnerie / total if total else 0.0
    summary.ratios = {m: round(over[m] / total * 100, 1) if total else 0.0 for m in SEUILS_MINUTES}
    summary.tag_rate_pct = round(tagged / total * 100, 1) if total else 0.0

    breakdown = []
    for label, terme in TAG_CATEGORIES:
        count = sum(c for val, c in tag_raw_counts.items() if terme.upper() in val.upper())
        pct = round(count / total * 100, 1) if total else 0.0
        breakdown.append(TagCategoryStat(label=label, count=count, pct=pct))
    summary.tag_breakdown = breakdown
    return summary


def build_report_data(
    conn: Connection,
    dimension: str,
    value: Optional[str],
    period_type: str,
    period_start: date,
    period_end: date,
    granularity: int,
) -> ReportData:
    start_iso = datetime.combine(period_start, datetime.min.time()).isoformat()
    end_iso = datetime.combine(period_end, datetime.max.time()).isoformat()
    rows = db.calls_for_dimension(conn, dimension, value, start_iso, end_iso)

    days = []
    d = period_start
    while d <= period_end:
        days.append(d)
        d += timedelta(days=1)

    grid: dict = {}
    day_totals = {d: GridCell() for d in days}
    slot_totals: dict = {}
    grand_total = GridCell()

    for row in rows:
        dt = datetime.fromisoformat(row["date_heure"])
        call_date = dt.date()
        weekday = call_date.weekday()

        grand_total.count += 1
        grand_total.comm_seconds += row["comm_seconds"]

        day_cell = day_totals.setdefault(call_date, GridCell())
        day_cell.count += 1
        day_cell.comm_seconds += row["comm_seconds"]

        if weekday == 6:
            continue  # dimanche : hors périmètre d'ouverture

        valid_slots = set(slots_for_weekday(weekday, granularity))
        slot_minute = (dt.minute // granularity) * granularity
        slot = (dt.hour, slot_minute)
        if slot not in valid_slots:
            continue

        cell = grid.setdefault((call_date, slot), GridCell())
        cell.count += 1
        cell.comm_seconds += row["comm_seconds"]

        scell = slot_totals.setdefault(slot, GridCell())
        scell.count += 1
        scell.comm_seconds += row["comm_seconds"]

    summary = build_summary(rows)
    label = _label_for(conn, dimension, value)

    return ReportData(
        dimension=dimension,
        value=value,
        label=label,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        granularity=granularity,
        days=days,
        grid=grid,
        day_totals=day_totals,
        slot_totals=slot_totals,
        grand_total=grand_total,
        summary=summary,
    )


def build_summary_for_month(
    conn: Connection, dimension: str, value: Optional[str], year: int, month: int
) -> Summary:
    start = date(year, month, 1)
    end = add_months(start, 1) - timedelta(days=1)
    start_iso = datetime.combine(start, datetime.min.time()).isoformat()
    end_iso = datetime.combine(end, datetime.max.time()).isoformat()
    rows = db.calls_for_dimension(conn, dimension, value, start_iso, end_iso)
    return build_summary(rows)


def build_monthly_synthesis(
    conn: Connection, dimension: str, value: Optional[str]
) -> list[tuple[str, Summary]]:
    """Un résumé (Summary) par mois pour la dimension/valeur donnée, pour tous les mois où
    au moins un appel existe dans la base (toutes dimensions confondues) — un mois sans
    appel pour cette valeur précise apparaît avec des totaux à zéro plutôt que d'être
    omis, pour que la synthèse couvre toute la période importée sans trou."""
    return [
        (ym, build_summary_for_month(conn, dimension, value, *(int(x) for x in ym.split("-"))))
        for ym in db.months_with_calls(conn)
    ]


def _dimension_entries(conn: Connection, dimension: str) -> list[tuple[Optional[str], str]]:
    if dimension == "client":
        return [(c.sda, c.label) for c in db.list_clients(conn)]
    if dimension == "operateur":
        return [("", "Non attribué")] + [(o.login, o.label) for o in db.list_operators(conn)]
    if dimension == "code_affaire":
        return [(code, code) for code in db.list_code_affaires(conn)]
    raise ValueError(f"Dimension inconnue : {dimension}")


def build_dimension_breakdown(
    conn: Connection, dimension: str, period_start: date, period_end: date
) -> list[tuple[str, Summary]]:
    """Un résumé (Summary) par valeur de la dimension (chaque client/opérateur/code
    affaire), sur une période donnée — pour comparer toutes les valeurs entre elles sur la
    même période plutôt qu'une seule à la fois. Triée par nombre d'appels décroissant ; les
    valeurs sans aucun appel sur la période sont omises (elles seraient nombreuses et sans
    intérêt pour une comparaison)."""
    start_iso = datetime.combine(period_start, datetime.min.time()).isoformat()
    end_iso = datetime.combine(period_end, datetime.max.time()).isoformat()

    rows = []
    for value, label in _dimension_entries(conn, dimension):
        calls = db.calls_for_dimension(conn, dimension, value, start_iso, end_iso)
        summary = build_summary(calls)
        if summary.total_calls == 0:
            continue
        rows.append((label, summary))
    rows.sort(key=lambda r: r[1].total_calls, reverse=True)
    return rows
