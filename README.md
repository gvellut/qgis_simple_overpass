
# Simple Overpass (QGIS plugin)

Simple Overpass is a small QGIS plugin that lets you click on the map and retrieve OpenStreetMap (OSM) objects around that location using a configurable Overpass API or OSM.org's dedicated “Query Features” endpoint.

It is very similar to the [QGIS OSM Info plugin](https://github.com/nextgis/qgis_osminfo) but with additional config + queries + optimised display of the info.

The results are shown in a dock panel, grouped into:

- **Nearby features**: nodes/ways/relations within a radius around the clicked point.
- **Is inside**: enclosing ways/relations for the clicked point.

## Features

- Click on the map to query OSM data via Overpass or Direct OSM.
- Nearby and enclosing queries run concurrently and display results independently.
- Clicking again cancels previous requests and pending result rendering.
- Partial responses retain their features and show the server's warning in the affected section.
- Results dock with a tree view of features and their tags.
- Selecting a feature highlights it on the map.
- Right-click actions on a feature:
	- Zoom to feature
	- Copy name/ID
	- Copy OpenStreetMap URL
	- Open in OpenStreetMap
	- Copy feature geometry to clipboard
	- Save feature to a new temporary (memory) layer
	- Save feature to the currently selected vector layer (when compatible)
- Right-click actions on a tag:
	- Copy value

## Requirements

- QGIS 4.x (see plugin metadata in the plugin folder)
- Network access to the selected endpoint (and `www.openstreetmap.org` for Direct OSM cookie fetching)

Default endpoint: `https://overpass-api.de/api/interpreter`

## Install (development)

1. Set the env var QGIS_PLUGINPATH to the directory eg `/Users/guilhem/Documents/projects/github/qgis_simple_overpass`
2. Restart QGIS.
3. Enable the plugin in **Plugins → Manage and Install Plugins…**.
4. (optional) For development, install the **Plugin Reloader** plugin 

*Note*: Multiple plugin paths can be passed, separated with `:`

OR if multiple plugins (and no issues with tests folders):

1. Create a directory
2. Add symbolic links to the root module of each plugin eg `simple_overpass -> /Users/guilhem/dev/projects/github/qgis_simple_overpass/simple_overpass`
3. Set the env var QGIS_PLUGINPATH to the directory with the links
4. Restart QGIS.
5. Enable the pluginss

## Usage

1. Activate the tool: **Web → Simple Overpass → Query OSM info**.
	 - The plugin also registers an icon in the Web toolbar and adds a toolbar icon.
2. Left-click the map.
3. The **Simple Overpass** dock opens (or becomes visible) and starts loading results.
4. Click a feature in the list to highlight it on the map.
5. Right-click a feature (or a tag) for actions like copy/open/zoom/save.

## Settings

Open settings via **Web → Simple Overpass → Settings** (or QGIS **Settings → Options** and find “Simple Overpass”).

- **Data source**: **Overpass API** (default) or **Direct OSM**. Existing installations keep their configured Overpass URL.
- **Overpass API endpoint**: URL of the Overpass interpreter endpoint; disabled in Direct OSM mode.
- **Distance**: radius in meters used for the “Nearby features” query.
- **Timeout**: Overpass timeout in seconds.
- **Nearby / Enclosing**: enable/disable each section.
- **Only include objects with tag**: filters objects without any tags.
- **Date filter (UTC)**: optional Overpass query date (sent as `[date:"YYYY-MM-DDT00:00:00Z"]`). Disabled and omitted from requests in Direct OSM mode, which supports current data only. The saved date is restored when switching back to Overpass.
- **Tag filter**: optional global tag filter applied to both queries.
	- `key` (tag exists), e.g. `highway`
	- `key=value` (exact match), e.g. `building=house`
- **Only center**: for the nearby query, request center points instead of full geometry.
- **Enable Debug**: logs the provider, generated queries, response times, HTTP statuses, and element counts to the QGIS log. Cookie values are never logged.

Direct OSM sends queries to `https://query.openstreetmap.org/query-features`. On first use, it anonymously obtains the website's query cookie from `https://www.openstreetmap.org/`. The cookie is kept only in plugin memory, reused until near expiry, and refreshed when needed. A forbidden query triggers one shared cookie refresh and one retry of each affected section. Other failures are shown without automatically switching providers.

Applying a change to the data source or Overpass endpoint cancels active requests and clears results, map highlights, and plugin-owned cookies. Canceling the settings dialog leaves the active session unchanged. QGIS's shared cookie store is not modified.

## Troubleshooting

- **“Network error” / request fails**: check your network and the configured endpoint.
- **Overpass returns an error remark**: available features are retained alongside a warning, and the dock marks the response as partial. Try increasing timeout, reducing distance, or switching endpoint.
- **Direct OSM cookie or HTTP 403 error**: the plugin could not obtain or refresh the website cookie, or the query remained forbidden after a retry. Check access to OSM.org or select Overpass API. Direct OSM depends on the website's cookie mechanism.
- **“Parsing data error”**: usually means the endpoint did not return valid Overpass JSON.
- **No sections appear**: enable “Nearby” and/or “Enclosing” in settings.
- **Save to selected layer disabled**: select a target vector layer in the Layers panel; it must be compatible with the feature geometry type.

## Development

Run `uv run pytest` for the standalone tests. Tests requiring QGIS are skipped when its Python modules are unavailable. To include the request lifecycle, settings, and dock tests, run `python -m unittest discover -s tests -v` in a configured QGIS 4 Python environment. Those tests use mocked network replies and an isolated temporary settings profile; public server availability does not affect their results.

### VSCode settings

Add this to get PyQGIS autocomplete:

```json
    "python.analysis.extraPaths": [
        "/Applications/QGIS.app/Contents/Resources/python3.12/site-packages",
    ],
    "python.autoComplete.extraPaths": [
        "/Applications/QGIS.app/Contents/Resources/python3.12/site-packages",
    ]
```

TODO test qgis-stubs

## Disclaimer

This plugin is not affiliated with OpenStreetMap. Please be considerate with Overpass API usage and follow the endpoint’s fair-use policies.

## License

GPL v3 or later.
