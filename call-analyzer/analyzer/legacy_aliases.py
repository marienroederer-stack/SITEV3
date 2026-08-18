"""Correspondances pour l'import des anciens journaux d'appels (voir importer_legacy.py) :
avant l'ajout du SDA aux exports, le seul moyen d'identifier le client est son nom, qui a pu
changer depuis (cabinets repris, associations différentes...). Ce fichier centralise les
correspondances nom -> SDA déjà vérifiées manuellement, complétées au fur et à mesure de
l'import de nouveaux anciens fichiers.

Un nom absent d'ici, et ne correspondant pas exactement (une fois accents/casse normalisés)
à un nom déjà en base, est considéré comme un client résilié : ses appels sont quand même
importés, mais rattachés à la fiche générique PLACEHOLDER_SDA plutôt qu'à un client précis
(aucune perte de données, mais pas d'attribution individuelle possible sans SDA d'origine).
"""

PLACEHOLDER_SDA = "0000000000"
PLACEHOLDER_NOM = "Anciens clients résiliés / non identifiés (import sans SDA)"

# Format : "nom tel qu'il apparaît dans l'ancien fichier" -> SDA actuel du client.
# Comparaison faite après normalisation (accents/casse/espaces), donc la casse exacte
# ci-dessous n'a pas d'importance.
LEGACY_NAME_TO_SDA = {
    "POUZADOUX & SALABERT": "0973030986",
    "MAITRE & RAMBAUD": "0973014152",
    "BUDILLON & RIDAO": "0973030971",
    "ROUSSEAUX-DURY et MONNET-ROIRON": "0973030977",
    "Cabinet médical des Drs JANOTS et ALEGRE": "0973030941",
    "Cabinet TAUTOU-BONDUELLE-THOURET": "0973030967",
    "Drs ROCHE et RABILLER": "0973030930",
    "LAFON et CHAMBON": "0973030998",
    "O. DAVID et PATOOR": "0973030999",
    "PENY & VAURE": "0973030959",
    "SLAMANI & OLIVIER": "0973030972",
    "Cabinet de pédiatrie CHARDON & HOURIEZ": "0973030970",
    "Cabinet d ostéopathie de Pérouges": "0973030932",
    "GENESTE & MERAL": "0973030918",
    "Cab. de S-F de Mmes LAFAGE-GOFFIN et GILIBERT": "0973030931",
    "Cabinet d acupuncture Dr MONFOURNY": "0973030911",
    "Cabinet d ostéopathie de Corbas": "0973030960",
}
