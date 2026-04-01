"""SWC Studio GUI entrypoint."""

import sys

from PySide6.QtGui import QColor, QPalette

from .font_utils import pick_app_font
from .main_window import SWCMainWindow


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("SWC Studio")
    app.setStyle("Fusion")
    app.setFont(pick_app_font())
    palette = app.palette()
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipText, QColor("#000000"))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QToolTip {
          color: #000000;
          background-color: #ffffff;
          border: 1px solid #b8c4d3;
          padding: 2px 6px;
          margin: 0px;
        }
        """
    )

    window = SWCMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
