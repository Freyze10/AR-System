import sys
from datetime import datetime
import qtawesome as fa
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QFrame, QPushButton, QStackedWidget, QStatusBar, QMessageBox
)

from db.schema import create_table
from styles.styles import AppStyles
from menu.ar_report import AcknowledgementReceiptWidget

class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self, username="Brant", role="IT ADMIN"):
        super().__init__()
        self.username = username
        self.role = role
        self.setWindowTitle("AR-SYSTEM-2017 | MASTERBATCH PHILIPPINES INCORPORATED")
        self.setGeometry(100, 100, 1300, 700)
        self.showMaximized()
        self.init_ui()

        create_table()

    def init_ui(self):
        self.setStyleSheet(AppStyles.GLOBAL_STYLESHEET)

        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Build Sidebar
        main_layout.addWidget(self.create_side_menu())

        # Build Content Stack Panel
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(AcknowledgementReceiptWidget())  # Index 0: AR Report
        self.stacked_widget.addWidget(QWidget())                       # Index 1: Audit Trail Placeholder

        main_layout.addWidget(self.stacked_widget)
        self.setCentralWidget(main_widget)
        self.set_status_bar()

    def create_menu_button(self, text, icon_name, page_index):
        btn = QPushButton(text, icon=fa.icon(icon_name, color='#ecf0f1'), checkable=True, autoExclusive=True)
        btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(page_index))
        return btn

    def create_side_menu(self):
        menu = QWidget(objectName="SideMenu")
        layout = QVBoxLayout(menu)
        layout.setContentsMargins(5, 20, 5, 15)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 1. USER PROFILE SECTION (TOP)
        profile_widget = QWidget()
        user_profile_layout = QHBoxLayout(profile_widget)
        user_profile_layout.setContentsMargins(10, 8, 10, 8)
        user_profile_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        user_profile_layout.addWidget(QLabel(pixmap=fa.icon('fa5s.user-circle', color="#2DD4BF").pixmap(QSize(38, 38))))

        labels_widget = QWidget()
        labels_layout = QVBoxLayout(labels_widget)
        labels_layout.setContentsMargins(4, 0, 0, 0)
        labels_layout.setSpacing(0)
        labels_layout.addWidget(QLabel(f"<b>MBPI-IT\\{self.username}</b>"))
        labels_layout.addWidget(QLabel(f"<font color='#94A3B8'>{self.role}</font>"))

        user_profile_layout.addWidget(labels_widget)
        layout.addWidget(profile_widget)

        sep_top = QFrame(frameShape=QFrame.Shape.HLine, objectName="SidebarSeparator")
        layout.addWidget(sep_top)

        # 2. NAVIGATION MENU SECTION
        layout.addWidget(QLabel("NAVIGATION", objectName="MenuLabel"))

        self.btn_ar_report = self.create_menu_button(" AR Report", "fa5s.file-invoice", 0)
        self.btn_audit_trail = self.create_menu_button(" Audit Trail", "fa5s.history", 1)
        self.btn_ar_report.setChecked(True)

        layout.addWidget(self.btn_ar_report)
        layout.addWidget(self.btn_audit_trail)

        # Spacer
        layout.addStretch(1)

        # 3. LOGOUT BUTTON (Cleanly styled via Global QSS Object Name)
        sep_bottom = QFrame(frameShape=QFrame.Shape.HLine, objectName="SidebarSeparator")
        layout.addWidget(sep_bottom)

        self.btn_logout = QPushButton("  Logout", icon=fa.icon('fa5s.sign-out-alt', color="#EF4444"))
        self.btn_logout.setObjectName("LogoutButton") # <--- Links directly to global QSS selector
        self.btn_logout.clicked.connect(self.handle_logout)
        layout.addWidget(self.btn_logout)

        return menu

    def handle_logout(self):
        msg = QMessageBox.question(
            self, "Logout", "Are you sure you want to logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if msg == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit()
            self.close()

    def set_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.time_label = QLabel()

        for status in [self.time_label, QLabel(" PC: MBPI-IT"), QLabel(" IP: 192.168.1.50")]:
            self.status_bar.addPermanentWidget(status)

        self.time_timer = QTimer(self, timeout=self.update_time)
        self.time_timer.start(1000)
        self.update_time()

    def update_time(self):
        self.time_label.setText(f" {datetime.now().strftime('%b %d, %Y  %I:%M:%S %p')}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())