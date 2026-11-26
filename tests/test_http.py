"""Drive the browser's JSON protocol through the actual HTTP handler, without binding a port."""
import io
import json
import unittest
from http.client import HTTPResponse
from types import SimpleNamespace
from unittest.mock import patch

from app import Handler
from paktwerk.scenarios import Boxes
from paktwerk.store import Store
from tests.support import scripted, turn


class Request:
    def __init__(self, raw):
        self.input = io.BytesIO(raw)
        self.output = io.BytesIO()

    def makefile(self, *args, **kwargs):
        return self.input

    def sendall(self, data):
        self.output.write(data)


class BrowserProtocol(unittest.TestCase):
    def setUp(self):
        agents, _ = scripted(buyer=[turn("accept", "Wir empfehlen dieses Paket.")],
                             seller=[turn("offer", "", {**Boxes.request, "price": 31000})])
        self.store = Store(delay=0, agents=agents)
        self.addCleanup(self.store.close)

    def request(self, method, path, data=None, token=None):
        body = json.dumps(data).encode() if data is not None else b""
        headers = ["Host: localhost", "Content-Type: application/json", f"Content-Length: {len(body)}"]
        if token:
            headers.append("Authorization: Bearer " + token)
        head = "\r\n".join([f"{method} {path} HTTP/1.0", *headers, "", ""])
        socket = Request(head.encode() + body)
        with patch.object(Handler, "log_request"):
            Handler(socket, ("127.0.0.1", 0), SimpleNamespace(store=self.store))
        response = HTTPResponse(Request(socket.output.getvalue()))
        response.begin()
        content = response.read()
        return response.status, json.loads(content) if response.headers.get_content_type() == "application/json" else content

    def test_two_browser_credentials_can_complete_only_their_own_actions(self):
        status, creator = self.request("POST", "/api/rooms", {"demo": True})
        self.assertEqual(status, 200)
        path, a = "/api/rooms/" + creator["room"], creator["token"]
        self.assertEqual(self.request("GET", path)[0], 403)
        invite = self.request("POST", path + "/invite", {}, a)[1]
        b = self.request("POST", path + "/join", invite)[1]["token"]
        self.assertEqual(self.request("POST", path + "/join", invite)[0], 403)
        profile = self.request("GET", path + "/template?profile=flexibel", token=b)[1]
        self.assertNotIn("limits", profile)
        self.assertEqual(self.request("POST", path + "/action", {"action": "mode", "epoch": 0,
                         "mode": "agent", "mandate": profile}, b)[0], 200)
        for _ in range(2):  # The supplier's agent offers, then the buyer's agent recommends it.
            self.store.prepare()
            self.store.dispatch()
        for side, credential in (("A", a), ("B", b)):
            _, view = self.request("GET", path, token=credential)
            self.assertEqual(view["me"]["side"], side)
            self.assertEqual(view["room"]["status"], "review")
            self.assertEqual(view["room"]["offers"][-1]["terms"]["price"], 31000)
            approval = {"action": "approve", "version": 2}
            self.assertEqual(self.request("POST", path + "/action", approval, credential)[0], 200)
        _, result = self.request("GET", path, token=b)
        self.assertEqual(result["room"]["agreement"]["version"], 2)
        self.assertEqual(result["room"]["approvals"], {"A": 2, "B": 2})

    def test_entry_point_assets_and_private_files(self):
        self.assertIn(b'lang="de"', self.request("GET", "/")[1])
        for asset in ("/app.js", "/styles.css", "/assets/versandboxen.webp"):
            self.assertEqual(self.request("GET", asset)[0], 200)
        for private in ("/.paktwerk/rooms.sqlite3", "/paktwerk/templates.py"):
            self.assertEqual(self.request("GET", private)[0], 404)
