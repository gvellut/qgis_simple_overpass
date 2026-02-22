from __future__ import annotations

import json

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QThread, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from .query_builder import (
    QueryContext,
    build_enclosing_query,
    build_nearby_query,
)
from .settings import SimpleOverpassSettings

LOG_TAG = "Simple Overpass"


class OverpassWorker(QThread):
    section_result = pyqtSignal(int, str, list)
    error = pyqtSignal(int, str)
    done = pyqtSignal(int)

    def __init__(
        self,
        request_id: int,
        lon: float,
        lat: float,
        bbox: tuple[float, float, float, float],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.request_id = request_id
        self._context = QueryContext(
            lon=float(lon),
            lat=float(lat),
            south=float(bbox[0]),
            west=float(bbox[1]),
            north=float(bbox[2]),
            east=float(bbox[3]),
        )

    def run(self) -> None:
        try:
            self._run_impl()
        except Exception as exc:
            self.error.emit(self.request_id, str(exc))
        finally:
            self.done.emit(self.request_id)

    def _run_impl(self) -> None:
        if abs(self._context.lon) > 180 or abs(self._context.lat) > 90:
            raise RuntimeError(self.tr("Clicked coordinates are invalid."))

        settings = SimpleOverpassSettings()
        if not settings.fetch_nearby and not settings.fetch_enclosing:
            raise RuntimeError(self.tr("Enable Nearby and/or Enclosing in settings."))

        if settings.fetch_nearby:
            nearby_query = build_nearby_query(settings, self._context)
            self._debug_log(settings, "Nearby", nearby_query)
            nearby = self._fetch_from_overpass(settings.endpoint, nearby_query)
            self._debug_count(settings, "nearby", nearby)
            self.section_result.emit(self.request_id, "nearby", nearby)

        if settings.fetch_enclosing:
            enclosing_query = build_enclosing_query(settings, self._context)
            self._debug_log(settings, "Enclosing", enclosing_query)
            enclosing = self._fetch_from_overpass(settings.endpoint, enclosing_query)
            self._debug_count(settings, "enclosing", enclosing)
            self.section_result.emit(self.request_id, "enclosing", enclosing)

    def _fetch_from_overpass(self, endpoint: str, query: str) -> list:
        request = QNetworkRequest(QUrl(endpoint))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/x-www-form-urlencoded",
        )

        reply = QgsNetworkAccessManager.instance().blockingPost(
            request,
            query.encode("utf-8"),
        )

        if reply.error() != QNetworkReply.NetworkError.NoError:
            raise RuntimeError(reply.errorString() or self.tr("Network error"))

        try:
            payload = json.loads(reply.content().data())
        except Exception as exc:
            raise RuntimeError(self.tr("Parsing data error")) from exc

        if payload.get("remark"):
            raise RuntimeError(str(payload["remark"]))

        elements = payload.get("elements", [])
        if not isinstance(elements, list):
            raise RuntimeError(self.tr("Unexpected response from Overpass API"))
        return elements

    def _debug_log(
        self,
        settings: SimpleOverpassSettings,
        label: str,
        query: str,
    ) -> None:
        if not settings.debug_enabled:
            return
        QgsMessageLog.logMessage(
            f"{label} query to {settings.endpoint}:\n{query}",
            LOG_TAG,
            level=Qgis.Info,
        )

    def _debug_count(
        self,
        settings: SimpleOverpassSettings,
        label: str,
        elements: list,
    ) -> None:
        if not settings.debug_enabled:
            return
        QgsMessageLog.logMessage(
            f"Fetched {len(elements)} {label} elements",
            LOG_TAG,
            level=Qgis.Info,
        )
