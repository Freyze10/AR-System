import os
import shutil
import sys
import tempfile

import pythoncom
import qtawesome as fa
import win32com.client
import win32print
from openpyxl import load_workbook
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, "ar_template.xlsx")

# ── Template layout: edit these to match ar_template.xlsx ─────────────────
# Cell addresses are PLACEHOLDERS. For merged cells use the top-left cell.
# Set a value to None to skip that field.
SHEET = None                      # sheet name, or None for the first/active sheet
HEADER_CELLS = {
    "ar_no": "F2",
    "ar_date": "F3",
    "customer": "B4",
    "prepared_by": "B20",
    "item_count": "F20",
}
ITEM_START_ROW = 8                # first item row; each next item goes one row down
ITEM_COLUMNS = {
    "qty": "A",
    "unit": "B",
    "prod_code": "C",
    "prod_color": "D",
    "lot_no": "E",
    "notes": "F",
}


# ── Data ──────────────────────────────────────────────────────────────────
def build_print_data(ar_no, ar_date, customer, prepared_by, items):
    """Everything shown in the entry tab, ready for the template.

    items: [(qty, unit, prod_code, prod_color, lot_no, notes), ...] (the entry table rows)
    """
    return {
        "ar_no": f"{int(ar_no):07d}",
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


# ── Excel helpers ─────────────────────────────────────────────────────────
def fill_template(template_path, out_path, data):
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found:\n{template_path}")

    wb = load_workbook(template_path)
    ws = wb[SHEET] if SHEET else wb.active

    for key, cell in HEADER_CELLS.items():
        if cell:
            ws[cell] = data[key]

    for i, item in enumerate(data["items"]):
        row = ITEM_START_ROW + i
        for key, col in ITEM_COLUMNS.items():
            if col:
                ws[f"{col}{row}"] = item[key]
        if ITEM_COLUMNS.get("qty"):
            ws[f"{ITEM_COLUMNS['qty']}{row}"].number_format = "#,##0.000"

    wb.save(out_path)


def _new_excel():
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    return excel


def export_pdf(xlsx_path, pdf_path):
    """Convert the filled sheet to a PDF (used only for the preview)."""
    pythoncom.CoInitialize()
    excel = None
    try:
        excel = _new_excel()
        wb = excel.Workbooks.Open(os.path.abspath(xlsx_path), ReadOnly=True)
        wb.ActiveSheet.ExportAsFixedFormat(0, os.path.abspath(pdf_path))  # 0 = PDF
        wb.Close(False)
    finally:
        if excel is not None:
            excel.Quit()
        pythoncom.CoUninitialize()


def print_xlsx(xlsx_path, printer_name):
    """Print the filled sheet through Excel on the chosen printer."""
    pythoncom.CoInitialize()
    excel = None
    previous = None
    try:
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
        if previous and printer_name and printer_name != previous:
            win32print.SetDefaultPrinter(previous)
        pythoncom.CoUninitialize()


# ── Preview window ────────────────────────────────────────────────────────
class _Worker(QThread):
    """Runs a slow Excel call off the UI thread."""
    ok = pyqtSignal()
    failed = pyqtSignal(str)

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
    """Shows the filled Excel template as a PDF; prints only when Print is clicked."""

    printed = pyqtSignal()

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self._worker = None
        self._ready = False

        self.tmp_dir = tempfile.mkdtemp(prefix="mbpi_ar_")
        self.xlsx_path = os.path.join(self.tmp_dir, "ar.xlsx")
        self.pdf_path = os.path.join(self.tmp_dir, "ar.pdf")

        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.WindowMinimizeButtonHint |
                            Qt.WindowType.WindowMaximizeButtonHint |
                            Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"Print Preview | AR {data['ar_no']}")
        self.resize(900, 900)

        self._build_ui()
        self._build_preview()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

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

        self.pdf_doc = QPdfDocument(self)
        self.pdf_view = QPdfView(self)
        self.pdf_view.setDocument(self.pdf_doc)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        root.addWidget(self.pdf_view, 1)

    def _load_printers(self):
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            for p in win32print.EnumPrinters(flags):
                self.cmb_printer.addItem(p[2])
            self.cmb_printer.setCurrentText(win32print.GetDefaultPrinter())
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────
    def _set_busy(self, busy, text=""):
        self.lbl_status.setText(text)
        self.btn_print.setEnabled(self._ready and not busy)

    def _run(self, fn, *args, done):
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
        try:
            fill_template(TEMPLATE_PATH, self.xlsx_path, self.data)
        except Exception as e:
            self._on_error(f"Could not fill the template:\n{e}")
            return
        self._run(export_pdf, self.xlsx_path, self.pdf_path, done=self._show_pdf)

    def _show_pdf(self):
        self.pdf_doc.load(self.pdf_path)
        self._ready = True
        self._set_busy(False)

    # ── Printing ──────────────────────────────────────────────────────────
    def print_report(self):
        self.btn_print.setText(" Sending...")
        self._set_busy(True, "Sending to printer...")
        self._run(print_xlsx, self.xlsx_path, self.cmb_printer.currentText(), done=self._printed)

    def _printed(self):
        QMessageBox.information(self, "Printed", "Sent to the printer.")
        self.printed.emit()
        self.close()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        self.pdf_doc.close()  # release the file so the temp folder can be deleted
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        super().closeEvent(event)