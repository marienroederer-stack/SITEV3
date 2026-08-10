"""Notification de l'espace client web après publication d'un rapport.

Appelle l'API espace-client/api/update.php pour que le tableau de statistiques
du client se mette à jour automatiquement (nombre d'appels, lien vers le rapport),
sans ressaisie manuelle.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class WebApiConfig:
    api_url: str  # ex: https://doctel.fr/espace-client/api/update.php
    api_key: str


def notify(config: WebApiConfig, slug: str, annee: int, mois: int, type_: str, url: str, nb_appels: int | None = None) -> None:
    """Envoie la mise à jour à l'espace client. Lève une exception en cas d'échec."""
    payload = {"slug": slug, "annee": annee, "mois": mois, "type": type_, "url": url}
    if nb_appels is not None:
        payload["nb_appels"] = nb_appels

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        config.api_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": config.api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"L'espace client a refusé la mise à jour ({exc.code}) : {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Impossible de joindre l'espace client : {exc.reason}") from exc
