from __future__ import annotations

from dataclasses import dataclass
import unittest

from simple_overpass.query_builder import (
    OverpassQueryError,
    QueryContext,
    build_enclosing_query,
    build_nearby_query,
    build_query_prefix,
    build_tag_filter_clause,
)


@dataclass
class SettingsStub:
    distance: int = 15
    timeout: int = 30
    date_filter: str = ""
    global_tag_filter: str = ""
    only_center: bool = False
    only_with_tags: bool = True


class TestQueryBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = QueryContext(
            lon=6.052496,
            lat=45.880732,
            south=45.879063,
            west=6.048043,
            north=45.881984,
            east=6.059899,
        )

    def test_tag_filter_empty(self) -> None:
        self.assertEqual(build_tag_filter_clause(""), "")
        self.assertEqual(build_tag_filter_clause("   "), "")

    def test_tag_filter_presence(self) -> None:
        self.assertEqual(build_tag_filter_clause("name"), '["name"]')
        self.assertEqual(build_tag_filter_clause("  highway  "), '["highway"]')

    def test_tag_filter_exact_match(self) -> None:
        self.assertEqual(
            build_tag_filter_clause("building=house"),
            '["building"="house"]',
        )
        self.assertEqual(
            build_tag_filter_clause("  addr:housenumber = 10A "),
            '["addr:housenumber"="10A"]',
        )

    def test_tag_filter_escapes_quotes_and_backslashes(self) -> None:
        self.assertEqual(
            build_tag_filter_clause(r'name=Bob "B" \ team'),
            r'["name"="Bob \"B\" \\ team"]',
        )

    def test_tag_filter_invalid_empty_key(self) -> None:
        with self.assertRaises(OverpassQueryError):
            build_tag_filter_clause("=house")

    def test_query_prefix_without_date(self) -> None:
        settings = SettingsStub(timeout=25, date_filter="")
        self.assertEqual(build_query_prefix(settings), "[out:json][timeout:25];")

    def test_query_prefix_with_date(self) -> None:
        settings = SettingsStub(timeout=25, date_filter="2025-07-25")
        self.assertEqual(
            build_query_prefix(settings),
            '[out:json][date:"2025-07-25T00:00:00Z"][timeout:25];',
        )

    def test_nearby_query_geom_mode(self) -> None:
        settings = SettingsStub(
            distance=15,
            timeout=30,
            only_center=False,
            only_with_tags=True,
            global_tag_filter="highway",
        )
        query = build_nearby_query(settings, self.ctx)
        self.assertIn("[out:json][timeout:30];", query)
        self.assertIn(
            "nwr(around:15,45.880732,6.052496)[\"highway\"](if:count_tags() > 0);",
            query,
        )
        self.assertIn(
            "out tags geom(45.879063,6.048043,45.881984,6.059899);",
            query,
        )

    def test_nearby_query_center_mode(self) -> None:
        settings = SettingsStub(
            only_center=True,
            only_with_tags=False,
            global_tag_filter="building=house",
        )
        query = build_nearby_query(settings, self.ctx)
        self.assertIn(
            'nwr(around:15,45.880732,6.052496)["building"="house"];',
            query,
        )
        self.assertIn("out tags center;", query)
        self.assertNotIn("out tags geom(", query)

    def test_enclosing_query_with_filters(self) -> None:
        settings = SettingsStub(
            timeout=40,
            date_filter="2024-01-02",
            global_tag_filter="name",
            only_with_tags=True,
        )
        query = build_enclosing_query(settings, self.ctx)
        self.assertIn(
            '[out:json][date:"2024-01-02T00:00:00Z"][timeout:40];',
            query,
        )
        self.assertIn("is_in(45.880732,6.052496)->.a;", query)
        self.assertIn('way(pivot.a)["name"](if:count_tags() > 0);', query)
        self.assertIn('relation(pivot.a)["name"](if:count_tags() > 0);', query)
        self.assertEqual(query.count("out tags bb;"), 2)


if __name__ == "__main__":
    unittest.main()
