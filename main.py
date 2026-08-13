"""程序入口：启动 GUI。"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui_window import MainWindow
from utils import setup_logging


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("平台数据采集")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
