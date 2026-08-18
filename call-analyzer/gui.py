"""Interface graphique de l'application (PySide6)."""

import re
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QMarginsF, Qt, QTimer
from PySide6.QtGui import QIcon, QPageLayout, QPageSize
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

from . import db, importer, importer_legacy, legacy_aliases, report, stats
from .config import icon_path as app_icon_path

APP_TITLE = "CADUCEA - Analyse interne des appels"

DIMENSION_ALL_LABELS = {
    "client": "Tous les clients",
    "operateur": "Tous les opérateurs",
    "code_affaire": "Tous les codes affaire",
}

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


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower() or "rapport"


def export_web_view_to_pdf(parent: QWidget, web_view: QWebEngineView, default_name: str) -> None:
    """Exporte le contenu HTML affiché dans `web_view` en PDF, avec confirmation de succès/
    échec et un délai de sécurité au cas où le signal de fin n'arriverait jamais."""
    path_str, _ = QFileDialog.getSaveFileName(parent, "Exporter en PDF", default_name, "PDF (*.pdf)")
    if not path_str:
        return

    page = web_view.page()
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
            QMessageBox.information(parent, APP_TITLE, "PDF exporté avec succès.")
        else:
            QMessageBox.critical(
                parent, APP_TITLE,
                "Échec de l'export PDF.\n\nVous pouvez réessayer, ou agrandir la fenêtre et "
                "réessayer si le rapport est très large.",
            )

    def on_timeout():
        if state["handled"]:
            return
        state["handled"] = True
        cleanup()
        QMessageBox.critical(
            parent, APP_TITLE,
            "L'export PDF n'a pas abouti (délai dépassé). Réessayez.",
        )

    layout = QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(10, 10, 10, 10))
    page.pdfPrintingFinished.connect(on_finished)
    try:
        page.printToPdf(path_str, layout)
    except Exception as exc:
        state["handled"] = True
        cleanup()
        QMessageBox.critical(parent, APP_TITLE, f"Échec de l'export PDF :\n{exc}")
        return
    QTimer.singleShot(20000, on_timeout)


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


class PeriodState:
    """Période (vue, créneau, décalage) partagée entre les onglets Par client / Par
    opérateur / Par code affaire : changer de période dans l'un se reflète dans les
    autres, pour ne pas perdre son contexte en changeant d'onglet."""

    def __init__(self):
        self.period_type = "mois"
        self.granularity = 60
        self.offset = 0
        self._listeners: list = []

    def subscribe(self, callback) -> None:
        self._listeners.append(callback)

    def set(self, period_type=None, granularity=None, offset=None) -> None:
        if period_type is not None:
            self.period_type = period_type
        if granularity is not None:
            self.granularity = granularity
        if offset is not None:
            self.offset = offset
        for callback in self._listeners:
            callback()


class AnalysisTab(QWidget):
    """Un onglet d'analyse (par client, par opérateur ou par code affaire)."""

    def __init__(self, conn, dimension: str, dimension_title: str, period_state: PeriodState):
        super().__init__()
        self.conn = conn
        self.dimension = dimension
        self.period_state = period_state
        self._current_start = self._current_end = date.today()

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
        self.period_type_combo.currentIndexChanged.connect(self._on_period_type_control_changed)
        controls.addWidget(self.period_type_combo)

        controls.addWidget(QLabel("Créneaux :"))
        self.granularity_combo = QComboBox()
        for g in stats.GRANULARITES:
            self.granularity_combo.addItem(f"{g} min", g)
        self.granularity_combo.currentIndexChanged.connect(self._on_granularity_control_changed)
        controls.addWidget(self.granularity_combo)

        layout.addLayout(controls)

        nav = QHBoxLayout()
        prev_btn = QPushButton("◀ Période précédente")
        prev_btn.clicked.connect(self.on_prev_period)
        nav.addWidget(prev_btn)

        today_btn = QPushButton("Période actuelle")
        today_btn.clicked.connect(self.on_today)
        nav.addWidget(today_btn)

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

        nav.addStretch(1)

        export_btn = QPushButton("Exporter PDF")
        export_btn.clicked.connect(self.on_export_pdf)
        nav.addWidget(export_btn)

        synthesis_btn = QPushButton("Synthèse mensuelle…")
        synthesis_btn.clicked.connect(self.on_monthly_synthesis)
        nav.addWidget(synthesis_btn)

        breakdown_btn = QPushButton(f"{DIMENSION_ALL_LABELS[dimension]} — cette période…")
        breakdown_btn.clicked.connect(self.on_breakdown)
        nav.addWidget(breakdown_btn)

        layout.addLayout(nav)

        self.web_view = QWebEngineView()
        # Le bouton "Imprimer / Export PDF" du rapport (window.print()) est relayé vers
        # notre propre export PDF natif, qui fonctionne réellement dans une QWebEngineView.
        self.web_view.page().printRequested.connect(self.on_export_pdf)
        layout.addWidget(self.web_view, 1)

        self.reload_values()
        self.reload_compare_months()
        self.period_state.subscribe(self._sync_period_controls)
        self._sync_period_controls()

    # -- Rechargement des listes déroulantes --------------------------------

    def reload_values(self):
        current = self.value_combo.currentData()
        self.value_combo.blockSignals(True)
        self.value_combo.clear()
        self.value_combo.addItem(DIMENSION_ALL_LABELS[self.dimension], None)
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

    def _on_period_type_control_changed(self):
        self.period_state.set(period_type=self.period_type_combo.currentData(), offset=0)

    def _on_granularity_control_changed(self):
        self.period_state.set(granularity=self.granularity_combo.currentData())

    def on_today(self):
        self.period_state.set(offset=0)

    def on_prev_period(self):
        self.period_state.set(offset=self.period_state.offset - 1)

    def on_next_period(self):
        self.period_state.set(offset=self.period_state.offset + 1)

    def _sync_period_controls(self):
        self.period_type_combo.blockSignals(True)
        idx = self.period_type_combo.findData(self.period_state.period_type)
        if idx >= 0:
            self.period_type_combo.setCurrentIndex(idx)
        self.period_type_combo.blockSignals(False)

        self.granularity_combo.blockSignals(True)
        idx = self.granularity_combo.findData(self.period_state.granularity)
        if idx >= 0:
            self.granularity_combo.setCurrentIndex(idx)
        self.granularity_combo.blockSignals(False)

        self.refresh()

    # -- Rafraîchissement --------------------------------------------------

    def refresh(self):
        value = self.value_combo.currentData()
        period_type = self.period_state.period_type
        granularity = self.period_state.granularity

        start, end = stats.get_period(period_type, date.today(), self.period_state.offset)
        self._current_start, self._current_end = start, end
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

    # -- Export --------------------------------------------------------

    def _default_filename(self) -> str:
        value_slug = _slugify(self.value_combo.currentText())
        period_slug = _slugify(self.period_label.text())
        return f"analyse-{self.dimension}-{value_slug}-{period_slug}"

    def on_export_pdf(self):
        export_web_view_to_pdf(self, self.web_view, self._default_filename() + ".pdf")

    def on_monthly_synthesis(self):
        value = self.value_combo.currentData()
        label = self.value_combo.currentText()
        dialog = SynthesisDialog(self.conn, self.dimension, value, label, self)
        dialog.exec()

    def on_breakdown(self):
        dialog = BreakdownDialog(self.conn, self.dimension, self._current_start, self._current_end, self)
        dialog.exec()


class SynthesisDialog(QDialog):
    """Synthèse mensuelle (une ligne de totaux par mois) pour la valeur sélectionnée dans
    l'onglet d'analyse — vue "données synthétiques" complémentaire à la grille détaillée,
    exportable en PDF."""

    def __init__(self, conn, dimension: str, value, label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Synthèse mensuelle — {label}")
        self.resize(1000, 700)

        layout = QVBoxLayout(self)

        rows = stats.build_monthly_synthesis(conn, dimension, value)
        html_content = report.render_monthly_synthesis(label, rows)

        self.web_view = QWebEngineView()
        self.web_view.setHtml(html_content)
        self.web_view.page().printRequested.connect(self.on_export_pdf)
        layout.addWidget(self.web_view, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        export_btn = QPushButton("Exporter PDF")
        export_btn.clicked.connect(self.on_export_pdf)
        btn_row.addWidget(export_btn)
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def on_export_pdf(self):
        slug = _slugify(self.windowTitle())
        export_web_view_to_pdf(self, self.web_view, slug + ".pdf")


class BreakdownDialog(QDialog):
    """Comparaison de toutes les valeurs d'une dimension (tous les clients, tous les
    opérateurs ou tous les codes affaire) sur la période actuellement affichée dans
    l'onglet d'analyse — pour voir tout le monde côte à côte plutôt qu'un(e) seul(e) client/
    opérateur/code affaire à la fois."""

    def __init__(self, conn, dimension: str, period_start, period_end, parent=None):
        super().__init__(parent)
        period_str = f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"
        self.setWindowTitle(f"{DIMENSION_ALL_LABELS[dimension]} — {period_str}")
        self.resize(1100, 700)

        layout = QVBoxLayout(self)

        rows = stats.build_dimension_breakdown(conn, dimension, period_start, period_end)
        total_summary = stats.build_summary(db.calls_for_dimension(
            conn, dimension, None,
            datetime.combine(period_start, datetime.min.time()).isoformat(),
            datetime.combine(period_end, datetime.max.time()).isoformat(),
        ))
        html_content = report.render_dimension_breakdown(dimension, period_start, period_end, rows, total_summary)

        self.web_view = QWebEngineView()
        self.web_view.setHtml(html_content)
        self.web_view.page().printRequested.connect(self.on_export_pdf)
        layout.addWidget(self.web_view, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        export_btn = QPushButton("Exporter PDF")
        export_btn.clicked.connect(self.on_export_pdf)
        btn_row.addWidget(export_btn)
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def on_export_pdf(self):
        slug = _slugify(self.windowTitle())
        export_web_view_to_pdf(self, self.web_view, slug + ".pdf")


class LongTermTab(QWidget):
    """Comparaison sur le long terme : tous les mois importés en colonnes, un
    sous-ensemble d'indicateurs clés en lignes, pour un client ou un opérateur choisi."""

    def __init__(self, conn):
        super().__init__()
        self.conn = conn

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Comparer par :"))
        self.dimension_combo = QComboBox()
        self.dimension_combo.addItem("Client", "client")
        self.dimension_combo.addItem("Opérateur", "operateur")
        self.dimension_combo.currentIndexChanged.connect(self._on_dimension_changed)
        controls.addWidget(self.dimension_combo)

        controls.addWidget(QLabel("Valeur :"))
        self.value_combo = SearchableComboBox()
        self.value_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.value_combo, 1)

        export_btn = QPushButton("Exporter PDF")
        export_btn.clicked.connect(self.on_export_pdf)
        controls.addWidget(export_btn)

        layout.addLayout(controls)

        self.web_view = QWebEngineView()
        self.web_view.page().printRequested.connect(self.on_export_pdf)
        layout.addWidget(self.web_view, 1)

        self.reload_values()

    @property
    def dimension(self) -> str:
        return self.dimension_combo.currentData()

    def _on_dimension_changed(self):
        self.reload_values()

    def reload_values(self):
        current = self.value_combo.currentData()
        self.value_combo.blockSignals(True)
        self.value_combo.clear()
        self.value_combo.addItem(DIMENSION_ALL_LABELS[self.dimension], None)
        if self.dimension == "client":
            for c in db.list_clients(self.conn):
                self.value_combo.addItem(f"{c.label} ({c.sda})", c.sda)
        else:
            self.value_combo.addItem("Non attribué", "")
            for o in db.list_operators(self.conn):
                self.value_combo.addItem(f"{o.label} ({o.login})", o.login)
        idx = self.value_combo.findData(current) if current is not None else -1
        self.value_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.value_combo.blockSignals(False)
        self.refresh()

    def refresh(self):
        value = self.value_combo.currentData()
        label = self.value_combo.currentText()
        rows = stats.build_monthly_synthesis(self.conn, self.dimension, value)
        html_content = report.render_long_term_comparison(label, rows)
        self.web_view.setHtml(html_content)

    def on_export_pdf(self):
        slug = _slugify(f"comparaison-long-terme-{self.dimension}-{self.value_combo.currentText()}")
        export_web_view_to_pdf(self, self.web_view, slug + ".pdf")


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

    def __init__(self, conn, on_data_changed):
        super().__init__()
        self.conn = conn
        self.on_data_changed = on_data_changed
        layout = QVBoxLayout(self)

        actions = QHBoxLayout()
        purge_btn = QPushButton("Purger les données…")
        purge_btn.clicked.connect(self.on_purge)
        actions.addWidget(purge_btn)
        legacy_btn = QPushButton("Importer un ancien fichier (avant 2024)…")
        legacy_btn.clicked.connect(self.on_import_legacy)
        actions.addWidget(legacy_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)
        self.reload()

    def on_purge(self):
        dialog = PurgeDialog(self.conn, self)
        if dialog.exec() == QDialog.Accepted:
            self.on_data_changed()

    def on_import_legacy(self):
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un ancien journal d'appels (format sans SDA, avant 2024)",
            "",
            "Fichiers appels (*.xlsx *.xlsm *.csv)",
        )
        if not path_str:
            return
        try:
            result = importer_legacy.import_legacy_file(self.conn, Path(path_str))
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(self, APP_TITLE, f"Échec de l'import :\n{exc}")
            return

        self.on_data_changed()

        unresolved_text = ""
        if result.unresolved_names:
            top = sorted(result.unresolved_names.items(), key=lambda x: -x[1])[:10]
            lines = "\n".join(f"  • {nom} ({count} appel(s))" for nom, count in top)
            more = len(result.unresolved_names) - len(top)
            suffix = f"\n  … et {more} autre(s)" if more > 0 else ""
            unresolved_text = (
                f"\n\nClients non reconnus, rattachés à \"{legacy_aliases.PLACEHOLDER_NOM}\" "
                f"({sum(result.unresolved_names.values())} appel(s) au total) :\n{lines}{suffix}"
            )

        QMessageBox.information(
            self,
            APP_TITLE,
            (
                f"Import (ancien format) terminé.\n\n"
                f"Lignes lues : {result.total_rows}\n"
                f"Appels ajoutés : {result.inserted}\n"
                f"Déjà présents (ignorés) : {result.duplicates}\n"
                f"Lignes invalides : {result.invalid_rows}\n"
                f"Nouveaux opérateurs détectés : {len(result.new_operators)}\n\n"
                f"Rappel : pour cette période, l'attente globale ne reflète que la sonnerie "
                f"(pas de file/annonce dans ce format)."
            )
            + unresolved_text,
        )

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
        self.setMinimumWidth(480)

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
        self.date_edit.setMinimumWidth(120)
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
        self.import_status = QLabel("Aucun import effectué.")
        toolbar.addWidget(self.import_status, 1)
        root.addLayout(toolbar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.period_state = PeriodState()
        self.client_tab = AnalysisTab(self.conn, "client", "Client", self.period_state)
        self.operateur_tab = AnalysisTab(self.conn, "operateur", "Opérateur", self.period_state)
        self.code_affaire_tab = AnalysisTab(self.conn, "code_affaire", "Code affaire", self.period_state)
        self.long_term_tab = LongTermTab(self.conn)
        self.clients_listing_tab = ClientsListingTab(self.conn)
        self.operators_listing_tab = OperatorsListingTab(self.conn)
        self.imports_log_tab = ImportsLogTab(self.conn, self._refresh_all_tabs)

        self.tabs.addTab(self.client_tab, "Par client")
        self.tabs.addTab(self.operateur_tab, "Par opérateur")
        self.tabs.addTab(self.code_affaire_tab, "Par code affaire")
        self.tabs.addTab(self.long_term_tab, "Comparaison long terme")
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
        self.long_term_tab.reload_values()
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


def main():
    app = QApplication(sys.argv)
    icon = app_icon_path()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
