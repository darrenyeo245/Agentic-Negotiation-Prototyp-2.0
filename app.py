#!/usr/bin/env python3
"""Paktwerk's local HTTP server. Claude agents need the anthropic package; the rule-based agents only the standard library."""
import argparse
import json
import logging
import mimetypes
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from paktwerk.claude import EFFORT, MODEL, ClaudeAgents
from paktwerk.domain import Problem
from paktwerk.env import load_env
from paktwerk.scenarios import SCENARIOS, STRATEGIES, schema
from paktwerk.store import Store
from paktwerk.templates import mandate_template
from research import benchmark

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "web"
ROOM_ROUTE = re.compile(r"/api/rooms/([0-9A-F]{10})(?:/(invite|join|action|template))?")
ASSETS = {"/" + str(p.relative_to(PUBLIC)): p for p in PUBLIC.rglob("*") if p.is_file()}


class Handler(BaseHTTPRequestHandler):
    server_version = "Paktwerk/1.0"

    def send_data(self, status, data, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, obj):
        self.send_data(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def body(self):
        if self.headers.get_content_type() != "application/json":
            raise Problem("JSON-Daten erwartet.", 415)
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise Problem("Ungültige Anfragegröße.")
        if not 0 <= size <= 64_000:
            raise Problem("Die Anfrage ist zu groß.", 413)
        try:
            data = json.loads(self.rfile.read(size))
        except (UnicodeError, ValueError, RecursionError):
            raise Problem("Ungültige JSON-Daten.")
        if not isinstance(data, dict):
            raise Problem("Ein JSON-Objekt wird erwartet.")
        return data

    def route(self, method):
        u = urlsplit(self.path)
        path, q = u.path, parse_qs(u.query)
        db = self.server.store
        data = self.body() if method == "POST" else {}
        if method == "GET" and not path.startswith("/api/"):
            file = ASSETS.get(path)
            if path == "/" or re.fullmatch(r"/r/[0-9A-F]{10}/?", path):
                file = PUBLIC / "index.html"
            if not file:
                raise Problem("Seite nicht gefunden.", 404)
            self.send_data(200, file.read_bytes(), mimetypes.guess_type(file)[0] or "application/octet-stream")
            return
        if path == "/api/setup" and method == "GET":
            s = SCENARIOS.get(q.get("scenario", ["boxes"])[0])
            if not s:
                raise Problem("Unbekanntes Szenario.")
            result = {"schema": schema(s), "mandate": mandate_template(s, "A"), "strategies": STRATEGIES}
        elif path == "/api/rooms" and method == "POST":
            result = db.create(data)
        elif path == "/api/research" and method == "POST":
            try:
                result = benchmark(data.get("scenario", "all"), data.get("repeats", 1))
            except (TypeError, ValueError) as e:
                raise Problem(str(e))
        else:
            match = ROOM_ROUTE.fullmatch(path)
            if not match:
                raise Problem("Seite nicht gefunden.", 404)
            room, action = match.groups()
            auth = self.headers.get("Authorization", "")
            token = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
            if method == "GET" and action is None:
                result = db.read(room, token)
            elif method == "GET" and action == "template":
                result = db.template(room, token, q.get("profile", ["flexibel"])[0])
            elif method == "POST" and action == "invite":
                result = db.invite(room, token)
            elif method == "POST" and action == "join":
                result = db.join(room, data.get("invite"))
            elif method == "POST" and action == "action":
                result = db.act(room, token, data)
            else:
                raise Problem("Methode nicht verfügbar.", 405)
        self.send_json(200, result)

    def handle_method(self):
        try:
            self.route(self.command)
        except Problem as exc:
            self.send_json(exc.status, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = do_POST = handle_method

    def log_request(self, code="-", size="-"):
        # Routine polling should not flood the demo console.
        if isinstance(code, int) and code >= 400:
            self.log_message("%s %s (%s)", self.command, urlsplit(self.path).path, code)


def serve(host, port, path, agents=None, delay=4):
    db = Store(path, delay=delay, agents=agents)
    http = ThreadingHTTPServer((host, port), Handler)
    http.store = db
    stop = threading.Event()
    # Model calls take seconds. They run here, outside the write lock, so rooms stay responsive.
    thinkers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-think")

    def work():
        while not stop.wait(0.35):
            db.dispatch()
            for room in db.claim():
                thinkers.submit(db.think, room)

    worker = threading.Thread(target=work, name="agent-outbox", daemon=True)
    worker.start()
    engine = f"Claude-Agenten ({agents.label})" if agents else "regelbasierte Agenten"
    print(f"Paktwerk läuft auf http://{host}:{http.server_port} · {engine} · Datenbank {path}", flush=True)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.join()
        thinkers.shutdown(wait=False, cancel_futures=True)
        http.server_close()
        db.close()


def claude_agents(model, effort):
    try:
        agents = ClaudeAgents(model=model, effort=effort)
    except RuntimeError as exc:
        sys.exit(f"{exc}\nAlternativ mit --agents regeln ohne Claude starten.")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or (Path.home() / ".config" / "anthropic").exists()):
        print("Hinweis: Keine Zugangsdaten für die Claude API gefunden. Bitte ANTHROPIC_API_KEY in .env "
              "oder als Umgebungsvariable setzen. "
              "Ohne Zugang geben die Agenten die Vertretung an ihre Firmen zurück.", file=sys.stderr, flush=True)
    return agents


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Paktwerk – bilaterale Verhandlungsplattform starten")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=ROOT / ".paktwerk" / "rooms.sqlite3")
    parser.add_argument("--agents", choices=("claude", "regeln"), default="claude",
                        help="Claude-Agenten über die Claude API (Standard) oder die regelbasierten Agenten")
    parser.add_argument("--model", default=MODEL, help=f"Claude-Modell beider Agenten (Standard {MODEL})")
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default=EFFORT,
                        help=f"Denkaufwand je Verhandlungszug (Standard {EFFORT})")
    args = parser.parse_args()
    load_env(ROOT / ".env")
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s: %(message)s")
    logging.getLogger("paktwerk").setLevel(logging.INFO)
    os.umask(0o077)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    serve(args.host, args.port, args.db, claude_agents(args.model, args.effort) if args.agents == "claude" else None)
