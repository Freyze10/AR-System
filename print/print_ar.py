"""AR print preview.

The big picture:
  1. The entry tab gives us the receipt data (header + items).
  2. We open the Excel template (ar_template.xlsx) in a hidden Excel and fill in its cells.
  3. We save the filled copy as an .xlsx file and also export it as a PDF.
  4. The window shows that PDF as the preview. The .xlsx is only sent to the printer
     (through Excel) when the user clicks Print.

Excel is controlled through COM (win32com), so this only works on Windows with Excel installed.
"""
import os
import shutil
import sys
import tempfile

import pythoncom                     # needed to use COM from a background thread
import qtawesome as fa
import win32com.client               # lets Python control Excel
import win32print                    # lists printers / changes the default printer
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

# Where the template lives. When the app is packaged with PyInstaller the files are
# unpacked into sys._MEIPASS; otherwise we use the folder of this file.
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, "ar_template.xlsx")

# ── Template layout (ar_template.xlsx) ────────────────────────────────────
# Excel cell address for each header value on the form.
HEADER_CELLS = {
    "ar_no": "M4",
    "ar_date": "O7",
    "customer": "C7",
    "prepared_by": "D24",
}
# These two can be long, so Excel shrinks their font to fit instead of cutting the text.
SHRINK_HEADERS = ("customer", "prepared_by")

# The item table on the form: rows 9 to 21 (13 rows). Each item uses one or more rows.
FIRST_ROW, LAST_ROW = 9, 21

# Column letters of each field. A pair like ("C", "E") means "merge column C to E",
# so the text has the width of the whole merged block.
QTY_COL = "B"
UNIT_COLS = ("C", "E")             # merged, centered
CODE_COLS = ("F", "H")             # merged, centered
COLOR_COLS = ("I", "J")            # merged, left aligned
LOT_COLS = ("K", "Q")              # merged, left aligned
NOTE_COLS = ("B", "P")             # merged, left aligned, indented, placed on the rows after the item
NOTE_INDENT = 9                   # how far the note is pushed to the right (Excel indent levels)
FOOTER_COLS = ("B", "Q")           # merged, centered, placed right after the last item row
FOOTER_TEXT = "*****NOTHING FOLLOWS*****"

# Extra space (in points) kept free when checking whether a piece of text fits in a cell.
FIT_MARGIN_PTS = 2.0

# Excel's numbers for alignment options (from the Excel object model).
XL_CENTER, XL_LEFT, XL_BOTTOM = -4108, -4131, -4107


# ── Data ──────────────────────────────────────────────────────────────────
def build_print_data(ar_no, ar_date, customer, prepared_by, items):
    """Turns what the entry tab shows into a plain dict the template code uses.

    items: [(qty, unit, prod_code, prod_color, lot_no, notes), ...] (the entry table rows)
    """
    return {
        "ar_no": f"{int(ar_no):07d}",                                # 12435 -> "0012435"
        "ar_date": ar_date.strftime("%m/%d/%Y") if ar_date else "",
        "customer": (customer or "").strip(),
        "prepared_by": prepared_by or "",
        "item_count": len(items),
        "items": [
            {
                "qty": float(qty or 0),
                "unit": unit or "",
                "prod_code": code or "",
                "prod_color": color or "",
                "lot_no": lot or "",
                "notes": note or "",
            }
            for qty, unit, code, color, lot, note in items
        ],
    }


# ── Layout logic (no Excel needed) ────────────────────────────────────────
def split_to_fit(text, fits):
    """Splits text into lines so that every line passes fits(line).

    fits(line) is a function that says whether the line is narrow enough for the cell.
    We split on spaces. A single word that is longer than a whole line is cut by
    characters, so nothing is ever lost. Empty text gives [].
    """
    lines, current = [], ""
    for word in (text or "").split():
        # Try to add the word to the line we are building
        trial = f"{current} {word}" if current else word
        if fits(trial):
            current = trial
            continue
        # It does not fit: close the current line and start a new one with this word
        if current:
            lines.append(current)
            current = ""
        if fits(word):
            current = word
            continue
        # The word alone is wider than a line: break it character by character
        chunk = ""
        for ch in word:
            if fits(chunk + ch):
                chunk += ch
            else:
                if chunk:
                    lines.append(chunk)
                chunk = ch
        current = chunk
    if current:
        lines.append(current)
    return lines


def plan_rows(items, code_fits, lot_fits, note_fits):
    """Decides which table rows the receipt needs.

    An item takes one "detail" row, or more when its product code or lot number is too
    long and wraps onto extra lines. After the detail rows, each line of the item's
    note gets its own "note" row.
    """
    rows = []
    for item in items:
        code_lines = split_to_fit(item["prod_code"], code_fits)
        lot_lines = split_to_fit(item["lot_no"], lot_fits)
        # The item needs as many detail rows as its longest wrapped field (at least 1)
        for k in range(max(len(code_lines), len(lot_lines), 1)):
            rows.append({
                "type": "detail",
                "first": k == 0,                     # first row also holds qty / unit / color
                "item": item,
                "code": code_lines[k] if k < len(code_lines) else None,
                "lot": lot_lines[k] if k < len(lot_lines) else None,
            })
        for line in split_to_fit(item["notes"], note_fits):
            rows.append({"type": "note", "text": line})
    return rows


# ── Filling the sheet (ws = Excel worksheet) ──────────────────────────────
def _font(ws, addr):
    """Name, size and bold of a cell, so we can measure text in the same font."""
    f = ws.Range(addr).Font
    return (f.Name, f.Size, bool(f.Bold))


def _put_text(cell, text):
    """Writes text into a cell as real text."""
    cell.NumberFormat = "@"      # "@" = Text format: "0011723" keeps its zeros, "1-2" is not turned into a date
    cell.Value = text


def _merge(ws, row, cols, horizontal, indent=0):
    """Merges cols[0]..cols[1] on one row and sets how the text sits inside.

    horizontal: XL_LEFT or XL_CENTER. Text is always bottom aligned and never wraps
    (we do the wrapping ourselves in split_to_fit, one Excel row per line).
    Returns the first cell of the block, which is the one that holds the value.
    """
    c1, c2 = cols
    rng = ws.Range(f"{c1}{row}:{c2}{row}")
    rng.Merge()
    rng.HorizontalAlignment = horizontal
    rng.VerticalAlignment = XL_BOTTOM
    rng.WrapText = False
    if indent:
        rng.IndentLevel = indent
    return ws.Range(f"{c1}{row}")


def fill_sheet(ws, data, fit):
    """Writes the header and the items into the template.

    fit.width(text, font) returns how wide a text is in points (measured by Excel).
    """
    # 1. Header values (AR no., date, customer, prepared by)
    for key, addr in HEADER_CELLS.items():
        _put_text(ws.Range(addr), data[key])
    for key in SHRINK_HEADERS:
        ws.Range(HEADER_CELLS[key]).ShrinkToFit = True

    # 2. Helper that builds a "does this text fit?" test for a block of columns
    def fits_for(cols, indent=0):
        first = f"{cols[0]}{FIRST_ROW}"
        font = _font(ws, first)                                      # the font used in that block
        width = ws.Range(f"{cols[0]}{FIRST_ROW}:{cols[1]}{FIRST_ROW}").Width   # block width in points
        # An indent pushes the text right, so it takes space from the line.
        # One indent level is about the width of 3 spaces.
        indent_pts = indent * (fit.width("   X", font) - fit.width("X", font))
        limit = width - indent_pts - FIT_MARGIN_PTS
        return lambda text: fit.width(text, font) <= limit

    # 3. Work out the rows needed (long codes, lots and notes wrap onto extra rows)
    rows = plan_rows(data["items"], fits_for(CODE_COLS), fits_for(LOT_COLS),
                     fits_for(NOTE_COLS, NOTE_INDENT))

    # 4. The form has a fixed number of rows. +1 is for the NOTHING FOLLOWS row.
    capacity = LAST_ROW - FIRST_ROW + 1
    if len(rows) + 1 > capacity:
        raise ValueError(
            f"This receipt needs {len(rows) + 1} rows but the form only has {capacity}.\n"
            "Shorten the product codes, lot numbers or notes.")

    # 5. Write every planned row into the sheet
    for i, spec in enumerate(rows):
        r = FIRST_ROW + i

        # A note row: one merged, left aligned, indented line
        if spec["type"] == "note":
            _put_text(_merge(ws, r, NOTE_COLS, XL_LEFT, NOTE_INDENT), spec["text"])
            continue

        # A detail row. Only the first row of an item holds qty, unit and color.
        item = spec["item"]
        if spec["first"]:
            qty = ws.Range(f"{QTY_COL}{r}")
            qty.NumberFormat = "#,##0.000"        # 10 -> 10.000
            qty.Value = item["qty"]
            qty.ShrinkToFit = True
            _put_text(_merge(ws, r, UNIT_COLS, XL_CENTER), item["unit"])
            _put_text(_merge(ws, r, COLOR_COLS, XL_LEFT), item["prod_color"])   # left + bottom aligned

        # Product code: the first row, or any extra row that carries a wrapped piece of it
        if spec["first"] or spec["code"] is not None:
            cell = _merge(ws, r, CODE_COLS, XL_CENTER)
            if spec["code"]:
                _put_text(cell, spec["code"])

        # Lot number: same idea as the product code, but left + bottom aligned
        if spec["first"] or spec["lot"] is not None:
            cell = _merge(ws, r, LOT_COLS, XL_LEFT)
            if spec["lot"]:
                _put_text(cell, spec["lot"])

    # 6. The closing line right after the last used row
    _put_text(_merge(ws, FIRST_ROW + len(rows), FOOTER_COLS, XL_CENTER), FOOTER_TEXT)


# ── Excel helpers ─────────────────────────────────────────────────────────
def _new_excel():
    """Starts a separate, hidden Excel just for us (it does not touch Excel files the user has open)."""
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False        # no pop-up questions from Excel
    return excel


class _ExcelFit:
    """Measures how wide a text is, using Excel itself.

    It types the text in a scratch workbook, lets Excel AutoFit the column, and reads
    the column width (in points). Results are cached so each text is measured only once.
    """

    def __init__(self, excel):
        self.wb = excel.Workbooks.Add()
        self.cell = self.wb.Worksheets(1).Range("A1")
        self.col = self.wb.Worksheets(1).Columns(1)
        self.cell.NumberFormat = "@"
        self._cache = {}

    def width(self, text, font):
        key = (text, font)
        if key not in self._cache:
            self.cell.Font.Name, self.cell.Font.Size, self.cell.Font.Bold = font
            self.cell.Value = text
            self.col.AutoFit()
            self._cache[key] = self.col.Width
        return self._cache[key]

    def close(self):
        self.wb.Close(False)           # False = do not save the scratch workbook


def render_files(template_path, xlsx_path, pdf_path, data):
    """Fills the template, then saves the filled copy (.xlsx) and a PDF of it (for the preview)."""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found:\n{template_path}")

    pythoncom.CoInitialize()           # required before using COM in a background thread
    excel = None
    try:
        excel = _new_excel()
        # ReadOnly: the template itself is never changed
        wb = excel.Workbooks.Open(os.path.abspath(template_path), ReadOnly=True)
        ws = wb.ActiveSheet

        fit = _ExcelFit(excel)
        try:
            fill_sheet(ws, data, fit)
        finally:
            fit.close()

        wb.Activate()
        wb.SaveCopyAs(os.path.abspath(xlsx_path))                 # the filled .xlsx used for printing
        ws.ExportAsFixedFormat(0, os.path.abspath(pdf_path))      # 0 = PDF, used for the preview
        wb.Close(False)
    finally:
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()


def print_xlsx(xlsx_path, printer_name):
    """Prints the filled sheet through Excel on the chosen printer."""
    pythoncom.CoInitialize()
    excel = None
    previous = None
    try:
        # Excel prints to the Windows default printer, so we switch it for a moment
        previous = win32print.GetDefaultPrinter()
        if printer_name and printer_name != previous:
            win32print.SetDefaultPrinter(printer_name)

        excel = _new_excel()
        wb = excel.Workbooks.Open(os.path.abspath(xlsx_path), ReadOnly=True)
        wb.ActiveSheet.PrintOut(Copies=1)
        wb.Close(False)
    finally:
        if excel is not None:
            excel.Quit()
        # Always put the user's original default printer back
        if previous and printer_name and printer_name != previous:
            win32print.SetDefaultPrinter(previous)
        pythoncom.CoUninitialize()


# ── Preview window ────────────────────────────────────────────────────────
class _Worker(QThread):
    """Runs a slow Excel call in the background so the window does not freeze."""
    ok = pyqtSignal()                  # sent when the call finished fine
    failed = pyqtSignal(str)           # sent with the error message if it failed

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.fn(*self.args)
            self.ok.emit()
        except Exception as e:
            self.failed.emit(str(e))


class ARPrintPreview(QWidget):
    """Window that shows the filled Excel template as a PDF and prints only when Print is clicked."""

    printed = pyqtSignal(str)          # sent after the receipt was sent to the printer (with the printer name)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self._worker = None            # the background job currently running
        self._ready = False            # True once the preview PDF is loaded
        self._printer = ""             # the printer that was chosen when Print was clicked

        # A private temp folder for the filled .xlsx and the PDF; deleted when the window closes
        self.tmp_dir = tempfile.mkdtemp(prefix="mbpi_ar_")
        self.xlsx_path = os.path.join(self.tmp_dir, "ar.xlsx")
        self.pdf_path = os.path.join(self.tmp_dir, "ar.pdf")

        # Open as its own normal window (with minimize / maximize / close buttons)
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.WindowMinimizeButtonHint |
                            Qt.WindowType.WindowMaximizeButtonHint |
                            Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"Print Preview | AR {data['ar_no']}")
        self.resize(900, 900)

        self._build_ui()
        self._build_preview()          # start creating the preview right away

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Top bar: printer choice, status text, Print and Close buttons
        bar = QHBoxLayout()
        bar.setSpacing(8)
        lbl = QLabel("PRINTER")
        lbl.setObjectName("FieldLabel")
        self.cmb_printer = QComboBox()
        self._load_printers()
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("SubtitleLabel")

        self.btn_print = QPushButton(
            " Print", icon=fa.icon("fa5s.print", color="white", color_disabled="#94A3B8"))
        self.btn_print.setObjectName("PrimaryButton")
        self.btn_print.clicked.connect(self.print_report)

        btn_close = QPushButton(" Close", icon=fa.icon("fa5s.times", color="#DC2626", color_active="white"))
        btn_close.setObjectName("DangerOutlineButton")
        btn_close.clicked.connect(self.close)

        bar.addWidget(lbl)
        bar.addWidget(self.cmb_printer, 1)
        bar.addWidget(self.lbl_status)
        bar.addWidget(self.btn_print)
        bar.addWidget(btn_close)
        root.addLayout(bar)

        # The PDF viewer, fitted to the window width
        self.pdf_doc = QPdfDocument(self)
        self.pdf_view = QPdfView(self)
        self.pdf_view.setDocument(self.pdf_doc)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        root.addWidget(self.pdf_view, 1)

    def _load_printers(self):
        """Fills the printer list and selects the Windows default printer."""
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            for p in win32print.EnumPrinters(flags):
                self.cmb_printer.addItem(p[2])               # p[2] is the printer name
            self.cmb_printer.setCurrentText(win32print.GetDefaultPrinter())
        except Exception:
            pass                                             # no printers found: the list stays empty

    # ── Helpers ───────────────────────────────────────────────────────────
    def _set_busy(self, busy, text=""):
        """Shows a status text and only enables Print when the preview is ready and nothing is running."""
        self.lbl_status.setText(text)
        self.btn_print.setEnabled(self._ready and not busy)

    def _run(self, fn, *args, done):
        """Runs fn(*args) in the background; calls done() when it finishes, or shows an error."""
        self._worker = _Worker(fn, *args)
        self._worker.ok.connect(done)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_error(self, msg):
        self.btn_print.setText(" Print")
        self._set_busy(False)
        QMessageBox.critical(self, "Error", msg)

    # ── Preview ───────────────────────────────────────────────────────────
    def _build_preview(self):
        self._set_busy(True, "Preparing preview...")
        self._run(render_files, TEMPLATE_PATH, self.xlsx_path, self.pdf_path, self.data,
                  done=self._show_pdf)

    def _show_pdf(self):
        """Called when the PDF is ready: load it into the viewer and allow printing."""
        self.pdf_doc.load(self.pdf_path)
        self._ready = True
        self._set_busy(False)

    # ── Printing ──────────────────────────────────────────────────────────
    def print_report(self):
        self._printer = self.cmb_printer.currentText()    # remember it for the audit trail
        self.btn_print.setText(" Sending...")
        self._set_busy(True, "Sending to printer...")
        self._run(print_xlsx, self.xlsx_path, self._printer, done=self._printed)

    def _printed(self):
        # Tell the entry tab first so the audit entry is written right away,
        # not only after someone clicks OK on the message below
        self.printed.emit(self._printer)
        QMessageBox.information(self, "Printed", "Sent to the printer.")
        self.close()

    def closeEvent(self, event):
        # Wait for any running Excel job, then clean up the temp files
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        self.pdf_doc.close()  # release the PDF file so the temp folder can be deleted
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().closeEvent(event)