

def error_log_path() -> Path:
    return app_data_dir() / "erreurs.log"


def log_error(context: str, detail: str) -> None:
    """Ajoute une entrée horodatée au journal d'erreurs local (aide au diagnostic)."""
    import datetime as _datetime

    try:
        with open(error_log_path(), "a", encoding="utf-8") as f:
            f.write(f"[{_datetime.datetime.now().isoformat(timespec='seconds')}] {context}\n{detail}\n\n")
    except OSError:
        pass
