from datetime import datetime

import qtawesome as fa
from PyQt6.QtCore import Qt, QStringListModel, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView,
    QMessageBox, QComboBox, QCompleter, QTabWidget
)

from db.read.user_management import get_roles, get_users, get_user, username_exists, get_role_usage, role_exists
from db.write.audit_trail import log_action
from db.write.user_management import update_user, add_user, delete_user, add_role, delete_role
from menu.ar_report.ar_audit import workstation_mac

MIN_PASSWORD = 6


# ── Helpers ───────────────────────────────────────────────────────────────
def _icon(name, color, active=None):
    return fa.icon(name, color=color, color_active=active or color, color_disabled="#94A3B8")


def _now():
    """Current time for the 'refreshed at' text next to the record count."""
    return datetime.now().strftime("%I:%M:%S %p")


def _db_error(parent, title, error):
    QMessageBox.critical(parent, title, f"{title}:\n{error}")


def _confirm(parent, title, text):
    return QMessageBox.question(
        parent, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    ) == QMessageBox.StandardButton.Yes


def _card(title):
    frame = QFrame()
    frame.setObjectName("Card")
    body = QVBoxLayout(frame)
    body.setContentsMargins(8, 8, 8, 8)
    body.setSpacing(12)
    lbl = QLabel(title)
    lbl.setObjectName("CardTitle")
    body.addWidget(lbl)
    return frame, body, lbl


def _field(caption, widget, required=False):
    box = QVBoxLayout()
    box.setSpacing(4)
    text = caption + (' <span style="color:#EF4444">*</span>' if required else "")
    lbl = QLabel(text)
    lbl.setObjectName("FieldLabel")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    box.addWidget(lbl)
    box.addWidget(widget)
    return box


def _heading(title_text, subtitle_text):
    box = QVBoxLayout()
    box.setSpacing(2)
    title = QLabel(title_text)
    title.setObjectName("HeadingTitle")
    subtitle = QLabel(subtitle_text)
    subtitle.setObjectName("SubtitleLabel")
    box.addWidget(title)
    box.addWidget(subtitle)
    return box


def _make_table(columns):
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(36)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return table


def _refresh_button(slot):
    """The teal Refresh button used in the footer of both tabs."""
    btn = QPushButton(" Refresh", icon=_icon("fa5s.sync-alt", "white"))
    btn.setObjectName("PrimaryButton")
    btn.clicked.connect(slot)
    return btn


def _password_field(placeholder):
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setPlaceholderText(placeholder)
    edit.setMaxLength(36)  # tbl_user.password is VARCHAR(36)

    action = edit.addAction(_icon("fa5s.eye", "#64748B"), QLineEdit.ActionPosition.TrailingPosition)
    action.setCheckable(True)
    action.setToolTip("Show / hide password")

    def toggle(show):
        edit.setEchoMode(QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password)
        action.setIcon(_icon("fa5s.eye-slash" if show else "fa5s.eye", "#64748B"))

    action.toggled.connect(toggle)
    return edit


# ── Tab 1: User Accounts ──────────────────────────────────────────────────
# TODO: ADD first name and lastname in the field for the user && update the database to contain fullname
class UsersTab(QWidget):
    def __init__(self, username="Brant"):
        super().__init__()
        self.username = username
        self._editing_id = None
        self._build_ui()
        self.load_roles()
        self.load_users()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addLayout(_heading("User Accounts", "Create and manage who can sign in to the system"))

        # Form
        card, body, self.card_title = _card("NEW USER ACCOUNT")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("e.g. jdelacruz")
        self.txt_username.setMaxLength(50)
        self.txt_password = _password_field(f"At least {MIN_PASSWORD} characters")
        self.txt_confirm = _password_field("Re-enter password")
        self.cmb_role = QComboBox()

        grid.addLayout(_field("Username", self.txt_username, True), 0, 0)
        grid.addLayout(_field("Role (Department — Role)", self.cmb_role, True), 0, 1)
        grid.addLayout(_field("Password", self.txt_password, True), 1, 0)
        grid.addLayout(_field("Confirm Password", self.txt_confirm, True), 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        body.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        hint = QLabel("Hostname, IP address and MAC address are filled in automatically at the user's first login.")
        hint.setObjectName("SubtitleLabel")
        actions.addWidget(hint)
        actions.addStretch(1)

        self.btn_clear = QPushButton(" Clear", icon=_icon("fa5s.eraser", "#334155"))
        self.btn_clear.clicked.connect(self.clear_form)
        self.btn_save = QPushButton(" Save User", icon=_icon("fa5s.save", "white"))
        self.btn_save.setObjectName("SuccessButton")
        self.btn_save.clicked.connect(self.save_user)
        actions.addWidget(self.btn_clear)
        actions.addWidget(self.btn_save)
        body.addLayout(actions)
        root.addWidget(card)

        self.txt_confirm.returnPressed.connect(self.save_user)

        # Table
        self.table = _make_table(["Username", "Department", "Role", "Hostname", "IP Address", "MAC Address"])
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_user())
        root.addWidget(self.table, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("SubtitleLabel")
        footer.addWidget(self.lbl_count)
        footer.addStretch(1)

        self.btn_edit = QPushButton(" Edit", icon=_icon("fa5s.edit", "white"))
        self.btn_edit.setObjectName("WarningButton")
        self.btn_edit.clicked.connect(self.edit_user)

        self.btn_delete = QPushButton(" Delete", icon=_icon("fa5s.trash-alt", "#DC2626", "white"))
        self.btn_delete.setObjectName("DangerOutlineButton")
        self.btn_delete.clicked.connect(self.delete_user)

        footer.addWidget(_refresh_button(self.refresh))
        footer.addWidget(self.btn_edit)
        footer.addWidget(self.btn_delete)
        root.addLayout(footer)
        self._on_selection()

    # ── Data ──────────────────────────────────────────────────────────────
    def load_roles(self):
        current = self.cmb_role.currentData()
        try:
            rows = get_roles()
        except Exception as e:
            _db_error(self, "Could not load roles", e)
            return

        self.cmb_role.clear()
        self.cmb_role.addItem("Select department and role...", None)
        for role_id, dept, role in rows:
            self.cmb_role.addItem(f"{dept}  —  {role}", role_id)
        self.cmb_role.setCurrentIndex(max(self.cmb_role.findData(current), 0))

    def load_users(self):
        try:
            rows = get_users()
        except Exception as e:
            _db_error(self, "Could not load users", e)
            return

        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for r, (user_id, username, dept, role, host, ip, mac) in enumerate(rows):
            values = [username, dept, role, host or "—", ip or "—", mac or "—"]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, user_id)
                self.table.setItem(r, c, item)

        # The time shows when the list was last read from the database
        self.lbl_count.setText(f"{len(rows):,} account(s)  ·  refreshed {_now()}")
        self._on_selection()

    def refresh(self):
        """Read the roles and users from the database again (for example to see a
        user's hostname, IP and MAC after their first login). The selected user stays
        selected, and whatever is typed in the form is left alone."""
        selected = self._selected()
        self.load_roles()
        self.load_users()
        if selected:
            self._select_user(selected[0])

    def _select_user(self, user_id):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) == user_id:
                self.table.selectRow(r)
                return

    # ── Form mode ─────────────────────────────────────────────────────────
    def _set_mode(self, user_id=None):
        self._editing_id = user_id
        editing = user_id is not None
        self.card_title.setText("EDIT USER ACCOUNT" if editing else "NEW USER ACCOUNT")
        self.btn_save.setText(" Update User" if editing else " Save User")
        self.btn_clear.setText(" Cancel" if editing else " Clear")

    def clear_form(self):
        self.txt_username.clear()
        self.txt_password.clear()
        self.txt_confirm.clear()
        self.cmb_role.setCurrentIndex(0)
        self._set_mode(None)
        self.txt_username.setFocus()

    def edit_user(self):
        sel = self._selected()
        if not sel:
            return
        user_id, _ = sel

        try:
            user = get_user(user_id)
        except Exception as e:
            _db_error(self, "Could not load user", e)
            return
        if not user:
            QMessageBox.warning(self, "Not Found", "That user no longer exists.")
            self.load_users()
            return

        username, role_id, password = user
        self.txt_username.setText(username)
        self.txt_password.setText(password)
        self.txt_confirm.setText(password)
        self.cmb_role.setCurrentIndex(max(self.cmb_role.findData(role_id), 0))
        self._set_mode(user_id)
        self.txt_username.setFocus()

    # ── Actions ───────────────────────────────────────────────────────────
    def save_user(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text()
        confirm = self.txt_confirm.text()
        role_id = self.cmb_role.currentData()

        if len(username) < 3:
            return self._warn("Username", "Username must be at least 3 characters.", self.txt_username)
        if role_id is None:
            return self._warn("Role", "Please select a department and role.", self.cmb_role)
        if len(password) < MIN_PASSWORD:
            return self._warn("Password", f"Password must be at least {MIN_PASSWORD} characters.", self.txt_password)
        if password != confirm:
            return self._warn("Password", "The passwords do not match.", self.txt_confirm)

        editing = self._editing_id is not None
        try:
            if username_exists(username, self._editing_id):
                return self._warn("Username Taken", f"The username '{username}' already exists.", self.txt_username)

            if editing:
                update_user(self._editing_id, role_id, username, password)
                log_action("UPDATE", f"Updated user account '{username}'",
                           username=self.username, mac_address=workstation_mac())  # Or pass current admin username if tracked
            else:
                add_user(role_id, username, password)
                log_action("SAVE", f"Created new user account '{username}'",
                           username=self.username, mac_address=workstation_mac())
        except Exception as e:
            _db_error(self, "Could not save user", e)
            return

        QMessageBox.information(
            self, "Saved", f"User account '{username}' {'updated' if editing else 'created'}.")
        self.clear_form()
        self.load_users()

    def _warn(self, title, text, widget):
        QMessageBox.warning(self, title, text)
        widget.setFocus()

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole), self.table.item(row, 0).text()

    def _on_selection(self):
        enabled = self._selected() is not None
        self.btn_edit.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)

    def delete_user(self):
        sel = self._selected()
        if not sel:
            return
        user_id, username = sel
        if not _confirm(self, "Delete User", f"Delete the account '{username}'?\nThis cannot be undone."):
            return

        try:
            delete_user(user_id)
            log_action("DELETE", f"Deleted user account '{username}'",
                       username=self.username, mac_address=workstation_mac())
        except Exception as e:
            _db_error(self, "Could not delete user", e)
            return

        if self._editing_id == user_id:
            self.clear_form()
        self.load_users()


# ── Tab 2: Departments & Roles ────────────────────────────────────────────
class RolesTab(QWidget):
    roles_changed = pyqtSignal()

    def __init__(self, username="Brant"):
        super().__init__()
        self.username = username
        self._departments = []
        self.dept_model = QStringListModel(self)
        self._build_ui()
        self.load_roles()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addLayout(_heading("Departments & Roles", "Define the department and role choices used for accounts"))

        card, body, _ = _card("ADD DEPARTMENT / ROLE")
        row = QHBoxLayout()
        row.setSpacing(16)

        self.txt_dept = QLineEdit()
        self.txt_dept.setPlaceholderText("Pick an existing department or type a new one")
        self.txt_dept.setMaxLength(36)
        completer = QCompleter(self.dept_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.txt_dept.setCompleter(completer)

        self.txt_role = QLineEdit()
        self.txt_role.setPlaceholderText("e.g. Staff")
        self.txt_role.setMaxLength(10)

        row.addLayout(_field("Department", self.txt_dept, True), 3)
        row.addLayout(_field("Role (max 10 characters)", self.txt_role, True), 2)
        body.addLayout(row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        hint = QLabel("A new department name creates the department. An existing name adds another role to it.")
        hint.setObjectName("SubtitleLabel")
        actions.addWidget(hint)
        actions.addStretch(1)
        btn_add = QPushButton(" Add", icon=_icon("fa5s.plus", "white"))
        btn_add.setObjectName("PrimaryButton")
        btn_add.clicked.connect(self.add_role)
        actions.addWidget(btn_add)
        body.addLayout(actions)
        root.addWidget(card)

        self.txt_role.returnPressed.connect(self.add_role)
        self.txt_dept.returnPressed.connect(self.add_role)

        self.table = _make_table(["Department", "Role", "Users"])
        self.table.itemSelectionChanged.connect(self._on_selection)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("SubtitleLabel")
        footer.addWidget(self.lbl_count)
        footer.addStretch(1)
        self.btn_delete = QPushButton(" Delete Role", icon=_icon("fa5s.trash-alt", "#DC2626", "white"))
        self.btn_delete.setObjectName("DangerOutlineButton")
        self.btn_delete.clicked.connect(self.delete_role)
        footer.addWidget(_refresh_button(self.load_roles))
        footer.addWidget(self.btn_delete)
        root.addLayout(footer)
        self._on_selection()

    # ── Data ──────────────────────────────────────────────────────────────
    def load_roles(self):
        try:
            rows = get_role_usage()
        except Exception as e:
            _db_error(self, "Could not load roles", e)
            return

        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for r, (role_id, dept, role, users) in enumerate(rows):
            for c, text in enumerate([dept, role, str(users)]):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, (role_id, users))
                if c == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)

        self._departments = sorted({row[1] for row in rows})
        self.dept_model.setStringList(self._departments)
        self.lbl_count.setText(
            f"{len(rows):,} role(s) in {len(self._departments):,} department(s)  ·  refreshed {_now()}")
        self._on_selection()

    # ── Actions ───────────────────────────────────────────────────────────
    def add_role(self):
        dept = self.txt_dept.text().strip()
        role = self.txt_role.text().strip()
        if not dept:
            QMessageBox.warning(self, "Department", "Please enter the department.")
            self.txt_dept.setFocus()
            return
        if not role:
            QMessageBox.warning(self, "Role", "Please enter the role.")
            self.txt_role.setFocus()
            return

        # Reuse the stored spelling if the department already exists (ignoring case)
        dept = next((d for d in self._departments if d.lower() == dept.lower()), dept)

        try:
            if role_exists(dept, role):
                QMessageBox.warning(self, "Already Exists", f"'{dept} — {role}' already exists.")
                return
            add_role(dept, role)
            log_action("SAVE", f"Created department and role choice: '{dept} — {role}'",
                       username=self.username, mac_address=workstation_mac())
        except Exception as e:
            _db_error(self, "Could not add role", e)
            return

        self.txt_role.clear()
        self.txt_role.setFocus()
        self.load_roles()
        self.roles_changed.emit()

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        role_id, users = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return role_id, users, self.table.item(row, 0).text(), self.table.item(row, 1).text()

    def _on_selection(self):
        self.btn_delete.setEnabled(self._selected() is not None)

    def delete_role(self):
        sel = self._selected()
        if not sel:
            return
        role_id, users, dept, role = sel

        if users:
            QMessageBox.warning(
                self, "Role In Use",
                f"'{dept} — {role}' is assigned to {users} user(s).\n"
                "Reassign or delete those users first.")
            return
        if not _confirm(self, "Delete Role", f"Delete '{dept} — {role}'?"):
            return

        try:
            delete_role(role_id)
            log_action("DELETE", f"Deleted department and role choice: '{dept} — {role}'",
                       username=self.username, mac_address=workstation_mac())
        except Exception as e:
            _db_error(self, "Could not delete role", e)
            return
        self.load_roles()
        self.roles_changed.emit()


# ── Container ─────────────────────────────────────────────────────────────
class UserManagementWidget(QWidget):
    """User management: Tab 1 = user accounts, Tab 2 = departments & roles."""

    def __init__(self, username="Brant"):
        super().__init__()
        self.username = username
        self.users_tab = UsersTab(username=self.username)
        self.roles_tab = RolesTab(username=self.username)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainTabs")
        self.tabs.addTab(self.users_tab, _icon("fa5s.users", "#64748B"), " User Accounts")
        self.tabs.addTab(self.roles_tab, _icon("fa5s.sitemap", "#64748B"), " Departments && Roles")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

        self.roles_tab.roles_changed.connect(self.users_tab.load_roles)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        widget = self.tabs.widget(index)
        if widget is self.roles_tab:
            self.roles_tab.load_roles()      # refresh the per-role user counts
        elif widget is self.users_tab:
            self.users_tab.load_users()