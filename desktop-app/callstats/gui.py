"""Interface graphique de l'application (PySide6)."""

import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QMarginsF, Qt, QTimer
from PySide6.QtGui import QIcon, QPageLayout, QPageSize
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from . import db, ftp_publish, importer, report, stats
from .config import resource_path
from .db import Client

APP_TITLE = "DOCTEL - analyse appels entrants"


class ClientsSettingsTab(QWidget):
    def __init__(self, conn, on_saved):
        super().__init__()
        self.conn = conn
        self.on_saved = on_saved

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Le \"Nom (fichier import)\" vient du listing d'appels et n'est pas modifiable ici (il sert à "
            "retrouver le client lors des imports). Le \"Nom affiché\" est optionnel : renseignez-le pour "
            "remplacer ce nom dans l'application et les rapports (ex : \"Dr BERTRAND-JARROUSSE Véronique\" "
            "pour un client nommé \"BERTRAND\" dans le fichier). Le jour de cycle est fixe : 1 = mois civil."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Nom (fichier import)", "Nom affiché", "Numéro appelé", "Identifiant (slug)", "Jour de cycle"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)

        save_btn = QPushButton("Enregistrer les modifications")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self._reload()

    def _reload(self):
        clients = db.list_clients(self.conn)
        self.table.setRowCount(len(clients))
        for row, c in enumerate(clients):
            nom_item = QTableWidgetItem(c.nom_appele)
            nom_item.setFlags(nom_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, nom_item)
            self.table.setItem(row, 1, QTableWidgetItem(c.display_name or ""))
            numero_item = QTableWidgetItem(c.numero_appele)
            numero_item.setFlags(numero_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, numero_item)
            self.table.setItem(row, 3, QTableWidgetItem(c.slug))
            spin = QSpinBox()
            spin.setRange(1, 31)
            spin.setValue(c.cycle_start_day)
            self.table.setCellWidget(row, 4, spin)

    def _save(self):
        for row in range(self.table.rowCount()):
            numero = self.table.item(row, 2).text()
            display_name = self.table.item(row, 1).text().strip()
            slug = self.table.item(row, 3).text().strip() or db.slugify(self.table.item(row, 0).text())
            spin: QSpinBox = self.table.cellWidget(row, 4)
            db.update_client(self.conn, numero, slug, spin.value(), display_name)
        self.conn.commit()
        self.on_saved()
        QMessageBox.information(self, APP_TITLE, "Réglages clients enregistrés.")


class PublishSettingsTab(QWidget):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn

        form = QFormLayout(self)

        self.protocol = QComboBox()
        self.protocol.addItems(["ftp", "sftp"])
        form.addRow("Protocole", self.protocol)

        self.host = QLineEdit()
        form.addRow("Serveur (hôte)", self.host)

        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(21)
        form.addRow("Port", self.port)

        self.username = QLineEdit()
        form.addRow("Identifiant", self.username)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        form.addRow("Mot de passe", self.password)

        self.remote_dir = QLineEdit("/rapports")
        form.addRow("Dossier distant", self.remote_dir)

        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://doctel.fr/rapports")
        form.addRow("URL publique de base", self.base_url)

        save_btn = QPushButton("Enregistrer les identifiants de publication")
        save_btn.clicked.connect(self._save)
        form.addRow(save_btn)

        self._load()

    def _load(self):
        from . import crypto_store

        c = self.conn
        self.protocol.setCurrentText(db.get_setting(c, "ftp_protocol", "ftp"))
        self.host.setText(db.get_setting(c, "ftp_host"))
        self.port.setValue(int(db.get_setting(c, "ftp_port", "21") or 21))
        self.username.setText(db.get_setting(c, "ftp_username"))
        encrypted = db.get_setting(c, "ftp_password")
        if encrypted:
            try:
                self.password.setText(crypto_store.decrypt(encrypted))
            except Exception:
                pass
        self.remote_dir.setText(db.get_setting(c, "ftp_remote_dir", "/rapports"))
        self.base_url.setText(db.get_setting(c, "ftp_base_url"))

    def _save(self):
        from . import crypto_store

        c = self.conn
        db.set_setting(c, "ftp_protocol", self.protocol.currentText())
        db.set_setting(c, "ftp_host", self.host.text().strip())
        db.set_setting(c, "ftp_port", str(self.port.value()))
        db.set_setting(c, "ftp_username", self.username.text().strip())
        db.set_setting(c, "ftp_password", crypto_store.encrypt(self.password.text()))
        db.set_setting(c, "ftp_remote_dir", self.remote_dir.text().strip() or "/rapports")
        db.set_setting(c, "ftp_base_url", self.base_url.text().strip())
        c.commit()
        QMessageBox.information(self, APP_TITLE, "Identifiants de publication enregistrés.")

    def get_config(self) -> ftp_publish.PublishConfig:
        return ftp_publish.PublishConfig(
            protocol=db.get_setting(self.conn, "ftp_protocol", "ftp"),
            host=db.get_setting(self.conn, "ftp_host"),
            port=int(db.get_setting(self.conn, "ftp_port", "21") or 21),
            username=db.get_setting(self.conn, "ftp_username"),
            password=self._decrypted_password(),
            remote_dir=db.get_setting(self.conn, "ftp_remote_dir", "/rapports"),
            base_url=db.get_setting(self.conn, "ftp_base_url"),
        )

    def _decrypted_password(self) -> str:
        from . import crypto_store

        encrypted = db.get_setting(self.conn, "ftp_password")
        return crypto_store.decrypt(encrypted) if encrypted else ""


class ArchiveSettingsTab(QWidget):
    def __init__(self, conn, on_purged):
        super().__init__()
        self.conn = conn
        self.on_purged = on_purged

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Exportez un mois civil en CSV pour vos archives. Une fois un ou plusieurs mois exportés, "
            "le bouton en bas permet de supprimer d'un coup les appels de tous les mois déjà archivés "
            "(utile si vous archivez plusieurs mois en retard)."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Mois", "Nb appels", "Statut"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.table)

        export_btn = QPushButton("Exporter le mois sélectionné en CSV…")
        export_btn.clicked.connect(self._export_selected)
        layout.addWidget(export_btn)

        self.purge_btn = QPushButton("Supprimer les appels des mois déjà archivés")
        self.purge_btn.clicked.connect(self._purge)
        layout.addWidget(self.purge_btn)

        self._reload()

    def _reload(self):
        from . import archive

        self._months = archive.list_months(self.conn)
        self.table.setRowCount(len(self._months))
        for row, m in enumerate(self._months):
            self.table.setItem(row, 0, QTableWidgetItem(archive.month_label(m.year_month)))
            self.table.setItem(row, 1, QTableWidgetItem(str(m.call_count)))
            if m.purged_at:
                statut = f"Purgé le {m.purged_at[:10]}"
            elif m.exported_at:
                statut = f"Archivé le {m.exported_at[:10]}"
            else:
                statut = "Non archivé"
            self.table.setItem(row, 2, QTableWidgetItem(statut))

        purgeable = archive.list_purgeable(self.conn)
        self.purge_btn.setEnabled(bool(purgeable))
        self.purge_btn.setText(
            f"Supprimer les appels des {len(purgeable)} mois déjà archivés"
            if purgeable
            else "Aucun mois archivé à supprimer"
        )

    def _export_selected(self):
        from . import archive

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, APP_TITLE, "Sélectionnez d'abord un mois dans la liste.")
            return
        month = self._months[row]
        default_name = f"appels-{month.year_month}.csv"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exporter en CSV", default_name, "CSV (*.csv)")
        if not path_str:
            return
        count = archive.export_csv(self.conn, month.year_month, Path(path_str))
        self._reload()
        QMessageBox.information(self, APP_TITLE, f"{count} appel(s) exporté(s) vers {path_str}.")

    def _purge(self):
        from . import archive

        purgeable = archive.list_purgeable(self.conn)
        if not purgeable:
            return
        labels = ", ".join(archive.month_label(ym) for ym in purgeable)
        confirm = QMessageBox.warning(
            self,
            APP_TITLE,
            f"Supprimer définitivement les appels de : {labels} ?\n\n"
            "Cette action est irréversible. Assurez-vous d'avoir bien exporté ces mois au préalable.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        result = archive.purge_archived(self.conn)
        self._reload()
        self.on_purged()
        QMessageBox.information(
            self, APP_TITLE, f"{result.rows_deleted} appel(s) supprimé(s) pour {len(result.months)} mois."
        )


class SettingsDialog(QDialog):
    def __init__(self, conn, on_clients_saved, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Réglages")
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.clients_tab = ClientsSettingsTab(conn, on_clients_saved)
        self.publish_tab = PublishSettingsTab(conn)
        self.archive_tab = ArchiveSettingsTab(conn, on_clients_saved)
        tabs.addTab(self.clients_tab, "Clients")
        tabs.addTab(self.publish_tab, "Publication")
        tabs.addTab(self.archive_tab, "Archivage")
        layout.addWidget(tabs)
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(str(resource_path("icon.ico"))))
        self.resize(1200, 900)

        self.conn = db.connect()
        self.period_offset = 0
        self.current_data: Optional[stats.ReportData] = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        import_btn = QPushButton("Importer un fichier…")
        import_btn.clicked.connect(self.on_import)
        toolbar.addWidget(import_btn)

        toolbar.addWidget(QLabel("Client :"))
        self.client_combo = QComboBox()
        self.client_combo.currentIndexChanged.connect(self.on_client_changed)
        toolbar.addWidget(self.client_combo, 1)

        prev_btn = QPushButton("◀ Période précédente")
        prev_btn.clicked.connect(self.on_prev_period)
        toolbar.addWidget(prev_btn)

        self.period_label = QLabel()
        toolbar.addWidget(self.period_label)

        next_btn = QPushButton("Période suivante ▶")
        next_btn.clicked.connect(self.on_next_period)
        toolbar.addWidget(next_btn)

        settings_btn = QPushButton("Réglages…")
        settings_btn.clicked.connect(self.on_settings)
        toolbar.addWidget(settings_btn)

        root.addLayout(toolbar)

        actions = QHBoxLayout()
        pdf_btn = QPushButton("Exporter PDF")
        pdf_btn.clicked.connect(self.on_export_pdf)
        actions.addWidget(pdf_btn)

        html_btn = QPushButton("Exporter HTML")
        html_btn.clicked.connect(self.on_export_html)
        actions.addWidget(html_btn)

        publish_btn = QPushButton("Publier sur le site")
        publish_btn.clicked.connect(self.on_publish)
        actions.addWidget(publish_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        self.export_buttons = [pdf_btn, html_btn, publish_btn]

        self.web_view = QWebEngineView()
        self.web_view.loadFinished.connect(self._on_report_loaded)
        # Le bouton "Imprimer / Export PDF" du rapport appelle window.print(), qui ne fait rien
        # dans une QWebEngineView sans ce relais : on le fait pointer vers notre propre export PDF.
        self.web_view.page().printRequested.connect(self.on_export_pdf)
        root.addWidget(self.web_view, 1)

        self.reload_clients()
        self.refresh_report()

    # -- Données -----------------------------------------------------

    def reload_clients(self):
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem("Tous les clients", None)
        for c in db.list_clients(self.conn):
            self.client_combo.addItem(c.label, c.numero_appele)
        self.client_combo.blockSignals(False)

    def current_client(self) -> Optional[Client]:
        numero = self.client_combo.currentData()
        return db.get_client(self.conn, numero) if numero else None

    def current_cycle_start_day(self) -> int:
        client = self.current_client()
        return client.cycle_start_day if client else 1

    def refresh_report(self):
        numero = self.client_combo.currentData()
        start, end = stats.get_period(self.current_cycle_start_day(), date.today(), self.period_offset)
        self.period_label.setText(f"{start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')}")
        self.current_data = stats.build_report_data(self.conn, numero, start, end)
        html_content = report.render_report(self.current_data)
        for btn in self.export_buttons:
            btn.setEnabled(False)
        self.web_view.setHtml(html_content, baseUrl="about:blank")

    def _on_report_loaded(self, ok: bool):
        for btn in self.export_buttons:
            btn.setEnabled(ok)

    # -- Actions -------------------------------------------------------

    def on_import(self):
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Importer un listing d'appels", "", "Fichiers appels (*.xlsx *.xlsm *.csv)"
        )
        if not path_str:
            return
        try:
            result = importer.import_file(self.conn, Path(path_str))
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(self, APP_TITLE, f"Échec de l'import :\n{exc}")
            return

        self.reload_clients()
        self.refresh_report()
        QMessageBox.information(
            self,
            APP_TITLE,
            (
                f"Import terminé.\n\n"
                f"Lignes lues : {result.total_rows}\n"
                f"Appels ajoutés : {result.inserted}\n"
                f"Déjà présents (ignorés) : {result.duplicates}\n"
                f"Exclus (sortant/manqué/<8s) : {result.filtered_out}\n"
                f"Nouveaux clients détectés : {len(result.new_clients)}"
            ),
        )

    def on_client_changed(self):
        self.period_offset = 0
        self.refresh_report()

    def on_prev_period(self):
        self.period_offset -= 1
        self.refresh_report()

    def on_next_period(self):
        self.period_offset += 1
        self.refresh_report()

    def on_settings(self):
        dialog = SettingsDialog(self.conn, self.on_clients_saved, parent=self)
        dialog.exec()

    def on_clients_saved(self):
        self.reload_clients()
        self.refresh_report()

    def on_export_pdf(self):
        if self.current_data is None:
            return
        default_name = self._default_filename() + ".pdf"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exporter en PDF", default_name, "PDF (*.pdf)")
        if not path_str:
            return

        page = self.web_view.page()
        state = {"handled": False}

        def cleanup():
            try:
                page.pdfPrintingFinished.disconnect(on_finished)
            except (RuntimeError, TypeError):
                pass

        def on_finished(file_path: str, success: bool):
            if state["handled"] or file_path != path_str:
                return  # le délai de sécurité a déjà réagi, ou signal pour un autre export
            state["handled"] = True
            cleanup()
            if success:
                QMessageBox.information(self, APP_TITLE, "PDF exporté avec succès.")
            else:
                from . import config

                config.log_error("export_pdf", f"pdfPrintingFinished a signalé un échec ({path_str}).")
                QMessageBox.critical(
                    self,
                    APP_TITLE,
                    "Échec de l'export PDF.\n\n"
                    "Vous pouvez utiliser «Exporter HTML» puis imprimer depuis le "
                    "fichier ouvert dans un navigateur, qui fonctionne dans tous les cas.",
                )

        def on_timeout():
            if state["handled"]:
                return
            state["handled"] = True
            cleanup()
            from . import config

            config.log_error("export_pdf", f"printToPdf n'a pas répondu dans le délai imparti ({path_str}).")
            QMessageBox.critical(
                self,
                APP_TITLE,
                "L'export PDF n'a pas abouti (délai dépassé).\n\n"
                "Vous pouvez utiliser «Exporter HTML» puis imprimer depuis le fichier "
                "ouvert dans un navigateur, qui fonctionne dans tous les cas.",
            )

        layout = QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(10, 10, 10, 10))
        page.pdfPrintingFinished.connect(on_finished)
        try:
            page.printToPdf(path_str, layout)
        except Exception as exc:
            state["handled"] = True
            cleanup()
            from . import config

            config.log_error("export_pdf", f"Exception synchrone lors de l'appel à printToPdf :\n{traceback.format_exc()}")
            QMessageBox.critical(self, APP_TITLE, f"Échec de l'export PDF :\n{exc}")
            return

        QTimer.singleShot(20000, on_timeout)

    def on_export_html(self):
        if self.current_data is None:
            return
        default_name = self._default_filename() + ".html"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exporter en HTML", default_name, "HTML (*.html)")
        if not path_str:
            return
        Path(path_str).write_text(report.render_report(self.current_data), encoding="utf-8")
        QMessageBox.information(self, APP_TITLE, "Fichier HTML exporté avec succès.")

    def on_publish(self):
        client = self.current_client()
        if client is None:
            QMessageBox.warning(
                self, APP_TITLE, "Sélectionnez un client précis (pas « Tous les clients ») pour publier son rapport."
            )
            return
        if self.current_data is None:
            return

        tab = PublishSettingsTab(self.conn)  # simple porteur de config, non affiché
        config = tab.get_config()
        if not config.host or not config.base_url:
            QMessageBox.warning(
                self, APP_TITLE, "Configurez d'abord les identifiants de publication dans Réglages > Publication."
            )
            return

        try:
            url = ftp_publish.publish(config, client.slug, report.render_report(self.current_data))
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(self, APP_TITLE, f"Échec de la publication :\n{exc}")
            return

        QMessageBox.information(self, APP_TITLE, f"Rapport publié avec succès :\n{url}")

    def _default_filename(self) -> str:
        client = self.current_client()
        base = client.slug if client else "tous-clients"
        start, end = stats.get_period(self.current_cycle_start_day(), date.today(), self.period_offset)
        return f"rapport-{base}-{start.strftime('%Y-%m')}"


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(resource_path("icon.ico"))))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
