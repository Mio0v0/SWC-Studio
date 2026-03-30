"""SWC Studio GUI entrypoint."""

import sys

from .font_utils import pick_app_font
from .main_window import SWCMainWindow


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("SWC Studio")
    app.setStyle("Fusion")
    app.setFont(pick_app_font())

    window = SWCMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
