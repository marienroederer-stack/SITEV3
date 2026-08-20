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
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDoubleSpinBox,
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

from . import db, ftp_publish, importer, importer_sortants, report, report_sortants, stats, stats_sortants, webapi_publish
from .config import resource_path
from .db import Client

APP_TITLE = "DOCTEL - analyse appels entrants"


class _SelectAllLineEdit(QLineEdit):
    """Champ de texte qui sélectionne tout son contenu à chaque clic, pour que la frappe le
    remplace directement au lieu de s'insérer au milieu.

    Un simple filtre sur l'événement FocusIn ne suffit pas : il ne se déclenche qu'au premier
    clic (quand le champ n'a pas encore le focus). Un second clic sur un champ déjà focalisé ne
    génère pas de nouveau FocusIn, donc rien ne serait sélectionné - d'où la gestion explicite du
    clic souris en plus."""

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def mousePressEvent(self, event):
        already_focused = self.hasFocus()
        super().mousePressEvent(event)
        if already_focused:
            self.selectAll()


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

        self.search_edit = _SelectAllLineEdit()
        self.search_edit.setPlaceholderText("Rechercher un client (nom, quelques caractères suffisent)…")
        self.search_edit.textChanged.connect(self._filter_table)
        layout.addWidget(self.search_edit)

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
        self._filter_table(self.search_edit.text())

    def _filter_table(self, text: str):
        needle = text.strip().lower()
        for row in range(self.table.rowCount()):
            nom = self.table.item(row, 0).text().lower()
            display = self.table.item(row, 1).text().lower()
            self.table.setRowHidden(row, bool(needle) and needle not in nom and needle not in display)

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


class TarifsSettingsTab(QWidget):
    """Tarifs des appels sortants/aboutements : un tarif global par défaut, personnalisable par client."""

    def __init__(self, conn):
        super().__init__()
        self.conn = conn

        layout = QVBoxLayout(self)

        global_box = QFormLayout()
        self.global_aboutement_fixe = QDoubleSpinBox()
        self.global_aboutement_portable = QDoubleSpinBox()
        self.global_sortant_fixe = QDoubleSpinBox()
        self.global_sortant_portable = QDoubleSpinBox()
        for spin in (
            self.global_aboutement_fixe, self.global_aboutement_portable,
            self.global_sortant_fixe, self.global_sortant_portable,
        ):
            spin.setRange(0, 99)
            spin.setDecimals(2)
            spin.setSingleStep(0.01)
            spin.setSuffix(" € HT")
        global_box.addRow("Aboutement vers fixe", self.global_aboutement_fixe)
        global_box.addRow("Aboutement vers portable", self.global_aboutement_portable)
        global_box.addRow("Sortant vers fixe", self.global_sortant_fixe)
        global_box.addRow("Sortant vers portable", self.global_sortant_portable)
        layout.addLayout(global_box)

        save_global_btn = QPushButton("Enregistrer les tarifs globaux (par défaut)")
        save_global_btn.clicked.connect(self._save_global)
        layout.addWidget(save_global_btn)

        info_label = QLabel(
            "Un client sans tarif dédié utilise les tarifs globaux ci-dessus. Cochez « Tarif dédié » "
            "sur une ligne pour lui appliquer des tarifs personnalisés (ex : BERTRAND)."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.search_edit = _SelectAllLineEdit()
        self.search_edit.setPlaceholderText("Rechercher un client…")
        self.search_edit.textChanged.connect(self._filter_table)
        layout.addWidget(self.search_edit)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Client", "Tarif dédié", "Abt. fixe", "Abt. portable", "Sortant fixe", "Sortant portable"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table)

        save_btn = QPushButton("Enregistrer les tarifs par client")
        save_btn.clicked.connect(self._save_clients)
        layout.addWidget(save_btn)

        self._reload()

    def _make_tarif_spin(self, value: float, enabled: bool) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 99)
        spin.setDecimals(2)
        spin.setSingleStep(0.01)
        spin.setValue(value)
        spin.setEnabled(enabled)
        return spin

    def _reload(self):
        globaux = db.get_global_tarifs(self.conn)
        self.global_aboutement_fixe.setValue(globaux["aboutement_fixe"])
        self.global_aboutement_portable.setValue(globaux["aboutement_portable"])
        self.global_sortant_fixe.setValue(globaux["sortant_fixe"])
        self.global_sortant_portable.setValue(globaux["sortant_portable"])

        clients = db.list_clients(self.conn)
        self.table.setRowCount(len(clients))
        for row, c in enumerate(clients):
            nom_item = QTableWidgetItem(c.label)
            nom_item.setFlags(nom_item.flags() & ~Qt.ItemIsEditable)
            nom_item.setData(Qt.UserRole, c.numero_appele)
            self.table.setItem(row, 0, nom_item)

            override = db.get_client_tarifs_override(self.conn, c.numero_appele)
            dedie = any(v is not None for v in override.values())

            checkbox = QCheckBox()
            checkbox.setChecked(dedie)
            self.table.setCellWidget(row, 1, checkbox)

            spins = {
                "aboutement_fixe": self._make_tarif_spin(
                    override["aboutement_fixe"] if dedie else globaux["aboutement_fixe"], dedie
                ),
                "aboutement_portable": self._make_tarif_spin(
                    override["aboutement_portable"] if dedie else globaux["aboutement_portable"], dedie
                ),
                "sortant_fixe": self._make_tarif_spin(
                    override["sortant_fixe"] if dedie else globaux["sortant_fixe"], dedie
                ),
                "sortant_portable": self._make_tarif_spin(
                    override["sortant_portable"] if dedie else globaux["sortant_portable"], dedie
                ),
            }
            self.table.setCellWidget(row, 2, spins["aboutement_fixe"])
            self.table.setCellWidget(row, 3, spins["aboutement_portable"])
            self.table.setCellWidget(row, 4, spins["sortant_fixe"])
            self.table.setCellWidget(row, 5, spins["sortant_portable"])

            def on_toggled(checked, row=row, spins=spins):
                for spin in spins.values():
                    spin.setEnabled(checked)

            checkbox.toggled.connect(on_toggled)

        self._filter_table(self.search_edit.text())

    def _filter_table(self, text: str):
        needle = text.strip().lower()
        for row in range(self.table.rowCount()):
            nom = self.table.item(row, 0).text().lower()
            self.table.setRowHidden(row, bool(needle) and needle not in nom)

    def _save_global(self):
        db.set_global_tarifs(
            self.conn,
            self.global_aboutement_fixe.value(),
            self.global_aboutement_portable.value(),
            self.global_sortant_fixe.value(),
            self.global_sortant_portable.value(),
        )
        self.conn.commit()
        self._reload()
        QMessageBox.information(self, APP_TITLE, "Tarifs globaux enregistrés.")

    def _save_clients(self):
        for row in range(self.table.rowCount()):
            numero = self.table.item(row, 0).data(Qt.UserRole)
            checkbox: QCheckBox = self.table.cellWidget(row, 1)
            if checkbox.isChecked():
                spins = [self.table.cellWidget(row, c) for c in (2, 3, 4, 5)]
                db.set_client_tarifs_override(self.conn, numero, *(s.value() for s in spins))
            else:
                db.set_client_tarifs_override(self.conn, numero, None, None, None, None)
        self.conn.commit()
        self._reload()
        QMessageBox.information(self, APP_TITLE, "Tarifs par client enregistrés.")


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

        self.webapi_url = QLineEdit()
        self.webapi_url.setPlaceholderText("https://doctel.fr/espace-client/api/update.php")
        form.addRow("URL API espace client", self.webapi_url)

        self.webapi_key = QLineEdit()
        self.webapi_key.setEchoMode(QLineEdit.Password)
        form.addRow("Clé API espace client", self.webapi_key)

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
        self.webapi_url.setText(db.get_setting(c, "webapi_url"))
        encrypted_key = db.get_setting(c, "webapi_key")
        if encrypted_key:
            try:
                self.webapi_key.setText(crypto_store.decrypt(encrypted_key))
            except Exception:
                pass

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
        db.set_setting(c, "webapi_url", self.webapi_url.text().strip())
        db.set_setting(c, "webapi_key", crypto_store.encrypt(self.webapi_key.text()))
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

    def get_webapi_config(self) -> Optional["webapi_publish.WebApiConfig"]:
        api_url = db.get_setting(self.conn, "webapi_url")
        if not api_url:
            return None
        from . import crypto_store

        encrypted_key = db.get_setting(self.conn, "webapi_key")
        api_key = crypto_store.decrypt(encrypted_key) if encrypted_key else ""
        return webapi_publish.WebApiConfig(api_url=api_url, api_key=api_key)


class ArchiveSettingsTab(QWidget):
    def __init__(self, conn, on_purged):
        super().__init__()
        self.conn = conn
        self.on_purged = on_purged

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Exportez un mois civil en CSV pour vos archives (entrants et sortants séparément). "
            "Une fois un ou plusieurs mois exportés, le bouton en bas permet de supprimer d'un coup "
            "les appels de tous les mois déjà archivés (utile si vous archivez plusieurs mois en retard)."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Mois", "Nb entrants", "Statut entrants", "Nb sortants", "Statut sortants"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.table)

        export_row = QHBoxLayout()
        export_btn = QPushButton("Exporter les appels ENTRANTS du mois sélectionné…")
        export_btn.clicked.connect(self._export_selected)
        export_row.addWidget(export_btn)

        export_sortants_btn = QPushButton("Exporter les appels SORTANTS du mois sélectionné…")
        export_sortants_btn.clicked.connect(self._export_selected_sortants)
        export_row.addWidget(export_sortants_btn)
        layout.addLayout(export_row)

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

            self.table.setItem(row, 3, QTableWidgetItem(str(m.call_count_sortants)))
            if m.purged_at_sortants:
                statut_s = f"Purgé le {m.purged_at_sortants[:10]}"
            elif m.exported_at_sortants:
                statut_s = f"Archivé le {m.exported_at_sortants[:10]}"
            else:
                statut_s = "Non archivé"
            self.table.setItem(row, 4, QTableWidgetItem(statut_s))

        purgeable = archive.list_purgeable(self.conn)
        purgeable_sortants = archive.list_purgeable_sortants(self.conn)
        total_purgeable = len(set(purgeable) | set(purgeable_sortants))
        self.purge_btn.setEnabled(bool(purgeable or purgeable_sortants))
        self.purge_btn.setText(
            f"Supprimer les appels des {total_purgeable} mois déjà archivés"
            if (purgeable or purgeable_sortants)
            else "Aucun mois archivé à supprimer"
        )

    def _export_selected(self):
        from . import archive

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, APP_TITLE, "Sélectionnez d'abord un mois dans la liste.")
            return
        month = self._months[row]
        default_name = f"appels-entrants-{month.year_month}.csv"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exporter en CSV", default_name, "CSV (*.csv)")
        if not path_str:
            return
        count = archive.export_csv(self.conn, month.year_month, Path(path_str))
        self._reload()
        QMessageBox.information(self, APP_TITLE, f"{count} appel(s) exporté(s) vers {path_str}.")

    def _export_selected_sortants(self):
        from . import archive

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, APP_TITLE, "Sélectionnez d'abord un mois dans la liste.")
            return
        month = self._months[row]
        default_name = f"appels-sortants-{month.year_month}.csv"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exporter en CSV", default_name, "CSV (*.csv)")
        if not path_str:
            return
        count = archive.export_csv_sortants(self.conn, month.year_month, Path(path_str))
        self._reload()
        QMessageBox.information(self, APP_TITLE, f"{count} appel(s) exporté(s) vers {path_str}.")

    def _purge(self):
        from . import archive

        purgeable = archive.list_purgeable(self.conn)
        purgeable_sortants = archive.list_purgeable_sortants(self.conn)
        if not purgeable and not purgeable_sortants:
            return
        labels = ", ".join(archive.month_label(ym) for ym in sorted(set(purgeable) | set(purgeable_sortants)))
        confirm = QMessageBox.warning(
            self,
            APP_TITLE,
            f"Supprimer définitivement les appels (entrants et/ou sortants selon ce qui est archivé) de : "
            f"{labels} ?\n\n"
            "Cette action est irréversible. Assurez-vous d'avoir bien exporté ces mois au préalable.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        result = archive.purge_archived(self.conn)
        result_sortants = archive.purge_archived_sortants(self.conn)
        self._reload()
        self.on_purged()
        total_months = len(set(result.months) | set(result_sortants.months))
        QMessageBox.information(
            self,
            APP_TITLE,
            f"{result.rows_deleted} appel(s) entrant(s) et {result_sortants.rows_deleted} appel(s) "
            f"sortant(s)/aboutement(s) supprimé(s) pour {total_months} mois.",
        )


class SettingsDialog(QDialog):
    def __init__(self, conn, on_clients_saved, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Réglages")
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.clients_tab = ClientsSettingsTab(conn, on_clients_saved)
        self.tarifs_tab = TarifsSettingsTab(conn)
        self.publish_tab = PublishSettingsTab(conn)
        self.archive_tab = ArchiveSettingsTab(conn, on_clients_saved)
        tabs.addTab(self.clients_tab, "Clients")
        tabs.addTab(self.tarifs_tab, "Tarifs")
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
        self.current_data_sortants: Optional[stats_sortants.SortantsReportData] = None
        self._entrants_loaded = False
        self._sortants_loaded = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        import_btn = QPushButton("Importer un fichier…")
        import_btn.clicked.connect(self.on_import)
        toolbar.addWidget(import_btn)

        toolbar.addWidget(QLabel("Client :"))
        self.client_combo = QComboBox()
        self.client_combo.setEditable(True)
        self.client_combo.setInsertPolicy(QComboBox.NoInsert)
        # Champ personnalisé pour sélectionner tout le texte au clic (voir _SelectAllLineEdit).
        self.client_combo.setLineEdit(_SelectAllLineEdit())
        # Tapez quelques lettres (ex : "BERT") pour filtrer la liste, où qu'elles apparaissent dans le nom.
        combo_completer = self.client_combo.completer()
        combo_completer.setCompletionMode(QCompleter.PopupCompletion)
        combo_completer.setFilterMode(Qt.MatchContains)
        combo_completer.setCaseSensitivity(Qt.CaseInsensitive)
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

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(lambda _i: self._update_export_buttons_enabled())
        root.addWidget(self.tabs, 1)

        self.web_view = QWebEngineView()
        self.web_view.loadFinished.connect(self._on_entrants_loaded)
        # Le bouton "Imprimer / Export PDF" du rapport appelle window.print(), qui ne fait rien
        # dans une QWebEngineView sans ce relais : on le fait pointer vers notre propre export PDF.
        self.web_view.page().printRequested.connect(self.on_export_pdf)
        self.tabs.addTab(self.web_view, "Appels entrants")

        sortants_widget = QWidget()
        sortants_layout = QVBoxLayout(sortants_widget)
        sortants_layout.setContentsMargins(0, 0, 0, 0)

        self.web_view_sortants = QWebEngineView()
        self.web_view_sortants.loadFinished.connect(self._on_sortants_loaded)
        self.web_view_sortants.page().printRequested.connect(self.on_export_pdf)
        sortants_layout.addWidget(self.web_view_sortants, 1)

        sms_row = QHBoxLayout()
        sms_row.addWidget(QLabel("SMS de rappel/annulation de RDV :"))
        self.sms_rappel_spin = QSpinBox()
        self.sms_rappel_spin.setRange(0, 99999)
        sms_row.addWidget(self.sms_rappel_spin)
        sms_row.addWidget(QLabel("SMS contact :"))
        self.sms_contact_spin = QSpinBox()
        self.sms_contact_spin.setRange(0, 99999)
        sms_row.addWidget(self.sms_contact_spin)
        self.sms_save_btn = QPushButton("Enregistrer les SMS de cette période")
        self.sms_save_btn.clicked.connect(self.on_save_sms)
        sms_row.addWidget(self.sms_save_btn)
        sms_row.addStretch(1)
        sortants_layout.addLayout(sms_row)

        self.tabs.addTab(sortants_widget, "Appels sortants")

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

        self._entrants_loaded = False
        self._sortants_loaded = False
        for btn in self.export_buttons:
            btn.setEnabled(False)

        self.current_data = stats.build_report_data(self.conn, numero, start, end)
        self.web_view.setHtml(report.render_report(self.current_data), baseUrl="about:blank")

        self.current_data_sortants = stats_sortants.build_sortants_report_data(self.conn, numero, start, end)
        self.web_view_sortants.setHtml(
            report_sortants.render_report(self.current_data_sortants), baseUrl="about:blank"
        )

        self.sms_rappel_spin.blockSignals(True)
        self.sms_contact_spin.blockSignals(True)
        self.sms_rappel_spin.setValue(self.current_data_sortants.sms_rappel)
        self.sms_contact_spin.setValue(self.current_data_sortants.sms_contact)
        self.sms_rappel_spin.blockSignals(False)
        self.sms_contact_spin.blockSignals(False)
        sms_enabled = numero is not None
        self.sms_rappel_spin.setEnabled(sms_enabled)
        self.sms_contact_spin.setEnabled(sms_enabled)
        self.sms_save_btn.setEnabled(sms_enabled)

    def _on_entrants_loaded(self, ok: bool):
        self._entrants_loaded = ok
        self._update_export_buttons_enabled()

    def _on_sortants_loaded(self, ok: bool):
        self._sortants_loaded = ok
        self._update_export_buttons_enabled()

    def _update_export_buttons_enabled(self):
        loaded = self._entrants_loaded if self.tabs.currentIndex() == 0 else self._sortants_loaded
        for btn in self.export_buttons:
            btn.setEnabled(loaded)

    def _active_web_view(self) -> QWebEngineView:
        return self.web_view if self.tabs.currentIndex() == 0 else self.web_view_sortants

    def _active_html(self) -> Optional[str]:
        if self.tabs.currentIndex() == 0:
            return report.render_report(self.current_data) if self.current_data is not None else None
        if self.current_data_sortants is None:
            return None
        return report_sortants.render_report(self.current_data_sortants)

    def _active_filename_suffix(self) -> str:
        return "" if self.tabs.currentIndex() == 0 else "-sortants"

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

        try:
            result_sortants = importer_sortants.import_file(self.conn, Path(path_str))
            sortants_summary = (
                f"\n\nAppels sortants / aboutements :\n"
                f"Lignes ajoutées : {result_sortants.inserted}\n"
                f"Déjà présentes (ignorées) : {result_sortants.duplicates}"
            )
        except ValueError:
            sortants_summary = (
                "\n\n(Fichier non compatible avec le pointage des appels sortants — "
                "colonnes manquantes (SDA, Description...) : cette partie a été ignorée.)"
            )
        except Exception:
            traceback.print_exc()
            sortants_summary = "\n\n(Échec de l'import des appels sortants — voir le journal d'erreurs.)"

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
            )
            + sortants_summary,
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
        # Les tarifs (par ex.) peuvent avoir changé sans passer par on_clients_saved : on
        # rafraîchit systématiquement pour que le rapport sortants reflète l'état actuel.
        self.refresh_report()

    def on_save_sms(self):
        numero = self.client_combo.currentData()
        if numero is None:
            return
        start, _end = stats.get_period(self.current_cycle_start_day(), date.today(), self.period_offset)
        db.set_sms_manuels(
            self.conn, numero, start.isoformat(), self.sms_rappel_spin.value(), self.sms_contact_spin.value()
        )
        self.conn.commit()
        self.refresh_report()
        QMessageBox.information(self, APP_TITLE, "SMS enregistrés pour cette période.")

    def on_clients_saved(self):
        self.reload_clients()
        self.refresh_report()

    def on_export_pdf(self):
        if self._active_html() is None:
            return
        default_name = self._default_filename() + ".pdf"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exporter en PDF", default_name, "PDF (*.pdf)")
        if not path_str:
            return

        page = self._active_web_view().page()
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
        html_content = self._active_html()
        if html_content is None:
            return
        default_name = self._default_filename() + ".html"
        path_str, _ = QFileDialog.getSaveFileName(self, "Exporter en HTML", default_name, "HTML (*.html)")
        if not path_str:
            return
        Path(path_str).write_text(html_content, encoding="utf-8")
        QMessageBox.information(self, APP_TITLE, "Fichier HTML exporté avec succès.")

    def on_publish(self):
        client = self.current_client()
        if client is None:
            QMessageBox.warning(
                self, APP_TITLE, "Sélectionnez un client précis (pas « Tous les clients ») pour publier son rapport."
            )
            return
        html_content = self._active_html()
        if html_content is None:
            return

        tab = PublishSettingsTab(self.conn)  # simple porteur de config, non affiché
        config = tab.get_config()
        if not config.host or not config.base_url:
            QMessageBox.warning(
                self, APP_TITLE, "Configurez d'abord les identifiants de publication dans Réglages > Publication."
            )
            return

        start, end = stats.get_period(self.current_cycle_start_day(), date.today(), self.period_offset)
        # Nom de fichier propre à ce mois : sans ça, chaque publication écraserait celle
        # du mois précédent (même client, même nom de fichier), et "Voir" afficherait
        # toujours le dernier mois envoyé quel que soit le mois cliqué dans l'espace client.
        slug = client.slug + self._active_filename_suffix() + "-" + start.strftime("%Y-%m")
        try:
            url = ftp_publish.publish(config, slug, html_content)
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(self, APP_TITLE, f"Échec de la publication :\n{exc}")
            return

        message = f"Rapport publié avec succès :\n{url}"

        webapi_config = tab.get_webapi_config()
        if webapi_config is not None:
            is_entrants = self.tabs.currentIndex() == 0
            nb_appels = self.current_data.total_calls if is_entrants and self.current_data else None
            try:
                webapi_publish.notify(
                    webapi_config,
                    slug=client.slug,
                    annee=start.year,
                    mois=start.month,
                    type_="entrants" if is_entrants else "sortants",
                    url=url,
                    nb_appels=nb_appels,
                    periode_debut=start.isoformat(),
                    periode_fin=end.isoformat(),
                )
            except Exception as exc:
                traceback.print_exc()
                message += f"\n\nAttention : la mise à jour de l'espace client a échoué :\n{exc}"

        QMessageBox.information(self, APP_TITLE, message)

    def _default_filename(self) -> str:
        client = self.current_client()
        base = client.slug if client else "tous-clients"
        start, end = stats.get_period(self.current_cycle_start_day(), date.today(), self.period_offset)
        return f"rapport-{base}{self._active_filename_suffix()}-{start.strftime('%Y-%m')}"


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(resource_path("icon.ico"))))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
