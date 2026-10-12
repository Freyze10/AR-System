import qtawesome as fa
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView,
    QMessageBox
)

from db.connection import get_connection

ROW_LIMIT = 1000

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


class AcknowledgementReceiptWidget(QWidget):
    """AR Report: searchable record table with a selected-record summary."""

    view_requested = pyqtSignal(int)    # ar_no
    update_requested = pyqtSignal(int)  # ar_no
    close_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
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

        btn_search = QPushButton(" Search", icon=fa.icon("fa5s.search", color="white"))
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

        # Table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)

        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Customer
        for col, width in {0: 100, 1: 120, 3: 220, 4: 150, 5: 150}.items():
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, width)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self._emit_for_selected(self.view_requested))
        root.addWidget(self.table, 1)

        # Footer: record count + actions
        footer = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("SubtitleLabel")
        footer.addWidget(self.lbl_count)
        footer.addStretch(1)

        self.btn_update = QPushButton(" Update", icon=fa.icon("fa5s.edit", color="#334155"))
        self.btn_update.clicked.connect(lambda: self._emit_for_selected(self.update_requested))

        self.btn_view = QPushButton(" View", icon=fa.icon("fa5s.eye", color="white"))
        self.btn_view.setObjectName("SecondaryButton")
        self.btn_view.clicked.connect(lambda: self._emit_for_selected(self.view_requested))

        btn_refresh = QPushButton(" Refresh", icon=fa.icon("fa5s.sync-alt", color="white"))
        btn_refresh.setObjectName("PrimaryButton")
        btn_refresh.clicked.connect(self.load_records)

        btn_close = QPushButton(" Close", icon=fa.icon("fa5s.times", color="#334155"))
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

        self._populate(rows)

    def _populate(self, rows):
        self.table.setUpdatesEnabled(False)
        self.table.clearSelection()
        self.table.setRowCount(len(rows))

        for r, (ar_no, ar_date, customer, code, color, qty, unit, canceled) in enumerate(rows):
            date_txt = ar_date.strftime("%m/%d/%Y") if ar_date else ""
            qty_txt = ""
            if qty is not None:
                qty_txt = f"{float(qty):,.2f}" + (f" {unit}" if unit else "")

            values = [str(ar_no), date_txt, customer or "", code or "", color or "", qty_txt]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, ar_no)
                if c in (0, 1):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                elif c == 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if canceled:
                    item.setForeground(QColor("#EF4444"))
                    font = item.font()
                    font.setStrikeOut(True)
                    item.setFont(font)
                self.table.setItem(r, c, item)

        self.table.setUpdatesEnabled(True)

        suffix = f" (showing first {ROW_LIMIT})" if len(rows) >= ROW_LIMIT else ""
        self.lbl_count.setText(f"{len(rows):,} record(s){suffix}")
        self._on_selection_changed()

    # ── Selection / actions ───────────────────────────────────────────────
    def _selected_ar_no(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _on_selection_changed(self):
        ar_no = self._selected_ar_no()
        if ar_no is None:
            self.lbl_ar_no.setText("—")
            self.lbl_customer.setText("—")
            self.lbl_ar_date.setText("—")
            self._set_actions_enabled(False)
            return

        row = self.table.currentRow()
        self.lbl_ar_no.setText(str(ar_no))
        self.lbl_customer.setText(self.table.item(row, 2).text() or "—")
        self.lbl_ar_date.setText(self.table.item(row, 1).text() or "—")
        self._set_actions_enabled(True)

    def _set_actions_enabled(self, enabled):
        self.btn_update.setEnabled(enabled)
        self.btn_view.setEnabled(enabled)

    def _emit_for_selected(self, signal):
        ar_no = self._selected_ar_no()
        if ar_no is not None:
            signal.emit(ar_no)