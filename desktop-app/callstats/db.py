    """Insère un appel ; retourne False si déjà présent (dédoublonnage par call_id).

    Si l'appel existe déjà mais que son Tag diffère (ex: base créée avant l'ajout de
    cette colonne), le Tag est mis à jour rétroactivement lors d'un ré-import.
    """
    existing = conn.execute("SELECT tag FROM appels WHERE call_id = ?", (call_id,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO appels (call_id, numero_appele, numero_appelant, date_heure, comm_seconds, tag) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (call_id, numero_appele, numero_appelant, date_heure.isoformat(), comm_seconds, tag or None),
        )
        return True
    if (existing["tag"] or "") != (tag or ""):
        conn.execute("UPDATE appels SET tag = ? WHERE call_id = ?", (tag or None, call_id))
    return False
