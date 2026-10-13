import qtawesome as fa
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from menu.ar_report.ar_records_tab import ARRecordsTab
from menu.ar_report.ar_entry_tab import AREntryTab, MODE_VIEW, MODE_UPDATE


class AcknowledgementReceiptWidget(QWidget):
    """AR module: Tab 1 = record browser, Tab 2 = receipt entry / view / update."""

    close_requested = pyqtSignal()

    def __init__(self, username="User"):
        super().__init__()
        self.records_tab = ARRecordsTab()
        self.entry_tab = AREntryTab(username)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainTabs")
        self.tabs.addTab(self.records_tab, fa.icon("fa5s.list-alt", color="#64748B"),
                         " Acknowledgement Receipt Record")
        self.tabs.addTab(self.entry_tab, fa.icon("fa5s.edit", color="#64748B"),
                         " Acknowledgement Receipt Entry")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

        # Wiring
        self.records_tab.view_requested.connect(lambda ar_no: self._open_record(ar_no, MODE_VIEW))
        self.records_tab.update_requested.connect(lambda ar_no: self._open_record(ar_no, MODE_UPDATE))
        self.entry_tab.saved.connect(lambda _ar_no: self.records_tab.load_records())
        self.entry_tab.close_requested.connect(lambda: self.tabs.setCurrentWidget(self.records_tab))
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _open_record(self, ar_no, mode):
        if self.entry_tab.load_record(ar_no, mode):
            self.tabs.setCurrentWidget(self.entry_tab)

    def _on_tab_changed(self, index):
        if self.tabs.widget(index) is self.entry_tab:
            self.entry_tab.refresh_ar_number()