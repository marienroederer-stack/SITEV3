"""Chiffrement local du mot de passe FTP/SFTP.

Protège contre une lecture accidentelle du fichier de base de données (ex: copie,
sauvegarde), mais la clé étant stockée sur le même poste, cela ne protège pas
contre un accès complet à la machine. C'est un compromis raisonnable pour un
outil interne mono-poste ; ne pas réutiliser ce mot de passe ailleurs.
"""

import os
import stat

from cryptography.fernet import Fernet

from .config import key_path


def _get_or_create_key() -> bytes:
    path = key_path()
    if path.exists():
        return path.read_bytes()
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return key


def encrypt(plain_text: str) -> str:
    if not plain_text:
        return ""
    fernet = Fernet(_get_or_create_key())
    return fernet.encrypt(plain_text.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    fernet = Fernet(_get_or_create_key())
    return fernet.decrypt(token.encode("ascii")).decode("utf-8")
