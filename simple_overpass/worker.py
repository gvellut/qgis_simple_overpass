from __future__ import annotations

from dataclasses import replace
import json
import math
import time
from urllib.parse import urlencode

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QDateTime, QObject, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkCookie, QNetworkReply, QNetworkRequest

from .query_builder import QueryContext, build_enclosing_query, build_nearby_query
from .settings import QueryOptions

LOG_TAG = "Simple Overpass"
OSM_COOKIE_URL = "https://www.openstreetmap.org/"
TOKEN_NAME = b"_osm_totp_token"


class QueryController(QObject):
    """Own asynchronous replies and an isolated, in-memory OSM cookie session."""

    section_result = pyqtSignal(int, str, list)
    section_warning = pyqtSignal(int, str, str)
    section_error = pyqtSignal(int, str, str)
    section_done = pyqtSignal(int, str)

    def __init__(self, parent=None, network_manager=None) -> None:
        super().__init__(parent)
        self._network = (
            network_manager
            if network_manager is not None
            else QgsNetworkAccessManager.instance()
        )
        self._generation = 0
        self._connection: tuple[str, str, str] | None = None
        self._token: QNetworkCookie | None = None
        self._token_generation = 0
        self._cookie_reply: QNetworkReply | None = None
        self._replies: dict[str, QNetworkReply] = {}
        self._pending: set[str] = set()
        self._waiting_for_cookie: set[str] = set()
        self._retried: set[str] = set()
        self._refresh_attempted = False
        self._queries: dict[str, str] = {}
        self._request_id = 0
        self._options: QueryOptions | None = None

    def cancel(self) -> None:
        # abort() can emit finished synchronously. Invalidate callbacks first.
        self._generation += 1
        replies = list(self._replies.values())
        if self._cookie_reply is not None:
            replies.append(self._cookie_reply)
        self._replies.clear()
        self._cookie_reply = None
        self._pending.clear()
        self._waiting_for_cookie.clear()
        self._queries.clear()
        self._retried.clear()
        for reply in replies:
            reply.abort()

    def reset(self) -> None:
        self.cancel()
        self._token = None
        self._token_generation += 1
        self._connection = None

    def start(
        self, request_id: int, context: QueryContext, options: QueryOptions
    ) -> None:
        self.cancel()
        connection = (options.provider, options.endpoint, options.user_agent)
        if connection != self._connection:
            self._token = None
            self._connection = connection
        if options.provider == "osm":
            options = replace(options, date_filter="")
        self._options = options
        self._request_id = request_id
        self._refresh_attempted = False
        builders = []
        if options.fetch_nearby:
            builders.append(("nearby", build_nearby_query))
        if options.fetch_enclosing:
            builders.append(("enclosing", build_enclosing_query))
        self._pending = {section for section, _ in builders}
        valid = (
            math.isfinite(context.lon)
            and math.isfinite(context.lat)
            and abs(context.lon) <= 180
            and abs(context.lat) <= 90
        )
        for section, builder in builders:
            try:
                if not valid:
                    raise ValueError(self.tr("Clicked coordinates are invalid."))
                self._queries[section] = builder(options, context)
            except ValueError as exc:
                self._fail(section, str(exc))
        for section in list(self._queries):
            self._dispatch(section)

    def _request(self, url: str) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", self._options.user_agent.encode("utf-8"))
        # Never read or write cookies in QGIS's application-wide cookie jar.
        for attribute in (
            QNetworkRequest.Attribute.CookieLoadControlAttribute,
            QNetworkRequest.Attribute.CookieSaveControlAttribute,
        ):
            request.setAttribute(attribute, QNetworkRequest.LoadControl.Manual)
        if self._options.provider == "osm":
            request.setAttribute(
                QNetworkRequest.Attribute.RedirectPolicyAttribute,
                QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy,
            )
        request.setAttribute(
            QNetworkRequest.Attribute.CacheLoadControlAttribute,
            QNetworkRequest.CacheLoadControl.AlwaysNetwork,
        )
        return request

    def _token_valid(self) -> bool:
        return self._token is not None and (
            self._token.expirationDate() > QDateTime.currentDateTimeUtc().addSecs(30)
        )

    def _dispatch(self, section: str) -> None:
        options = self._options
        if options.provider == "osm" and not self._token_valid():
            self._waiting_for_cookie.add(section)
            self._fetch_cookie()
            return
        request = self._request(options.query_endpoint)
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/x-www-form-urlencoded",
        )
        if options.provider == "osm":
            request.setRawHeader(
                b"Cookie",
                self._token.toRawForm(QNetworkCookie.RawForm.NameAndValueOnly),
            )
        body = urlencode({"data": self._queries[section]}).encode("utf-8")
        self._log(
            f"{section} query to {options.query_endpoint}:\n{self._queries[section]}"
        )
        generation = self._generation
        token_generation = self._token_generation
        started = time.monotonic()
        reply = self._network.post(request, body)
        self._replies[section] = reply
        reply.finished.connect(
            lambda: self._query_finished(
                generation, section, token_generation, started, reply
            )
        )

    def _fetch_cookie(self) -> None:
        if self._cookie_reply is not None:
            return
        generation = self._generation
        started = time.monotonic()
        reply = self._network.get(self._request(OSM_COOKIE_URL))
        self._cookie_reply = reply
        reply.finished.connect(
            lambda: self._cookie_finished(generation, started, reply)
        )

    def _cookie_finished(
        self, generation: int, started: float, reply: QNetworkReply
    ) -> None:
        try:
            if generation != self._generation:
                return
            self._cookie_reply = None
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            self._log(
                f"cookie fetch: HTTP {status}, {time.monotonic() - started:.3f} s"
            )
            error = self._network_error(reply, status)
            if error:
                raise ValueError(
                    self.tr("Could not fetch OSM cookie: {error}").format(error=error)
                )
            cookies = []
            for name, value in reply.rawHeaderPairs():
                if bytes(name).lower() == b"set-cookie":
                    cookies.extend(QNetworkCookie.parseCookies(value))
            self._token = next(
                (
                    cookie
                    for cookie in cookies
                    if bytes(cookie.name()) == TOKEN_NAME
                    and cookie.value()
                    and cookie.domain().lstrip(".")
                    in {"openstreetmap.org", "www.openstreetmap.org"}
                    and not cookie.isSessionCookie()
                    and cookie.expirationDate()
                    > QDateTime.currentDateTimeUtc().addSecs(30)
                ),
                None,
            )
            if self._token is None:
                raise ValueError(self.tr("OSM did not return a valid query cookie."))
            self._token_generation += 1
            waiting = list(self._waiting_for_cookie)
            self._waiting_for_cookie.clear()
            for section in waiting:
                self._dispatch(section)
        except ValueError as exc:
            self._token = None
            waiting = list(self._waiting_for_cookie)
            self._waiting_for_cookie.clear()
            for section in waiting:
                self._fail(section, str(exc))
        finally:
            reply.deleteLater()

    def _query_finished(
        self,
        generation: int,
        section: str,
        token_generation: int,
        started: float,
        reply: QNetworkReply,
    ) -> None:
        try:
            if generation != self._generation:
                return
            self._replies.pop(section, None)
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            self._log(f"{section}: HTTP {status}, {time.monotonic() - started:.3f} s")
            if status == 403 and self._options.provider == "osm":
                self._retry_with_cookie(section, token_generation)
                return
            error = self._network_error(reply, status)
            if error:
                raise ValueError(error)
            try:
                payload = json.loads(bytes(reply.readAll()))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError(self.tr("Parsing data error")) from exc
            if not isinstance(payload, dict):
                raise ValueError(self.tr("Unexpected response from Overpass API"))
            remark = payload.get("remark")
            elements = payload.get("elements", [] if remark else None)
            if not isinstance(elements, list) or any(
                not isinstance(element, dict) for element in elements
            ):
                raise ValueError(self.tr("Unexpected response from Overpass API"))
            self._log(f"{section}: fetched {len(elements)} elements")
            self.section_result.emit(self._request_id, section, elements)
            if remark:
                self.section_warning.emit(self._request_id, section, str(remark))
            self._finish(section)
        except ValueError as exc:
            self._fail(section, str(exc))
        finally:
            reply.deleteLater()

    def _retry_with_cookie(self, section: str, token_generation: int) -> None:
        if section in self._retried:
            self._fail(
                section,
                self.tr(
                    "OSM query was forbidden after refreshing its cookie (HTTP 403)."
                ),
            )
            return
        self._retried.add(section)
        if token_generation != self._token_generation and self._token_valid():
            self._dispatch(section)
        elif self._cookie_reply is not None:
            self._waiting_for_cookie.add(section)
        elif not self._refresh_attempted:
            self._refresh_attempted = True
            self._token = None
            self._waiting_for_cookie.add(section)
            self._fetch_cookie()
        else:
            self._fail(
                section,
                self.tr(
                    "OSM query was forbidden (HTTP 403); cookie refresh already failed."
                ),
            )

    def _network_error(self, reply: QNetworkReply, status: int | None) -> str:
        if status is not None and not 200 <= status < 300:
            return self.tr("HTTP {status}: {message}").format(
                status=status, message=reply.errorString()
            )
        if reply.error() != QNetworkReply.NetworkError.NoError:
            return reply.errorString() or self.tr("Network error")
        return ""

    def _fail(self, section: str, message: str) -> None:
        self.section_error.emit(self._request_id, section, message)
        self._finish(section)

    def _finish(self, section: str) -> None:
        self._pending.discard(section)
        self.section_done.emit(self._request_id, section)

    def _log(self, message: str) -> None:
        if self._options is not None and self._options.debug_enabled:
            QgsMessageLog.logMessage(
                f"[{self._options.provider}] {message}",
                LOG_TAG,
                level=Qgis.MessageLevel.Info,
            )
