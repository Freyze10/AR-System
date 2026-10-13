import sys

from PyQt6.QtWidgets import QApplication, QDialog

from db.schema import create_table
from login import LoginWindow
from main_window import MainWindow
from styles.styles import AppStyles


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(AppStyles.GLOBAL_STYLESHEET)  # login + main window share the global theme
    create_table()

    while True:
        login = LoginWindow()
        if login.exec() != QDialog.DialogCode.Accepted:
            break

        window = MainWindow(login.username, login.role)
        logged_out = []
        window.logout_requested.connect(lambda: logged_out.append(True))
        app.exec()

        if not logged_out:   # window closed normally -> quit; logout -> back to sign-in
            break

    sys.exit(0)


if __name__ == "__main__":
    main()