# ion_overlay.py
import json
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

class ScreenAnnotationOverlay(QWidget):
    """
    Transparent click-through overlay that draws boxes for a short time.

    Accepts tool_args as either:
    - JSON list: [{"x":10,"y":20,"w":200,"h":80,"label":"Button"}, ...]
    - Or anything else -> shows nothing (won't crash).
    """
    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)

        self._boxes = []

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def draw_boxes(self, tool_args: str, ms: int = 2000):
        self._boxes = self._parse_boxes(tool_args)

        screen = QApplication.primaryScreen()
        geo = screen.virtualGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.setGeometry(geo)

        self.show()
        self.raise_()
        self.update()
        self._hide_timer.start(ms)

    def _parse_boxes(self, tool_args: str):
        try:
            data = json.loads(tool_args)
            if isinstance(data, list):
                out = []
                for b in data:
                    if not isinstance(b, dict):
                        continue
                    x = int(b.get("x", 0))
                    y = int(b.get("y", 0))
                    w = int(b.get("w", 0))
                    h = int(b.get("h", 0))
                    label = str(b.get("label", "") or "")
                    if w > 0 and h > 0:
                        out.append({"x": x, "y": y, "w": w, "h": h, "label": label})
                return out
        except Exception:
            pass
        return []

    def paintEvent(self, _event):
        if not self._boxes:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(QColor("#3daee9"))
        pen.setWidth(3)
        p.setPen(pen)

        font = QFont("Sans Serif", 10)
        p.setFont(font)

        for b in self._boxes:
            rect = QRect(b["x"], b["y"], b["w"], b["h"])
            p.drawRect(rect)
            if b["label"]:
                p.setPen(QColor("#ffffff"))
                p.drawText(rect.adjusted(6, 14, -6, -6), b["label"])
                p.setPen(pen)
