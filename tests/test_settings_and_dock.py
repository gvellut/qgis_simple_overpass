from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from qgis_test_support import (
    APP,
    FakeNetwork,
    QDate,
    QgisTestCase,
    QgsSettings,
    QMainWindow,
    token_cookie,
)

from simple_overpass.results_dock import CHUNK_SIZE, SimpleOverpassResultsDock
from simple_overpass.settings import (
    DEFAULT_CUSTOM_USER_AGENT,
    DEFAULT_ENDPOINT,
    DEFAULT_USER_AGENT,
    SimpleOverpassOptionsPageWidget,
    SimpleOverpassOptionsWidgetFactory,
    SimpleOverpassSettings,
)
from simple_overpass.simple_overpass import SimpleOverpassPlugin

ELEMENT = {
    "type": "node",
    "id": 1,
    "lat": 45.7185,
    "lon": 6.567,
    "tags": {"name": "Test"},
}
BBOX = (45.71, 6.56, 45.73, 6.58)


class TestSettings(QgisTestCase):
    def test_user_agent_selection_persists_and_resets_effective_identity(self):
        settings = SimpleOverpassSettings()
        page = SimpleOverpassOptionsPageWidget()
        reset = Mock()
        page.connection_changed.connect(reset)
        self.assertEqual(settings.snapshot().user_agent, DEFAULT_USER_AGENT)
        self.assertFalse(page.custom_user_agent_edit.isEnabled())
        self.assertEqual(page.custom_user_agent_edit.text(), DEFAULT_CUSTOM_USER_AGENT)
        page.user_agent_combo.setCurrentIndex(1)
        self.assertTrue(page.custom_user_agent_edit.isEnabled())
        page.custom_user_agent_edit.setText("MyClient/1.0")
        page.apply()
        self.assertEqual(settings.snapshot().user_agent, "MyClient/1.0")
        reset.assert_called_once()
        page.deleteLater()

        reopened = SimpleOverpassOptionsPageWidget()
        reopened.connection_changed.connect(reset)
        self.assertTrue(reopened.user_agent_combo.currentData())
        self.assertEqual(reopened.custom_user_agent_edit.text(), "MyClient/1.0")
        reopened.user_agent_combo.setCurrentIndex(0)
        reopened.apply()
        self.assertEqual(reset.call_count, 2)
        self.assertEqual(settings.snapshot().user_agent, DEFAULT_USER_AGENT)
        self.assertEqual(settings.custom_user_agent, "MyClient/1.0")
        reopened.deleteLater()

    def test_cancel_user_agent_change_and_empty_custom_value(self):
        settings = SimpleOverpassSettings()
        page = SimpleOverpassOptionsPageWidget()
        reset = Mock()
        page.connection_changed.connect(reset)
        page.user_agent_combo.setCurrentIndex(1)
        page.custom_user_agent_edit.setText("Canceled/1.0")
        page.cancel()
        self.assertEqual(settings.user_agent, DEFAULT_USER_AGENT)
        self.assertEqual(settings.custom_user_agent, DEFAULT_CUSTOM_USER_AGENT)
        reset.assert_not_called()
        page.custom_user_agent_edit.clear()
        page.apply()
        self.assertEqual(settings.user_agent, DEFAULT_CUSTOM_USER_AGENT)
        reset.assert_called_once()
        page.deleteLater()

    def test_provider_defaults_and_legacy_custom_url(self):
        settings = SimpleOverpassSettings()
        self.assertEqual(settings.provider, "overpass")
        settings.endpoint = "https://example.com/api/interpreter"
        self.assertEqual(settings.snapshot().query_endpoint, settings.endpoint)
        QgsSettings().setValue("SimpleOverpass/provider", "unknown")
        self.assertEqual(settings.provider, "overpass")

    def test_cancel_does_not_persist_changes_or_emit_reset(self):
        page = SimpleOverpassOptionsPageWidget()
        reset = Mock()
        page.connection_changed.connect(reset)
        page.provider_combo.setCurrentIndex(1)
        page.endpoint_edit.setText("https://example.com/api/interpreter")
        page.cancel()
        self.assertEqual(SimpleOverpassSettings().provider, "overpass")
        self.assertEqual(SimpleOverpassSettings().endpoint, DEFAULT_ENDPOINT)
        reset.assert_not_called()
        page.deleteLater()

    def test_mode_controls_and_date_survive_applying_osm(self):
        settings = SimpleOverpassSettings()
        settings.date_filter = "2025-02-03"
        page = SimpleOverpassOptionsPageWidget()
        reset = Mock()
        page.connection_changed.connect(reset)
        self.assertTrue(page.date_edit.isEnabled())
        page.provider_combo.setCurrentIndex(1)
        self.assertFalse(page.endpoint_edit.isEnabled())
        self.assertFalse(page.date_enabled_checkbox.isEnabled())
        self.assertFalse(page.date_edit.isEnabled())
        page.apply()
        self.assertEqual(settings.provider, "osm")
        self.assertEqual(settings.date_filter, "2025-02-03")
        self.assertEqual(settings.snapshot().date_filter, "")
        reset.assert_called_once()
        page.deleteLater()
        reopened = SimpleOverpassOptionsPageWidget()
        reopened.provider_combo.setCurrentIndex(0)
        self.assertTrue(reopened.date_edit.isEnabled())
        self.assertEqual(reopened.date_edit.date(), QDate(2025, 2, 3))
        reopened.apply()
        self.assertEqual(settings.snapshot().date_filter, "2025-02-03")
        reopened.deleteLater()

    def test_only_connection_changes_emit_reset_through_factory(self):
        factory = SimpleOverpassOptionsWidgetFactory()
        reset = Mock()
        factory.connection_changed.connect(reset)
        page = factory.createWidget()
        self.assertIsInstance(page, SimpleOverpassOptionsPageWidget)
        page.distance_spin.setValue(20)
        page.apply()
        reset.assert_not_called()
        page.endpoint_edit.setText("https://example.com/api/interpreter")
        page.apply()
        reset.assert_called_once()
        page.apply()
        reset.assert_called_once()
        page.deleteLater()
        factory.deleteLater()


class TestResultsDock(QgisTestCase):
    def setUp(self):
        super().setUp()
        self.window = QMainWindow()
        self.bar = Mock()
        self.iface = SimpleNamespace(
            mainWindow=lambda: self.window,
            messageBar=lambda: self.bar,
            mapCanvas=Mock(),
        )
        with patch("simple_overpass.results_dock.MapResultRenderer"):
            self.dock = SimpleOverpassResultsDock(self.iface, "Simple Overpass")
        self.network = FakeNetwork()
        self.dock.controller._network = self.network

    def tearDown(self):
        self.dock.cleanup()
        self.dock.deleteLater()
        self.window.deleteLater()
        super().tearDown()

    def start(self):
        self.dock.start_query(6.567, 45.7185, BBOX)

    def drain(self):
        for _ in range(8):
            APP.processEvents()

    def test_failed_section_does_not_remove_successful_features(self):
        for error_first in [True, False]:
            with self.subTest(error_first=error_first):
                self.start()
                nearby, enclosing = self.network.posts[-2:]
                if error_first:
                    nearby.complete(status=502)
                enclosing.complete({"elements": [ELEMENT]})
                self.drain()
                if not error_first:
                    nearby.complete(status=502)
                self.drain()
                self.assertEqual(self.dock._feature_count, 1)
                self.assertEqual(len(self.dock._section_items), 2)
                self.assertIn("Partial results", self.dock.status_label.text())
                self.assertIn(
                    "Error:", self.dock._section_items["nearby"].child(0).text(0)
                )
                self.assertEqual(
                    self.dock._section_items["enclosing"].child(0).text(0), "Test"
                )

    def test_partial_elements_keep_geometry_actions_and_warning(self):
        self.start()
        self.network.posts[0].complete({"elements": [ELEMENT], "remark": "Timed out"})
        self.network.posts[1].complete()
        self.drain()
        parent = self.dock._section_items["nearby"]
        self.assertEqual(parent.childCount(), 2)
        self.assertEqual(self.dock._feature_count, 1)
        self.assertIn("Timed out", self.dock.status_label.text())
        self.assertNotIn("Loading", self.dock.status_label.text())
        feature_item = next(
            parent.child(i)
            for i in range(parent.childCount())
            if parent.child(i).text(0) == "Test"
        )
        self.dock.tree.setCurrentItem(feature_item)
        feature = self.dock._selected_feature()
        self.assertIsNotNone(feature.geometry())
        self.assertEqual(feature.osm_url(), "https://www.openstreetmap.org/node/1")

    def test_empty_remark_is_not_labeled_no_features(self):
        self.start()
        self.network.posts[0].complete({"remark": "Out of memory"})
        self.network.posts[1].complete()
        self.drain()
        self.assertIn("Out of memory", self.dock.status_label.text())
        self.assertNotIn(
            "No features", self.dock._section_items["nearby"].child(0).text(0)
        )
        self.assertEqual(
            self.dock._section_items["enclosing"].child(0).text(0), "No features found"
        )

    def test_completion_waits_for_all_render_chunks(self):
        self.start()
        elements = [dict(ELEMENT, id=i) for i in range(CHUNK_SIZE * 3)]
        self.network.posts[0].complete({"elements": elements})
        self.network.posts[1].complete()
        self.assertIn("Loading", self.dock.status_label.text())
        self.drain()
        self.assertEqual(self.dock._feature_count, len(elements))
        self.assertFalse(self.dock._pending_sections)
        self.assertNotIn("Loading", self.dock.status_label.text())

    def test_new_click_invalidates_old_rendering_without_touching_new_queue(self):
        self.start()
        old_id = self.dock._current_request_id
        old_replies = self.network.posts[:]
        old_replies[0].complete({"elements": [ELEMENT] * (CHUNK_SIZE * 3)})
        self.start()
        self.assertTrue(old_replies[1].aborted)
        self.network.posts[-2].complete({"elements": [dict(ELEMENT, id=99)]})
        self.dock._process_section_chunk(old_id, "nearby")
        self.assertTrue(self.dock._section_processing["nearby"])
        self.network.posts[-1].complete()
        self.drain()
        self.assertEqual(self.dock._feature_count, 1)
        self.assertEqual(self.dock._section_counts["nearby"], 1)
        self.bar.pushMessage.assert_not_called()

    def test_apply_provider_change_clears_active_state_and_cookie(self):
        settings = SimpleOverpassSettings()
        settings.provider = "osm"
        self.start()
        self.network.gets[0].complete(cookies=[token_cookie()])
        replies = self.network.posts[:]
        replies[0].complete({"elements": [ELEMENT]})
        page = SimpleOverpassOptionsPageWidget()
        page.connection_changed.connect(self.dock.reset_connection)
        page.provider_combo.setCurrentIndex(0)
        page.apply()
        self.drain()
        self.assertTrue(replies[1].aborted)
        self.assertIsNone(self.dock.controller._token)
        self.assertEqual(self.dock.tree.topLevelItemCount(), 0)
        self.assertEqual(self.dock._feature_count, 0)
        self.assertFalse(self.dock._pending_sections)
        self.assertIn("Click the map", self.dock.status_label.text())
        self.dock.renderer.cleanup.assert_called()
        page.deleteLater()

    def test_apply_user_agent_change_clears_active_osm_session(self):
        settings = SimpleOverpassSettings()
        settings.provider = "osm"
        self.start()
        self.network.gets[0].complete(cookies=[token_cookie()])
        old_replies = self.network.posts[:]
        page = SimpleOverpassOptionsPageWidget()
        page.connection_changed.connect(self.dock.reset_connection)
        page.user_agent_combo.setCurrentIndex(1)
        page.apply()
        self.assertTrue(all(reply.aborted for reply in old_replies))
        self.assertIsNone(self.dock.controller._token)
        self.assertEqual(self.dock.tree.topLevelItemCount(), 0)
        self.start()
        self.assertEqual(len(self.network.gets), 2)
        self.assertEqual(
            bytes(self.network.gets[-1].request.rawHeader(b"User-Agent")),
            DEFAULT_CUSTOM_USER_AGENT.encode(),
        )
        page.deleteLater()

    def test_unload_aborts_replies_without_warnings(self):
        self.start()
        plugin = SimpleOverpassPlugin(self.iface)
        plugin.results_dock = self.dock
        plugin.unload()
        self.assertTrue(all(reply.aborted for reply in self.network.posts))
        self.bar.pushMessage.assert_not_called()

    def test_empty_and_disabled_sections(self):
        self.start()
        for reply in self.network.posts:
            reply.complete()
        self.drain()
        self.assertEqual(self.dock.status_label.text(), "No features found.")
        settings = SimpleOverpassSettings()
        settings.fetch_nearby = False
        settings.fetch_enclosing = False
        self.start()
        self.assertEqual(len(self.network.posts), 2)
        self.assertIn("Enable Nearby", self.dock.status_label.text())
