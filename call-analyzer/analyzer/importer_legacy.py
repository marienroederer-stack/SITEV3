"""Import des anciens journaux d'appels (avant l'ajout du SDA aux exports, ex: 2023 et
antérieur) : colonnes Date, Heure, Numéro, Identifiant, Nom, Description, Sonnerie, Appel,
Comm, Tag.

Différences avec le format actuel (voir importer.py) :
 - pas de colonne Type : tous les appels de cet export sont considérés entrants (l'activité
   de télésecrétariat ne traite que des appels reçus, il n'y a pas d'appels sortants dans ce
   journal).
 - pas de SDA (Numéro Appelé) : le client n'est identifiable que par son nom ("Nom"), moins
   fiable que le SDA puisque les noms changent avec le temps. Résolution par nom exact (une
   fois accents/casse normalisés) contre le répertoire actuel, puis par la table de
   correspondances legacy_aliases.LEGACY_NAME_TO_SDA tenue à jour manuellement au fil des
   imports. Un nom qui ne correspond à rien de connu est un client résilié : ses appels sont
   quand même importés, rattachés à la fiche générique legacy_aliases.PLACEHOLDER_SDA (pas de
   perte de données, simplement pas d'attribution individuelle faute de SDA d'origine).
 - pas de Durée Totale / Annonce / File : l'attente moyenne globale et les ratios d'appels
   >3/4/5/6 min ne peuvent donc pas être calculés correctement pour cette période (les
   colonnes sources n'existent pas) — laissés à 0 plutôt qu'approximés, pour ne pas produire
   un chiffre plausible mais faux. L'attente sur sonnerie reste fiable (colonne Sonnerie
   présente), tout comme l'opérateur (colonne Identifiant), individualisé normalement.
"""

import hashlib
from pathlib import Path
from sqlite3 import Connection

from . import db
from .importer import (
    ImportResult,
    _iter_rows_csv,
    _iter_rows_xlsx,
    _normalize,
    parse_datetime,
    parse_duration_seconds,
)
from .legacy_aliases import LEGACY_NAME_TO_SDA, PLACEHOLDER_NOM, PLACEHOLDER_SDA

LEGACY_COLUMN_CANDIDATES = {
    "date": ["date"],
    "heure": ["heure"],
    "numero_appelant": ["numero"],
    "identifiant_appele": ["identifiant"],
    "nom_appele": ["nom"],
    "sonnerie": ["sonnerie"],
    "comm": ["comm"],
    "tag": ["tag"],
}
LEGACY_REQUIRED_FIELDS = ("heure", "nom_appele")


def _build_header_index(headers: list) -> dict:
    normalized = {_normalize(h): i for i, h in enumerate(headers) if h is not None}
    index = {}
    for field_name, candidates in LEGACY_COLUMN_CANDIDATES.items():
        for candidate in candidates:
            if candidate in normalized:
                index[field_name] = normalized[candidate]
                break
    return index


def import_legacy_file(conn: Connection, path: Path) -> ImportResult:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        row_iter = _iter_rows_xlsx(path)
    elif path.suffix.lower() == ".csv":
        row_iter = _iter_rows_csv(path)
    else:
        raise ValueError(f"Format de fichier non supporté : {path.suffix}")

    db.get_or_create_client(conn, PLACEHOLDER_SDA, PLACEHOLDER_NOM, "")

    known_client_names = {_normalize(c.nom): c.sda for c in db.list_clients(conn) if c.nom}
    alias_lookup = {_normalize(nom): sda for nom, sda in LEGACY_NAME_TO_SDA.items()}

    result = ImportResult()
    idx = None
    known_operators = {o.login for o in db.list_operators(conn)}
    import_id = None

    for headers, row in row_iter:
        if idx is None:
            idx = _build_header_index(headers)
            missing = [f for f in LEGACY_REQUIRED_FIELDS if f not in idx]
            if missing:
                raise ValueError(
                    "Colonnes manquantes dans le fichier (format ancien) : " + ", ".join(missing)
                )
            import_id = db.record_import(conn, path.name, result)

        result.total_rows += 1

        def cell(field_name):
            i = idx.get(field_name)
            return row[i] if i is not None and i < len(row) else None

        nom_appele = str(cell("nom_appele") or "").strip()
        if not nom_appele:
            result.invalid_rows += 1
            continue

        call_dt = parse_datetime(cell("heure"), date_fallback=cell("date"))
        if call_dt is None:
            result.invalid_rows += 1
            continue

        key = _normalize(nom_appele)
        sda = known_client_names.get(key) or alias_lookup.get(key)
        if sda is None:
            sda = PLACEHOLDER_SDA
            result.unresolved_names[nom_appele] = result.unresolved_names.get(nom_appele, 0) + 1

        operateur = str(cell("identifiant_appele") or "").strip()
        if operateur and operateur not in known_operators and not db.is_excluded_operator_login(operateur):
            _, op_created = db.get_or_create_operator(conn, operateur)
            if op_created:
                known_operators.add(operateur)
                result.new_operators.append(operateur)

        numero_appelant = str(cell("numero_appelant") or "").strip()
        raw = f"legacy|{sda}|{call_dt.isoformat()}|{numero_appelant}|{operateur}"
        call_id = hashlib.sha1(raw.encode("utf-8")).hexdigest()

        inserted = db.insert_call(
            conn,
            call_id=call_id,
            date_heure=call_dt.isoformat(),
            sda=sda,
            operateur=operateur,
            numero_appelant=numero_appelant,
            code_affaire_row="",
            tag=str(cell("tag") or "").strip(),
            priorite="",
            raison_rejet="",
            duree_totale_seconds=0,
            annonce_seconds=0,
            file_seconds=0,
            sonnerie_seconds=parse_duration_seconds(cell("sonnerie")),
            comm_seconds=parse_duration_seconds(cell("comm")),
            import_id=import_id,
        )
        if inserted:
            result.inserted += 1
        else:
            result.duplicates += 1

    if import_id is not None:
        conn.execute(
            "UPDATE imports SET rows_total = ?, rows_inserted = ?, rows_duplicates = ?, "
            "rows_filtered = ?, rows_invalid = ?, new_clients = ?, new_operators = ? WHERE id = ?",
            (
                result.total_rows,
                result.inserted,
                result.duplicates,
                result.filtered_out,
                result.invalid_rows,
                len(result.new_clients),
                len(result.new_operators),
                import_id,
            ),
        )
    conn.commit()
    return result
