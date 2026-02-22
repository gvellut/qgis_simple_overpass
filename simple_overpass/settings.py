from __future__ import annotations

from pathlib import Path

from qgis.core import QgsSettings
from qgis.gui import QgsOptionsPageWidget, QgsOptionsWidgetFactory
from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
SETTINGS_ROOT = "SimpleOverpass"


class SimpleOverpassSettings:
    def __init__(self) -> None:
        self._settings = QgsSettings()

    def _key(self, name: str) -> str:
        return f"{SETTINGS_ROOT}/{name}"

    @property
    def endpoint(self) -> str:
        value = self._settings.value(
            self._key("endpoint"),
            defaultValue=DEFAULT_ENDPOINT,
            type=str,
        )
        value = (value or "").strip()
        return value or DEFAULT_ENDPOINT

    @endpoint.setter
    def endpoint(self, value: str) -> None:
        value = (value or "").strip() or DEFAULT_ENDPOINT
        self._settings.setValue(self._key("endpoint"), value)

    @property
    def distance(self) -> int:
        return max(
            1,
            self._settings.value(self._key("distance"), defaultValue=15, type=int),
        )

    @distance.setter
    def distance(self, value: int) -> None:
        self._settings.setValue(self._key("distance"), max(1, int(value)))

    @property
    def timeout(self) -> int:
        return max(
            1,
            self._settings.value(self._key("timeout"), defaultValue=30, type=int),
        )

    @timeout.setter
    def timeout(self, value: int) -> None:
        self._settings.setValue(self._key("timeout"), max(1, int(value)))

    @property
    def fetch_nearby(self) -> bool:
        return self._settings.value(
            self._key("fetch_nearby"),
            defaultValue=True,
            type=bool,
        )

    @fetch_nearby.setter
    def fetch_nearby(self, value: bool) -> None:
        self._settings.setValue(self._key("fetch_nearby"), bool(value))

    @property
    def fetch_enclosing(self) -> bool:
        return self._settings.value(
            self._key("fetch_enclosing"),
            defaultValue=True,
            type=bool,
        )

    @fetch_enclosing.setter
    def fetch_enclosing(self, value: bool) -> None:
        self._settings.setValue(self._key("fetch_enclosing"), bool(value))

    @property
    def debug_enabled(self) -> bool:
        return self._settings.value(
            self._key("debug_enabled"),
            defaultValue=False,
            type=bool,
        )

    @debug_enabled.setter
    def debug_enabled(self, value: bool) -> None:
        self._settings.setValue(self._key("debug_enabled"), bool(value))

    @property
    def only_with_tags(self) -> bool:
        return self._settings.value(
            self._key("only_with_tags"),
            defaultValue=True,
            type=bool,
        )

    @only_with_tags.setter
    def only_with_tags(self, value: bool) -> None:
        self._settings.setValue(self._key("only_with_tags"), bool(value))

    @property
    def date_filter(self) -> str:
        return (
            self._settings.value(
                self._key("date_filter"),
                defaultValue="",
                type=str,
            )
            or ""
        ).strip()

    @date_filter.setter
    def date_filter(self, value: str) -> None:
        self._settings.setValue(self._key("date_filter"), (value or "").strip())

    @property
    def global_tag_filter(self) -> str:
        return (
            self._settings.value(
                self._key("global_tag_filter"),
                defaultValue="",
                type=str,
            )
            or ""
        ).strip()

    @global_tag_filter.setter
    def global_tag_filter(self, value: str) -> None:
        self._settings.setValue(
            self._key("global_tag_filter"),
            (value or "").strip(),
        )

    @property
    def only_center(self) -> bool:
        return self._settings.value(
            self._key("only_center"),
            defaultValue=False,
            type=bool,
        )

    @only_center.setter
    def only_center(self, value: bool) -> None:
        self._settings.setValue(self._key("only_center"), bool(value))


class SimpleOverpassOptionsPageWidget(QgsOptionsPageWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._load_settings()

    def apply(self) -> None:
        settings = SimpleOverpassSettings()
        settings.endpoint = self.endpoint_edit.text()
        settings.distance = self.distance_spin.value()
        settings.timeout = self.timeout_spin.value()
        settings.fetch_nearby = self.nearby_checkbox.isChecked()
        settings.fetch_enclosing = self.enclosing_checkbox.isChecked()
        settings.debug_enabled = self.debug_checkbox.isChecked()
        settings.only_with_tags = self.only_tags_checkbox.isChecked()
        settings.global_tag_filter = self.tag_filter_edit.text()
        settings.only_center = self.only_center_checkbox.isChecked()

        if self.date_enabled_checkbox.isChecked():
            settings.date_filter = self.date_edit.date().toString("yyyy-MM-dd")
        else:
            settings.date_filter = ""

    def cancel(self) -> None:
        pass

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        container = QWidget(self)
        form = QFormLayout(container)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.endpoint_edit = QLineEdit(container)
        self.endpoint_edit.setPlaceholderText(DEFAULT_ENDPOINT)
        form.addRow(self.tr("Overpass API endpoint"), self.endpoint_edit)

        self.distance_spin = QSpinBox(container)
        self.distance_spin.setRange(1, 1_000_000)
        self.distance_spin.setSuffix(" m")
        form.addRow(self.tr("Distance"), self.distance_spin)

        self.timeout_spin = QSpinBox(container)
        self.timeout_spin.setRange(1, 3600)
        self.timeout_spin.setSuffix(" s")
        form.addRow(self.tr("Timeout"), self.timeout_spin)

        self.nearby_checkbox = QCheckBox(self.tr("Nearby"), container)
        form.addRow(self.nearby_checkbox)

        self.enclosing_checkbox = QCheckBox(self.tr("Enclosing"), container)
        form.addRow(self.enclosing_checkbox)

        self.debug_checkbox = QCheckBox(self.tr("Enable Debug"), container)
        form.addRow(self.debug_checkbox)

        self.only_tags_checkbox = QCheckBox(
            self.tr("Only include objects with tag"),
            container,
        )
        form.addRow(self.only_tags_checkbox)

        date_row = QWidget(container)
        date_layout = QHBoxLayout(date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(8)

        self.date_enabled_checkbox = QCheckBox(self.tr("Use date"), date_row)
        self.date_edit = QDateEdit(date_row)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setEnabled(False)
        self.date_enabled_checkbox.toggled.connect(self.date_edit.setEnabled)

        date_layout.addWidget(self.date_enabled_checkbox)
        date_layout.addWidget(self.date_edit, 1)
        form.addRow(self.tr("Date filter (UTC)"), date_row)

        self.tag_filter_edit = QLineEdit(container)
        self.tag_filter_edit.setPlaceholderText("name  or  building=house")
        form.addRow(self.tr("Tag filter"), self.tag_filter_edit)

        self.only_center_checkbox = QCheckBox(self.tr("Only center"), container)
        form.addRow(self.only_center_checkbox)

        hint = QLabel(
            self.tr(
                "Tag filter supports `key` (tag exists) or `key=value` (exact match)."
            ),
            container,
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        root.addWidget(container)
        root.addWidget(hint)
        root.addStretch(1)

    def _load_settings(self) -> None:
        settings = SimpleOverpassSettings()
        self.endpoint_edit.setText(settings.endpoint)
        self.distance_spin.setValue(settings.distance)
        self.timeout_spin.setValue(settings.timeout)
        self.nearby_checkbox.setChecked(settings.fetch_nearby)
        self.enclosing_checkbox.setChecked(settings.fetch_enclosing)
        self.debug_checkbox.setChecked(settings.debug_enabled)
        self.only_tags_checkbox.setChecked(settings.only_with_tags)
        self.tag_filter_edit.setText(settings.global_tag_filter)
        self.only_center_checkbox.setChecked(settings.only_center)

        if settings.date_filter:
            date = QDate.fromString(settings.date_filter, "yyyy-MM-dd")
            if date.isValid():
                self.date_enabled_checkbox.setChecked(True)
                self.date_edit.setEnabled(True)
                self.date_edit.setDate(date)
            else:
                self.date_enabled_checkbox.setChecked(False)
                self.date_edit.setEnabled(False)
        else:
            self.date_enabled_checkbox.setChecked(False)
            self.date_edit.setEnabled(False)


class SimpleOverpassOptionsErrorPageWidget(QgsOptionsPageWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(self.tr("Simple Overpass settings could not be loaded."), self)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)

    def apply(self) -> None:
        pass

    def cancel(self) -> None:
        pass


class SimpleOverpassOptionsWidgetFactory(QgsOptionsWidgetFactory):
    def __init__(self, icon_path: str | None = None) -> None:
        self._icon = QIcon(icon_path) if icon_path else QIcon()
        super().__init__("Simple Overpass", self._icon)

    def path(self) -> list[str]:
        return ["Simple Overpass"]

    def icon(self) -> QIcon:
        return self._icon

    def createWidget(
        self,
        parent: QWidget | None = None,
    ) -> QgsOptionsPageWidget | None:
        try:
            return SimpleOverpassOptionsPageWidget(parent)
        except Exception:
            return SimpleOverpassOptionsErrorPageWidget(parent)


def default_icon_path() -> str:
    return str(Path(__file__).parent / "icons" / "simple_overpass.svg")
