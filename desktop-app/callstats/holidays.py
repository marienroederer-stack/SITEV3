"""Jours fériés français (métropole), calculés pour n'importe quelle année."""

from datetime import date, timedelta


def _paques(year: int) -> date:
    """Dimanche de Pâques (algorithme de Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def jours_feries(year: int) -> set:
    paques = _paques(year)
    return {
        date(year, 1, 1): "Jour de l'an",
        paques + timedelta(days=1): "Lundi de Pâques",
        date(year, 5, 1): "Fête du travail",
        date(year, 5, 8): "Victoire 1945",
        paques + timedelta(days=39): "Ascension",
        paques + timedelta(days=50): "Lundi de Pentecôte",
        date(year, 7, 14): "Fête nationale",
        date(year, 8, 15): "Assomption",
        date(year, 11, 1): "Toussaint",
        date(year, 11, 11): "Armistice 1918",
        date(year, 12, 25): "Noël",
    }


def jour_ferie_label(d: date) -> str:
    """Nom du jour férié si `d` en est un, sinon chaîne vide."""
    return jours_feries(d.year).get(d, "")


def is_jour_ferie(d: date) -> bool:
    return bool(jour_ferie_label(d))
