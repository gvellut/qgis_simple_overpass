"""Qt test fixtures with an isolated settings profile and controllable replies."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_PROFILE = tempfile.TemporaryDirectory(prefix="simple-overpass-tests-")
os.environ["QGIS_CUSTOM_CONFIG_PATH"] = _PROFILE.name

try:
    from qgis.core import QgsApplication, QgsSettings
    from qgis.PyQt.QtCore import (
        QByteArray,
        QDate as QDate,
        QDateTime,
        QObject,
        QSettings,
        pyqtSignal,
    )
    from qgis.PyQt.QtNetwork import QNetworkCookie, QNetworkReply, QNetworkRequest
    from qgis.PyQt.QtWidgets import QMainWindow as QMainWindow
except ModuleNotFoundError as exc:
    if exc.name == "qgis":
        raise unittest.SkipTest("Requires the QGIS 4 Python runtime") from exc
    raise

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _PROFILE.name)
APP = QgsApplication.instance() or QgsApplication([], True)
APP.setOrganizationName("SimpleOverpassTests")
APP.setApplicationName("SimpleOverpassTests")
APP.initQgis()


def token_cookie(value=b"test-token", lifetime=3600):
    cookie = QNetworkCookie(b"_osm_totp_token", value)
    cookie.setDomain(".openstreetmap.org")
    cookie.setPath("/")
    cookie.setSecure(True)
    cookie.setExpirationDate(QDateTime.currentDateTimeUtc().addSecs(lifetime))
    return cookie


class FakeReply(QObject):
    finished = pyqtSignal()

    def __init__(self, request):
        super().__init__()
        self.request = request
        self.status = None
        self.body = b""
        self.headers = []
        self.network_error = QNetworkReply.NetworkError.NoError
        self.aborted = False

    def attribute(self, attribute):
        assert attribute == QNetworkRequest.Attribute.HttpStatusCodeAttribute
        return self.status

    def rawHeaderPairs(self):
        return self.headers

    def readAll(self):
        return QByteArray(self.body)

    def error(self):
        return self.network_error

    def errorString(self):
        return "Simulated network error" if self.network_error.value else "OK"

    def abort(self):
        self.aborted = True
        self.network_error = QNetworkReply.NetworkError.OperationCanceledError
        self.finished.emit()

    def complete(self, payload=None, status=200, body=None, cookies=(), error=None):
        self.status = status
        self.body = (
            body
            if body is not None
            else json.dumps(
                payload if payload is not None else {"elements": []}
            ).encode()
        )
        self.headers = [(b"Set-Cookie", cookie.toRawForm()) for cookie in cookies]
        if error is not None:
            self.network_error = error
        self.finished.emit()


class FakeNetwork:
    def __init__(self):
        self.gets = []
        self.posts = []

    def get(self, request):
        reply = FakeReply(request)
        self.gets.append(reply)
        return reply

    def post(self, request, body):
        reply = FakeReply(request)
        reply.post_body = body
        self.posts.append(reply)
        return reply


class QgisTestCase(unittest.TestCase):
    def setUp(self):
        QgsSettings().remove("SimpleOverpass")

    def tearDown(self):
        APP.processEvents()
