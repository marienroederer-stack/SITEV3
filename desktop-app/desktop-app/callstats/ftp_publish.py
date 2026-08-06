"""Publication du rapport HTML sur l'hébergeur du site (FTP ou SFTP)."""

import ftplib
import io
from dataclasses import dataclass


@dataclass
class PublishConfig:
    protocol: str  # "ftp" ou "sftp"
    host: str
    port: int
    username: str
    password: str
    remote_dir: str  # ex: "/rapports"
    base_url: str  # ex: "https://doctel.fr/rapports"


def publish(config: PublishConfig, slug: str, html_content: str) -> str:
    """Envoie le rapport sur le serveur et retourne l'URL publique."""
    remote_dir = config.remote_dir.rstrip("/") or "/"
    filename = f"{slug}.html"
    remote_path = f"{remote_dir}/{filename}"
    data = html_content.encode("utf-8")

    if config.protocol == "sftp":
        _publish_sftp(config, remote_dir, remote_path, data)
    elif config.protocol == "ftp":
        _publish_ftp(config, remote_dir, remote_path, data)
    else:
        raise ValueError(f"Protocole inconnu : {config.protocol}")

    base = config.base_url.rstrip("/")
    return f"{base}/{filename}"


def _publish_ftp(config: PublishConfig, remote_dir: str, remote_path: str, data: bytes) -> None:
    with ftplib.FTP() as ftp:
        ftp.connect(config.host, config.port or 21, timeout=30)
        ftp.login(config.username, config.password)
        _ensure_ftp_dir(ftp, remote_dir)
        ftp.storbinary(f"STOR {remote_path}", io.BytesIO(data))


def _ensure_ftp_dir(ftp: ftplib.FTP, remote_dir: str) -> None:
    parts = [p for p in remote_dir.split("/") if p]
    path = ""
    for part in parts:
        path += "/" + part
        try:
            ftp.mkd(path)
        except ftplib.error_perm:
            pass  # le dossier existe déjà


def _publish_sftp(config: PublishConfig, remote_dir: str, remote_path: str, data: bytes) -> None:
    import paramiko

    transport = paramiko.Transport((config.host, config.port or 22))
    try:
        transport.connect(username=config.username, password=config.password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            _ensure_sftp_dir(sftp, remote_dir)
            with sftp.open(remote_path, "wb") as f:
                f.write(data)
        finally:
            sftp.close()
    finally:
        transport.close()


def _ensure_sftp_dir(sftp, remote_dir: str) -> None:
    parts = [p for p in remote_dir.split("/") if p]
    path = ""
    for part in parts:
        path += "/" + part
        try:
            sftp.stat(path)
        except FileNotFoundError:
            sftp.mkdir(path)
