"""AR print preview.

The big picture:
  1. The entry tab gives us the receipt data (header + items).
  2. We open the Excel template (ar_template.xlsx, or the wide one) in a hidden Excel,
     set the paper size the user picked, and fill in its cells.
     (For dot matrix printers like the EPSON LX, the preview is drawn with the Windows
     PDF printer, because Excel draws dotted, low resolution text for them.
     Printing still goes to the printer the user chose.)
  3. We save the filled copy as an .xlsx file and also export it as a PDF.
  4. The window shows that PDF as the preview. The .xlsx is only sent to the printer
     (through Excel) when the user clicks Print.
  5. Changing the printer or the paper size builds the preview again, so the preview
     always shows what will be printed on that paper.

Excel is controlled through COM (win32com), so this only works on Windows with Excel installed.
"""
import os
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager

import pythoncom                     # needed to use COM from a background thread
import qtawesome as fa
import win32com.client               # lets Python control Excel
import win32con                      # Windows constants (DC_PAPERS, DC_PAPERNAMES)
import win32print                    # lists printers / paper sizes / changes the default printer
from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

# Where the templates live. When the app is packaged with PyInstaller the files are
# unpacked into sys._MEIPASS; otherwise we use the folder of this file.
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, "ar_template.xlsx")
# Template with the wider product code column, used by the "Print Wide" button
TEMPLATE_WIDE_PATH = os.path.join(BASE_DIR, "ar_template_prod_code_wide.xlsx")

# The printer with this text in its name is selected automatically.
# If there is none, the Windows default printer is selected.
PREFERRED_PRINTER = "LX"

# First item of the paper list: keep the paper size saved inside the template.
TEMPLATE_PAPER_LABEL = "(Template default)"

# Dot matrix printers (like the EPSON LX) make Excel draw the preview with low resolution
# printer fonts, so the preview looks dotted and the font looks different, even though the
# real print is fine. For those printers the preview is drawn with the Windows PDF printer
# instead (the printer with this text in its name).
PDF_PRINTER_HINT = "Print to PDF"

# Only one Excel job at a time: every job switches the Windows default printer while it
# runs, so two jobs must never overlap.
_JOB_LOCK = threading.Lock()

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

# ── Template layout (ar_template_prod_code_wide.xlsx) ─────────────────────
# The wide template has a wider product code column, so the product code, color and lot
# blocks start one column later. Quantity, unit, notes and the footer are the same.
WIDE_CODE_COLS = ("F", "I")        # merged, centered
WIDE_COLOR_COLS = ("J", "K")       # merged, left aligned
WIDE_LOT_COLS = ("L", "Q")         # merged, left aligned

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


# ── Printers and paper sizes ──────────────────────────────────────────────
def list_printers():
    """Names of all printers Windows knows (local and network)."""
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]       # p[2] is the printer name


def pick_printer(names):
    """The printer to select first: one with PREFERRED_PRINTER in its name, else the Windows default."""
    for name in names:
        if PREFERRED_PRINTER.upper() in name.upper():
            return name
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return names[0] if names else ""


def is_dot_matrix(printer_name):
    """True for dot matrix printers: the preferred (LX) printer or any ESC/P printer."""
    name = (printer_name or "").upper()
    return PREFERRED_PRINTER.upper() in name or "ESC/P" in name


def pick_preview_printer(selected, names):
    """The printer Excel draws the preview with.

    That is the selected printer, except for dot matrix printers: those use the Windows
    PDF printer when there is one (its text is smooth), otherwise the selected printer.
    """
    if is_dot_matrix(selected):
        for name in names:
            if PDF_PRINTER_HINT.upper() in name.upper():
                return name
    return selected


def get_paper_sizes(printer_name):
    """Paper sizes the printer offers, as [(paper_id, name), ...].

    Windows reports the user-defined sizes added in the printer's settings too.
    The id is the number Excel uses for that paper size.
    """
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            port = win32print.GetPrinter(handle, 2)["pPortName"]
        finally:
            win32print.ClosePrinter(handle)
        ids = win32print.DeviceCapabilities(printer_name, port, win32con.DC_PAPERS) or []
        names = win32print.DeviceCapabilities(printer_name, port, win32con.DC_PAPERNAMES) or []
    except Exception:
        return []                                  # printer offline / no info: only the template paper is offered
    return [(int(i), str(n).strip("\x00 ")) for i, n in zip(ids, names)]


@contextmanager
def _printer_as_default(printer_name):
    """Makes printer_name the Windows default printer while the block runs, then puts the old one back.

    Excel works with the paper sizes of its current printer, which is the Windows default
    printer when Excel starts. So the chosen printer must be the default while Excel runs.
    """
    previous = win32print.GetDefaultPrinter()
    switched = bool(printer_name) and printer_name != previous
    if switched:
        win32print.SetDefaultPrinter(printer_name)
    try:
        yield
    finally:
        if switched:
            win32print.SetDefaultPrinter(previous)   # always restore the user's default printer


def _apply_paper(ws, paper_id):
    """Uses the chosen paper size on the sheet. None = keep the paper size saved in the template.

    Returns False when Excel refuses the paper size. That happens for user defined sizes
    added in the printer's settings (like "AR"): Excel can only set the standard Windows
    paper sizes. The sheet then keeps the paper size saved in the template.
    """
    if not paper_id:
        return True
    try:
        ws.PageSetup.PaperSize = paper_id
        return True
    except Exception:
        return False


# ── Layout logic (no Excel needed) ────────────────────────────────────────
def split_to_fit(text, fits):
    """Splits text into lines so that every line passes fits(line).

    fits(line) is a function that says whether the line is narrow enough for the cell.
    We split on spaces. A single word that is longer than a whole line is cut by
    characters, so nothing is ever lost. Empty text gives [].
    """
    text = " ".join((text or "").split())      # one clean line (no double spaces / line breaks)
    if not text:
        return []
    if fits(text):                              # the usual case: it all fits on one line,
        return [text]                           # so we only had to measure once

    lines, current = [], ""
    for word in text.split():
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


def fill_sheet(ws, data, fit, wide=False):
    """Writes the header and the items into the template.

    fit.width(text, font) returns how wide a text is in points (measured by Excel).
    wide=True uses the column blocks of the wide template (WIDE_CODE_COLS and so on).
    """
    # Which columns hold the product code, color and lot number in this template
    if wide:
        code_cols, color_cols, lot_cols = WIDE_CODE_COLS, WIDE_COLOR_COLS, WIDE_LOT_COLS
    else:
        code_cols, color_cols, lot_cols = CODE_COLS, COLOR_COLS, LOT_COLS

    # 1. Header values (AR no., date, customer, prepared by)
    for key, addr in HEADER_CELLS.items():
        _put_text(ws.Range(addr), data[key])
    for key in SHRINK_HEADERS:
        ws.Range(HEADER_CELLS[key]).ShrinkToFit = True

    # 2. Helper that builds a "does this text fit?" test for a block of columns
    def fits_for(cols, indent=0):
        first = f"{cols[0]}{FIRST_ROW}"
        font = _font(ws, first)                                      # the font used in that block
        size = font[1]                                               # font size in points
        width = ws.Range(f"{cols[0]}{FIRST_ROW}:{cols[1]}{FIRST_ROW}").Width   # block width in points
        # An indent pushes the text right, so it takes space from the line.
        # One indent level is about the width of 3 spaces.
        indent_pts = 0
        if indent:
            indent_pts = indent * (fit.width("   X", font) - fit.width("X", font))
        limit = width - indent_pts - FIT_MARGIN_PTS

        def fits(text):
            # Short text always fits: even the widest letter is about one font size wide, so
            # when that many characters fit we do not need to ask Excel (asking is slow)
            if len(text) * size + 8 <= limit:
                return True
            return fit.width(text, font) <= limit
        return fits

    # 3. Work out the rows needed (long codes, lots and notes wrap onto extra rows)
    rows = plan_rows(data["items"], fits_for(code_cols), fits_for(lot_cols),
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
            _put_text(_merge(ws, r, color_cols, XL_CENTER), item["prod_color"])    # left + bottom aligned

        # Product code: the first row, or any extra row that carries a wrapped piece of it
        if spec["first"] or spec["code"] is not None:
            cell = _merge(ws, r, code_cols, XL_CENTER)
            if spec["code"]:
                _put_text(cell, spec["code"])

        # Lot number: same idea as the product code, but left + bottom aligned
        if spec["first"] or spec["lot"] is not None:
            cell = _merge(ws, r, lot_cols, XL_LEFT)
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
    excel.ScreenUpdating = False       # nothing is drawn on screen, so do not spend time on it
    excel.EnableEvents = False         # no workbook events (faster)
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
        self._font = None              # the font set on the cell right now

    def width(self, text, font):
        key = (text, font)
        if key not in self._cache:
            if font != self._font:     # only talk to Excel about the font when it changes
                self.cell.Font.Name, self.cell.Font.Size, self.cell.Font.Bold = font
                self._font = font
            self.cell.Value = text
            self.col.AutoFit()
            self._cache[key] = self.col.Width
        return self._cache[key]

    def close(self):
        self.wb.Close(False)           # False = do not save the scratch workbook


def render_files(template_path, xlsx_path, pdf_path, data, printer_name="", paper_id=None,
                 notes=None, on_ready=None):
    """Fills the template, then saves the filled copy (.xlsx) and a PDF of it (for the preview).

    printer_name / paper_id decide the page size used for the PDF and saved in the copy.
    notes:    a list; a message is added to it when something could not be done exactly
              (for example the paper size could not be set).
    on_ready: called as soon as the PDF exists, before Excel is closed, so the preview
              can show right away while Excel finishes closing in the background.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found:\n{template_path}")
    if notes is None:
        notes = []

    # The wide template has its own column blocks (see WIDE_CODE_COLS and so on)
    wide = os.path.abspath(template_path) == os.path.abspath(TEMPLATE_WIDE_PATH)

    # Excel draws the preview for one printer. Dot matrix printers get the PDF printer.
    try:
        draw_printer = pick_preview_printer(printer_name, list_printers())
    except Exception:
        draw_printer = printer_name
    # A paper id only means the same thing on another printer if that printer knows it.
    # (Standard sizes like Letter or A4 are known everywhere; user defined sizes are not.)
    if draw_printer != printer_name and paper_id not in [i for i, _ in get_paper_sizes(draw_printer)]:
        paper_id = None

    pythoncom.CoInitialize()           # required before using COM in a background thread
    try:
        with _JOB_LOCK, _printer_as_default(draw_printer):
            excel = _new_excel()
            wb = None
            try:
                # ReadOnly: the template itself is never changed. UpdateLinks=0: do not refresh links.
                wb = excel.Workbooks.Open(os.path.abspath(template_path), UpdateLinks=0, ReadOnly=True)
                ws = wb.ActiveSheet
                if not _apply_paper(ws, paper_id):
                    notes.append("Excel cannot use this paper size, so the template's paper size is used.")

                fit = _ExcelFit(excel)
                try:
                    fill_sheet(ws, data, fit, wide=wide)
                finally:
                    fit.close()

                wb.Activate()
                wb.SaveCopyAs(os.path.abspath(xlsx_path))                 # the filled .xlsx used for printing
                ws.ExportAsFixedFormat(0, os.path.abspath(pdf_path))      # 0 = PDF, used for the preview

                if on_ready is not None:
                    on_ready()                 # show the preview now; closing Excel can wait
            finally:
                # Cleanup problems must not turn a good preview into an error message
                try:
                    if wb is not None:
                        wb.Close(False)
                except Exception:
                    pass
                try:
                    excel.Quit()
                except Exception:
                    pass
    finally:
        pythoncom.CoUninitialize()


def print_xlsx(xlsx_path, printer_name, paper_id=None):
    """Prints the filled sheet through Excel on the chosen printer and paper size."""
    pythoncom.CoInitialize()
    try:
        with _JOB_LOCK, _printer_as_default(printer_name):
            excel = _new_excel()
            try:
                wb = excel.Workbooks.Open(os.path.abspath(xlsx_path), UpdateLinks=0, ReadOnly=True)
                ws = wb.ActiveSheet
                _apply_paper(ws, paper_id)       # if Excel refuses it, the saved paper size is used
                ws.PrintOut(Copies=1)
                wb.Close(False)
            finally:
                excel.Quit()
    finally:
        pythoncom.CoUninitialize()


# ── Preview window ────────────────────────────────────────────────────────
class _Worker(QThread):
    """Runs a slow Excel call in the background so the window does not freeze."""
    ok = pyqtSignal()                  # sent when the call finished fine
    failed = pyqtSignal(str)           # sent with the error message if it failed

    def __init__(self, fn, *args, early=False):
        super().__init__()
        self.fn, self.args = fn, args
        self.early = early             # True: the job itself says when its result is ready

    def run(self):
        try:
            if self.early:
                # The job calls on_ready as soon as the result is usable (before it cleans up)
                self.fn(*self.args, on_ready=self.ok.emit)
            else:
                self.fn(*self.args)
                self.ok.emit()
        except Exception as e:
            self.failed.emit(str(e))


class _HoverIconButton(QPushButton):
    """A push button whose icon changes color while the mouse is over it.

    Qt does not do this by itself for push buttons (the "active" icon color is only used
    when the button has keyboard focus), so we swap the icon when the mouse enters and leaves.
    """

    def __init__(self, text, icon_name, normal_color, hover_color):
        super().__init__(text)
        # color_active is the same as color, so keyboard focus never changes the icon
        self._normal_icon = fa.icon(icon_name, color=normal_color, color_active=normal_color)
        self._hover_icon = fa.icon(icon_name, color=hover_color, color_active=hover_color)
        self.setIcon(self._normal_icon)

    def enterEvent(self, event):
        self.setIcon(self._hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._normal_icon)
        super().leaveEvent(event)


class ARPrintPreview(QWidget):
    """Window that shows the filled Excel template as a PDF and prints only when Print is clicked.

    template_path: TEMPLATE_PATH (standard form) or TEMPLATE_WIDE_PATH (wide product code form).
    """

    printed = pyqtSignal(str)          # sent after the receipt was sent to the printer (with the printer name)

    def __init__(self, data, parent=None, template_path=TEMPLATE_PATH):
        super().__init__(parent)
        self.data = data
        self.template_path = template_path     # which Excel template this preview is built from
        self._workers = []             # background jobs that are still running
        self._notes = []               # messages from the last preview build (shown next to the paper size)
        self._ready = False            # True once the preview PDF of the current printer/paper is loaded
        self._printer = ""             # the printer that was chosen when Print was clicked
        self._build_no = 0             # counts preview builds, so every build gets its own files
        self._settings = QSettings("MBPI", "AR-System")    # remembers the paper size picked per printer

        # A private temp folder for the filled .xlsx and the PDFs; deleted when the window closes
        self.tmp_dir = tempfile.mkdtemp(prefix="mbpi_ar_")
        self.xlsx_path = ""
        self.pdf_path = ""

        # Open as its own normal window (with minimize / maximize / close buttons)
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.WindowMinimizeButtonHint |
                            Qt.WindowType.WindowMaximizeButtonHint |
                            Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        kind = " (Wide)" if template_path == TEMPLATE_WIDE_PATH else ""
        self.setWindowTitle(f"Print Preview{kind} | AR {data['ar_no']}")
        self.resize(900, 900)

        self._build_ui()
        self._build_preview()          # start creating the preview right away

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Top bar: printer choice, Print and Close buttons
        bar = QHBoxLayout()
        bar.setSpacing(8)
        lbl = QLabel("PRINTER")
        lbl.setObjectName("FieldLabel")
        self.cmb_printer = QComboBox()

        self.btn_print = QPushButton(
            " Print", icon=fa.icon("fa5s.print", color="white", color_disabled="#94A3B8"))
        self.btn_print.setObjectName("PrimaryButton")
        self.btn_print.clicked.connect(self.print_report)

        btn_close = _HoverIconButton(" Close", "fa5s.times", "#DC2626", "white")   # red icon, white on hover
        btn_close.setObjectName("DangerOutlineButton")
        btn_close.clicked.connect(self.close)
        # When the window opens, Print and the lists are disabled (the preview is being built),
        # so Close would be the only widget that can take focus and would show a focus look.
        # Clicking is all this button needs, so it never takes keyboard focus.
        btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        bar.addWidget(lbl)
        bar.addWidget(self.cmb_printer, 1)
        bar.addWidget(self.btn_print)
        bar.addWidget(btn_close)
        root.addLayout(bar)

        # Second bar: paper size choice and status text
        bar2 = QHBoxLayout()
        bar2.setSpacing(8)
        lbl2 = QLabel("PAPER SIZE")
        lbl2.setObjectName("FieldLabel")
        self.cmb_paper = QComboBox()
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("SubtitleLabel")
        bar2.addWidget(lbl2)
        bar2.addWidget(self.cmb_paper, 1)
        bar2.addWidget(self.lbl_status)
        root.addLayout(bar2)

        # Fill both lists first, then listen for the user's choices.
        # "activated" fires only when the USER picks an item, not when we fill the list.
        self._load_printers()
        self._load_papers()
        self.cmb_printer.activated.connect(self._on_printer_changed)
        self.cmb_paper.activated.connect(self._on_paper_changed)

        # The PDF viewer, fitted to the window width. All pages are shown, so you can see
        # if the print would continue on a second page.
        self.pdf_doc = QPdfDocument(self)
        self.pdf_view = QPdfView(self)
        self.pdf_view.setDocument(self.pdf_doc)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        root.addWidget(self.pdf_view, 1)

    def _load_printers(self):
        """Fills the printer list and selects the LX printer, or the Windows default if there is none."""
        try:
            names = list_printers()
        except Exception:
            names = []                                       # no printers found: the list stays empty
        self.cmb_printer.addItems(names)
        self.cmb_printer.setCurrentText(pick_printer(names))

    def _paper_key(self):
        """Settings key that remembers the paper size for the selected printer."""
        printer = self.cmb_printer.currentText().replace("\\", "_").replace("/", "_")
        return f"paper/{printer}"

    def _load_papers(self):
        """Fills the paper list for the selected printer and selects the one used last time."""
        self.cmb_paper.clear()
        self.cmb_paper.addItem(TEMPLATE_PAPER_LABEL, None)   # None = do not change the template's paper
        for paper_id, name in get_paper_sizes(self.cmb_printer.currentText()):
            self.cmb_paper.addItem(name, paper_id)
        saved = str(self._settings.value(self._paper_key(), ""))
        self.cmb_paper.setCurrentIndex(max(self.cmb_paper.findText(saved), 0))

    # ── Helpers ───────────────────────────────────────────────────────────
    def _set_busy(self, busy, text=""):
        """Shows a status text. While busy the choices are locked, and Print is only enabled
        when the preview of the current printer and paper is ready."""
        self.lbl_status.setText(text)
        self.btn_print.setEnabled(self._ready and not busy)
        self.cmb_printer.setEnabled(not busy)
        self.cmb_paper.setEnabled(not busy)

    def _run(self, fn, *args, done, early=False):
        """Runs fn(*args) in the background; calls done() when it finishes, or shows an error.

        early=True: done() is called as soon as the job says its result is ready, even though
        it is still cleaning up. Every running job is kept in a list so none is dropped while running.
        """
        worker = _Worker(fn, *args, early=early)
        worker.ok.connect(done)
        worker.failed.connect(self._on_error)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _on_error(self, msg):
        self.btn_print.setText(" Print")
        self._set_busy(False)
        QMessageBox.critical(self, "Error", msg)

    # ── Changing printer / paper ──────────────────────────────────────────
    def _on_printer_changed(self, _index):
        self._load_papers()            # every printer has its own paper sizes
        self._build_preview()

    def _on_paper_changed(self, _index):
        self._settings.setValue(self._paper_key(), self.cmb_paper.currentText())   # remember it
        self._build_preview()

    # ── Preview ───────────────────────────────────────────────────────────
    def _build_preview(self):
        """Builds the preview for the selected printer and paper size (in the background)."""
        self._ready = False            # no printing until this preview is ready
        self._build_no += 1
        # New file names each time: the previous PDF may still be open in the viewer
        self.xlsx_path = os.path.join(self.tmp_dir, f"ar_{self._build_no}.xlsx")
        self.pdf_path = os.path.join(self.tmp_dir, f"ar_{self._build_no}.pdf")

        self._notes = []               # the job adds messages here, for example "paper size not used"
        self._set_busy(True, "Preparing preview...")
        self._run(render_files, self.template_path, self.xlsx_path, self.pdf_path, self.data,
                  self.cmb_printer.currentText(), self.cmb_paper.currentData(), self._notes,
                  done=self._show_pdf, early=True)

    def _show_pdf(self):
        """Called when the PDF is ready: load it into the viewer and allow printing."""
        self.pdf_doc.load(self.pdf_path)
        self._ready = True
        self._set_busy(False, "  ".join(self._notes))     # empty unless something could not be done exactly

    # ── Printing ──────────────────────────────────────────────────────────
    def print_report(self):
        self._printer = self.cmb_printer.currentText()    # remember it for the audit trail
        self.btn_print.setText(" Sending...")
        self._set_busy(True, "Sending to printer...")
        self._run(print_xlsx, self.xlsx_path, self._printer, self.cmb_paper.currentData(),
                  done=self._printed)

    def _printed(self):
        # Tell the entry tab first so the audit entry is written right away,
        # not only after someone clicks OK on the message below
        self.printed.emit(self._printer)
        QMessageBox.information(self, "Printed", "Sent to the printer.")
        self.close()

    def closeEvent(self, event):
        # Wait for any running Excel job, then clean up the temp files
        for worker in list(self._workers):
            worker.wait()
        self.pdf_doc.close()  # release the PDF file so the temp folder can be deleted
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().closeEvent(event)