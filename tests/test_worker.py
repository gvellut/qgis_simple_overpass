from __future__ import annotations

from dataclasses import replace
from urllib.parse import parse_qs

from qgis_test_support import (
    FakeNetwork,
    QgisTestCase,
    QNetworkReply,
    QNetworkRequest,
    token_cookie,
)

from simple_overpass.query_builder import QueryContext
from simple_overpass.settings import OSM_ENDPOINT, SimpleOverpassSettings
from simple_overpass.worker import QueryController

CONTEXT = QueryContext(
    lon=6.5670374, lat=45.718501, south=45.71, west=6.56, north=45.73, east=6.58
)
ELEMENT = {
    "type": "node",
    "id": 1,
    "lat": 45.7185,
    "lon": 6.567,
    "tags": {"name": "Test"},
}


class TestQueryController(QgisTestCase):
    def setUp(self):
        super().setUp()
        self.network = FakeNetwork()
        self.controller = QueryController(network_manager=self.network)
        self.results = []
        self.errors = []
        self.warnings = []
        self.done = []
        self.controller.section_result.connect(lambda *args: self.results.append(args))
        self.controller.section_error.connect(lambda *args: self.errors.append(args))
        self.controller.section_warning.connect(
            lambda *args: self.warnings.append(args)
        )
        self.controller.section_done.connect(lambda *args: self.done.append(args))
        self.options = SimpleOverpassSettings().snapshot()
        self.addCleanup(self.controller.reset)

    def start(self, provider="overpass", request_id=1, **changes):
        options = replace(self.options, provider=provider, **changes)
        self.controller.start(request_id, CONTEXT, options)

    def bootstrap(self):
        self.start("osm")
        self.network.gets[-1].complete(cookies=[token_cookie()])

    def test_sections_dispatch_concurrently_and_finish_in_either_order(self):
        for order in [(0, 1), (1, 0)]:
            with self.subTest(order=order):
                self.results.clear()
                self.done.clear()
                self.start()
                replies = self.network.posts[-2:]
                self.assertEqual(len(self.controller._replies), 2)
                for index in order:
                    replies[index].complete({"elements": [ELEMENT]})
                self.assertEqual(len(self.results), 2)
                self.assertEqual(len(self.done), 2)
                self.assertFalse(self.controller._pending)

    def test_one_error_leaves_other_request_running(self):
        self.start()
        nearby, enclosing = self.network.posts
        nearby.complete(status=502)
        self.assertEqual(len(self.errors), 1)
        self.assertEqual(self.done, [(1, "nearby")])
        self.assertFalse(enclosing.aborted)
        enclosing.complete({"elements": [ELEMENT]})
        self.assertEqual(self.results, [(1, "enclosing", [ELEMENT])])

    def test_form_encoding_preserves_special_tag_characters(self):
        self.start(global_tag_filter="name=A&B + café=1")
        query = parse_qs(self.network.posts[0].post_body.decode())["data"][0]
        self.assertIn('["name"="A&B + café=1"]', query)

    def test_one_bootstrap_shared_by_sections_and_cookie_reused(self):
        self.start("osm")
        self.assertEqual(len(self.network.gets), 1)
        self.assertFalse(self.network.posts)
        self.network.gets[0].complete(cookies=[token_cookie()])
        self.assertEqual(len(self.network.posts), 2)
        for reply in self.network.posts:
            self.assertEqual(reply.request.url().toString(), OSM_ENDPOINT)
            self.assertEqual(
                bytes(reply.request.rawHeader(b"Cookie")),
                b"_osm_totp_token=test-token",
            )
        self.start("osm", request_id=2)
        self.assertEqual(len(self.network.gets), 1)
        self.assertEqual(len(self.network.posts), 4)

    def test_cookie_isolation_and_no_cookie_on_overpass(self):
        self.bootstrap()
        self.start("overpass", endpoint="https://example.com/api/interpreter")
        for reply in self.network.gets + self.network.posts:
            for attribute in [
                QNetworkRequest.Attribute.CookieLoadControlAttribute,
                QNetworkRequest.Attribute.CookieSaveControlAttribute,
            ]:
                self.assertEqual(
                    reply.request.attribute(attribute),
                    QNetworkRequest.LoadControl.Manual,
                )
        for reply in self.network.posts[-2:]:
            self.assertIsNone(
                reply.request.header(QNetworkRequest.KnownHeaders.CookieHeader)
            )
        self.assertIsNone(self.controller._token)

    def test_cookie_near_expiry_is_refetched(self):
        self.bootstrap()
        self.controller._token = token_cookie(lifetime=20)
        self.start("osm", request_id=2)
        self.assertEqual(len(self.network.gets), 2)
        self.assertEqual(len(self.network.posts), 2)

    def test_concurrent_403_responses_share_refresh_and_retry_once(self):
        self.bootstrap()
        first, second = self.network.posts
        first.complete(status=403)
        second.complete(status=403)
        self.assertEqual(len(self.network.gets), 2)
        self.network.gets[1].complete(cookies=[token_cookie(b"new-token")])
        self.assertEqual(len(self.network.posts), 4)
        for reply in self.network.posts[2:]:
            reply.complete(status=403)
        self.assertEqual(len(self.errors), 2)
        self.assertEqual(len(self.done), 2)
        self.assertEqual(len(self.network.gets), 2)

    def test_late_403_does_not_invalidate_new_cookie(self):
        self.bootstrap()
        first, second = self.network.posts
        first.complete(status=403)
        self.network.gets[1].complete(cookies=[token_cookie(b"new-token")])
        second.complete(status=403)
        self.assertEqual(len(self.network.gets), 2)
        self.assertEqual(len(self.network.posts), 4)
        self.assertEqual(bytes(self.controller._token.value()), b"new-token")
        for reply in self.network.posts[2:]:
            reply.complete()
        self.assertEqual(len(self.results), 2)
        self.assertFalse(self.errors)

    def test_refresh_failure_finishes_waiting_sections_without_loop(self):
        self.bootstrap()
        first, second = self.network.posts
        first.complete(status=403)
        self.network.gets[1].complete(status=503)
        second.complete(status=403)
        self.assertEqual(len(self.network.gets), 2)
        self.assertEqual(len(self.errors), 2)
        self.assertFalse(self.controller._pending)

    def test_missing_or_expired_cookie_is_reported_for_both_sections(self):
        for cookies in [[], [token_cookie(lifetime=-1)]]:
            with self.subTest(cookies=bool(cookies)):
                self.errors.clear()
                self.start("osm")
                self.network.gets[-1].complete(cookies=cookies)
                self.assertEqual(len(self.errors), 2)
                self.assertFalse(self.controller._pending)

    def test_new_click_aborts_both_replies_and_ignores_late_responses(self):
        self.start()
        previous = self.network.posts[:]
        self.start(request_id=2)
        self.assertTrue(all(reply.aborted for reply in previous))
        for reply in previous:
            reply.complete({"elements": [ELEMENT]})
        self.assertFalse(self.results)
        self.assertFalse(self.errors)
        self.assertFalse(self.done)
        self.network.posts[-1].complete()
        self.assertEqual(self.results[0][0], 2)

    def test_cancelling_cookie_fetch_cannot_start_old_queries(self):
        self.start("osm")
        old = self.network.gets[0]
        self.start("osm", request_id=2)
        self.assertTrue(old.aborted)
        old.complete(cookies=[token_cookie()])
        self.assertFalse(self.network.posts)
        self.assertIsNone(self.controller._token)
        self.network.gets[1].complete(cookies=[token_cookie()])
        self.assertEqual(len(self.network.posts), 2)
        self.assertFalse(self.errors)

    def test_reset_cancels_replies_and_removes_cookie(self):
        self.bootstrap()
        replies = self.network.posts[:]
        self.controller.reset()
        self.assertTrue(all(reply.aborted for reply in replies))
        self.assertIsNone(self.controller._token)
        self.assertFalse(self.errors)
        self.assertFalse(self.done)

    def test_partial_results_and_empty_remarks_for_both_providers(self):
        for provider in ["overpass", "osm"]:
            with self.subTest(provider=provider):
                self.results.clear()
                self.warnings.clear()
                self.start(provider)
                if self.controller._cookie_reply is not None:
                    self.network.gets[-1].complete(cookies=[token_cookie()])
                first, second = self.network.posts[-2:]
                first.complete({"elements": [ELEMENT], "remark": "Timed out"})
                second.complete({"remark": "Out of memory"})
                self.assertEqual(len(self.results), 2)
                self.assertEqual(self.results[0][2], [ELEMENT])
                self.assertEqual(self.results[1][2], [])
                self.assertEqual(len(self.warnings), 2)
                self.assertFalse(self.errors)

    def test_invalid_responses_and_network_errors(self):
        cases = [
            dict(body=b"<html>bad gateway</html>"),
            dict(payload=[]),
            dict(payload={"elements": {}}),
            dict(payload={"elements": [None]}),
            dict(payload={}),
            dict(status=None, error=QNetworkReply.NetworkError.HostNotFoundError),
        ]
        for response in cases:
            with self.subTest(response=response):
                self.errors.clear()
                self.start(fetch_enclosing=False)
                self.network.posts[-1].complete(**response)
                self.assertEqual(len(self.errors), 1)
                self.assertFalse(self.controller._pending)

    def test_osm_omits_date_while_overpass_uses_it(self):
        self.start("osm", date_filter="2025-01-01")
        self.network.gets[-1].complete(cookies=[token_cookie()])
        self.assertNotIn(
            "[date:", parse_qs(self.network.posts[-1].post_body.decode())["data"][0]
        )
        self.start("overpass", date_filter="2025-01-01")
        self.assertIn(
            "[date:", parse_qs(self.network.posts[-1].post_body.decode())["data"][0]
        )

    def test_disabled_sections_and_invalid_coordinates(self):
        self.start(fetch_enclosing=False)
        self.assertEqual(len(self.network.posts), 1)
        self.controller.start(2, replace(CONTEXT, lat=float("nan")), self.options)
        self.assertEqual(len(self.errors), 2)
        self.assertFalse(self.controller._pending)
        self.start(fetch_nearby=False, fetch_enclosing=False)
        self.assertEqual(len(self.network.posts), 1)
