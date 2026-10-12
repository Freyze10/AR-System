class AppStyles:
    """Tailwind-inspired Global Design System — Corporate Teal & Slate Theme"""

    # ── Tailwind Color Palette Tokens ──────────────────────────────────────────
    # Primary: Teal Scale
    TEAL_50 = "#F0FDFA"
    TEAL_100 = "#CCFBF1"
    TEAL_200 = "#99F6E4"
    TEAL_400 = "#2DD4BF"
    TEAL_500 = "#14B8A6"  # Primary Accent
    TEAL_600 = "#0D9488"  # Primary Hover
    TEAL_700 = "#0F766E"  # Primary Active / Dark

    # Neutral: Slate Scale
    SLATE_50 = "#F8FAFC"
    SLATE_100 = "#F1F5F9"
    SLATE_200 = "#E2E8F0"
    SLATE_300 = "#CBD5E1"
    SLATE_400 = "#94A3B8"
    SLATE_500 = "#64748B"
    SLATE_600 = "#475569"
    SLATE_700 = "#334155"
    SLATE_800 = "#1E293B"
    SLATE_900 = "#0F172A"

    # Semantic Status Colors
    EMERALD_500 = "#10B981"  # Success / Add
    EMERALD_600 = "#059669"

    AMBER_200 = "#FDECCE"  # Highlight / Warning fill
    AMBER_500 = "#F59E0B"
    AMBER_600 = "#D97706"
    AMBER_700 = "#B45309"

    RED_50 = "#FEF2F2"
    RED_300 = "#FCA5A5"
    RED_500 = "#EF4444"  # Danger / Delete / Remove
    RED_600 = "#DC2626"

    BLUE_500 = "#3B82F6"  # Info / Action
    BLUE_600 = "#2563EB"

    # ── Global Application Stylesheet (QSS) ────────────────────────────────────
    GLOBAL_STYLESHEET = f"""
        /* Base Window & Widget Resets */
        QMainWindow, QWidget {{
            background-color: {SLATE_50};
            font-family: "Inter", "Segoe UI", system-ui, sans-serif;
            font-size: 14px;
            color: {SLATE_900};
        }}

        /* ── Typography & Labels ──────────────────────────────────────────── */
        QLabel {{
            color: {SLATE_900};
            font-size: 13px;
        }}

        QLabel#HeadingTitle {{
            font-size: 20px;
            font-weight: 700;
            color: {SLATE_900};
        }}

        QLabel#SubtitleLabel {{
            font-size: 13px;
            color: {SLATE_600};
        }}

        /* Labels inside white cards must not paint the slate page background */
        QFrame#Card QLabel {{
            background: transparent;
        }}

        QLabel#CardTitle {{
            font-size: 11px;
            font-weight: 700;
            color: {TEAL_700};
            letter-spacing: 0.08em;
        }}

        QLabel#FieldLabel {{
            font-size: 12px;
            font-weight: 600;
            color: {SLATE_700};
        }}

        QLabel#CounterValue {{
            font-size: 26px;
            font-weight: 700;
            color: {TEAL_600};
        }}

        QLabel#InfoValue {{
            font-size: 14px;
            font-weight: 600;
            color: {SLATE_800};
        }}

        /* Summary card (selected record) */
        QLabel#SummaryLabel {{
            background: transparent;
            font-size: 11px;
            font-weight: 700;
            color: {SLATE_500};
            letter-spacing: 0.08em;
        }}

        QLabel#SummaryValue {{
            background: transparent;
            font-size: 20px;
            font-weight: 700;
            color: {TEAL_600};
        }}

        /* ── Form Inputs (Inputs, Dropdowns, DatePickers) ─────────────────── */
        QLineEdit, QComboBox, QDateEdit, QTextEdit, QDoubleSpinBox, QSpinBox {{
            background: white;
            border: 2px solid {SLATE_400};
            border-radius: 8px;
            padding: 5px 9px;
            color: {SLATE_900};
            selection-background-color: {TEAL_400};
            selection-color: {SLATE_900};
        }}

        QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTextEdit:hover,
        QDoubleSpinBox:hover, QSpinBox:hover {{
            border: 2px solid {SLATE_500};
        }}

        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus,
        QDoubleSpinBox:focus, QSpinBox:focus {{
            border: 2px solid {TEAL_600};
            background: white;
        }}

        QLineEdit:read-only, QLineEdit#ReadOnlyField {{
            background: {SLATE_100};
            color: {SLATE_600};
            border: 2px solid {SLATE_300};
        }}

        QLineEdit#ArNumberField {{
            background: {TEAL_50};
            color: {TEAL_700};
            border: 2px solid {TEAL_400};
            font-weight: 700;
            font-size: 15px;
        }}

        QLineEdit::placeholder, QTextEdit::placeholder {{
            color: {SLATE_400};
        }}

        QComboBox QAbstractItemView {{
            background: white;
            border: 2px solid {SLATE_400};
            selection-background-color: {TEAL_100};
            selection-color: {SLATE_900};
            outline: 0;
        }}

        /* ── Buttons (Tailwind Variants) ──────────────────────────────────── */
        QPushButton {{
            background: white;
            border: 2px solid {SLATE_400};
            border-radius: 8px;
            padding: 7px 15px;
            font-weight: 600;
            color: {SLATE_700};
        }}

        QPushButton:hover {{
            background: {SLATE_100};
            border-color: {SLATE_500};
            color: {SLATE_900};
        }}

        QPushButton:pressed {{
            background: {SLATE_200};
        }}

        QPushButton:disabled {{
            background: {SLATE_100};
            color: {SLATE_400};
            border-color: {SLATE_200};
        }}

        /* Primary Button (Corporate Teal Accent) */
        QPushButton#PrimaryButton, QPushButton.btn-primary {{
            background: {TEAL_600};
            color: white;
            border: 2px solid {TEAL_700};
            font-weight: 600;
        }}

        QPushButton#PrimaryButton:hover, QPushButton.btn-primary:hover {{
            background: {TEAL_700};
        }}

        QPushButton#PrimaryButton:pressed, QPushButton.btn-primary:pressed {{
            background: {TEAL_700};
            border-color: {SLATE_900};
        }}

        /* Secondary / Action Button (Slate Dark) */
        QPushButton#SecondaryButton, QPushButton.btn-secondary {{
            background: {SLATE_700};
            color: white;
            border: 2px solid {SLATE_900};
            font-weight: 600;
        }}

        QPushButton#SecondaryButton:hover, QPushButton.btn-secondary:hover {{
            background: {SLATE_900};
        }}

        /* Semantic Buttons */
        QPushButton#SuccessButton   {{ background: {EMERALD_600}; color: white; border: 2px solid #047857; font-weight: 600; }}
        QPushButton#SuccessButton:hover {{ background: #047857; }}

        QPushButton#DangerButton    {{ background: {RED_500}; color: white; border: 2px solid {RED_600}; font-weight: 600; }}
        QPushButton#DangerButton:hover  {{ background: {RED_600}; }}

        /* Warning Button (Update / Edit) */
        QPushButton#WarningButton {{
            background: {AMBER_500};
            color: white;
            border: 2px solid {AMBER_600};
            font-weight: 600;
        }}
        QPushButton#WarningButton:hover {{ background: {AMBER_600}; }}
        QPushButton#WarningButton:pressed {{ background: {AMBER_700}; }}

        /* Danger Outline Button (Close / Remove) */
        QPushButton#DangerOutlineButton {{
            background: white;
            color: {RED_600};
            border: 2px solid {RED_500};
            font-weight: 600;
        }}
        QPushButton#DangerOutlineButton:hover {{
            background: {RED_500};
            color: white;
            border-color: {RED_600};
        }}
        QPushButton#DangerOutlineButton:pressed {{
            background: {RED_600};
            color: white;
        }}

        /* Disabled state for every named button variant */
        QPushButton#PrimaryButton:disabled, QPushButton#SecondaryButton:disabled,
        QPushButton#SuccessButton:disabled, QPushButton#DangerButton:disabled,
        QPushButton#WarningButton:disabled, QPushButton#DangerOutlineButton:disabled {{
            background: {SLATE_100};
            color: {SLATE_400};
            border: 2px solid {SLATE_200};
        }}

        /* ── Tables & Data Grids ──────────────────────────────────────────── */
        QTableView, QTableWidget {{
            border: 2px solid {SLATE_400};
            border-radius: 8px;
            background-color: white;
            alternate-background-color: {SLATE_100};
            gridline-color: {SLATE_300};
            selection-background-color: {TEAL_100};
            selection-color: {SLATE_900};
            outline: 0;
        }}

        QTableWidget::item, QTableView::item {{
            padding: 6px;
            border-bottom: 1px solid {SLATE_300};
        }}

        QTableWidget::item:selected, QTableView::item:selected {{
            background-color: {TEAL_100};
            color: {SLATE_900};
            font-weight: 600;
            border-bottom: 1px solid {TEAL_500};
        }}

        QHeaderView::section {{
            background-color: {SLATE_200};
            color: {SLATE_700};
            padding: 8px 6px;
            border: none;
            border-right: 1px solid {SLATE_300};
            border-bottom: 2px solid {SLATE_400};
            font-weight: 700;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        /* ── Tabs Component ───────────────────────────────────────────────── */
        QTabWidget::pane {{
            border: 2px solid {SLATE_300};
            background: white;
            border-radius: 8px;
            margin-top: -1px;
        }}

        QTabBar::tab {{
            background: {SLATE_100};
            border: 2px solid {SLATE_300};
            padding: 10px 20px;
            margin-right: 4px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            color: {SLATE_600};
            font-weight: 500;
        }}

        QTabBar::tab:hover {{
            background: {SLATE_50};
            color: {SLATE_900};
        }}

        QTabBar::tab:selected {{
            background: white;
            color: {TEAL_700};
            border-bottom: 3px solid {TEAL_500};
            font-weight: 600;
        }}

        /* Main module tabs (AR Record / AR Entry) */
        QTabWidget#MainTabs::pane {{
            border: none;
            border-top: 2px solid {SLATE_300};
            border-radius: 0px;
            background: {SLATE_50};
        }}
        QTabWidget#MainTabs::tab-bar {{
            left: 24px;
        }}
        QTabWidget#MainTabs QTabBar::tab {{
            margin-top: 12px;
        }}
        QTabWidget#MainTabs QTabBar::tab:selected {{
            background: {SLATE_50};
        }}

        /* ── Cards / Containers ───────────────────────────────────────────── */
        QFrame#Card, QWidget#Card {{
            background: white;
            border: 2px solid {SLATE_300};
            border-radius: 12px;
            padding: 16px;
        }}

        /* ── Scrollbars ───────────────────────────────────────────────────── */
        QScrollBar:vertical {{
            background: {SLATE_100};
            width: 12px;
            border-radius: 6px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {SLATE_400};
            border-radius: 6px;
            min-height: 36px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {SLATE_500};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        /* ── Sidebar Component Styles ─────────────────────────────────────── */
        QWidget#SideMenu {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SLATE_900}, stop:1 {SLATE_800});
            min-width: 260px;
            border-right: 1px solid rgba(255,255,255,0.06);
        }}
        QWidget#SideMenu QWidget {{
            background: transparent;
            color: white;
        }}

        #SideMenu QWidget QLabel {{
            color: white;
            background: transparent;
        }}

        #SideMenu QWidget#ProfileCard {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            margin: 8px 8px 0px 8px;
            padding: 4px;
        }}

        #SideMenu #MenuLabel {{
            font-size: 11px;
            font-weight: 700;
            color: {SLATE_400};
            padding: 16px 20px 8px 20px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        #SideMenu QPushButton {{
            background: transparent;
            color: {SLATE_300};
            border: none;
            text-align: left;
            padding: 14px 20px;
            font-size: 14px;
            font-weight: 500;
            border-radius: 10px;
            margin: 2px 12px;
        }}

        #SideMenu QPushButton:hover {{
            background: rgba(255,255,255,0.07);
            color: white;
            padding-left: 24px;
        }}

        #SideMenu QPushButton:checked {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {TEAL_600}, stop:1 {TEAL_500});
            font-weight: 600;
            color: white;
        }}

        QFrame#SidebarSeparator {{
            background: rgba(255,255,255,0.10);
            height: 1px;
            margin: 10px 0;
        }}

        /* ── Logout Button Style (Global Definition) ─────────────────────── */
        QPushButton#LogoutButton {{
            background: transparent;
            color: {RED_500};
            border: none;
            text-align: left;
            padding: 12px 20px;
            font-size: 14px;
            font-weight: 600;
            border-radius: 10px;
            margin: 2px 12px;
        }}

        QPushButton#LogoutButton:hover {{
            background: rgba(239, 68, 68, 0.1);
            color: #F87171;
            padding-left: 24px;
        }}

    """