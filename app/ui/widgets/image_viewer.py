"""Interactive pan and zoom image viewer canvas with overlay annotations."""
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsEllipseItem
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QWheelEvent
from PySide6.QtCore import Qt, QRectF, Signal
import cv2
import numpy as np


class ImageViewer(QGraphicsView):
    """QGraphicsView with smooth mouse wheel zooming, panning, and coordinate overlays."""

    bubbleClicked = Signal(int, str)  # (question_number, option)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem = None

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        self._zoom_factor = 1.15
        self._current_zoom = 1.0

    def set_cv_image(self, img_bgr: np.ndarray) -> None:
        """Converts an OpenCV BGR image and displays it in the scene."""
        if img_bgr is None or img_bgr.size == 0:
            return

        h, w, c = img_bgr.shape
        bytes_per_line = c * w
        # Convert BGR to RGB for Qt
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._current_zoom = 1.0

    def add_bubble_overlay(
        self,
        center_x: float,
        center_y: float,
        radius: float,
        color_hex: str,
        label: str = ""
    ) -> None:
        """Draws an overlay circle over a detected bubble."""
        color = QColor(color_hex)
        pen = QPen(color, 2)
        brush = QBrush(QColor(color.red(), color.green(), color.blue(), 60))

        item = self._scene.addEllipse(
            center_x - radius, center_y - radius,
            radius * 2, radius * 2,
            pen, brush
        )
        if label:
            item.setToolTip(label)

    def highlight_box(self, x: int, y: int, w: int, h: int, color_hex: str = "#FFCC00") -> None:
        """Draws a rectangular highlight box around an identification field."""
        color = QColor(color_hex)
        pen = QPen(color, 2, Qt.DashLine)
        brush = QBrush(QColor(color.red(), color.green(), color.blue(), 40))
        self._scene.addRect(x, y, w, h, pen, brush)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handles mouse wheel zooming."""
        if event.angleDelta().y() > 0:
            factor = self._zoom_factor
            self._current_zoom *= factor
        else:
            factor = 1.0 / self._zoom_factor
            self._current_zoom *= factor

        # Clamp zoom limits
        if 0.1 <= self._current_zoom <= 15.0:
            self.scale(factor, factor)
        else:
            self._current_zoom /= factor

    def reset_view(self) -> None:
        """Resets the zoom to fit the image on screen."""
        if self._pixmap_item:
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self._current_zoom = 1.0

