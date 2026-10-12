from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class AcknowledgementReceiptWidget(QWidget):
    """Bare placeholder layout for the AR Report section"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        # Simple placeholder heading to signify navigation landing zone
        title = QLabel("Acknowledgement Receipt Module")
        title.setObjectName("HeadingTitle")
        layout.addWidget(title)

        subtitle = QLabel("Module layout cleared. Ready for your custom view design.")
        subtitle.setStyleSheet("color: #64748B; font-size: 14px;")
        layout.addWidget(subtitle)

        layout.addStretch()