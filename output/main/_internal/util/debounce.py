from PyQt6.QtCore import QTimer


def finished_typing(line_edit, callback, delay=400):
    """Calls `callback` once the user has stopped typing in `line_edit` for `delay` ms.
    Returns the timer so the caller can stop it."""
    timer = QTimer(line_edit)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)

    # Restart the timer on every text change
    line_edit.textChanged.connect(lambda: timer.start(delay))
    return timer