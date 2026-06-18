"""SWC Studio GUI entrypoint."""

import sys

from PySide6.QtGui import QColor, QPalette

from .font_utils import pick_app_font


def _apply_light_palette(app) -> None:
    """Pin the application palette to a light theme.

    Without this, Qt's Fusion style follows the host OS theme — which
    on Windows means a fresh user with system dark mode enabled sees a
    half-broken UI: panels with explicit light stylesheets stay white
    while widgets without explicit colors fall through to dark
    palette roles, leaving white text on white backgrounds (and vice
    versa) all over the place. Pinning every palette role here gives
    identical rendering on macOS, Windows light mode, and Windows dark
    mode.
    """
    palette = QPalette()

    # Active group — the standard look for foreground windows.
    palette.setColor(QPalette.Window, QColor("#f0f0f0"))
    palette.setColor(QPalette.WindowText, QColor("#000000"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f6f6f6"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.PlaceholderText, QColor("#888888"))
    palette.setColor(QPalette.Text, QColor("#000000"))
    palette.setColor(QPalette.Button, QColor("#e1e1e1"))
    palette.setColor(QPalette.ButtonText, QColor("#000000"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Light, QColor("#ffffff"))
    palette.setColor(QPalette.Midlight, QColor("#e3e3e3"))
    palette.setColor(QPalette.Dark, QColor("#555555"))
    palette.setColor(QPalette.Mid, QColor("#b3b3b3"))
    palette.setColor(QPalette.Shadow, QColor("#767676"))
    # Selection background is a soft blue tint with dark text instead of
    # the classic Fusion vivid-blue + white text. Vivid blue + white can
    # render as white-on-very-light-grey on some Windows configurations,
    # making selected items unreadable; dark text on light blue is safe
    # on every theme.
    palette.setColor(QPalette.Highlight, QColor("#d6e8ff"))
    palette.setColor(QPalette.HighlightedText, QColor("#000000"))
    palette.setColor(QPalette.Link, QColor("#0066cc"))
    palette.setColor(QPalette.LinkVisited, QColor("#663399"))

    # Disabled group — used when widgets are greyed out during long
    # operations (e.g. while a worker thread is running).
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#909090"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#909090"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#909090"))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#cccccc"))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor("#666666"))

    app.setPalette(palette)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--swcstudio-auto-label-worker":
        from .auto_label_process import run_files

        run_files(sys.argv[2], sys.argv[3])
        return

    if len(sys.argv) == 4 and sys.argv[1] == "--swcstudio-type-suspicion-worker":
        from .type_suspicion_process import run_files

        run_files(sys.argv[2], sys.argv[3])
        return

    from PySide6.QtWidgets import QApplication
    from .main_window import SWCMainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("SWC Studio")
    # Use Fusion so the rendering is identical across platforms — the
    # native macOS / Windows styles otherwise apply different padding,
    # corner radii, and palette interpretation.
    app.setStyle("Fusion")
    app.setFont(pick_app_font())
    _apply_light_palette(app)

    # Application-wide stylesheet for widget classes that don't honour
    # the palette directly (tooltips, item-view rows). Per-panel
    # stylesheets in main_window.py and the panel files override
    # individual surfaces; this is the safety net.
    app.setStyleSheet(
        """
        QToolTip {
          color: #000000;
          background-color: #ffffff;
          border: 1px solid #b8c4d3;
          padding: 2px 6px;
          margin: 0px;
        }
        QWidget {
          color: #000000;
          background-color: #f0f0f0;
        }
        QAbstractItemView {
          color: #000000;
          background-color: #ffffff;
          alternate-background-color: #f6f6f6;
        }
        QAbstractItemView::item {
          color: #000000;
        }
        /* No global selection-background rule: panels that want a
           selection highlight rely on the soft-blue palette set above,
           and panels that want NO highlight (e.g. the Issues panel,
           which explicitly forces a transparent highlight in its own
           per-widget stylesheet and palette) are not stomped by this
           sheet. */
        QHeaderView::section {
          color: #000000;
          background-color: #e1e1e1;
        }
        QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
        QComboBox, QComboBox QAbstractItemView {
          color: #000000;
          background-color: #ffffff;
        }
        QMenu, QMenuBar, QMenuBar::item {
          color: #000000;
          background-color: #f0f0f0;
        }
        /* Hover/selected menu items: keep dark text, soft blue
           background. The previous white-on-blue rendered as
           white-on-light-grey on Windows Fusion, leaving the text
           almost invisible. */
        QMenu::item:selected, QMenuBar::item:selected {
          color: #000000;
          background-color: #d6e8ff;
        }
        QPushButton:hover {
          background-color: #ebf2fb;
        }
        QPushButton:default {
          color: #000000;
        }
        QTabWidget::pane {
          background-color: #f0f0f0;
        }
        QTabBar::tab {
          color: #000000;
          background-color: #e1e1e1;
        }
        QTabBar::tab:hover {
          color: #000000;
          background-color: #ebf2fb;
        }
        QTabBar::tab:selected {
          color: #000000;
          background-color: #ffffff;
        }
        """
    )

    window = SWCMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
