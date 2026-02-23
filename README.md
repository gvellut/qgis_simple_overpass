
# Simple Overpass (QGIS plugin)

Simple Overpass is a small QGIS plugin that lets you click on the map and retrieve OpenStreetMap (OSM) objects around that location using the Overpass API (similar to the “Query Features” tool on openstreetmap.org).

It is very similar to the [QGIS OSM Info plugin](https://github.com/nextgis/qgis_osminfo) but with additional config + queries + optimised display of the info.

The results are shown in a dock panel, grouped into:

- **Nearby features**: nodes/ways/relations within a radius around the clicked point.
- **Is inside**: enclosing ways/relations for the clicked point.

## Features

- Click on the map to query OSM data via Overpass.
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

- QGIS 3.22+ (see plugin metadata in the plugin folder)
- Network access to an Overpass API endpoint

Default endpoint: `https://overpass-api.de/api/interpreter`

## Install (development)

1. Set the env var QGIS_PLUGINPATH to the directory eg `/Users/guilhem/Documents/projects/github/qgis_simple_overpass`
2. Restart QGIS.
3. Enable the plugin in **Plugins → Manage and Install Plugins…**.
4. (optional) For development, install the **Plugin Reloader** plugin 

*Note*: Multiple plugin paths can be passed, separated with `:`

## Usage

1. Activate the tool: **Web → Simple Overpass → Query OSM info from Overpass**.
	 - The plugin also registers an icon in the Web toolbar and adds a toolbar icon.
2. Left-click the map.
3. The **Simple Overpass** dock opens (or becomes visible) and starts loading results.
4. Click a feature in the list to highlight it on the map.
5. Right-click a feature (or a tag) for actions like copy/open/zoom/save.

## Settings

Open settings via **Web → Simple Overpass → Settings** (or QGIS **Settings → Options** and find “Simple Overpass”).

- **Overpass API endpoint**: URL of the Overpass interpreter endpoint.
- **Distance**: radius in meters used for the “Nearby features” query.
- **Timeout**: Overpass timeout in seconds.
- **Nearby / Enclosing**: enable/disable each section.
- **Only include objects with tag**: filters objects without any tags.
- **Date filter (UTC)**: optional Overpass query date (sent as `[date:"YYYY-MM-DDT00:00:00Z"]`).
- **Tag filter**: optional global tag filter applied to both queries.
	- `key` (tag exists), e.g. `highway`
	- `key=value` (exact match), e.g. `building=house`
- **Only center**: for the nearby query, request center points instead of full geometry.
- **Enable Debug**: logs the generated queries and element counts to the QGIS log.

## Troubleshooting

- **“Network error” / request fails**: check your network and the configured endpoint.
- **Overpass returns an error remark**: the message from Overpass is shown in QGIS; try increasing timeout, reducing distance, or switching endpoint.
- **“Parsing data error”**: usually means the endpoint did not return valid Overpass JSON.
- **No sections appear**: enable “Nearby” and/or “Enclosing” in settings.
- **Save to selected layer disabled**: select a target vector layer in the Layers panel; it must be compatible with the feature geometry type.

## Development

### VSCode settings

Add this to get PyQGIS autocomplete:

```json
    "python.analysis.extraPaths": [
        "/Applications/QGIS.app/Contents/Resources/python3.11/site-packages",
    ],
    "python.autoComplete.extraPaths": [
        "/Applications/QGIS.app/Contents/Resources/python3.11/site-packages",
    ]
```

TODO test qgis-stubs

## License

GPL v3 or later.