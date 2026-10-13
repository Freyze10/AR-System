import qtawesome as fa
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QMessageBox
)

from db.read.login import authenticate_user, has_mac_address
from db.write.login import register_workstation

from workstation.workstation import get_workstation_info
from styles.styles import AppStyles


class LoginWindow(QDialog):
    """Sign-in dialog. After exec() == Accepted, read .username and .role."""

    def __init__(self):
        super().__init__()
        self.username = None
        self.role = None

        self.setObjectName("LoginWindow")
        self.setWindowTitle("AR-SYSTEM | Sign In")
        self.setFixedSize(820, 500)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_brand_panel())
        root.addWidget(self._build_form_panel(), 1)

    def _build_brand_panel(self):
        panel = QFrame()
        panel.setObjectName("LoginBrand")
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(36, 48, 36, 36)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(fa.icon("fa5s.file-signature", color=AppStyles.TEAL_400).pixmap(QSize(72, 72)))
        layout.addWidget(icon)
        layout.addSpacing(12)

        title = QLabel("AR System")
        title.setObjectName("LoginBrandTitle")
        text = QLabel("Acknowledgement Receipt\nManagement")
        text.setObjectName("LoginBrandText")
        layout.addWidget(title)
        layout.addWidget(text)

        layout.addStretch(1)
        footer = QLabel("MASTERBATCH PHILIPPINES INCORPORATED")
        footer.setObjectName("LoginBrandFooter")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return panel

    def _build_form_panel(self):
        panel = QFrame()
        panel.setObjectName("LoginForm")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(56, 48, 56, 36)
        layout.setSpacing(12)

        title = QLabel("Sign In")
        title.setObjectName("LoginTitle")
        subtitle = QLabel("Enter your username and password to continue")
        subtitle.setObjectName("SubtitleLabel")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)

        self.txt_username = QLineEdit()
        self.txt_username.setObjectName("LoginInput")
        self.txt_username.setPlaceholderText("Username")
        self.txt_username.setMaxLength(50)
        self.txt_username.addAction(fa.icon("fa5s.user", color=AppStyles.SLATE_500),
                                    QLineEdit.ActionPosition.LeadingPosition)

        self.txt_password = QLineEdit()
        self.txt_password.setObjectName("LoginInput")
        self.txt_password.setPlaceholderText("Password")
        self.txt_password.setMaxLength(36)
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.addAction(fa.icon("fa5s.lock", color=AppStyles.SLATE_500),
                                    QLineEdit.ActionPosition.LeadingPosition)
        self._add_show_toggle(self.txt_password)

        layout.addLayout(self._field("Username", self.txt_username))
        layout.addLayout(self._field("Password", self.txt_password))

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("LoginError")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        layout.addSpacing(8)
        self.btn_login = QPushButton(
            " Sign In", icon=fa.icon("fa5s.sign-in-alt", color="white", color_disabled=AppStyles.SLATE_400))
        self.btn_login.setObjectName("PrimaryButton")
        self.btn_login.setMinimumHeight(46)
        self.btn_login.setDefault(True)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.clicked.connect(self.handle_login)
        layout.addWidget(self.btn_login)

        layout.addStretch(1)
        btn_exit = QPushButton("Close Application")
        btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exit.clicked.connect(self.reject)
        layout.addWidget(btn_exit)

        self.txt_username.returnPressed.connect(self.txt_password.setFocus)
        self.txt_password.returnPressed.connect(self.handle_login)
        self.txt_username.setFocus()
        return panel

    def _field(self, caption, widget):
        box = QVBoxLayout()
        box.setSpacing(4)
        lbl = QLabel(caption)
        lbl.setObjectName("FieldLabel")
        box.addWidget(lbl)
        box.addWidget(widget)
        return box

    def _add_show_toggle(self, edit):
        action = edit.addAction(fa.icon("fa5s.eye", color=AppStyles.SLATE_500),
                                QLineEdit.ActionPosition.TrailingPosition)
        action.setCheckable(True)
        action.setToolTip("Show / hide password")

        def toggle(show):
            edit.setEchoMode(QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password)
            action.setIcon(fa.icon("fa5s.eye-slash" if show else "fa5s.eye", color=AppStyles.SLATE_500))

        action.toggled.connect(toggle)

    def _show_error(self, text):
        self.lbl_error.setText(text)
        self.lbl_error.show()

    # ── Login ─────────────────────────────────────────────────────────────
    def handle_login(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text()

        if not username or not password:
            self._show_error("Please enter your username and password.")
            return

        try:
            user = authenticate_user(username, password)
            if user is None:
                self._show_error("Invalid username or password.")
                self.txt_password.clear()
                self.txt_password.setFocus()
                return

            user_id, name, _department, role = user

            # First login on a workstation: record hostname / IP / MAC
            if not has_mac_address(user_id):
                ws = get_workstation_info()
                register_workstation(user_id, ws["h"], ws["i"], ws["m"])
        except Exception as e:
            QMessageBox.critical(self, "Sign In Failed", f"Could not sign in:\n{e}")
            return

        self.username = name
        self.role = role
        self.accept()