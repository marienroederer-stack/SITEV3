"""Interface graphique de l'application (PySide6)."""

import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from . import db, importer, report, stats
from .config import icon_path as app_icon_path

APP_TITLE = "CADUCEA - Analyse interne des appels"

MOIS_LABELS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _month_label(ym: str) -> str:
    year, month = ym.split("-")
    return f"{MOIS_LABELS[int(month) - 1]} {year}"


def _period_label(period_type: str, start: date, end: date) -> str:
    if period_type == "jour":
        return start.strftime("%A %d/%m/%Y").capitalize()
    if period_type == "semaine":
        return f"Semaine du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}"
    return f"{MOIS_LABELS[start.month - 1].capitalize()} {start.year}"


class SelectAllLineEdit(QLineEdit):
    """Champ de saisie d'un QComboBox éditable : un clic n'importe où sélectionne tout le
    texte déjà présent (prêt à être remplacé en tapant, sans avoir à l'effacer à la main)
    et ouvre la liste déroulante, comme un clic sur la flèche en bout de ligne."""

    def __init__(self, combo: QComboBox):
        super().__init__(combo)
        self._combo = combo

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selectAll()
        self._combo.showPopup()


class SearchableComboBox(QComboBox):
    """QComboBox éditable avec recherche par saisie (filtre les éléments contenant le texte
    tapé, où qu'il apparaisse, insensible à la casse) et sélection totale du texte au clic."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setLineEdit(SelectAllLineEdit(self))
        completer = self.completer()
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)


class AnalysisTab(QWidget):
    """Un onglet d'analyse (par client, par opérateur ou par code affaire)."""

    def __init__(self, conn, dimension: str, dimension_title: str):
        super().__init__()
        self.conn = conn
        self.dimension = dimension
        self.period_offset = 0

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(f"{dimension_title} :"))
        self.value_combo = SearchableComboBox()
        self.value_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.value_combo, 1)

        controls.addWidget(QLabel("Vue :"))
        self.period_type_combo = QComboBox()
        self.period_type_combo.addItem("Jour", "jour")
        self.period_type_combo.addItem("Semaine", "semaine")
        self.period_type_combo.addItem("Mois", "mois")
        self.period_type_combo.setCurrentIndex(1)  # Semaine par défaut
        self.period_type_combo.currentIndexChanged.connect(self._on_period_type_changed)
        controls.addWidget(self.period_type_combo)

        controls.addWidget(QLabel("Créneaux :"))
        self.granularity_combo = QComboBox()
        for g in stats.GRANULARITES:
            self.granularity_combo.addItem(f"{g} min", g)
        self.granularity_combo.setCurrentIndex(2)  # 60 min par défaut (par heure)
        self.granularity_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.granularity_combo)

        layout.addLayout(controls)

        nav = QHBoxLayout()
        prev_btn = QPushButton("◀ Période précédente")
        prev_btn.clicked.connect(self.on_prev_period)
        nav.addWidget(prev_btn)

        self.period_label = QLabel()
        self.period_label.setStyleSheet("font-weight: 600;")
        nav.addWidget(self.period_label, 1, Qt.AlignCenter)

        next_btn = QPushButton("Période suivante ▶")
        next_btn.clicked.connect(self.on_next_period)
        nav.addWidget(next_btn)

        nav.addWidget(QLabel("Comparer avec :"))
        self.compare_combo = QComboBox()
        self.compare_combo.currentIndexChanged.connect(self.refresh)
        nav.addWidget(self.compare_combo)

        layout.addLayout(nav)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view, 1)

        self.reload_values()
        self.reload_compare_months()

    # -- Rechargement des listes déroulantes --------------------------------

    def reload_values(self):
        current = self.value_combo.currentData()
        self.value_combo.blockSignals(True)
        self.value_combo.clear()
        all_label = {
            "client": "Tous les clients",
            "operateur": "Tous les opérateurs",
            "code_affaire": "Tous les codes affaire",
        }[self.dimension]
        self.value_combo.addItem(all_label, None)
        if self.dimension == "client":
            for c in db.list_clients(self.conn):
                self.value_combo.addItem(f"{c.label} ({c.sda})", c.sda)
        elif self.dimension == "operateur":
            self.value_combo.addItem("Non attribué", "")
            for o in db.list_operators(self.conn):
                self.value_combo.addItem(f"{o.label} ({o.login})", o.login)
        elif self.dimension == "code_affaire":
            for code in db.list_code_affaires(self.conn):
                self.value_combo.addItem(code, code)
        if current is not None:
            idx = self.value_combo.findData(current)
            if idx >= 0:
                self.value_combo.setCurrentIndex(idx)
        self.value_combo.blockSignals(False)

    def reload_compare_months(self):
        current = self.compare_combo.currentData()
        self.compare_combo.blockSignals(True)
        self.compare_combo.clear()
        self.compare_combo.addItem("Aucune", None)
        for ym in reversed(db.months_with_calls(self.conn)):
            self.compare_combo.addItem(_month_label(ym), ym)
        if current is not None:
            idx = self.compare_combo.findData(current)
            if idx >= 0:
                self.compare_combo.setCurrentIndex(idx)
        self.compare_combo.blockSignals(False)

    # -- Navigation -----------------------------------------------------

    def _on_period_type_changed(self):
        self.period_offset = 0
        self.refresh()

    def on_prev_period(self):
        self.period_offset -= 1
        self.refresh()

    def on_next_period(self):
        self.period_offset += 1
        self.refresh()

    # -- Rafraîchissement --------------------------------------------------

    def refresh(self):
        value = self.value_combo.currentData()
        period_type = self.period_type_combo.currentData() or "semaine"
        granularity = self.granularity_combo.currentData() or 60

        start, end = stats.get_period(period_type, date.today(), self.period_offset)
        data = stats.build_report_data(self.conn, self.dimension, value, period_type, start, end, granularity)
        self.period_label.setText(_period_label(period_type, start, end))

        comparison = None
        ym = self.compare_combo.currentData()
        if ym:
            year, month = (int(x) for x in ym.split("-"))
            compare_summary = stats.build_summary_for_month(self.conn, self.dimension, value, year, month)
            comparison = (_month_label(ym), compare_summary)

        html = report.render_report(data, comparison=comparison)
        self.web_view.setHtml(html)


class DirectoryTableBase(QWidget):
    """Base commune pour les onglets 'Listing clients' / 'Listing opérateurs'."""

    COLUMNS: list = []  # [(header, editable)]

    def __init__(self, conn):
        super().__init__()
        self.conn = conn

        layout = QVBoxLayout(self)

        actions = QHBoxLayout()
        self.save_btn = QPushButton("Enregistrer les modifications")
        self.save_btn.clicked.connect(self.on_save)
        actions.addWidget(self.save_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        layout.addWidget(self.table, 1)

        self.note = QLabel()
        self.note.setStyleSheet("color: #5a5f73;")
        layout.addWidget(self.note)

        self.reload()

    def _set_cell(self, row: int, col: int, text: str, editable: bool):
        item = QTableWidgetItem(text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, col, item)

    def reload(self):
        raise NotImplementedError

    def on_save(self):
        raise NotImplementedError


class ClientsListingTab(DirectoryTableBase):
    COLUMNS = [
        ("SDA", False),
        ("Nom / Dossier", True),
        ("Code affaire", True),
        ("Nb appels", False),
        ("Ajouté automatiquement", False),
    ]

    def reload(self):
        clients = db.list_clients(self.conn)
        self.table.setRowCount(len(clients))
        for row, c in enumerate(clients):
            self._set_cell(row, 0, c.sda, False)
            self._set_cell(row, 1, c.nom, True)
            self._set_cell(row, 2, c.code_affaire, True)
            self._set_cell(row, 3, str(db.call_count_for_client(self.conn, c.sda)), False)
            self._set_cell(row, 4, "Oui" if c.auto_detected else "", False)
        self.note.setText(
            f"{len(clients)} client(s). Les nouveaux SDA rencontrés dans un import sont ajoutés "
            "automatiquement (ligne \"Ajouté automatiquement\" = Oui, à compléter). Modifier le nom "
            "ou le code affaire ici ne supprime jamais les statistiques déjà enregistrées : elles "
            "restent attachées au SDA."
        )

    def on_save(self):
        for row in range(self.table.rowCount()):
            sda = self.table.item(row, 0).text()
            nom = self.table.item(row, 1).text()
            code = self.table.item(row, 2).text()
            db.update_client(self.conn, sda, nom, code)
        self.conn.commit()
        self.reload()
        QMessageBox.information(self, APP_TITLE, "Listing clients enregistré.")


class OperatorsListingTab(DirectoryTableBase):
    COLUMNS = [
        ("Login", False),
        ("Poste", True),
        ("Nom", True),
        ("Nb appels", False),
        ("Ajouté automatiquement", False),
    ]

    def reload(self):
        operators = db.list_operators(self.conn)
        self.table.setRowCount(len(operators))
        for row, o in enumerate(operators):
            self._set_cell(row, 0, o.login, False)
            self._set_cell(row, 1, o.poste, True)
            self._set_cell(row, 2, o.nom, True)
            self._set_cell(row, 3, str(db.call_count_for_operator(self.conn, o.login)), False)
            self._set_cell(row, 4, "Oui" if o.auto_detected else "", False)
        self.note.setText(
            f"{len(operators)} opérateur(s). Les nouveaux logins rencontrés dans un import sont "
            "ajoutés automatiquement (poste et nom à compléter ici)."
        )

    def on_save(self):
        for row in range(self.table.rowCount()):
            login = self.table.item(row, 0).text()
            poste = self.table.item(row, 1).text()
            nom = self.table.item(row, 2).text()
            db.update_operator(self.conn, login, poste, nom)
        self.conn.commit()
        self.reload()
        QMessageBox.information(self, APP_TITLE, "Listing opérateurs enregistré.")


class ImportsLogTab(QWidget):
    COLUMNS = [
        "Date", "Fichier", "Lignes lues", "Ajoutées", "Doublons",
        "Non entrants (filtrées)", "Invalides", "Nouveaux clients", "Nouveaux opérateurs",
    ]

    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)
        self.reload()

    def reload(self):
        imports = db.list_imports(self.conn)
        self.table.setRowCount(len(imports))
        for row, imp in enumerate(imports):
            values = [
                imp["imported_at"][:19].replace("T", " "),
                imp["filename"],
                imp["rows_total"],
                imp["rows_inserted"],
                imp["rows_duplicates"],
                imp["rows_filtered"],
                imp["rows_invalid"],
                imp["new_clients"],
                imp["new_operators"],
            ]
            for col, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, item)


class PurgeDialog(QDialog):
    """Purge définitive des appels antérieurs à une date choisie, avec confirmation de
    sécurité affichant le nombre exact d'appels concernés."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Purger les données")

        layout = QVBoxLayout(self)

        info = QLabel(
            "Supprime définitivement les appels enregistrés avant la date choisie.\n"
            "Les fiches clients et opérateurs ne sont pas affectées, et réimporter plus "
            "tard un fichier couvrant la période purgée fonctionne normalement."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QHBoxLayout()
        form.addWidget(QLabel("Purger les appels antérieurs au :"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._update_count)
        form.addWidget(self.date_edit)
        form.addStretch(1)
        layout.addLayout(form)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.count_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.purge_btn = QPushButton("Purger…")
        self.purge_btn.clicked.connect(self._on_purge_clicked)
        btn_row.addWidget(self.purge_btn)
        layout.addLayout(btn_row)

        self._update_count()

    def _cutoff_iso(self) -> str:
        d = self.date_edit.date().toPython()
        return datetime.combine(d, datetime.min.time()).isoformat()

    def _update_count(self):
        n = db.count_calls_before(self.conn, self._cutoff_iso())
        self.count_label.setText(f"{n} appel(s) seront supprimés définitivement.")
        self.purge_btn.setEnabled(n > 0)

    def _on_purge_clicked(self):
        n = db.count_calls_before(self.conn, self._cutoff_iso())
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        reply = QMessageBox.question(
            self,
            "Confirmer la purge",
            f"Confirmez-vous la suppression définitive de {n} appel(s) antérieur(s) au "
            f"{date_str} ?\n\nCette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            db.purge_calls_before(self.conn, self._cutoff_iso())
            self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        icon = app_icon_path()
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1400, 950)

        self.conn = db.connect()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        import_btn = QPushButton("Importer un fichier…")
        import_btn.clicked.connect(self.on_import)
        toolbar.addWidget(import_btn)
        purge_btn = QPushButton("Purger les données…")
        purge_btn.clicked.connect(self.on_purge)
        toolbar.addWidget(purge_btn)
        self.import_status = QLabel("Aucun import effectué.")
        toolbar.addWidget(self.import_status, 1)
        root.addLayout(toolbar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.client_tab = AnalysisTab(self.conn, "client", "Client")
        self.operateur_tab = AnalysisTab(self.conn, "operateur", "Opérateur")
        self.code_affaire_tab = AnalysisTab(self.conn, "code_affaire", "Code affaire")
        self.clients_listing_tab = ClientsListingTab(self.conn)
        self.operators_listing_tab = OperatorsListingTab(self.conn)
        self.imports_log_tab = ImportsLogTab(self.conn)

        self.tabs.addTab(self.client_tab, "Par client")
        self.tabs.addTab(self.operateur_tab, "Par opérateur")
        self.tabs.addTab(self.code_affaire_tab, "Par code affaire")
        self.tabs.addTab(self.clients_listing_tab, "Listing clients")
        self.tabs.addTab(self.operators_listing_tab, "Listing opérateurs")
        self.tabs.addTab(self.imports_log_tab, "Journal des imports")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        self._refresh_last_import_label()
        for tab in (self.client_tab, self.operateur_tab, self.code_affaire_tab):
            tab.refresh()

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        if isinstance(widget, AnalysisTab):
            widget.refresh()

    def _refresh_last_import_label(self):
        imports = db.list_imports(self.conn)
        if not imports:
            self.import_status.setText("Aucun import effectué.")
            return
        last = imports[0]
        self.import_status.setText(
            f"Dernier import : {last['filename']} le {last['imported_at'][:19].replace('T', ' ')} "
            f"({last['rows_inserted']} appel(s) ajouté(s))"
        )

    def _refresh_all_tabs(self):
        for tab in (self.client_tab, self.operateur_tab, self.code_affaire_tab):
            tab.reload_values()
            tab.reload_compare_months()
            tab.refresh()
        self.clients_listing_tab.reload()
        self.operators_listing_tab.reload()
        self.imports_log_tab.reload()
        self._refresh_last_import_label()

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

        self._refresh_all_tabs()

        QMessageBox.information(
            self,
            APP_TITLE,
            (
                f"Import terminé.\n\n"
                f"Lignes lues : {result.total_rows}\n"
                f"Appels ajoutés : {result.inserted}\n"
                f"Déjà présents (ignorés) : {result.duplicates}\n"
                f"Non entrants (exclus) : {result.filtered_out}\n"
                f"Lignes invalides : {result.invalid_rows}\n"
                f"Nouveaux clients détectés : {len(result.new_clients)}\n"
                f"Nouveaux opérateurs détectés : {len(result.new_operators)}"
            ),
        )

    def on_purge(self):
        dialog = PurgeDialog(self.conn, self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh_all_tabs()
            QMessageBox.information(self, APP_TITLE, "Purge terminée.")


def main():
    app = QApplication(sys.argv)
    icon = app_icon_path()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
