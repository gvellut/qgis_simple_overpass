from __future__ import annotations

import os
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .results_dock import SimpleOverpassResultsDock
from .settings import SimpleOverpassOptionsWidgetFactory
from .simple_overpass_tool import SimpleOverpassMapTool


class SimpleOverpassPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        self.tool_action: QAction | None = None
        self.settings_action: QAction | None = None
        self.map_tool: SimpleOverpassMapTool | None = None
        self.results_dock: SimpleOverpassResultsDock | None = None
        self.options_factory: SimpleOverpassOptionsWidgetFactory | None = None
        self._previous_tool = None
        self._added_plugin_toolbar_icon = False

    def tr(self, message: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, message)

    def initGui(self):
        icon_path = str(Path(self.plugin_dir) / "icons" / "simple_overpass.svg")
        icon = QIcon(icon_path)

        self.tool_action = QAction(
            icon,
            self.tr("Query OSM info from Overpass"),
            self.iface.mainWindow(),
        )
        self.tool_action.setCheckable(True)
        self.tool_action.setStatusTip(self.tr("Click map to query nearby OSM objects"))
        self.tool_action.triggered.connect(self._on_toggled)

        self.settings_action = QAction(
            icon,
            self.tr("Settings"),
            self.iface.mainWindow(),
        )
        self.settings_action.triggered.connect(self._open_settings)

        self.results_dock = SimpleOverpassResultsDock(
            self.iface,
            self.tr("Simple Overpass"),
        )
        self.map_tool = SimpleOverpassMapTool(
            self.iface,
            self.tool_action,
            self.results_dock,
        )
        self.iface.mapToolActionGroup().addAction(self.tool_action)

        menu_name = self.tr("Simple Overpass")
        self.iface.addPluginToWebMenu(menu_name, self.tool_action)
        self.iface.addPluginToWebMenu(menu_name, self.settings_action)
        self._set_web_menu_icon(icon)

        self.iface.addWebToolBarIcon(self.tool_action)

        # User requested a plugin toolbar icon in addition to the Web menu entry.
        self.iface.addToolBarIcon(self.tool_action)
        self._added_plugin_toolbar_icon = True

        self.options_factory = SimpleOverpassOptionsWidgetFactory(icon_path)
        self.iface.registerOptionsWidgetFactory(self.options_factory)

    def unload(self):
        canvas = self.iface.mapCanvas()
        if (
            self.map_tool
            and canvas.mapTool() == self.map_tool
            and self._previous_tool is not None
        ):
            canvas.setMapTool(self._previous_tool)

        if self.options_factory is not None:
            self.iface.unregisterOptionsWidgetFactory(self.options_factory)
            self.options_factory.deleteLater()
            self.options_factory = None

        menu_name = self.tr("Simple Overpass")
        if self.tool_action is not None:
            try:
                self.tool_action.triggered.disconnect(self._on_toggled)
            except TypeError:
                pass
            self.iface.removePluginWebMenu(menu_name, self.tool_action)
            self.iface.removeWebToolBarIcon(self.tool_action)
            if self._added_plugin_toolbar_icon:
                self.iface.removeToolBarIcon(self.tool_action)
            self.tool_action.deleteLater()
            self.tool_action = None

        if self.settings_action is not None:
            try:
                self.settings_action.triggered.disconnect(self._open_settings)
            except TypeError:
                pass
            self.iface.removePluginWebMenu(menu_name, self.settings_action)
            self.settings_action.deleteLater()
            self.settings_action = None

        if self.results_dock is not None:
            self.results_dock.cleanup()
            self.results_dock.deleteLater()
            self.results_dock = None

        if self.map_tool is not None:
            self.map_tool.deleteLater()
            self.map_tool = None

        self._previous_tool = None
        self._added_plugin_toolbar_icon = False

    def _on_toggled(self, checked: bool):
        if self.map_tool is None:
            return

        canvas = self.iface.mapCanvas()
        if checked:
            self._previous_tool = canvas.mapTool()
            canvas.setMapTool(self.map_tool)
            return

        if canvas.mapTool() == self.map_tool and self._previous_tool is not None:
            canvas.setMapTool(self._previous_tool)

    def _open_settings(self):
        self.iface.showOptionsDialog(
            self.iface.mainWindow(),
            self.tr("Simple Overpass"),
        )

    def _set_web_menu_icon(self, icon: QIcon) -> None:
        web_menu = self.iface.webMenu()
        if web_menu is None:
            return

        menu_name = self.tr("Simple Overpass")
        for action in web_menu.actions():
            if action.text() == menu_name:
                action.setIcon(icon)
                break
