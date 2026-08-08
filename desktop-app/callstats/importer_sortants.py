"""Import des appels sortants et aboutements depuis le même fichier journal que les entrants.

Règles de comptage (fixées avec le client) :
 - Sortants basiques : Type = sortant, comptabilisés vers fixe ou portable selon la racine du
   numéro appelé (06/07 = portable, tout le reste = fixe), pour une durée (Comm) de 5 secondes
   ou plus. Une "Tentative de transfert" en Description compte de la même façon (c'est un appel
   sortant normal).
 - Aboutements (appels transférés à un tiers pour être mis en relation avec un client) :
     - côté entrant : Description contient "Transfert accompagné vers:" ou "Transféré à:"
     - côté sortant : Description contient "Transféré au:", "Accompagné" ou "Transféré à:"
       (l'appel compte alors à la fois comme un sortant ET comme un aboutement)
   Le fixe/portable de l'aboutement est déterminé depuis le numéro/identifiant qui suit la
   mention dans la Description (un identifiant textuel ou un numéro à 4 chiffres est assimilé
   à du fixe).
 - Le client est identifié par sa SDA (colonne dédiée), qui est le même identifiant que le
   "Numéro appelé" utilisé pour les entrants.
 - Dédoublonnage entre imports successifs via "Call Id".
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Connection
from typing import Optional

from . import db
from .importer import (
    _build_header_index,
    _iter_rows_csv,
    _iter_rows_xlsx,
    _normalize,
    parse_datetime,
    parse_duration_seconds,
)

DUREE_MIN_SECONDES = 5

COLUMN_CANDIDATES = {
    "date": ["date"],
    "heure": ["heure"],
    "type": ["type"],
    "numero_appelant": ["numero appelant"],
    "numero_appele": ["numero appele"],
    "nom_appele": ["nom appele"],
    "nom": ["nom"],
    "sda": ["sda"],
    "description": ["description"],
    "comm": ["comm"],
    "call_id": ["call id", "callid"],
}

# Mentions déclenchant un aboutement, selon que la ligne est un appel entrant ou sortant.
MARQUEURS_ABOUTEMENT_ENTRANT = ("transfert accompagné vers", "transféré à")
MARQUEURS_ABOUTEMENT_SORTANT = ("transféré au", "accompagné", "transféré à")

# Capture la cible qui suit la mention (ex: "Transféré au: 2215, par: ..." -> "2215").
_CIBLE_RE = re.compile(
    r"(?:transfert\s+accompagn\w*\s+vers|transf[ée]r[ée]\s+(?:au|à))\s*:?\s*([^,]+?)(?:\s*,|\s+par\s*:|$)",
    re.IGNORECASE,
)

_MOBILE_RE = re.compile(r"^0[67]\d{8}$")

# Numéro (sans nom résolu) : sert à savoir si on doit se rabattre sur la colonne Nom pour le nom du client.
_NUMERO_BRUT_RE = re.compile(r"^0\d{8,9}$")


def classify_fixe_portable(value: Optional[str]) -> str:
    """« fixe » ou « portable » selon la racine d'un numéro ; tout ce qui n'est pas un numéro de
    mobile français standard (identifiant textuel, poste interne à 4 chiffres, numéro fixe...)
    est assimilé à du fixe."""
    if not value:
        return "fixe"
    cleaned = value.strip().replace(" ", "")
    return "portable" if _MOBILE_RE.match(cleaned) else "fixe"


def detect_aboutement(description: Optional[str], type_val: str) -> tuple[bool, Optional[str]]:
    """Détecte une mention d'aboutement dans la Description et sa cible éventuelle."""
    if not description:
        return False, None
    lower = description.lower()
    marqueurs = MARQUEURS_ABOUTEMENT_ENTRANT if type_val == "entrant" else MARQUEURS_ABOUTEMENT_SORTANT
    if not any(m in lower for m in marqueurs):
        return False, None
    match = _CIBLE_RE.search(description)
    cible = match.group(1).strip() if match else None
    return True, cible


def _candidate_nom(nom_appele_val: Optional[str], nom_val: Optional[str]) -> Optional[str]:
    """Devine un nom de client lisible à partir de « Nom Appelé » (I) ou, à défaut, du texte
    entre parenthèses de « Nom » (F). Ignore les candidats qui ne sont qu'un numéro brut."""
    def est_numero_brut(s: Optional[str]) -> bool:
        return bool(_NUMERO_BRUT_RE.match((s or "").strip()))

    if nom_appele_val and not est_numero_brut(nom_appele_val):
        return nom_appele_val.strip()
    if nom_val:
        m = re.search(r"\((.*?)(?:,|\))", nom_val)
        if m:
            candidat = m.group(1).strip()
            if candidat and not est_numero_brut(candidat):
                return candidat
    return None


@dataclass
class ImportSortantsResult:
    total_rows: int = 0
    inserted: int = 0
    duplicates: int = 0
    filtered_out: int = 0
    invalid_rows: int = 0
    new_clients: list = field(default_factory=list)


def import_file(conn: Connection, path: Path) -> ImportSortantsResult:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        row_iter = _iter_rows_xlsx(path)
    elif path.suffix.lower() == ".csv":
        row_iter = _iter_rows_csv(path)
    else:
        raise ValueError(f"Format de fichier non supporté : {path.suffix}")

    result = ImportSortantsResult()
    idx = None
    known_clients = {c.numero_appele for c in db.list_clients(conn)}

    for headers, row in row_iter:
        if idx is None:
            idx = _build_header_index(headers, COLUMN_CANDIDATES)
            missing = [f for f in ("heure", "type", "sda", "numero_appele", "comm", "description") if f not in idx]
            if missing:
                raise ValueError("Colonnes manquantes dans le fichier : " + ", ".join(missing))

        result.total_rows += 1

        def cell(field_name):
            i = idx.get(field_name)
            return row[i] if i is not None and i < len(row) else None

        type_val = _normalize(cell("type") or "")
        if type_val not in ("entrant", "sortant"):
            result.filtered_out += 1
            continue

        sda = str(cell("sda") or "").strip()
        if not sda:
            result.invalid_rows += 1
            continue

        comm_seconds = parse_duration_seconds(cell("comm"))
        description = cell("description")

        is_sortant = False
        sortant_type = None
        is_aboutement = False
        aboutement_type = None

        if type_val == "sortant" and comm_seconds >= DUREE_MIN_SECONDES:
            numero_appele_g = str(cell("numero_appele") or "").strip()
            sortant_type = classify_fixe_portable(numero_appele_g)
            is_sortant = True

        found, cible = detect_aboutement(description, type_val)
        if found:
            aboutement_type = classify_fixe_portable(cible)
            is_aboutement = True

        if not is_sortant and not is_aboutement:
            result.filtered_out += 1
            continue

        call_dt = parse_datetime(cell("heure"), date_fallback=cell("date"))
        if call_dt is None:
            result.invalid_rows += 1
            continue

        call_id = str(cell("call_id") or "").strip()
        if not call_id:
            raw = f"{sda}|{call_dt.isoformat()}|{cell('numero_appelant')}"
            call_id = hashlib.sha1(raw.encode("utf-8")).hexdigest()

        nom_candidat = _candidate_nom(
            str(cell("nom_appele") or "").strip() or None, str(cell("nom") or "").strip() or None
        )
        client = db.get_or_create_client(conn, sda, nom_candidat or sda)
        if sda not in known_clients:
            known_clients.add(sda)
            result.new_clients.append(client)

        inserted = db.insert_call_sortant(
            conn,
            call_id=call_id,
            numero_appele=sda,
            numero_appelant=str(cell("numero_appelant") or "").strip(),
            date_heure=call_dt,
            comm_seconds=comm_seconds,
            is_sortant=is_sortant,
            sortant_type=sortant_type,
            is_aboutement=is_aboutement,
            aboutement_type=aboutement_type,
        )
        if inserted:
            result.inserted += 1
        else:
            result.duplicates += 1

    conn.commit()
    return result
