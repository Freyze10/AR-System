import socket

import qtawesome as fa
from PyQt6.QtCore import Qt, QDate, QStringListModel, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView,
    QMessageBox, QDateEdit, QDoubleSpinBox, QComboBox, QCompleter
)

from db.read.ar_report import (get_customers, get_next_ar_no, get_receipt, get_receipt_items,
                               get_user_fullname, get_user_hostname)
from db.write.ar_report import update_receipt, create_receipt
from db.write.audit_trail import log_action
from menu.ar_report.ar_audit import (describe_save, describe_update,
                                     normalize_item, workstation_mac)
from print.print_ar import (ARPrintPreview, TEMPLATE_PATH, TEMPLATE_WIDE_PATH,
                            build_print_data)

MAX_ITEMS = 5
UNITS = ["KG.", "PC.", "PCS.", "MGS.", "GMS.", "SET.", "SETS."]
COLUMNS = ["Qty", "Unit", "Product Code", "Product Color", "Lot No.", "Note"]

MODE_IDLE = "idle"      # nothing loaded, form locked, Save disabled
MODE_NEW = "new"        # after New: editable, Save enabled
MODE_VIEW = "view"      # record loaded, read only, Save disabled
MODE_UPDATE = "update"  # record loaded, editable, Save becomes Update

PRINT_MODES = (MODE_VIEW, MODE_UPDATE)   # modes in which the Print buttons are enabled

TITLES = {
    MODE_IDLE: ("Acknowledgement Receipt Entry",
                "Click New to create a receipt, or choose a record in the Record tab to view or update it"),
    MODE_NEW: ("New Acknowledgement Receipt",
               f"Enter the customer details, then add up to {MAX_ITEMS} items to the receipt"),
    MODE_VIEW: ("View Acknowledgement Receipt", "Read only. Click New to create another receipt"),
    MODE_UPDATE: ("Update Acknowledgement Receipt", "Change the details below, then click Update to save"),
}


def _icon(name, color, active=None):
    return fa.icon(name, color=color, color_active=active or color, color_disabled="#94A3B8")


def _force_uppercase(edit):
    """Turns everything the user types or pastes into this text box into UPPERCASE.

    textEdited is only sent when the USER changes the text (typing, pasting), not when the
    program fills the box (for example when a receipt is loaded), so loaded data is shown as saved.
    """
    def to_upper(text):
        upper = text.upper()
        if upper != text:
            position = edit.cursorPosition()      # keep the cursor where the user was typing
            edit.setText(upper)
            edit.setCursorPosition(position)

    edit.textEdited.connect(to_upper)


class AREntryTab(QWidget):
    """AR Entry: customer info + up to 5 item lines. Modes: idle / new / view / update."""

    saved = pyqtSignal(int)        # ar_no
    close_requested = pyqtSignal()

    def __init__(self, username="Brant"):
        super().__init__()
        self.username = username
        # The PC this window is running on. Only for the audit trail, never shown in Prepared By.
        self.pc_name = socket.gethostname()
        # The user's OWN hostname saved in tbl_user. This is what Prepared By shows and saves.
        self.db_hostname = self._load_db_hostname()
        self.mode = MODE_IDLE
        self._current_ar_no = None
        self._loaded_snapshot = None
        self._loaded = None
        self._filling = False        # True while fields are set by code, not by the user
        self._item_dirty = False     # True when the user edited the item fields
        self.customer_model = QStringListModel(self)
        self._build_ui()
        self.reset_form()
        self.new_receipt()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Heading
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("HeadingTitle")
        self.lbl_subtitle = QLabel("")
        self.lbl_subtitle.setObjectName("SubtitleLabel")
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(self.lbl_title)
        head.addWidget(self.lbl_subtitle)
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
        self.lbl_count = QLabel(f"0 / {MAX_ITEMS}")
        self.lbl_count.setObjectName("CounterValue")
        self.lbl_by = QLabel("")
        self.lbl_by.setObjectName("InfoValue")
        srow.addLayout(self._field("No. of Items", self.lbl_count))
        srow.addLayout(self._field("Prepared By", self.lbl_by))
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
        self.spin_qty.setDecimals(2)
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

        # Everything typed in the text boxes becomes UPPERCASE (customer, code, color, lot, note)
        for edit in (self.txt_customer, self.txt_code, self.txt_color, self.txt_lot, self.txt_note):
            _force_uppercase(edit)

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

        # Replaces the selected row with what is in the fields (same position in the table)
        self.btn_update_item = QPushButton(" Update Item", icon=_icon("fa5s.edit", "white"))
        self.btn_update_item.setObjectName("WarningButton")
        self.btn_update_item.clicked.connect(self.update_item)

        self.btn_remove = QPushButton(" Remove", icon=_icon("fa5s.trash-alt", "#EF4444", "white"))
        self.btn_remove.setObjectName("DangerOutlineButton")
        self.btn_remove.clicked.connect(self.remove_item)

        self.btn_clear = QPushButton(" Clear", icon=_icon("fa5s.eraser", "#334155"))
        self.btn_clear.clicked.connect(self.clear_items)

        for b in (self.btn_add, self.btn_update_item, self.btn_remove, self.btn_clear):
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

        # Print Wide uses the template with the wider product code column.
        # The buttons use a lambda because clicked sends a True/False value we do not want in `wide`.
        self.btn_print_wide = QPushButton(" Print Wide", icon=_icon("fa5s.print", "white"))
        self.btn_print_wide.setObjectName("SecondaryButton")
        self.btn_print_wide.clicked.connect(lambda: self.print_receipt(wide=True))

        self.btn_print = QPushButton(" Print", icon=_icon("fa5s.print", "white"))
        self.btn_print.setObjectName("SecondaryButton")
        self.btn_print.clicked.connect(lambda: self.print_receipt())

        self.btn_new = QPushButton(" New", icon=_icon("fa5s.file-alt", "white"))
        self.btn_new.setObjectName("InfoButton")
        self.btn_new.clicked.connect(self.new_receipt)

        self.btn_save = QPushButton(" Save", icon=_icon("fa5s.save", "white"))
        self.btn_save.setObjectName("SuccessButton")
        self.btn_save.clicked.connect(self.save)

        btn_close = QPushButton(" Back", icon=_icon("ri.arrow-go-back-line", "#EF4444", "white"))
        btn_close.setObjectName("DangerOutlineButton")
        btn_close.clicked.connect(self.close_tab)

        for b in (self.btn_print_wide, self.btn_print, self.btn_new, self.btn_save, btn_close):
            footer.addWidget(b)
        root.addLayout(footer)

        # Widgets that are locked outside New / Update mode
        self._inputs = [self.txt_customer, self.date_ar, self.spin_qty, self.cmb_unit,
                        self.txt_code, self.txt_color, self.txt_lot, self.txt_note]

        # Live validation / state
        self.spin_qty.valueChanged.connect(self._on_field_changed)
        self.cmb_unit.currentIndexChanged.connect(self._on_field_changed)
        for w in (self.txt_code, self.txt_color, self.txt_lot, self.txt_note):
            w.textChanged.connect(self._on_field_changed)
            w.returnPressed.connect(self.add_item)
        self.table.itemSelectionChanged.connect(self._on_row_selected)

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

    def _items_from_table(self):
        return [normalize_item(self.table.item(r, 0).data(Qt.ItemDataRole.UserRole),
                               *(self.table.item(r, c).text() for c in range(1, 6)))
                for r in range(self.table.rowCount())]

    # ── Prepared By ───────────────────────────────────────────────────────
    def _load_db_hostname(self):
        """The hostname saved for this user in the database (not the name of this PC)."""
        try:
            return get_user_hostname(self.username)
        except Exception:
            return None

    def _me(self):
        """'Hostname\\Username' with the user's own hostname from the database.

        This is what Prepared By shows and what is saved with the receipt. If the user has
        no hostname saved yet, it is just the username.
        """
        return f"{self.db_hostname}\\{self.username}" if self.db_hostname else self.username

    def _prepared_by_fullname(self):
        """The full name of whoever is written in Prepared By, for the printed form.

        Prepared By looks like 'Hostname\\Username'. We split it at the backslash, find the
        user with that hostname and username in tbl_user, and return 'First Last'.
        If nobody matches (for example old records), the text is returned as it is.
        """
        text = self.lbl_by.text()
        # No backslash in the text: hostname is "" and username is the whole text
        hostname, _, username = text.rpartition("\\")
        try:
            return get_user_fullname(hostname.strip(), username.strip()) or text
        except Exception:
            return text

    # ── Mode / state ──────────────────────────────────────────────────────
    def _set_mode(self, mode):
        self.mode = mode
        editable = mode in (MODE_NEW, MODE_UPDATE)
        for w in self._inputs:
            w.setEnabled(editable)

        title, subtitle = TITLES[mode]
        if mode in (MODE_VIEW, MODE_UPDATE) and self._current_ar_no is not None:
            title += f"  {self._current_ar_no:07d}"
        self.lbl_title.setText(title)
        self.lbl_subtitle.setText(subtitle)
        self.btn_save.setText(" Update" if mode == MODE_UPDATE else " Save")
        self._refresh_state()

    def _fields_valid(self):
        return (self.spin_qty.value() > 0
                and bool(self.cmb_unit.currentText())
                and bool(self.txt_code.text().strip())
                and bool(self.txt_color.text().strip()))

    def _refresh_state(self):
        n = self.table.rowCount()
        editable = self.mode in (MODE_NEW, MODE_UPDATE)
        full = n >= MAX_ITEMS

        self.lbl_count.setText(f"{n} / {MAX_ITEMS}")
        row_selected = self._selected_row() is not None
        self.btn_add.setEnabled(editable and self._fields_valid() and not full)
        # Needs a selected row and valid fields; works even when the receipt is full
        self.btn_update_item.setEnabled(editable and row_selected and self._fields_valid())
        self.btn_remove.setEnabled(editable and row_selected)
        self.btn_clear.setEnabled(editable and n > 0)
        self.btn_save.setEnabled(editable)

        # Both print buttons follow the same rule
        can_print = self.mode in PRINT_MODES and self._current_ar_no is not None and n > 0
        self.btn_print.setEnabled(can_print)
        self.btn_print_wide.setEnabled(can_print)

        if self.mode == MODE_IDLE:
            hint = "Click New to start a receipt."
        elif self.mode == MODE_VIEW:
            hint = "Viewing only. Select an item row to see its details."
        elif row_selected:
            hint = "Change the fields, then click Update Item to replace the selected row."
        elif full:
            hint = f"Maximum of {MAX_ITEMS} items per receipt reached."
        else:
            hint = "Quantity, unit, product code and product color are required to add an item."
        self.lbl_hint.setText(hint)

    def _on_field_changed(self, *_):
        if not self._filling:
            self._item_dirty = True
        self._refresh_state()

    def _snapshot(self):
        items = tuple(
            tuple(self.table.item(r, c).text() for c in range(len(COLUMNS)))
            for r in range(self.table.rowCount()))
        return (self.txt_customer.text().strip().upper(), self.date_ar.date().toPyDate(), items)

    def has_unsaved(self):
        if self.mode == MODE_NEW:
            return bool(self.txt_customer.text().strip() or self.table.rowCount())
        if self.mode == MODE_UPDATE:
            return self._snapshot() != self._loaded_snapshot
        return False

    def _confirm(self, title, text):
        return QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes

    # ── Item fields / table ───────────────────────────────────────────────
    def _set_fields(self, qty=0.0, unit=None, code="", color="", lot="", note=""):
        """Set the item fields from code (not user edits). Empty call = clear."""
        self._filling = True
        try:
            self.spin_qty.setValue(qty)
            if unit:
                idx = self.cmb_unit.findText(unit)
                if idx < 0:
                    self.cmb_unit.addItem(unit)
                    idx = self.cmb_unit.count() - 1
                self.cmb_unit.setCurrentIndex(idx)
            self.txt_code.setText(code)
            self.txt_color.setText(color)
            self.txt_lot.setText(lot)
            self.txt_note.setText(note)
        finally:
            self._filling = False
        self._item_dirty = False
        self._refresh_state()

    def _selected_row(self):
        items = self.table.selectedItems()
        return items[0].row() if items else None

    def _on_row_selected(self):
        row = self._selected_row()
        if row is not None:
            self._set_fields(
                self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) or 0.0,
                self.table.item(row, 1).text(),
                self.table.item(row, 2).text(),
                self.table.item(row, 3).text(),
                self.table.item(row, 4).text(),
                self.table.item(row, 5).text(),
            )
        else:
            self._refresh_state()

    def _write_row(self, r, qty, unit, code, color, lot, note):
        """Put the values into table row r. Cells that already exist are changed in place,
        so an updated row keeps its position."""
        values = [f"{qty:,.2f}", unit, code, color, lot, note]
        for c, text in enumerate(values):
            item = self.table.item(r, c)
            if item is None:                      # a brand new row: create its cells
                item = QTableWidgetItem()
                if c == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif c == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)
            item.setText(text)
            if c == 0:
                item.setData(Qt.ItemDataRole.UserRole, qty)   # the exact number, used when saving

    def _append_row(self, qty, unit, code, color, lot, note):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._write_row(r, qty, unit, code, color, lot, note)

    def add_item(self):
        if not self.btn_add.isEnabled():
            return

        self._append_row(
            self.spin_qty.value(),
            self.cmb_unit.currentText(),
            self.txt_code.text().strip().upper(),
            self.txt_color.text().strip().upper(),
            self.txt_lot.text().strip(),
            self.txt_note.text().strip(),
        )
        self.table.clearSelection()
        self._set_fields()
        self.spin_qty.setFocus()
        self.spin_qty.selectAll()

    def update_item(self):
        """Replace the selected row with the values in the item fields (same position)."""
        row = self._selected_row()
        if row is None or not self.btn_update_item.isEnabled():
            return

        self._write_row(
            row,
            self.spin_qty.value(),
            self.cmb_unit.currentText(),
            self.txt_code.text().strip().upper(),
            self.txt_color.text().strip().upper(),
            self.txt_lot.text().strip(),
            self.txt_note.text().strip(),
        )
        self.table.clearSelection()
        self._set_fields()
        self.spin_qty.setFocus()
        self.spin_qty.selectAll()

    def remove_item(self):
        row = self._selected_row()
        if row is None:
            return
        self.table.removeRow(row)   # the fields keep the removed item's values for re-editing
        self.table.clearSelection()
        self._refresh_state()

    def clear_items(self):
        if self.table.rowCount() and not self._confirm(
                "Clear Items", "Remove all items from this receipt?"):
            return
        self.table.setRowCount(0)
        self._set_fields()

    # ── Data ──────────────────────────────────────────────────────────────
    def refresh_ar_number(self):
        if self.mode != MODE_NEW:
            return
        try:
            self.txt_ar_no.setText(f"{int(get_next_ar_no()):07d}")
        except Exception:
            self.txt_ar_no.setText("—")

    def _load_customers(self):
        try:
            self.customer_model.setStringList(get_customers())
        except Exception:
            self.customer_model.setStringList([])

    def load_record(self, ar_no, mode):
        """Open an existing receipt in MODE_VIEW or MODE_UPDATE. Returns True when loaded."""
        if self.has_unsaved() and not self._confirm(
                "Discard Changes", "Discard the receipt currently being entered?"):
            return False

        try:
            header = get_receipt(ar_no)
            items = get_receipt_items(ar_no)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not load receipt {ar_no}:\n{e}")
            return False
        if not header:
            QMessageBox.warning(self, "Not Found", f"Receipt {ar_no} no longer exists.")
            return False

        _, ar_date, customer, encoded_by = header
        self._clear_all()
        self._load_customers()
        self.txt_customer.setText(customer or "")
        if ar_date:
            self.date_ar.setDate(QDate(ar_date.year, ar_date.month, ar_date.day))
        self.txt_ar_no.setText(f"{ar_no:07d}")
        self.lbl_by.setText(encoded_by or "—")

        for qty, unit, code, color, lot, note in items:
            self._append_row(float(qty or 0), unit or "", code or "", color or "", lot or "", note or "")

        self._current_ar_no = ar_no
        self._loaded_snapshot = self._snapshot()
        self._loaded = {"customer": customer or "", "ar_date": ar_date,
                        "items": self._items_from_table()}
        self._set_mode(mode)
        return True

    def save(self):
        if self.mode not in (MODE_NEW, MODE_UPDATE):
            return

        customer = self.txt_customer.text().strip().upper()
        if not customer:
            QMessageBox.warning(self, "Missing Customer", "Please enter the customer name.")
            self.txt_customer.setFocus()
            return
        if self._item_dirty and self._fields_valid():
            if self._selected_row() is not None:
                QMessageBox.warning(self, "Item Not Updated",
                                    "The selected item was changed but not updated yet.\n"
                                    "Click Update Item to apply the change.")
            else:
                QMessageBox.warning(self, "Item Not Added",
                                    "The item in the form hasn't been added yet.\n"
                                    "Click Add to include it, or clear the item fields.")
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
            # 'Hostname\Username': saved as encoded_by (new receipt) or updated_by (update).
            # It is the logged-in user, not the Prepared By text, which shows the original
            # preparer while a receipt is being updated.
            "user": self._me()[:128],
        }

        updating = self.mode == MODE_UPDATE
        try:
            if updating:
                ar_no = self._current_ar_no
                update_receipt(ar_no, header, items)
            else:
                ar_no = create_receipt(header, items)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save the receipt:\n{e}")
            return

        if updating:
            new = {"customer": header["customer"], "ar_date": header["ar_date"],
                   "items": self._items_from_table()}
            log_action("UPDATED", describe_update(ar_no, self._loaded, new),
                       username=self.username, mac_address=workstation_mac())
        else:
            log_action("SAVED", describe_save(ar_no, header["customer"], len(items)),
                       username=self.username, mac_address=workstation_mac())

        QMessageBox.information(
            self, "Saved",
            f"Acknowledgement Receipt {ar_no:07d} {'updated' if updating else 'saved'}.")
        self.saved.emit(ar_no)                       # refreshes the list in the Record tab
        self._continue_with_saved(ar_no, header)     # stay on this receipt, ready to print or update again
        if updating:
            self.close_requested.emit()   # back to the Record tab

    def _continue_with_saved(self, ar_no, header):
        """Keeps the receipt that was just saved on screen, as if it was opened with Update.

        That way it can be printed right away (Print is enabled in Update mode), and changing
        it again and clicking Update saves those changes to the same receipt.
        """
        self._current_ar_no = ar_no
        self.txt_ar_no.setText(f"{ar_no:07d}")
        self.txt_customer.setText(header["customer"])     # shown exactly as it was saved

        # The form is now the saved version: it is what "unsaved changes" is compared with,
        # and what the next update's audit text compares against
        self._loaded_snapshot = self._snapshot()
        self._loaded = {"customer": header["customer"], "ar_date": header["ar_date"],
                        "items": self._items_from_table()}

        self.table.clearSelection()
        self._set_fields()                                # empty item fields, nothing selected
        self._set_mode(MODE_UPDATE)                       # title, Update button and Print buttons

    # ── Printing ──────────────────────────────────────────────────────────
    def print_receipt(self, wide=False):
        """Open the print preview for the receipt shown in the form.

        wide=True uses the template with the wider product code column.
        """
        if self.mode not in PRINT_MODES or self._current_ar_no is None:
            return
        # While updating, the print shows what is on screen, which may not be saved yet
        if self.mode == MODE_UPDATE and self.has_unsaved() and not self._confirm(
                "Unsaved Changes",
                "This receipt has changes that are not saved yet.\nPrint it as shown now?"):
            return

        rows = [
            (self.table.item(r, 0).data(Qt.ItemDataRole.UserRole),
             *(self.table.item(r, c).text() for c in range(1, 6)))
            for r in range(self.table.rowCount())
        ]
        data = build_print_data(
            ar_no=self._current_ar_no,
            ar_date=self.date_ar.date().toPyDate(),
            customer=self.txt_customer.text(),
            prepared_by=self._prepared_by_fullname(),   # the full name, not 'Hostname\Username'
            items=rows,
        )
        preview = ARPrintPreview(data, parent=self.window(),
                                 template_path=TEMPLATE_WIDE_PATH if wide else TEMPLATE_PATH)
        # The preview tells us when the receipt was really sent to the printer
        preview.printed.connect(lambda printer, d=data: self._log_print(d, printer))
        preview.show()

    def _log_print(self, data, printer):
        """Audit trail entry for a receipt that was sent to the printer."""
        log_action("PRINT",
                   f"AR NO: {data['ar_no']} for customer {data['customer']} "
                   f"with {data['item_count']} item(s) printed on {printer}",
                   username=self.username, mac_address=workstation_mac())

    # ── Form lifecycle ────────────────────────────────────────────────────
    def _clear_all(self):
        self.txt_customer.clear()
        self.date_ar.setDate(QDate.currentDate())
        self.table.setRowCount(0)
        self._filling = True
        try:
            self.cmb_unit.clear()
            self.cmb_unit.addItems(UNITS)
        finally:
            self._filling = False
        self._set_fields()
        self.lbl_by.setText(self._me())

    def reset_form(self):
        """Back to the idle, locked state."""
        self._clear_all()
        self._current_ar_no = None
        self._loaded_snapshot = None
        self.txt_ar_no.setText("—")
        self._set_mode(MODE_IDLE)

    def new_receipt(self):
        if self.has_unsaved() and not self._confirm(
                "New Receipt", "Discard the receipt currently being entered?"):
            return
        self._clear_all()
        self._current_ar_no = None
        self._loaded_snapshot = None
        self._load_customers()
        self._set_mode(MODE_NEW)
        self.refresh_ar_number()
        self.txt_customer.setFocus()

    def close_tab(self):
        if self.has_unsaved() and not self._confirm(
                "Back", "Discard the receipt currently being entered?"):
            return
        self.reset_form()
        self.close_requested.emit()