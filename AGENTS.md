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
- `simple_overpass/settings.py`: QGIS options page, provider selection, persisted settings, and immutable per-click query snapshots.
- `simple_overpass/worker.py`: asynchronous `QueryController`, concurrent section requests, cancellation, and isolated Direct OSM cookie acquisition/refresh through `QgsNetworkAccessManager`.
- `simple_overpass/query_builder.py`: pure Overpass QL builders.
- `simple_overpass/osm_elements.py`: Overpass JSON to title, URL, and `QgsGeometry` conversion helpers.
- `tests/test_query_builder.py`: unit tests for pure query-building behavior.
- `tests/qgis_test_support.py`: isolated QGIS/Qt test application and controllable network replies.
- `tests/test_worker.py`: concurrent requests, cancellation, cookie lifecycle, and response handling tests.
- `tests/test_settings_and_dock.py`: provider settings, session resets, partial results, and dock rendering lifecycle tests.

## Request lifecycle considerations

- Overpass remains the default provider. Preserve custom Overpass URLs and the saved historical date when switching providers; Direct OSM queries omit dates.
- Network requests are asynchronous Qt replies on the controller's thread. Abort replies on new clicks, connection changes, and unload; invalidate generations before aborting because `finished` can be emitted synchronously.
- Keep OSM tokens in plugin memory only. Use manual cookie controls on individual requests; never replace or clear QGIS's shared cookie jar, persist tokens, or log their values.
- Share cookie acquisition and 403 refresh between sections. Retry each forbidden section once, and do not invalidate a newer token because an older request returned 403.
- Results, warnings, errors, and completion are section-scoped. Preserve features returned with a `remark`; completion also waits for pending dock rendering. Stale render callbacks must return without mutating the current request's state.
- Run `uv run pytest` for standalone tests and `python -m unittest discover -s tests -v` in a configured QGIS 4 Python environment for the full suite. QGIS tests isolate settings and mock network replies.

## QGIS 4 porting considerations

- This branch targets QGIS 4 only. Keep `qgisMinimumVersion=4.0` and do not add QGIS 3 compatibility fallbacks.
- Use `qgis.PyQt` imports, but follow Qt 6 module locations, for example `QAction` from `qgis.PyQt.QtGui`.
- Use scoped Qt and QGIS enums such as `Qt.MouseButton.LeftButton`, `Qgis.MessageLevel.Warning`, and `Qgis.GeometryType.Point`.
- Use Qt 6 mouse event position APIs. Convert `event.position()` with `toPoint()` before passing pixel coordinates to QGIS canvas transforms.
- Use `QMetaType.Type` values for new `QgsField` instances, for example `QMetaType.Type.QString`.
