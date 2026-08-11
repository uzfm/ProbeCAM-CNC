import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from probe_cam_app import ProbeCAMMainWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("ProbeCAM CNC")
    app.setOrganizationName("ProbeCAM")
    app.setApplicationVersion("0.1.0")

    window = ProbeCAMMainWindow()
    window.show()

    sys.exit(app.exec())
