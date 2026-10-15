"""CheeseStick, the turtle this trainer is named for."""
import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

DEDICATION = "CheeseStick was a turtle. He stays here, in armor, with a shield."


def asset_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "cheesestick.jpg")


def pixmap(size):
    pm = QPixmap(asset_path())
    if pm.isNull() or size <= 0:
        return pm
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def icon():
    return QIcon(asset_path())


SHELL_GREEN = "#4f7a3a"
SHELL_GREEN_DARK = "#2c4424"


def shell_texture_path(size=48):
    """Paint a faint shell-hex tile once (QPainter, no extra deps) and return its path for the stylesheet."""
    import math, tempfile
    from PySide6.QtGui import QImage, QPainter, QPen, QColor, QPolygonF
    from PySide6.QtCore import QPointF
    path = os.path.join(tempfile.gettempdir(), "cheesestick_shell_%d.png" % size)
    if os.path.exists(path):
        return path
    r = size / 3.0
    w, h = int(round(3 * r)), int(round(math.sqrt(3) * r))
    img = QImage(w, h, QImage.Format_ARGB32); img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(79, 122, 58, 34), 1.2))

    def hexagon(cx, cy):
        return QPolygonF([QPointF(cx + r * math.cos(math.radians(60 * k)), cy + r * math.sin(math.radians(60 * k)))
                          for k in range(6)])
    for cx, cy in ((0, 0), (w, 0), (0, h), (w, h), (1.5 * r, h / 2)):
        p.drawPolygon(hexagon(cx, cy))
    p.end()
    img.save(path)
    return path


def shell_qss():
    """Extra stylesheet: hex shell texture on panels, shell-green accents next to the red and gold."""
    url = shell_texture_path().replace("\\", "/")
    return """
QTabWidget::pane { background-color: #181315; background-image: url(%(u)s); }
QGroupBox { border: 1px solid %(g2)s; }
QGroupBox::title { color: #f2c96d; border-bottom: 1px solid %(g)s; }
#HeaderBar { border-bottom: 2px solid #8a6d2f; }
#CheeseMark { border: 2px solid %(g)s; border-radius: 10px; background: %(g2)s; padding: 2px; }
QTabBar::tab:selected { border-bottom: 2px solid %(g)s; }
QCheckBox::indicator:checked { background: %(g)s; border-color: #c79a3a; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %(g2)s, stop:0.5 %(g)s, stop:1 #c79a3a); }
QSplitter::handle:hover { background: %(g)s; }
QPushButton#ShellButton { background: %(g2)s; border-color: %(g)s; color: #f0e6c8; }
QPushButton#ShellButton:hover { background: %(g)s; border-color: #c79a3a; }
""" % {"u": url, "g": SHELL_GREEN, "g2": SHELL_GREEN_DARK}
