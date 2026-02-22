from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QueryContext:
    lon: float
    lat: float
    south: float
    west: float
    north: float
    east: float


class OverpassQueryError(ValueError):
    pass


class QuerySettingsLike(Protocol):
    distance: int
    timeout: int
    date_filter: str
    global_tag_filter: str
    only_center: bool
    only_with_tags: bool


def build_nearby_query(settings: QuerySettingsLike, ctx: QueryContext) -> str:
    prefix = build_query_prefix(settings)
    selector = (
        f"nwr(around:{settings.distance},{fmt(ctx.lat)},{fmt(ctx.lon)})"
        f"{build_tag_filter_clause(settings.global_tag_filter)}"
        f"{build_only_tags_clause(settings.only_with_tags)}"
    )

    if settings.only_center:
        out_clause = "out tags center;"
    else:
        bbox = (
            f"({fmt(ctx.south)},{fmt(ctx.west)},{fmt(ctx.north)},{fmt(ctx.east)})"
        )
        out_clause = f"out tags geom{bbox};"

    return "\n".join([prefix, f"{selector};", out_clause])


def build_enclosing_query(settings: QuerySettingsLike, ctx: QueryContext) -> str:
    prefix = build_query_prefix(settings)
    filters = (
        f"{build_tag_filter_clause(settings.global_tag_filter)}"
        f"{build_only_tags_clause(settings.only_with_tags)}"
    )
    lines = [
        prefix,
        f"is_in({fmt(ctx.lat)},{fmt(ctx.lon)})->.a;",
        f"way(pivot.a){filters};",
        "out tags bb;",
        f"relation(pivot.a){filters};",
        "out tags bb;",
    ]
    return "\n".join(lines)


def build_query_prefix(settings: QuerySettingsLike) -> str:
    parts = ["[out:json]"]
    if settings.date_filter:
        parts.append(f"[date:\"{settings.date_filter}T00:00:00Z\"]")
    parts.append(f"[timeout:{settings.timeout}]")
    return "".join(parts) + ";"


def build_only_tags_clause(enabled: bool) -> str:
    if not enabled:
        return ""
    return "(if:count_tags() > 0)"


def build_tag_filter_clause(raw_filter: str) -> str:
    raw_filter = (raw_filter or "").strip()
    if not raw_filter:
        return ""

    key: str
    value: str | None
    if "=" in raw_filter:
        key, value = raw_filter.split("=", 1)
        key = key.strip()
        value = value.strip()
    else:
        key = raw_filter.strip()
        value = None

    if not key:
        raise OverpassQueryError("Tag filter key cannot be empty.")

    key_escaped = _escape_ql_string(key)
    if value is None:
        return f"[\"{key_escaped}\"]"

    value_escaped = _escape_ql_string(value)
    return f"[\"{key_escaped}\"=\"{value_escaped}\"]"


def _escape_ql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fmt(value: float) -> str:
    text = f"{value:.8f}"
    text = text.rstrip("0").rstrip(".")
    return text or "0"
