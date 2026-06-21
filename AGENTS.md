This is a QGIS plugin in python : It allows the user to point at a location in the map and get information on features around it.


## Development

```bash
# Install dependencies
uv sync

# Run linting and formatting. Always use --fix.
ruff check --fix
ruff format
```

## Update of AGENTS.md

After completing a feature, update this file AGENTS.md with the updated project structure. Also add considerations for reference for future work.

## Project structure

- `simple_overpass/__init__.py`: QGIS plugin entry point and factory.
- `simple_overpass/simple_overpass.py`: plugin lifecycle, actions, menu, toolbar, map tool, dock, and settings registration.
- `simple_overpass/simple_overpass_tool.py`: map click tool and map-to-WGS84 coordinate conversion.
- `simple_overpass/results_dock.py`: results dock UI, map highlighting, context menu actions, and saving queried features to layers.
- `simple_overpass/settings.py`: QGIS options page and persisted plugin settings.
- `simple_overpass/worker.py`: background Overpass requests through `QgsNetworkAccessManager`.
- `simple_overpass/query_builder.py`: pure Overpass QL builders.
- `simple_overpass/osm_elements.py`: Overpass JSON to title, URL, and `QgsGeometry` conversion helpers.
- `tests/test_query_builder.py`: unit tests for pure query-building behavior.

## QGIS 4 porting considerations

- This branch targets QGIS 4 only. Keep `qgisMinimumVersion=4.0` and do not add QGIS 3 compatibility fallbacks.
- Use `qgis.PyQt` imports, but follow Qt 6 module locations, for example `QAction` from `qgis.PyQt.QtGui`.
- Use scoped Qt and QGIS enums such as `Qt.MouseButton.LeftButton`, `Qgis.MessageLevel.Warning`, and `Qgis.GeometryType.Point`.
- Use Qt 6 mouse event position APIs. Convert `event.position()` with `toPoint()` before passing pixel coordinates to QGIS canvas transforms.
- Use `QMetaType.Type` values for new `QgsField` instances, for example `QMetaType.Type.QString`.
