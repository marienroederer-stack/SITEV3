"""Interface graphique de l'application (PySide6)."""

import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
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
from .db import Client

APP_TITLE = "DOCTEL — Statistiques d'appels"


class ClientsSettingsTab(QWidget):
    def __init__(self, conn, on_saved):
        super().__init__()
        self.conn = conn
        self.on_saved = on_saved

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Jour de début de cycle mensuel pour chaque client (1 = mois civil). "
            "Ce réglage est fixe : il ne change qu'à la demande."
        ))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Client", "Numéro appelé", "Identifiant (slug)", "Jour de cycle"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table)

        save_btn = QPushButton("Enregistrer les modifications")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self._reload()

    def _reload(self):
        clients = db.list_clients(self.conn)
        self.table.setRowCount(len(clients))
        for row, c in enumerate(clients):
            self.table.setItem(row, 0, QTableWidgetItem(c.nom_appele))
            numero_item = QTableWidgetItem(c.numero_appele)
            numero_item.setFlags(numero_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, numero_item)
            self.table.setItem(row, 2, QTableWidgetItem(c.slug))
            spin = QSpinBox()
            spin.setRange(1, 31)
            spin.setValue(c.cycle_start_day)
            self.table.setCellWidget(row, 3, spin)

    def _save(self):
        for row in range(self.table.rowCount()):
            numero = self.table.item(row, 1).text()
            slug = self.table.item(row, 2).text().strip() or db.slugify(self.table.item(row, 0).text())
            spin: QSpinBox = self.table.cellWidget(row, 3)
            db.update_client(self.conn, numero, slug, spin.value())
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


class SettingsDialog(QDialog):
    def __init__(self, conn, on_clients_saved, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Réglages")
        self.resize(650, 450)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.clients_tab = ClientsSettingsTab(conn, on_clients_saved)
        self.publish_tab = PublishSettingsTab(conn)
        tabs.addTab(self.clients_tab, "Clients")
        tabs.addTab(self.publish_tab, "Publication")
        layout.addWidget(tabs)
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
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
        root.addWidget(self.web_view, 1)

        self.reload_clients()
        self.refresh_report()

    # -- Données -----------------------------------------------------

    def reload_clients(self):
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem("Tous les clients", None)
        for c in db.list_clients(self.conn):
            self.client_combo.addItem(c.nom_appele, c.numero_appele)
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
                f"Exclus (sortant/manqué/<10s) : {result.filtered_out}\n"
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

        def done(data: bytes):
            if data:
                Path(path_str).write_bytes(data)
                QMessageBox.information(self, APP_TITLE, "PDF exporté avec succès.")
            else:
                QMessageBox.critical(self, APP_TITLE, "Échec de l'export PDF.")

        self.web_view.page().printToPdf(done)

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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
