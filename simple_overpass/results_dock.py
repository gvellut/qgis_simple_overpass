from __future__ import annotations

from collections import deque
from functools import partial

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsDockWidget, QgsRubberBand
from qgis.PyQt.QtCore import QSettings, Qt, QTimer, QUrl, QVariant, pyqtSignal
from qgis.PyQt.QtGui import QColor, QDesktopServices, QKeySequence
from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .osm_elements import OsmFeature
from .settings import SimpleOverpassSettings
from .worker import OverpassWorker

FEATURE_ITEM_TYPE = 1001
TAG_ITEM_TYPE = 1002
CHUNK_SIZE = 40
LOG_TAG = "Simple Overpass"

if hasattr(QgsWkbTypes, "PointGeometry"):
    POINT_GEOM = QgsWkbTypes.PointGeometry
    LINE_GEOM = QgsWkbTypes.LineGeometry
    POLYGON_GEOM = QgsWkbTypes.PolygonGeometry
else:
    POINT_GEOM = QgsWkbTypes.GeometryType.PointGeometry
    LINE_GEOM = QgsWkbTypes.GeometryType.LineGeometry
    POLYGON_GEOM = QgsWkbTypes.GeometryType.PolygonGeometry


class ResultsTreeWidget(QTreeWidget):
    copyShortcutRequested = pyqtSignal()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copyShortcutRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MapResultRenderer:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self._wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        self._transform = QgsCoordinateTransform(
            self._wgs84,
            self.canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )

        self._point_band = QgsRubberBand(self.canvas, POINT_GEOM)
        self._point_band.setColor(QColor("magenta"))
        self._point_band.setIconSize(12)
        self._point_band.setWidth(3)

        self._feature_band = QgsRubberBand(self.canvas, POINT_GEOM)
        self._feature_band.setColor(QColor("green"))
        self._feature_band.setFillColor(QColor(0, 255, 0, 60))
        self._feature_band.setWidth(3)

    def cleanup(self) -> None:
        self.clear_clicked_point()
        self.clear_feature()

    def clear_clicked_point(self) -> None:
        self._point_band.reset(POINT_GEOM)

    def clear_feature(self) -> None:
        self._feature_band.reset(POINT_GEOM)

    def show_clicked_point(self, point_wgs) -> None:
        self.clear_clicked_point()
        point = self._transform_point(point_wgs)
        if point is None:
            return
        self._point_band.addPoint(point)

    def show_feature(self, geometry_wgs: QgsGeometry) -> None:
        self.clear_feature()
        geom = QgsGeometry(geometry_wgs)
        geom = self._transform_geometry(geom)
        if geom is None:
            return

        if geom.type() == POINT_GEOM:
            self._feature_band.setFillColor(QColor("green"))
        else:
            self._feature_band.setFillColor(QColor(0, 255, 0, 60))
        self._feature_band.setToGeometry(geom, None)

    def zoom_to_bbox(self, bbox_wgs: QgsRectangle) -> None:
        bbox = self._transform_bbox(bbox_wgs)
        if bbox is None:
            return
        self.canvas.setExtent(bbox)
        self.canvas.refresh()

    def _need_transform(self) -> bool:
        return self.canvas.mapSettings().destinationCrs().authid() != "EPSG:4326"

    def _sync_transform(self) -> None:
        self._transform.setDestinationCrs(self.canvas.mapSettings().destinationCrs())

    def _transform_point(self, point):
        if not self._need_transform():
            return point
        self._sync_transform()
        try:
            return self._transform.transform(point)
        except Exception:
            return None

    def _transform_bbox(self, bbox):
        if not self._need_transform():
            return bbox
        self._sync_transform()
        try:
            return self._transform.transformBoundingBox(bbox)
        except Exception:
            return None

    def _transform_geometry(self, geometry: QgsGeometry) -> QgsGeometry | None:
        if not self._need_transform():
            return geometry
        self._sync_transform()
        try:
            geometry.transform(self._transform)
            return geometry
        except Exception:
            return None


class SimpleOverpassResultsDock(QgsDockWidget):
    def __init__(self, iface, title: str) -> None:
        main_window = iface.mainWindow()
        assert isinstance(main_window, QMainWindow)
        super().__init__(title, parent=main_window)

        self.iface = iface
        self.setObjectName("SimpleOverpassResultsDock")
        self.setWindowTitle(title)
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self.renderer = MapResultRenderer(iface)
        self._qgis_locale = self._detect_qgis_locale()
        self._workers: dict[int, OverpassWorker] = {}
        self._current_request_id = 0
        self._worker_done = False
        self._section_items: dict[str, QTreeWidgetItem] = {}
        self._loading_items: dict[str, QTreeWidgetItem] = {}
        self._section_queues: dict[str, deque[dict]] = {
            "nearby": deque(),
            "enclosing": deque(),
        }
        self._section_processing = {"nearby": False, "enclosing": False}
        self._feature_count = 0
        self._section_counts = {"nearby": 0, "enclosing": 0}
        self._error_message: str | None = None

        self._build_ui()

        if not main_window.restoreDockWidget(self):
            main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)

        self.visibilityChanged.connect(self._on_visibility_changed)
        self.status_label.setText(self.tr("Click the map to query OSM data."))

    def cleanup(self) -> None:
        for worker in list(self._workers.values()):
            try:
                worker.section_result.disconnect(self._on_section_result)
            except Exception:
                pass
            try:
                worker.error.disconnect(self._on_worker_error)
            except Exception:
                pass
            try:
                worker.done.disconnect(self._on_worker_done)
            except Exception:
                pass
        self._workers.clear()
        self.renderer.cleanup()

        main_window = self.iface.mainWindow()
        if isinstance(main_window, QMainWindow):
            main_window.removeDockWidget(self)

    def show_clicked_point(self, point_wgs) -> None:
        self.renderer.show_clicked_point(point_wgs)

    def clear_feature_highlight(self) -> None:
        self.renderer.clear_feature()

    def start_query(
        self,
        lon: float,
        lat: float,
        bbox_wgs: tuple[float, float, float, float],
    ) -> None:
        self._current_request_id += 1
        request_id = self._current_request_id
        self._worker_done = False
        self._error_message = None
        self._feature_count = 0
        self._section_counts = {"nearby": 0, "enclosing": 0}
        self._section_queues = {"nearby": deque(), "enclosing": deque()}
        self._section_processing = {"nearby": False, "enclosing": False}
        self._section_items = {}
        self._loading_items = {}

        self.renderer.clear_feature()
        self._reset_tree_for_loading()
        self._update_status_label()

        worker = OverpassWorker(request_id, lon, lat, bbox_wgs, None)
        worker.section_result.connect(self._on_section_result)
        worker.error.connect(self._on_worker_error)
        worker.done.connect(self._on_worker_done)
        worker.finished.connect(worker.deleteLater)
        self._workers[request_id] = worker
        worker.start()

    def ensure_visible(self) -> None:
        if hasattr(self, "setUserVisible"):
            try:
                self.setUserVisible(True)
                return
            except Exception:
                pass
        self.show()
        self.raise_()

    def _build_ui(self) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.tree = ResultsTreeWidget(container)
        self.tree.setUniformRowHeights(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([self.tr("Feature/Key"), self.tr("Value")])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.customContextMenuRequested.connect(self._open_context_menu)
        self.tree.copyShortcutRequested.connect(self._copy_from_selection)

        self.status_label = QLabel(container)
        self.status_label.setWordWrap(True)

        layout.addWidget(self.tree, 1)
        layout.addWidget(self.status_label)

        self.setWidget(container)

    def _detect_qgis_locale(self) -> str:
        settings = QSettings()
        if not settings.value("locale/overrideFlag", False, type=bool):
            locale = settings.value("locale/globalLocale", "", type=str) or ""
        else:
            locale = settings.value("locale/userLocale", "", type=str) or ""
        if not locale:
            locale = settings.value("locale/userLocale", "", type=str) or ""
        return locale[:2]

    def _reset_tree_for_loading(self) -> None:
        self.tree.clear()

        settings = SimpleOverpassSettings()
        if settings.fetch_nearby:
            self._add_section("nearby", self.tr("Nearby features"))
        if settings.fetch_enclosing:
            self._add_section("enclosing", self.tr("Is inside"))

        if not self._section_items:
            self.tree.addTopLevelItem(QTreeWidgetItem([self.tr("Loading...")]))

    def _add_section(self, section: str, label: str) -> None:
        item = QTreeWidgetItem([label, ""])
        self.tree.addTopLevelItem(item)
        self.tree.expandItem(item)
        loading = QTreeWidgetItem([self.tr("Loading..."), ""])
        item.addChild(loading)
        self._section_items[section] = item
        self._loading_items[section] = loading

    def _on_section_result(self, request_id: int, section: str, elements: list) -> None:
        if request_id != self._current_request_id:
            return
        if section not in self._section_items:
            return

        self._remove_loading_item(section)
        prepared = [e for e in elements if isinstance(e, dict)]
        if section == "enclosing":
            prepared.sort(key=_raw_bounds_area)

        self._section_queues[section].extend(prepared)
        self._schedule_section_processing(request_id, section)
        self._update_status_label()

    def _remove_loading_item(self, section: str) -> None:
        loading = self._loading_items.pop(section, None)
        parent = self._section_items.get(section)
        if loading is None or parent is None:
            return
        index = parent.indexOfChild(loading)
        if index >= 0:
            parent.takeChild(index)

    def _schedule_section_processing(self, request_id: int, section: str) -> None:
        if self._section_processing.get(section):
            return
        self._section_processing[section] = True
        QTimer.singleShot(
            0,
            partial(self._process_section_chunk, request_id, section),
        )

    def _process_section_chunk(self, request_id: int, section: str) -> None:
        if request_id != self._current_request_id:
            self._section_processing[section] = False
            return

        queue = self._section_queues[section]
        parent = self._section_items.get(section)
        if parent is None:
            self._section_processing[section] = False
            return

        processed = 0
        while queue and processed < CHUNK_SIZE:
            raw = queue.popleft()
            feature = OsmFeature.from_json(raw, self._qgis_locale)
            if feature is None:
                continue
            self._append_feature_item(parent, feature)
            self._feature_count += 1
            self._section_counts[section] += 1
            processed += 1

        if queue:
            QTimer.singleShot(
                0,
                partial(self._process_section_chunk, request_id, section),
            )
            self._update_status_label()
            return

        self._section_processing[section] = False
        self._update_status_label()
        self._finalize_if_idle()

    def _append_feature_item(
        self,
        parent: QTreeWidgetItem,
        feature: OsmFeature,
    ) -> None:
        item = QTreeWidgetItem(parent, [feature.title, ""], FEATURE_ITEM_TYPE)
        item.setData(0, Qt.ItemDataRole.UserRole, feature)

        for key, value in sorted(feature.tags.items(), key=lambda x: str(x[0])):
            tag_item = QTreeWidgetItem(
                item,
                [str(key), "" if value is None else str(value)],
                TAG_ITEM_TYPE,
            )
            tag_item.setData(
                1,
                Qt.ItemDataRole.UserRole,
                "" if value is None else str(value),
            )

    def _on_worker_error(self, request_id: int, message: str) -> None:
        self._workers.pop(request_id, None)
        if request_id != self._current_request_id:
            return

        self._error_message = message
        self._update_status_label()

        bar = self.iface.messageBar()
        if bar is not None:
            bar.pushMessage(LOG_TAG, message, level=Qgis.Warning, duration=5)

        if self._feature_count == 0:
            self.tree.clear()
            self.tree.addTopLevelItem(QTreeWidgetItem([message, ""]))
        else:
            self.tree.addTopLevelItem(QTreeWidgetItem([f"Error: {message}", ""]))

    def _on_worker_done(self, request_id: int) -> None:
        self._workers.pop(request_id, None)
        if request_id != self._current_request_id:
            return
        self._worker_done = True
        self._update_status_label()
        self._finalize_if_idle()

    def _finalize_if_idle(self) -> None:
        if not self._worker_done:
            return
        if any(self._section_processing.values()):
            return
        if any(self._section_queues[section] for section in self._section_queues):
            return

        if self._feature_count == 0 and not self._error_message:
            self.tree.clear()
            self.tree.addTopLevelItem(
                QTreeWidgetItem([self.tr("No features found"), ""])
            )
        self._update_status_label()

    def _update_status_label(self) -> None:
        if self._error_message:
            if self._feature_count > 0:
                self.status_label.setText(
                    self.tr("Partial results. Last error: {msg}").format(
                        msg=self._error_message
                    )
                )
            else:
                self.status_label.setText(self._error_message)
            return

        nearby_count = self._section_counts["nearby"]
        enclosing_count = self._section_counts["enclosing"]
        loading = not self._worker_done or any(self._section_processing.values())
        if loading:
            self.status_label.setText(
                self.tr("Loading… Nearby: {n}, Is inside: {e}").format(
                    n=nearby_count,
                    e=enclosing_count,
                )
            )
            return

        if self._feature_count == 0:
            self.status_label.setText(self.tr("No features found."))
            return

        self.status_label.setText(
            self.tr("Nearby: {n}, Is inside: {e}").format(
                n=nearby_count,
                e=enclosing_count,
            )
        )

    def _on_selection_changed(self) -> None:
        feature = self._selected_feature()
        self.renderer.clear_feature()
        if feature is None:
            return
        geometry = feature.geometry()
        if geometry is None:
            return
        self.renderer.show_feature(geometry)

    def _on_visibility_changed(self, visible: bool) -> None:
        if not visible:
            self.renderer.clear_feature()
            self.renderer.clear_clicked_point()

    def _selected_feature(self) -> OsmFeature | None:
        item = self._selected_item()
        if item is None:
            return None
        if item.type() == TAG_ITEM_TYPE:
            item = item.parent()
        if item is None or item.type() != FEATURE_ITEM_TYPE:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return data if isinstance(data, OsmFeature) else None

    def _selected_item(self) -> QTreeWidgetItem | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0]

    def _open_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        if item.type() not in {FEATURE_ITEM_TYPE, TAG_ITEM_TYPE}:
            return

        self.tree.setCurrentItem(item)

        menu = QMenu(self)
        if item.type() == TAG_ITEM_TYPE:
            copy_value_action = QAction(self.tr("Copy Value"), self)
            copy_value_action.triggered.connect(self._copy_tag_value)
            menu.addAction(copy_value_action)
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return

        self._populate_feature_menu(menu)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _populate_feature_menu(self, menu: QMenu) -> None:
        feature = self._selected_feature()
        item = self._selected_item()
        if feature is None or item is None:
            return

        geometry = feature.geometry()
        has_geometry = geometry is not None

        zoom_action = QAction(self.tr("Zoom to feature"), self)
        zoom_action.setEnabled(has_geometry)
        zoom_action.triggered.connect(self._zoom_to_feature)
        menu.addAction(zoom_action)

        copy_feature_action = QAction(self.tr("Copy feature to clipboard"), self)
        copy_feature_action.setEnabled(has_geometry)
        copy_feature_action.triggered.connect(self._copy_feature_geometry_to_clipboard)
        menu.addAction(copy_feature_action)

        save_new_action = QAction(self.tr("Save feature in new temporary layer"), self)
        save_new_action.setEnabled(has_geometry)
        save_new_action.triggered.connect(lambda: self._save_feature_to_layer(True))
        menu.addAction(save_new_action)

        save_selected_action = QAction(self.tr("Save feature in selected layer"), self)
        save_selected_action.setEnabled(
            has_geometry and self._can_save_to_selected_layer()
        )
        save_selected_action.triggered.connect(
            lambda: self._save_feature_to_layer(False)
        )
        menu.addAction(save_selected_action)

        menu.addSeparator()

        open_osm_action = QAction(self.tr("Open in OpenStreetMap"), self)
        open_osm_action.triggered.connect(self._open_in_osm)
        menu.addAction(open_osm_action)

        copy_osm_url_action = QAction(self.tr("Copy OpenStreetMap URL"), self)
        copy_osm_url_action.triggered.connect(self._copy_osm_url)
        menu.addAction(copy_osm_url_action)

        label = self.tr("Copy Name") if feature.has_name_title else self.tr("Copy ID")
        copy_label_action = QAction(label, self)
        copy_label_action.triggered.connect(self._copy_root_label)
        menu.addAction(copy_label_action)

    def _copy_from_selection(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if item.type() == TAG_ITEM_TYPE:
            self._copy_tag_value()
            return
        if item.type() == FEATURE_ITEM_TYPE:
            self._copy_root_label()

    def _copy_text(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _copy_root_label(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if item.type() != FEATURE_ITEM_TYPE:
            return
        self._copy_text(item.text(0))

    def _copy_tag_value(self) -> None:
        item = self._selected_item()
        if item is None or item.type() != TAG_ITEM_TYPE:
            return
        value = item.data(1, Qt.ItemDataRole.UserRole)
        self._copy_text(str(value or ""))

    def _zoom_to_feature(self) -> None:
        feature = self._selected_feature()
        if feature is None:
            return
        geometry = feature.geometry()
        if geometry is None:
            return
        self.renderer.zoom_to_bbox(geometry.boundingBox())

    def _open_in_osm(self) -> None:
        feature = self._selected_feature()
        if feature is None:
            return
        QDesktopServices.openUrl(QUrl(feature.osm_url()))

    def _copy_osm_url(self) -> None:
        feature = self._selected_feature()
        if feature is None:
            return
        self._copy_text(feature.osm_url())

    def _copy_feature_geometry_to_clipboard(self) -> None:
        feature = self._selected_feature()
        if feature is None:
            return

        layer = self._create_memory_layer_with_feature(feature)
        if layer is None:
            return
        layer.selectAll()
        self.iface.copySelectionToClipboard(layer)

    def _save_feature_to_layer(self, create_new: bool) -> None:
        feature = self._selected_feature()
        if feature is None:
            return

        if create_new:
            layer = self._create_memory_layer_with_feature(feature)
            if layer is None:
                return
            QgsProject.instance().addMapLayer(layer)
            return

        target = self._selected_vector_layer()
        if target is None:
            return
        self._append_feature_to_existing_layer(feature, target)

    def _create_memory_layer_with_feature(
        self,
        feature: OsmFeature,
    ) -> QgsVectorLayer | None:
        geometry = feature.geometry()
        if geometry is None:
            return None

        geom_type = _memory_geom_type_name(geometry)
        if geom_type is None:
            return None

        layer = QgsVectorLayer(
            f"{geom_type}?crs=EPSG:4326",
            feature.title,
            "memory",
        )
        if not layer.isValid():
            return None

        provider = layer.dataProvider()
        if provider is None:
            return None

        provider.addAttributes(
            [QgsField(str(k), QVariant.String) for k in feature.tags]
        )
        layer.updateFields()

        qgs_feature = QgsFeature(layer.fields())
        qgs_feature.setGeometry(geometry)
        field_names = layer.fields().names()
        qgs_feature.setAttributes(
            [_string_attr(feature.tags.get(name)) for name in field_names]
        )
        provider.addFeatures([qgs_feature])
        layer.updateExtents()
        return layer

    def _append_feature_to_existing_layer(
        self,
        feature: OsmFeature,
        layer: QgsVectorLayer,
    ) -> None:
        geometry = feature.geometry()
        if geometry is None:
            return

        if layer.geometryType() != geometry.type():
            self.iface.messageBar().pushMessage(
                LOG_TAG,
                self.tr("Selected layer geometry type is not compatible."),
                level=Qgis.Warning,
                duration=5,
            )
            return

        provider = layer.dataProvider()
        if provider is None:
            return

        missing = [name for name in feature.tags if name not in layer.fields().names()]
        if missing:
            provider.addAttributes(
                [QgsField(str(name), QVariant.String) for name in missing]
            )
            layer.updateFields()

        out_geometry = QgsGeometry(geometry)
        if layer.crs().authid() != "EPSG:4326":
            transform = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem.fromEpsgId(4326),
                layer.crs(),
                QgsProject.instance(),
            )
            try:
                out_geometry.transform(transform)
            except Exception as exc:
                self.iface.messageBar().pushMessage(
                    LOG_TAG,
                    str(exc),
                    level=Qgis.Warning,
                    duration=5,
                )
                return

        qgs_feature = QgsFeature(layer.fields())
        qgs_feature.setGeometry(out_geometry)
        qgs_feature.setAttributes(
            [_string_attr(feature.tags.get(name)) for name in layer.fields().names()]
        )

        was_editing = layer.isEditable()
        if not was_editing and not layer.startEditing():
            self.iface.messageBar().pushMessage(
                LOG_TAG,
                self.tr("Could not start editing selected layer."),
                level=Qgis.Warning,
                duration=5,
            )
            return

        ok = layer.addFeature(qgs_feature)
        if ok:
            layer.updateExtents()
            layer.triggerRepaint()

        if not was_editing:
            if ok:
                ok = layer.commitChanges()
            else:
                layer.rollBack()

        if not ok:
            self.iface.messageBar().pushMessage(
                LOG_TAG,
                self.tr("Could not save feature to selected layer."),
                level=Qgis.Warning,
                duration=5,
            )

    def _can_save_to_selected_layer(self) -> bool:
        feature = self._selected_feature()
        layer = self._selected_vector_layer()
        if feature is None or layer is None:
            return False
        geometry = feature.geometry()
        if geometry is None:
            return False
        return layer.geometryType() == geometry.type()

    def _selected_vector_layer(self) -> QgsVectorLayer | None:
        layers = self.iface.layerTreeView().selectedLayers()
        if len(layers) != 1:
            return None
        layer = layers[0]
        if not isinstance(layer, QgsVectorLayer):
            return None
        return layer


def _memory_geom_type_name(geometry: QgsGeometry) -> str | None:
    geom_type = geometry.type()
    if geom_type == POINT_GEOM:
        base = "Point"
    elif geom_type == LINE_GEOM:
        base = "LineString"
    elif geom_type == POLYGON_GEOM:
        base = "Polygon"
    else:
        return None
    if geometry.isMultipart():
        return f"Multi{base}"
    return base


def _string_attr(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _raw_bounds_area(raw: dict) -> float:
    bounds = raw.get("bounds")
    if not isinstance(bounds, dict):
        return float("inf")
    try:
        width = float(bounds["maxlon"]) - float(bounds["minlon"])
        height = float(bounds["maxlat"]) - float(bounds["minlat"])
    except Exception:
        return float("inf")
    return max(0.0, width) * max(0.0, height)
