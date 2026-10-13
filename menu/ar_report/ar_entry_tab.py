import qtawesome as fa
from PyQt6.QtCore import Qt, QDate, QStringListModel, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView,
    QMessageBox, QDateEdit, QDoubleSpinBox, QComboBox, QCompleter
)

from db.connection import get_connection

MAX_ITEMS = 4
UNITS = ["KG.", "PC.", "PCS.", "MGS.", "GMS.", "SET.", "SETS."]
COLUMNS = ["Qty", "Unit", "Product Code", "Product Color", "Lot No.", "Note"]


def _icon(name, color, active=None):
    return fa.icon(name, color=color, color_active=active or color, color_disabled="#94A3B8")


class AREntryTab(QWidget):
    """AR Entry: customer info + up to 4 item lines, saved to tbl_ar01 / tbl_ar02."""

    saved = pyqtSignal(int)        # ar_no
    close_requested = pyqtSignal()

    def __init__(self, username="Brant"):
        super().__init__()
        self.username = username
        self.customer_model = QStringListModel(self)
        self._build_ui()
        self.reset_form()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Heading
        title = QLabel("New Acknowledgement Receipt")
        title.setObjectName("HeadingTitle")
        subtitle = QLabel("Enter the customer details, then add up to "
                          f"{MAX_ITEMS} items to the receipt")
        subtitle.setObjectName("SubtitleLabel")
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(title)
        head.addWidget(subtitle)
        root.addLayout(head)

        # Top row: customer info + summary
        top = QHBoxLayout()
        top.setSpacing(16)

        info_card, info_body = self._card("CUSTOMER INFORMATION")
        row = QHBoxLayout()
        row.setSpacing(16)
        self.txt_customer = QLineEdit()
        self.txt_customer.setPlaceholderText("Customer name")
        completer = QCompleter(self.customer_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.txt_customer.setCompleter(completer)

        self.date_ar = QDateEdit(QDate.currentDate())
        self.date_ar.setCalendarPopup(True)
        self.date_ar.setDisplayFormat("MM/dd/yyyy")

        self.txt_ar_no = QLineEdit()
        self.txt_ar_no.setObjectName("ArNumberField")
        self.txt_ar_no.setReadOnly(True)

        row.addLayout(self._field("Customer", self.txt_customer, True), 3)
        row.addLayout(self._field("AR Date", self.date_ar, True), 1)
        row.addLayout(self._field("AR Number", self.txt_ar_no), 1)
        info_body.addLayout(row)
        top.addWidget(info_card, 3)

        sum_card, sum_body = self._card("RECEIPT SUMMARY")
        srow = QHBoxLayout()
        srow.setSpacing(24)
        self.lbl_count = QLabel("0 / 4")
        self.lbl_count.setObjectName("CounterValue")
        lbl_by = QLabel(f"MBPI-IT\\{self.username}")
        lbl_by.setObjectName("InfoValue")
        srow.addLayout(self._field("No. of Items", self.lbl_count))
        srow.addLayout(self._field("Prepared By", lbl_by))
        srow.addStretch(1)
        sum_body.addLayout(srow)
        top.addWidget(sum_card, 1)
        root.addLayout(top)

        # Item details card
        item_card, item_body = self._card("ITEM DETAILS")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        self.spin_qty = QDoubleSpinBox()
        self.spin_qty.setDecimals(3)
        self.spin_qty.setRange(0, 999_999_999)
        self.spin_qty.setGroupSeparatorShown(True)
        self.spin_qty.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_qty.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(UNITS)

        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText("e.g. RA16846E")
        self.txt_color = QLineEdit()
        self.txt_color.setPlaceholderText("e.g. RED")
        self.txt_lot = QLineEdit()
        self.txt_lot.setPlaceholderText("Optional")
        self.txt_note = QLineEdit()
        self.txt_note.setPlaceholderText("Optional")

        grid.addLayout(self._field("Quantity", self.spin_qty, True), 0, 0)
        grid.addLayout(self._field("Unit", self.cmb_unit, True), 0, 1)
        grid.addLayout(self._field("Product Code", self.txt_code, True), 0, 2)
        grid.addLayout(self._field("Product Color", self.txt_color, True), 0, 3)
        grid.addLayout(self._field("Lot No.", self.txt_lot), 1, 0, 1, 2)
        grid.addLayout(self._field("Note", self.txt_note), 1, 2, 1, 2)
        for col, stretch in enumerate((1, 1, 2, 2)):
            grid.setColumnStretch(col, stretch)
        item_body.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("SubtitleLabel")
        actions.addWidget(self.lbl_hint)
        actions.addStretch(1)

        self.btn_add = QPushButton(" Add", icon=_icon("fa5s.plus", "white"))
        self.btn_add.setObjectName("PrimaryButton")
        self.btn_add.clicked.connect(self.add_item)

        self.btn_remove = QPushButton(" Remove", icon=_icon("fa5s.trash-alt", "#EF4444", "white"))
        self.btn_remove.setObjectName("DangerOutlineButton")
        self.btn_remove.clicked.connect(self.remove_item)

        self.btn_clear = QPushButton(" Clear", icon=_icon("fa5s.eraser", "#334155"))
        self.btn_clear.clicked.connect(self.clear_items)

        for b in (self.btn_add, self.btn_remove, self.btn_clear):
            actions.addWidget(b)
        item_body.addLayout(actions)
        root.addWidget(item_card)

        # Items table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Note
        for col, width in {0: 120, 1: 90, 2: 220, 3: 180, 4: 160}.items():
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, width)
        root.addWidget(self.table, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)

        btn_save = QPushButton(" Save", icon=_icon("fa5s.save", "white"))
        btn_save.setObjectName("SuccessButton")
        btn_save.clicked.connect(self.save)

        btn_new = QPushButton(" New", icon=_icon("fa5s.file-alt", "#334155"))
        btn_new.clicked.connect(self.new_receipt)

        btn_close = QPushButton(" Back", icon=_icon("ri.arrow-go-back-line", "#EF4444", "white"))
        btn_close.setObjectName("DangerOutlineButton")
        btn_close.clicked.connect(self.close_tab)

        for b in (btn_save, btn_new, btn_close):
            footer.addWidget(b)
        root.addLayout(footer)

        # Live validation / state
        refresh = lambda *_: self._refresh_state()
        self.spin_qty.valueChanged.connect(refresh)
        self.cmb_unit.currentIndexChanged.connect(refresh)
        self.txt_code.textChanged.connect(refresh)
        self.txt_color.textChanged.connect(refresh)
        self.table.itemSelectionChanged.connect(refresh)
        for w in (self.txt_code, self.txt_color, self.txt_lot, self.txt_note):
            w.returnPressed.connect(self.add_item)

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

    def _field(self, caption, widget, required=False):
        box = QVBoxLayout()
        box.setSpacing(4)
        text = caption + (' <span style="color:#EF4444">*</span>' if required else "")
        lbl = QLabel(text)
        lbl.setObjectName("FieldLabel")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(lbl)
        box.addWidget(widget)
        return box

    # ── State ─────────────────────────────────────────────────────────────
    def _refresh_state(self):
        n = self.table.rowCount()
        full = n >= MAX_ITEMS
        valid = (self.spin_qty.value() > 0
                 and bool(self.cmb_unit.currentText())
                 and bool(self.txt_code.text().strip())
                 and bool(self.txt_color.text().strip()))

        self.lbl_count.setText(f"{n} / {MAX_ITEMS}")
        self.btn_add.setEnabled(valid and not full)
        self.btn_remove.setEnabled(bool(self.table.selectedItems()))
        self.btn_clear.setEnabled(n > 0)
        self.lbl_hint.setText(
            f"Maximum of {MAX_ITEMS} items per receipt reached."
            if full else "Quantity, unit, product code and product color are required to add an item."
        )

    def has_unsaved(self):
        return bool(self.txt_customer.text().strip() or self.table.rowCount())

    def _confirm(self, title, text):
        return QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes

    # ── Items ─────────────────────────────────────────────────────────────
    def add_item(self):
        if not self.btn_add.isEnabled():
            return

        qty = self.spin_qty.value()
        values = [
            f"{qty:,.3f}",
            self.cmb_unit.currentText(),
            self.txt_code.text().strip().upper(),
            self.txt_color.text().strip().upper(),
            self.txt_lot.text().strip(),
            self.txt_note.text().strip(),
        ]

        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, text in enumerate(values):
            item = QTableWidgetItem(text)
            if c == 0:
                item.setData(Qt.ItemDataRole.UserRole, qty)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            elif c == 1:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, c, item)

        self._clear_item_fields()
        self.spin_qty.setFocus()
        self.spin_qty.selectAll()
        self._refresh_state()

    def remove_item(self):
        row = self.table.currentRow()
        if row >= 0 and self.table.selectedItems():
            self.table.removeRow(row)
            self._refresh_state()

    def clear_items(self):
        if self.table.rowCount() and not self._confirm(
                "Clear Items", "Remove all items from this receipt?"):
            return
        self.table.setRowCount(0)
        self._clear_item_fields()
        self._refresh_state()

    def _clear_item_fields(self):
        self.spin_qty.setValue(0)
        for w in (self.txt_code, self.txt_color, self.txt_lot, self.txt_note):
            w.clear()

    # ── Data ──────────────────────────────────────────────────────────────
    def _query_scalar_list(self, sql):
        conn = None
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(sql)
                return [r[0] for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

    def refresh_ar_number(self):
        res = self._query_scalar_list("SELECT COALESCE(MAX(ar_no), 0) + 1 FROM tbl_ar01")
        self.txt_ar_no.setText(f"{int(res[0]):07d}" if res else "—")

    def _load_customers(self):
        self.customer_model.setStringList(self._query_scalar_list(
            "SELECT DISTINCT customer FROM tbl_ar01 WHERE customer <> '' ORDER BY customer"))

    def save(self):
        customer = self.txt_customer.text().strip().upper()
        if not customer:
            QMessageBox.warning(self, "Missing Customer", "Please enter the customer name.")
            self.txt_customer.setFocus()
            return
        if self.btn_add.isEnabled():
            QMessageBox.warning(self, "Item Not Added",
                                "The item in the form hasn't been added yet.\n"
                                "Click Add to include it, or clear the fields first.")
            return
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "No Items", "Add at least one item before saving.")
            return

        items = []
        for r in range(self.table.rowCount()):
            items.append({
                "quantity": self.table.item(r, 0).data(Qt.ItemDataRole.UserRole),
                "qty_unit": self.table.item(r, 1).text(),
                "sequence": r + 1,
                "prod_code": self.table.item(r, 2).text(),
                "prod_color": self.table.item(r, 3).text(),
                "lot_no": self.table.item(r, 4).text(),
                "notes": self.table.item(r, 5).text(),
            })

        header = {
            "ar_date": self.date_ar.date().toPyDate(),
            "customer": customer[:128],
            "t_items": len(items),
            "encoded_by": self.username[:128],
        }

        conn = None
        try:
            conn = get_connection()
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tbl_ar01 (ar_no, ar_date, customer, t_items, encoded_by,
                                          encoded_on, is_canceled, is_printed)
                    SELECT COALESCE(MAX(ar_no), 0) + 1, %(ar_date)s::date, %(customer)s::varchar,
                           %(t_items)s::int, %(encoded_by)s::varchar, NOW(), FALSE, FALSE
                    FROM tbl_ar01
                    RETURNING ar_no
                """, header)
                ar_no = cur.fetchone()[0]

                cur.executemany("""
                    INSERT INTO tbl_ar02 (ar_no, quantity, qty_unit, sequence,
                                          prod_code, prod_color, lot_no, notes)
                    VALUES (%(ar_no)s, %(quantity)s, %(qty_unit)s, %(sequence)s,
                            %(prod_code)s, %(prod_color)s, %(lot_no)s, %(notes)s)
                """, [dict(i, ar_no=ar_no) for i in items])
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            QMessageBox.critical(self, "Save Failed", f"Could not save the receipt:\n{e}")
            return
        finally:
            if conn:
                conn.close()

        QMessageBox.information(self, "Saved", f"Acknowledgement Receipt {ar_no:07d} saved.")
        self.saved.emit(ar_no)
        self.reset_form()

    # ── Form lifecycle ────────────────────────────────────────────────────
    def reset_form(self):
        self.txt_customer.clear()
        self.date_ar.setDate(QDate.currentDate())
        self.table.setRowCount(0)
        self._clear_item_fields()
        self.cmb_unit.setCurrentIndex(0)
        self._load_customers()
        self.refresh_ar_number()
        self._refresh_state()
        self.txt_customer.setFocus()

    def new_receipt(self):
        if not self.has_unsaved() or self._confirm(
                "New Receipt", "Discard the receipt currently being entered?"):
            self.reset_form()

    def close_tab(self):
        if not self.has_unsaved() or self._confirm(
                "Close Entry", "Discard the receipt currently being entered?"):
            self.reset_form()
            self.close_requested.emit()