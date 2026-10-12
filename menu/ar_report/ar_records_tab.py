import qtawesome as fa
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableView, QHeaderView, QFrame, QAbstractItemView, QMessageBox
)

from db.connection import get_connection

ROW_LIMIT = 5000

COLUMNS = ["AR No.", "AR Date", "Customer", "Product Code", "Product Color", "Quantity / Unit"]

QUERY = """
    SELECT h.ar_no, h.ar_date, h.customer, d.prod_code, d.prod_color,
           d.quantity, d.qty_unit, h.is_canceled
    FROM tbl_ar01 h
    LEFT JOIN tbl_ar02 d ON d.ar_no = h.ar_no
    WHERE (%(q)s = ''
           OR CAST(h.ar_no AS TEXT) ILIKE %(like)s
           OR h.customer   ILIKE %(like)s
           OR d.prod_code  ILIKE %(like)s
           OR d.prod_color ILIKE %(like)s)
    ORDER BY h.ar_no DESC, d.sequence
    LIMIT %(limit)s
"""

CENTER = Qt.AlignmentFlag.AlignCenter
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
ALIGNMENTS = [CENTER, CENTER, LEFT, LEFT, LEFT, RIGHT]

CANCELED_FG = QColor("#B91C1C")
CANCELED_BG = QColor("#FEF2F2")


def _icon(name, color, active=None):
    return fa.icon(name, color=color, color_active=active or color, color_disabled="#94A3B8")


class ARTableModel(QAbstractTableModel):
    """Read-only model. Display text is prepared once; the view only asks for visible rows."""

    def __init__(self):
        super().__init__()
        self._rows = []  # each: (texts: list[str], ar_no: int, canceled: bool)

    def set_rows(self, db_rows):
        rows = []
        for ar_no, ar_date, customer, code, color, qty, unit, canceled in db_rows:
            date_txt = ar_date.strftime("%m/%d/%Y") if ar_date else ""
            qty_txt = ""
            if qty is not None:
                qty_txt = f"{float(qty):,.2f}" + (f" {unit}" if unit else "")
            texts = [str(ar_no), date_txt, customer or "", code or "", color or "", qty_txt]
            rows.append((texts, ar_no, bool(canceled)))

        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def ar_no_at(self, row):
        return self._rows[row][1]

    def text_at(self, row, col):
        return self._rows[row][0][col]

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
        texts, ar_no, canceled = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return texts[col]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return ALIGNMENTS[col]
        if role == Qt.ItemDataRole.UserRole:
            return ar_no
        if canceled:
            if role == Qt.ItemDataRole.ForegroundRole:
                return CANCELED_FG
            if role == Qt.ItemDataRole.BackgroundRole:
                return CANCELED_BG
        return None


class ARRecordsTab(QWidget):
    """AR Record: searchable record table with a selected-record summary."""

    view_requested = pyqtSignal(int)    # ar_no
    update_requested = pyqtSignal(int)  # ar_no
    close_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.model = ARTableModel()
        self._build_ui()
        self.load_records()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header: title + search
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Acknowledgement Receipts")
        title.setObjectName("HeadingTitle")
        subtitle = QLabel("Browse and search delivered items per AR record")
        subtitle.setObjectName("SubtitleLabel")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search AR no., customer, product code or color...")
        self.search_input.setMinimumWidth(360)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.load_records)
        header.addWidget(self.search_input)

        btn_search = QPushButton(" Search", icon=_icon("fa5s.search", "white"))
        btn_search.setObjectName("PrimaryButton")
        btn_search.clicked.connect(self.load_records)
        header.addWidget(btn_search)
        root.addLayout(header)

        # Summary card for the selected record
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QHBoxLayout(card)
        card_layout.setSpacing(32)
        self.lbl_ar_no = self._summary_block(card_layout, "AR NO.", stretch=0)
        self.lbl_customer = self._summary_block(card_layout, "CUSTOMER", stretch=1)
        self.lbl_ar_date = self._summary_block(card_layout, "AR DATE", stretch=0)
        root.addWidget(card)

        # Table (QTableView + model: only visible rows are rendered)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Customer
        for col, width in {0: 100, 1: 120, 3: 220, 4: 150, 5: 160}.items():
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, width)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(lambda *_: self._emit_for_selected(self.view_requested))
        root.addWidget(self.table, 1)

        # Footer: record count + actions
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("SubtitleLabel")
        footer.addWidget(self.lbl_count)
        footer.addStretch(1)

        self.btn_update = QPushButton(" Update", icon=_icon("fa5s.edit", "white"))
        self.btn_update.setObjectName("WarningButton")
        self.btn_update.clicked.connect(lambda: self._emit_for_selected(self.update_requested))

        self.btn_view = QPushButton(" View", icon=_icon("fa5s.eye", "white"))
        self.btn_view.setObjectName("SecondaryButton")
        self.btn_view.clicked.connect(lambda: self._emit_for_selected(self.view_requested))

        btn_refresh = QPushButton(" Refresh", icon=_icon("fa5s.sync-alt", "white"))
        btn_refresh.setObjectName("PrimaryButton")
        btn_refresh.clicked.connect(self.load_records)

        btn_close = QPushButton(" Close", icon=_icon("fa5s.times", "#DC2626", "white"))
        btn_close.setObjectName("DangerOutlineButton")
        btn_close.clicked.connect(self.close_requested.emit)

        for b in (self.btn_update, self.btn_view, btn_refresh, btn_close):
            footer.addWidget(b)
        root.addLayout(footer)

        self._set_actions_enabled(False)

    def _summary_block(self, layout, caption, stretch):
        box = QVBoxLayout()
        box.setSpacing(0)
        cap = QLabel(caption)
        cap.setObjectName("SummaryLabel")
        val = QLabel("—")
        val.setObjectName("SummaryValue")
        box.addWidget(cap)
        box.addWidget(val)
        layout.addLayout(box, stretch)
        return val

    # ── Data ──────────────────────────────────────────────────────────────
    def load_records(self):
        search = self.search_input.text().strip()
        params = {"q": search, "like": f"%{search}%", "limit": ROW_LIMIT}

        conn = None
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(QUERY, params)
                rows = cur.fetchall()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not load AR records:\n{e}")
            return
        finally:
            if conn:
                conn.close()

        self.table.clearSelection()
        self.model.set_rows(rows)

        suffix = f" (showing newest {ROW_LIMIT:,})" if len(rows) >= ROW_LIMIT else ""
        self.lbl_count.setText(f"{len(rows):,} record(s){suffix}")
        self._on_selection_changed()

    # ── Selection / actions ───────────────────────────────────────────────
    def _selected_row(self):
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _selected_ar_no(self):
        row = self._selected_row()
        return None if row is None else self.model.ar_no_at(row)

    def _on_selection_changed(self, *_):
        row = self._selected_row()
        if row is None:
            self.lbl_ar_no.setText("—")
            self.lbl_customer.setText("—")
            self.lbl_ar_date.setText("—")
            self._set_actions_enabled(False)
            return

        self.lbl_ar_no.setText(self.model.text_at(row, 0))
        self.lbl_customer.setText(self.model.text_at(row, 2) or "—")
        self.lbl_ar_date.setText(self.model.text_at(row, 1) or "—")
        self._set_actions_enabled(True)

    def _set_actions_enabled(self, enabled):
        self.btn_update.setEnabled(enabled)
        self.btn_view.setEnabled(enabled)

    def _emit_for_selected(self, signal):
        ar_no = self._selected_ar_no()
        if ar_no is not None:
            signal.emit(ar_no)