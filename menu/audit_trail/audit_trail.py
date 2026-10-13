import csv

import qtawesome as fa
from PyQt6.QtCore import Qt, QAbstractTableModel, QDate, QEvent, QModelIndex, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableView,
    QHeaderView, QFrame, QAbstractItemView, QMessageBox, QDateEdit, QComboBox,
    QFileDialog, QApplication
)

from db.read.audit_trail import SEARCH_COLUMNS, get_records

ROW_LIMIT = 1000

COLUMNS = ["Timestamp", "Workstation", "Action", "Details", "IP Address",
           "User MAC", "Workstation MAC"]
DETAILS_COL = 3
MIN_DETAILS = 240
FIXED_WIDTHS = {0: 185, 1: 170, 2: 110, 4: 115, 5: 150, 6: 150}

LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def _icon(name, color, active=None):
    return fa.icon(name, color=color, color_active=active or color, color_disabled="#94A3B8")


def row_texts(db_row):
    """One database row -> list of display strings (also used by the CSV export)."""
    logged_at, workstation, action, details, ip, user_mac, ws_mac = db_row
    return [
        logged_at.strftime("%m/%d/%Y %I:%M:%S %p") if logged_at else "",
        workstation or "",
        action or "",
        details or "",
        ip or "",
        user_mac or "",
        ws_mac or "",
    ]


class AuditTableModel(QAbstractTableModel):
    """Read-only model. Display text is prepared once."""

    def __init__(self):
        super().__init__()
        self._rows = []

    def set_rows(self, db_rows):
        rows = [row_texts(r) for r in db_rows]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return LEFT
        return None


class AuditTrailWidget(QWidget):
    """Audit Trail: searchable, date-filtered log with CSV export."""

    def __init__(self):
        super().__init__()
        self.model = AuditTableModel()

        # Waits a moment after the user stops typing / picking before querying
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(350)
        self._reload_timer.timeout.connect(lambda: self.load_records(warn=False))

        # Re-measures row heights after the Details column changes width (word wrap)
        self._row_timer = QTimer(self)
        self._row_timer.setSingleShot(True)
        self._row_timer.setInterval(120)
        self._row_timer.timeout.connect(self.table_resize_rows)

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Heading
        title = QLabel("Audit Trail")
        title.setObjectName("HeadingTitle")
        subtitle = QLabel("Who did what, from which workstation, and when")
        subtitle.setObjectName("SubtitleLabel")
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(title)
        head.addWidget(subtitle)
        root.addLayout(head)

        # Search & filter card
        card, body = self._card("SEARCH & FILTER")
        row = QHBoxLayout()
        row.setSpacing(16)

        self.cmb_column = QComboBox()
        for label, key in SEARCH_COLUMNS:
            self.cmb_column.addItem(label, key)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Type to search...")
        self.txt_search.setClearButtonEnabled(True)

        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("MM/dd/yyyy")

        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("MM/dd/yyyy")

        row.addLayout(self._field("Search In", self.cmb_column), 1)
        row.addLayout(self._field("Search", self.txt_search), 3)
        row.addLayout(self._field("From", self.date_from), 1)
        row.addLayout(self._field("To", self.date_to), 1)
        body.addLayout(row)
        root.addWidget(card)

        self.txt_search.returnPressed.connect(lambda: self.load_records())
        self.txt_search.textChanged.connect(self._schedule_reload)
        self.cmb_column.currentIndexChanged.connect(self._on_column_changed)
        self.date_from.dateChanged.connect(self._schedule_reload)
        self.date_to.dateChanged.connect(self._schedule_reload)

        # Table
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setMinimumSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        for col in range(len(COLUMNS)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col, width in FIXED_WIDTHS.items():
            self.table.setColumnWidth(col, width)
        self.table.setColumnWidth(DETAILS_COL, 400)

        # Details takes whatever width is left (never below MIN_DETAILS); wrapped
        # rows are re-measured whenever that width changes.
        self.table.viewport().installEventFilter(self)
        hdr.sectionResized.connect(self._on_section_resized)
        root.addWidget(self.table, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("SubtitleLabel")
        footer.addWidget(self.lbl_count)
        footer.addStretch(1)

        self.btn_export = QPushButton(" Export", icon=_icon("fa5s.download", "white"))
        self.btn_export.setObjectName("SecondaryButton")
        self.btn_export.clicked.connect(self.export_csv)

        btn_refresh = QPushButton(" Refresh", icon=_icon("fa5s.sync-alt", "white"))
        btn_refresh.setObjectName("PrimaryButton")
        btn_refresh.clicked.connect(lambda: self.load_records())

        footer.addWidget(self.btn_export)
        footer.addWidget(btn_refresh)
        root.addLayout(footer)

    def _card(self, title):
        frame = QFrame()
        frame.setObjectName("Card")
        body = QVBoxLayout(frame)
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(12)
        lbl = QLabel(title)
        lbl.setObjectName("CardTitle")
        body.addWidget(lbl)
        return frame, body

    def _field(self, caption, widget):
        box = QVBoxLayout()
        box.setSpacing(4)
        lbl = QLabel(caption)
        lbl.setObjectName("FieldLabel")
        box.addWidget(lbl)
        box.addWidget(widget)
        return box

    # ── Column sizing / word wrap ─────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self.table.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_details()
        return super().eventFilter(obj, event)

    def _fit_details(self):
        hdr = self.table.horizontalHeader()
        others = sum(hdr.sectionSize(c) for c in range(len(COLUMNS)) if c != DETAILS_COL)
        free = self.table.viewport().width() - others
        self.table.setColumnWidth(DETAILS_COL, max(MIN_DETAILS, free))

    def _on_section_resized(self, index, _old, _new):
        if index == DETAILS_COL:
            self._row_timer.start()

    def table_resize_rows(self):
        self.table.resizeRowsToContents()

    # ── Data ──────────────────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        if not event.spontaneous():     # shown by navigation, not by minimize/restore
            self.load_records(warn=False)

    def _schedule_reload(self, *_):
        self._reload_timer.start()

    def _on_column_changed(self, *_):
        if self.txt_search.text().strip():
            self._schedule_reload()

    def _read_filters(self, warn):
        d_from = self.date_from.date().toPyDate()
        d_to = self.date_to.date().toPyDate()
        if d_from > d_to:
            if warn:
                QMessageBox.warning(self, "Invalid Dates",
                                    "The 'From' date is later than the 'To' date.")
            else:
                self.lbl_count.setText("The 'From' date is later than the 'To' date.")
            return None
        return {
            "search": self.txt_search.text().strip(),
            "column": self.cmb_column.currentData(),
            "date_from": d_from,
            "date_to": d_to,
        }

    def load_records(self, warn=True):
        self._reload_timer.stop()
        filters = self._read_filters(warn)
        if filters is None:
            return

        try:
            rows = get_records(limit=ROW_LIMIT, **filters)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not load the audit trail:\n{e}")
            return

        self.table.clearSelection()
        self.model.set_rows(rows)
        self.table.resizeRowsToContents()

        suffix = f" (showing newest {ROW_LIMIT:,}, export for all)" if len(rows) >= ROW_LIMIT else ""
        self.lbl_count.setText(f"{len(rows):,} record(s){suffix}")
        self.btn_export.setEnabled(len(rows) > 0)

    # ── Export ────────────────────────────────────────────────────────────
    def export_csv(self):
        """Exports every record matching the current filters (not just the first 1,000)."""
        filters = self._read_filters(warn=True)
        if filters is None:
            return

        default = f"audit_trail_{filters['date_from']:%Y%m%d}_{filters['date_to']:%Y%m%d}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export Audit Trail", default,
                                              "CSV Files (*.csv)")
        if not path:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            rows = get_records(limit=None, **filters)
            # utf-8-sig so Excel opens it with the right encoding
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(COLUMNS)
                for r in rows:
                    writer.writerow(row_texts(r))
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Export Failed", f"Could not export the audit trail:\n{e}")
            return
        QApplication.restoreOverrideCursor()

        QMessageBox.information(self, "Exported", f"{len(rows):,} record(s) saved to:\n{path}")