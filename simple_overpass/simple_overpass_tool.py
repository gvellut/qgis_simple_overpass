from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgsMapMouseEvent, QgsMapTool
from qgis.PyQt.QtCore import Qt


class SimpleOverpassMapTool(QgsMapTool):
    def __init__(self, iface, action, results_dock) -> None:
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.results_dock = results_dock
        self.setAction(action)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def activate(self):
        super().activate()

    def deactivate(self):
        super().deactivate()

    def canvasReleaseEvent(self, event: QgsMapMouseEvent | None):
        if event is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        try:
            point_wgs = self._event_point_to_wgs84(event)
            bbox_wgs = self._current_extent_to_wgs84_bbox()
        except Exception as exc:
            self.iface.messageBar().pushMessage(
                "Simple Overpass",
                str(exc),
                level=Qgis.Warning,
                duration=5,
            )
            return

        self.results_dock.ensure_visible()
        self.results_dock.show_clicked_point(point_wgs)
        self.results_dock.start_query(
            point_wgs.x(),
            point_wgs.y(),
            bbox_wgs,
        )

    def _event_point_to_wgs84(self, event: QgsMapMouseEvent) -> QgsPointXY:
        src_crs = self.canvas.mapSettings().destinationCrs()
        dst_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        point = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos())
        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
        return transform.transform(QgsPointXY(point.x(), point.y()))

    def _current_extent_to_wgs84_bbox(self) -> tuple[float, float, float, float]:
        src_crs = self.canvas.mapSettings().destinationCrs()
        dst_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        extent = self.canvas.extent()
        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
        bbox = transform.transformBoundingBox(extent)
        return (bbox.yMinimum(), bbox.xMinimum(), bbox.yMaximum(), bbox.xMaximum())
