"""Agrégation des statistiques d'appels sortants et aboutements pour une période donnée."""

from dataclasses import dataclass
from datetime import date, datetime
from sqlite3 import Connection
from typing import Optional

from . import db


@dataclass
class SortantsReportData:
    client: Optional[db.Client]
    period_start: date
    period_end: date
    aboutement_fixe: int
    aboutement_portable: int
    sortant_fixe: int
    sortant_portable: int
    tarifs: Optional[dict]  # None si "Tous les clients" (tarifs potentiellement différents par client)
    tarif_total: Optional[float]
    sms_rappel: int
    sms_contact: int


def build_sortants_report_data(
    conn: Connection, numero_appele: Optional[str], period_start: date, period_end: date
) -> SortantsReportData:
    client = db.get_client(conn, numero_appele) if numero_appele else None
    start_iso = datetime.combine(period_start, datetime.min.time()).isoformat()
    end_iso = datetime.combine(period_end, datetime.max.time()).isoformat()

    rows = db.sortants_for_client_range(conn, numero_appele, start_iso, end_iso)

    aboutement_fixe = sum(1 for r in rows if r["is_aboutement"] and r["aboutement_type"] == "fixe")
    aboutement_portable = sum(1 for r in rows if r["is_aboutement"] and r["aboutement_type"] == "portable")
    sortant_fixe = sum(1 for r in rows if r["is_sortant"] and r["sortant_type"] == "fixe")
    sortant_portable = sum(1 for r in rows if r["is_sortant"] and r["sortant_type"] == "portable")

    if numero_appele is not None:
        tarifs = db.get_effective_tarifs(conn, numero_appele)
        tarif_total = (
            aboutement_fixe * tarifs["aboutement_fixe"]
            + aboutement_portable * tarifs["aboutement_portable"]
            + sortant_fixe * tarifs["sortant_fixe"]
            + sortant_portable * tarifs["sortant_portable"]
        )
        sms_rappel, sms_contact = db.get_sms_manuels(conn, numero_appele, period_start.isoformat())
    else:
        # Pas de tarif global affiché pour "Tous les clients" : les tarifs peuvent différer d'un
        # client à l'autre, un montant unique mélangerait des taux différents et n'aurait pas de sens.
        tarifs = None
        tarif_total = None
        sms_rappel, sms_contact = 0, 0

    return SortantsReportData(
        client=client,
        period_start=period_start,
        period_end=period_end,
        aboutement_fixe=aboutement_fixe,
        aboutement_portable=aboutement_portable,
        sortant_fixe=sortant_fixe,
        sortant_portable=sortant_portable,
        tarifs=tarifs,
        tarif_total=tarif_total,
        sms_rappel=sms_rappel,
        sms_contact=sms_contact,
    )
