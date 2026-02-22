from __future__ import annotations

from dataclasses import dataclass

from qgis.core import QgsGeometry, QgsPointXY, QgsRectangle

TITLE_RULES = {
    "building": "building: {building}",
    "highway": "highway: {highway}",
    "amenity": "amenity: {amenity}",
}


class PolygonCreator:
    def __init__(self, is_outer: bool = True):
        self.curves: list[list[QgsPointXY]] = []
        self._is_outer = is_outer

    def add_curve(self, lon_lat_pairs: list[QgsPointXY]) -> None:
        curve = None
        for i in range(len(self.curves)):
            current = self.curves[i]
            if current[-1] == lon_lat_pairs[0]:
                curve = self.curves.pop(i)
                curve.extend(lon_lat_pairs)
                break
            if current[0] == lon_lat_pairs[-1]:
                curve = lon_lat_pairs[:-1]
                curve.extend(self.curves.pop(i))
                break
            if current[0] == lon_lat_pairs[0]:
                rev = list(reversed(lon_lat_pairs))
                curve = rev[:-1]
                curve.extend(self.curves.pop(i))
                break
            if current[-1] == lon_lat_pairs[-1]:
                rev = list(reversed(lon_lat_pairs))
                curve = self.curves.pop(i)
                curve.extend(rev)
                break

        if curve is not None:
            self.add_curve(curve)
            return
        self.curves.append(lon_lat_pairs)

    def is_polygon(self) -> bool:
        return len(self.curves) == 1 and self.curves[0][0] == self.curves[0][-1]

    def is_outer(self) -> bool:
        return self._is_outer

    def points(self) -> list[QgsPointXY]:
        all_points: list[QgsPointXY] = []
        for curve in self.curves:
            all_points.extend(curve)
        return all_points


@dataclass
class RelationWayPart:
    points: list[QgsPointXY]
    role: str | None = None

    def is_outer(self) -> bool:
        return self.role == "outer"


@dataclass
class OsmFeature:
    osm_type: str
    osm_id: str
    tags: dict[str, object]
    raw: dict
    title: str
    title_source: str

    _geometry_cache: QgsGeometry | None = None

    @classmethod
    def from_json(cls, raw: dict, locale: str) -> OsmFeature | None:
        if not isinstance(raw, dict):
            return None
        osm_type = str(raw.get("type", ""))
        if osm_type not in {"node", "way", "relation"}:
            return None
        osm_id = str(raw.get("id", raw.get("ref", "<unknown>")))
        raw_tags = raw.get("tags")
        tags = raw_tags if isinstance(raw_tags, dict) else {}
        title, source = build_title(tags, locale, osm_id)
        return cls(
            osm_type=osm_type,
            osm_id=osm_id,
            tags=tags,
            raw=raw,
            title=title,
            title_source=source,
        )

    @property
    def has_name_title(self) -> bool:
        return self.title_source.startswith("name")

    def osm_url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"

    def copy_label(self) -> str:
        return self.title

    def geometry(self) -> QgsGeometry | None:
        if self._geometry_cache is None:
            self._geometry_cache = geometry_from_element(self.raw)
        if self._geometry_cache is None:
            return None
        return QgsGeometry(self._geometry_cache)

    def bounds_area(self) -> float:
        bounds = self.raw.get("bounds")
        if not isinstance(bounds, dict):
            return float("inf")
        try:
            width = float(bounds["maxlon"]) - float(bounds["minlon"])
            height = float(bounds["maxlat"]) - float(bounds["minlat"])
            return max(0.0, width) * max(0.0, height)
        except Exception:
            return float("inf")

    @staticmethod
    def raw_bounds_area(raw: dict) -> float:
        feature = OsmFeature.from_json(raw, "")
        if feature is None:
            return float("inf")
        return feature.bounds_area()


def build_title(
    tags: dict[str, object],
    locale: str,
    fallback_id: str,
) -> tuple[str, str]:
    localized_name_key = f"name:{locale}" if locale else ""
    if localized_name_key and localized_name_key in tags:
        value = str(tags[localized_name_key])
        if value:
            return value, localized_name_key

    if "name" in tags:
        value = str(tags["name"])
        if value:
            return value, "name"

    for key, rule in TITLE_RULES.items():
        if key not in tags:
            continue
        try:
            return rule.format(**{k: str(v) for k, v in tags.items()}), key
        except Exception:
            continue

    return fallback_id, "id"


def geometry_from_element(raw: dict) -> QgsGeometry | None:
    element_type = raw.get("type")
    if element_type == "node":
        return _node_geometry(raw)
    if element_type == "way":
        return _way_geometry(raw)
    if element_type == "relation":
        return _relation_geometry(raw)
    return None


def _node_geometry(raw: dict) -> QgsGeometry | None:
    if "lon" in raw and "lat" in raw:
        try:
            return QgsGeometry.fromPointXY(
                QgsPointXY(float(raw["lon"]), float(raw["lat"]))
            )
        except Exception:
            return None

    center = raw.get("center")
    if isinstance(center, dict):
        return _center_point_geometry(center)
    bounds = raw.get("bounds")
    if isinstance(bounds, dict):
        return _bounds_geometry(bounds)
    return None


def _way_geometry(raw: dict) -> QgsGeometry | None:
    geometry = raw.get("geometry")
    if isinstance(geometry, list) and geometry:
        points = _geometry_points(geometry)
        if len(points) >= 2 and points[0] == points[-1] and len(points) >= 4:
            return QgsGeometry.fromPolygonXY([points])
        if len(points) >= 2:
            return QgsGeometry.fromPolylineXY(points)

    center = raw.get("center")
    if isinstance(center, dict):
        return _center_point_geometry(center)
    bounds = raw.get("bounds")
    if isinstance(bounds, dict):
        return _bounds_geometry(bounds)
    return None


def _relation_geometry(raw: dict) -> QgsGeometry | None:
    members = raw.get("members")
    if isinstance(members, list) and members:
        geom = _relation_geometry_from_members(members, raw)
        if geom is not None:
            return geom

    center = raw.get("center")
    if isinstance(center, dict):
        return _center_point_geometry(center)
    bounds = raw.get("bounds")
    if isinstance(bounds, dict):
        return _bounds_geometry(bounds)
    return None


def _center_point_geometry(center: dict) -> QgsGeometry | None:
    try:
        return QgsGeometry.fromPointXY(
            QgsPointXY(float(center["lon"]), float(center["lat"]))
        )
    except Exception:
        return None


def _bounds_geometry(bounds: dict) -> QgsGeometry | None:
    try:
        rect = QgsRectangle(
            float(bounds["minlon"]),
            float(bounds["minlat"]),
            float(bounds["maxlon"]),
            float(bounds["maxlat"]),
        )
    except Exception:
        return None
    return QgsGeometry.fromRect(rect)


def _geometry_points(geometry_list: list[dict]) -> list[QgsPointXY]:
    points: list[QgsPointXY] = []
    for coord in geometry_list:
        if not isinstance(coord, dict):
            continue
        try:
            points.append(QgsPointXY(float(coord["lon"]), float(coord["lat"])))
        except Exception:
            continue
    return points


def _relation_geometry_from_members(members: list, raw: dict) -> QgsGeometry | None:
    ways: list[RelationWayPart] = []
    line_parts: list[list[QgsPointXY]] = []

    for member in members:
        if not isinstance(member, dict):
            continue
        if member.get("type") != "way":
            continue
        points = _geometry_points(member.get("geometry") or [])
        if len(points) < 2:
            continue
        role = member.get("role") if isinstance(member.get("role"), str) else None
        ways.append(RelationWayPart(points, role))
        line_parts.append(points)

    if not ways:
        return None

    rel_type = str((raw.get("tags") or {}).get("type", ""))
    if rel_type not in {"multipolygon", "boundary"}:
        return QgsGeometry.fromMultiPolylineXY(line_parts)

    polygon_creators: list[PolygonCreator] = []
    is_polygon_finished = True
    for way in ways:
        if is_polygon_finished:
            polygon_creators.append(PolygonCreator(is_outer=way.is_outer()))
            is_polygon_finished = False
        polygon_creators[-1].add_curve(list(way.points))
        if polygon_creators[-1].is_polygon():
            is_polygon_finished = True

    return _polygon_creators_to_geometry(polygon_creators)


def _polygon_creators_to_geometry(creators: list[PolygonCreator]) -> QgsGeometry | None:
    polygons: list[QgsGeometry] = []
    inner_rings: list[QgsGeometry] = []

    for creator in creators:
        if not creator.is_polygon():
            continue
        points = creator.points()
        if creator.is_outer():
            polygons.append(QgsGeometry.fromPolygonXY([points]))
        else:
            inner_rings.append(QgsGeometry.fromPolylineXY(points))

    if not polygons and not inner_rings:
        return None

    polygons.sort(key=lambda g: g.area())
    added_inner: set[int] = set()
    for polygon in polygons:
        for idx, inner in enumerate(inner_rings):
            if idx in added_inner:
                continue
            if polygon.contains(inner):
                polygon.addRing(inner.asPolyline())
                added_inner.add(idx)

    for idx, inner in enumerate(inner_rings):
        if idx in added_inner:
            continue
        polygons.append(QgsGeometry.fromPolygonXY([inner.asPolyline()]))

    if len(polygons) == 1:
        return QgsGeometry(polygons[0])

    multi = QgsGeometry.fromMultiPolygonXY([])
    for polygon in polygons:
        multi.addPartGeometry(polygon)
    return multi
