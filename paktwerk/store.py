"""Transactional rooms and a durable outbox. All writes use the same dispatch gate."""
import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager

from .domain import AgentFailure, Problem, assessment, context, integer, mandate, package, plain, require_fit
from .scenarios import SCENARIOS, schema, without_price
from .templates import mandate_template

ENDINGS = {
    "no_fit": "Innerhalb der Verhandlungsfrist lag kein für uns tragfähiges Angebot vor. Die verfügbaren Konditionen sind ausgeschöpft.",
    "capacity": "Für die bereits bestätigten Eckdaten können wir kein leistbares Gesamtpaket anbieten.",
    "alternative": "Für uns ist die Alternative bei Nichteinigung wirtschaftlich günstiger.",
    "deadline": "Die vereinbarte Verhandlungsfrist ist abgelaufen. Es liegt keine beidseitig freigegebene Einigung vor.",
    "round_limit": "Die vereinbarte Höchstzahl an Verhandlungsschritten ist erreicht.",
    "validation": "Die vorbereitete Antwort konnte nicht als zulässiges Paket versendet werden.",
}
LIVE = ("active", "review")
# A job without an action waits for the AI agent to decide outside the write lock.
JOBS = """CREATE TABLE IF NOT EXISTS jobs(room TEXT PRIMARY KEY REFERENCES rooms(id), side TEXT NOT NULL,
    epoch INTEGER, revision INTEGER, version INTEGER, due INTEGER, action TEXT)"""
log = logging.getLogger(__name__)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def timestamp(fixed):
    return int(time.time()) if fixed is None else fixed


def other(side):
    return "B" if side == "A" else "A"


def event(p, now, kind, side, actor, text, **data):
    p["events"].append({"seq": len(p["events"]) + 1, "at": now, "kind": kind, "side": side,
                        "actor": actor, "text": text, **data})


def end(p, now, reason, side=None, note=None):
    p["status"], p["stopReason"] = "ended", reason
    event(p, now, "end", side, "agent" if side else "system", ENDINGS[reason], **remark(note))


def remark(note):
    """An agent's free text that accompanies a binding, platform-worded action."""
    return {"note": note} if note else {}


def record_offer(s, p, now, side, actor, terms, final=False, note=None):
    version = len(p["offers"]) + 1
    p["offers"].append({"version": version, "side": side, "actor": actor, "at": now, "terms": terms, "final": final})
    p.update(status="active", approvals={}, recommendation=None, turn=other(side))
    text = s.describe(terms)
    if final:
        text += " Dies ist unser abschließendes Paket."
    event(p, now, "offer", side, actor, text, version=version, **remark(note))
    p["turns"] += 1


class Store:
    def __init__(self, path=":memory:", delay=4, *, agents):
        self.lock = threading.RLock()
        self.delay = delay
        # The AI agents (ClaudeAgents) decide in think(), outside the write lock. Every answer passes the
        # same dispatch gate as a human action, and a human can take over at any time.
        self.agents = agents
        self.thinking = set()
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(f"""
            PRAGMA foreign_keys=ON;
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY, public TEXT NOT NULL, active_until INTEGER, invite_hash TEXT);
            CREATE TABLE IF NOT EXISTS members(room TEXT REFERENCES rooms(id), side TEXT, credential TEXT UNIQUE,
                mandate TEXT, blocked INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(room,side));
            CREATE TABLE IF NOT EXISTS notes(room TEXT REFERENCES rooms(id), side TEXT, text TEXT NOT NULL,
                PRIMARY KEY(room,side));
            {JOBS};
            CREATE INDEX IF NOT EXISTS room_deadlines ON rooms(active_until);
        """)
        if any(c["name"] == "action" and c["notnull"] for c in self.db.execute("PRAGMA table_info(jobs)")):
            # Older databases require an action for every queued job.
            self.db.executescript(f"""
                BEGIN IMMEDIATE;
                ALTER TABLE jobs RENAME TO jobs_v1;
                {JOBS};
                INSERT INTO jobs SELECT * FROM jobs_v1;
                DROP TABLE jobs_v1;
                COMMIT;
            """)
        self.db.execute("CREATE INDEX IF NOT EXISTS due_jobs ON jobs(due)")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self.db.rollback()
                raise
            else:
                self.db.commit()

    def save(self, p):
        p["revision"] += 1
        self.db.execute("UPDATE rooms SET public=?, active_until=? WHERE id=?",
                        (encode(p), p["deadline"] if p["status"] in LIVE else None, p["id"]))

    def load(self, room):
        row = self.db.execute("SELECT public FROM rooms WHERE id=?", (room,)).fetchone()
        if row is None:
            raise Problem("Raum oder Zugang ist ungültig.", 403)
        return json.loads(row["public"])

    def member(self, room, token):
        if not isinstance(token, str) or len(token) > 256:
            raise Problem("Raum oder Zugang ist ungültig.", 403)
        row = self.db.execute("SELECT * FROM members WHERE room=? AND credential=?", (room, digest(token))).fetchone()
        if row is None:
            raise Problem("Raum oder Zugang ist ungültig.", 403)
        return row

    def own(self, room, side):
        row = self.db.execute("SELECT mandate FROM members WHERE room=? AND side=?", (room, side)).fetchone()
        return json.loads(row["mandate"]) if row and row["mandate"] else None

    def note(self, room, side):
        """The private working note of one side's agent. It never enters the public room."""
        row = self.db.execute("SELECT text FROM notes WHERE room=? AND side=?", (room, side)).fetchone()
        return row["text"] if row else ""

    def create(self, data, now=None):
        key = data.get("scenario", "boxes")
        s = SCENARIOS.get(key) if isinstance(key, str) else None
        if s is None:
            raise Problem("Unbekanntes Szenario.")
        demo = data.get("demo") is True
        names = data.get("companies", s.companies)
        if not isinstance(names, dict):
            raise Problem("Bitte beide Firmen angeben.")
        names = {k: plain(names.get(k), "einen Firmennamen", 60) for k in ("A", "B")}
        subject = plain(data.get("subject", s.title), "einen Verhandlungsgegenstand", 100)
        minutes = integer(data.get("minutes", 60), 1, 10080, "Frist in Minuten")
        max_turns = integer(data.get("maxTurns", 18), 3, 100, "Verhandlungsschritte")
        m = mandate(s, "A", data.get("mandate", mandate_template(s, "A")), 1)
        mode = data.get("mode", "agent")
        if mode not in ("human", "agent"):
            raise Problem("Unbekannte Vertretung.")
        room, token = secrets.token_hex(5).upper(), secrets.token_urlsafe(32)
        now = timestamp(now)
        req = without_price(m["limits"]) if m["shareTerms"] else {}
        p = {"id": room, "scenario": s.key, "scenarioVersion": s.version, "demo": demo, "subject": subject,
             "companies": names, "created": now, "deadline": now + minutes * 60, "maxTurns": max_turns,
             "turns": 0, "turn": "B", "status": "active", "revision": 0, "offers": [], "events": [],
             "modes": {"A": mode, "B": "human"}, "epochs": {"A": 0, "B": 0}, "joined": {"A": True, "B": False},
             "request": req, "approvals": {}, "agreement": None,
             "recommendation": None, "stopReason": None}
        event(p, now, "request", "A", mode, s.request_text(req) if req else f"Bitte senden Sie ein vollständiges Angebot für „{subject}“.")
        with self.transaction():
            self.db.execute("INSERT INTO rooms(id,public,active_until) VALUES(?,?,?)", (room, encode(p), p["deadline"]))
            self.db.execute("INSERT INTO members(room,side,credential,mandate) VALUES(?,?,?,?)",
                            (room, "A", digest(token), encode(m)))
            self.db.execute("INSERT INTO members(room,side) VALUES(?,?)", (room, "B"))
            if demo:
                record_offer(s, p, now, "B", "human", package(s, s.opening))
            self.finish_write(p, now)
        return {"room": room, "side": "A", "token": token}

    def invite(self, room, token, now=None):
        with self.transaction():
            now = timestamp(now)
            actor = self.member(room, token)
            p = self.load(room)
            if actor["side"] != "A":
                raise Problem("Nur die einladende Firma kann einen Gastzugang erstellen.", 403)
            self.live(p, now)
            if p["joined"]["B"]:
                raise Problem("Der Gastzugang ist bereits einer Person zugeordnet.", 409)
            key = secrets.token_urlsafe(32)
            self.db.execute("UPDATE rooms SET invite_hash=? WHERE id=?", (digest(key), room))
        return {"invite": key}

    def join(self, room, key, now=None):
        if not isinstance(key, str) or len(key) > 256:
            raise Problem("Diese Einladung ist ungültig.", 403)
        token = secrets.token_urlsafe(32)
        with self.transaction():
            now = timestamp(now)
            result = self.db.execute("UPDATE rooms SET invite_hash=NULL WHERE id=? AND invite_hash=?",
                                     (room, digest(key)))
            if result.rowcount != 1:
                raise Problem("Diese Einladung wurde bereits eingelöst oder ersetzt.", 403)
            p = self.load(room)
            self.live(p, now)
            self.db.execute("UPDATE members SET credential=? WHERE room=? AND side='B'", (digest(token), room))
            p["joined"]["B"] = True
            event(p, now, "joined", "B", "system", "ist dem Raum als Gast beigetreten.")
            self.finish_write(p, now)
        return {"room": room, "side": "B", "token": token}

    @staticmethod
    def live(p, now):
        if now >= p["deadline"] or p["status"] not in LIVE:
            raise Problem("Diese Verhandlung ist beendet.", 409)

    def finish_write(self, p, now):
        self.db.execute("DELETE FROM jobs WHERE room=?", (p["id"],))
        if p["status"] == "active" and p["turns"] >= p["maxTurns"]:
            end(p, now, "round_limit")
        self.save(p)
        side = p["turn"]
        if p["status"] != "active" or p["modes"][side] != "agent" or not p["joined"][side]:
            return
        self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?)",
                        (p["id"], side, p["epochs"][side], p["revision"], len(p["offers"]), now + self.delay, None))

    def expire(self, p, now):
        if p["status"] in LIVE and now >= p["deadline"]:
            end(p, now, "deadline")
            self.finish_write(p, now)

    def read(self, room, token, now=None):
        with self.transaction():
            now = timestamp(now)
            person = self.member(room, token)
            p = self.load(room)
            self.expire(p, now)
            side, s = person["side"], SCENARIOS[p["scenario"]]
            m = json.loads(person["mandate"]) if person["mandate"] else None
            current = p["offers"][-1] if p["offers"] else None
            review = assessment(s, side, m, current["terms"]) if current else None
            job = self.db.execute("SELECT side FROM jobs WHERE room=?", (room,)).fetchone()
            return {"room": p, "schema": schema(s), "me": {"side": side, "mandate": m,
                    "assessment": review, "blocked": person["blocked"], "agentNote": self.note(room, side)},
                    "preparing": job["side"] if job else None}

    def template(self, room, token, profile):
        if profile not in ("flexibel", "eng"):
            raise Problem("Unbekanntes Mandatsprofil.")
        with self.transaction():
            person = self.member(room, token)
            return mandate_template(SCENARIOS[self.load(room)["scenario"]], person["side"], profile)

    def apply_agent(self, p, side, m, action, now):
        s, kind = SCENARIOS[p["scenario"]], action["kind"]
        if kind == "offer":
            terms = package(s, action["terms"])
            require_fit(s, side, m, terms)
            record_offer(s, p, now, side, "agent", terms, action["final"], action.get("note"))
        elif kind == "message":
            event(p, now, kind, side, "agent", plain(action["text"], "eine Nachricht", 2000))
            p["turn"], p["turns"] = other(side), p["turns"] + 1
        elif kind == "recommend":
            v = action["version"]
            if v != len(p["offers"]):
                raise Problem("Das Angebot wurde inzwischen geändert.", 409)
            require_fit(s, side, m, p["offers"][-1]["terms"])
            p.update(status="review", recommendation={"side": side, "version": v})
            event(p, now, kind, side, "agent", f"Ich empfehle Angebot V{v} zur persönlichen Freigabe.", version=v,
                  **remark(action.get("note")))
            p["turns"] += 1
        elif kind == "end":
            end(p, now, action["reason"], side, action.get("note"))
        else:
            raise Problem("Unbekannte Agentenentscheidung.")

    def dispatch(self, now=None):
        with self.transaction():
            checked_at = timestamp(now)
            for row in self.db.execute("SELECT id FROM rooms WHERE active_until<=?", (checked_at,)).fetchall():
                self.expire(self.load(row["id"]), checked_at)
            jobs = self.db.execute("SELECT * FROM jobs WHERE due<=? AND action IS NOT NULL ORDER BY due,room LIMIT 100",
                                   (checked_at,)).fetchall()
            for job in jobs:
                send_at = timestamp(now)
                room, side = job["room"], job["side"]
                p = self.load(room)
                self.expire(p, send_at)
                self.db.execute("DELETE FROM jobs WHERE room=?", (room,))
                # This check and the append below share the same SQLite write lock as takeover.
                if (p["status"] != "active" or p["modes"][side] != "agent" or p["epochs"][side] != job["epoch"]
                        or p["turn"] != side or p["revision"] != job["revision"] or len(p["offers"]) != job["version"]):
                    continue
                try:
                    self.apply_agent(p, side, self.own(room, side), json.loads(job["action"]), send_at)
                except Problem:
                    self.blocked(room, side)
                    end(p, send_at, "validation")
                self.finish_write(p, send_at)

    def claim(self):
        """Rooms whose agent still has to decide. Each room is handed to one thinker at a time."""
        with self.lock:
            rows = self.db.execute("SELECT room FROM jobs WHERE action IS NULL ORDER BY due").fetchall()
            rooms = [r["room"] for r in rows if r["room"] not in self.thinking]
            self.thinking.update(rooms)
        return rooms

    def think(self, room, now=None):
        """Let the agent decide without holding the write lock. Its answer is queued only if the turn still stands."""
        try:
            with self.transaction():
                job = self.db.execute("SELECT * FROM jobs WHERE room=? AND action IS NULL", (room,)).fetchone()
                if job is None:
                    return
                p, side = self.load(room), job["side"]
                ctx = context(SCENARIOS[p["scenario"]], side, self.own(room, side), p, timestamp(now))
                note = self.note(room, side)
            failure = None
            try:
                action, note = self.agents.decide(ctx, note)
            except AgentFailure as exc:
                failure = str(exc)
            except Exception:
                log.exception("Agent %s in Raum %s ist ausgefallen.", side, room)
                failure = "Der Agent ist ausgefallen. Einzelheiten stehen im Serverprotokoll."
            with self.transaction():
                send_at = timestamp(now)
                current = self.db.execute("SELECT * FROM jobs WHERE room=?", (room,)).fetchone()
                if (current is None or current["action"] is not None or current["side"] != side
                        or current["epoch"] != job["epoch"] or current["version"] != job["version"]):
                    return
                p = self.load(room)
                # Joins or the other firm's private edits rewrite the job but not what this agent saw or knows.
                if p["turns"] != ctx.shared["turns"] or self.own(room, side)["version"] != ctx.own["version"]:
                    return
                if failure:
                    self.hand_back(p, side, failure, send_at)
                    return
                self.db.execute("UPDATE jobs SET action=?, due=MAX(due, ?) WHERE room=?", (encode(action), send_at, room))
                self.db.execute("INSERT INTO notes(room,side,text) VALUES(?,?,?) "
                                "ON CONFLICT(room,side) DO UPDATE SET text=excluded.text", (room, side, note))
        finally:
            with self.lock:
                self.thinking.discard(room)

    def prepare(self, now=None):
        """Decide all waiting turns in the calling thread, for scripted runs with a logical clock."""
        for room in self.claim():
            self.think(room, now)

    def hand_back(self, p, side, reason, now):
        p["modes"][side] = "human"
        p["epochs"][side] += 1
        event(p, now, "mode", side, "system", f"vertritt sich wieder selbst. Der Agent konnte keinen Zug versenden: {reason}")
        self.finish_write(p, now)

    def blocked(self, room, side):
        self.db.execute("UPDATE members SET blocked=blocked+1 WHERE room=? AND side=?", (room, side))

    def act(self, room, token, data, now=None):
        try:
            with self.transaction():
                now = timestamp(now)
                person = self.member(room, token)
                side = person["side"]
                p = self.load(room)
                if (data.get("action") == "approve" and p["agreement"]
                        and p["agreement"]["version"] == data.get("version")):
                    return {"ok": True}
                self.live(p, now)
                if self.mutate(p, side, data, now):
                    self.finish_write(p, now)
        except Problem as exc:
            if exc.status == 422:
                with self.transaction():
                    self.blocked(room, side)
            raise
        return {"ok": True}

    def mutate(self, p, side, data, now):
        room, s = p["id"], SCENARIOS[p["scenario"]]
        m = self.own(room, side)
        action, version = data.get("action"), len(p["offers"])
        if action in ("message", "offer", "mode") and data.get("epoch") != p["epochs"][side]:
            raise Problem("Die aktive Vertretung hat sich geändert. Bitte erneut prüfen.", 409)
        if action in ("message", "offer") and p["modes"][side] != "human":
            raise Problem("Bitte zuerst selbst übernehmen.", 409)
        if action in ("offer", "approve") and (type(data.get("version")) is not int or data["version"] != version):
            raise Problem("Eine neuere Angebotsversion liegt vor. Bitte erneut prüfen.", 409)
        if action == "mode":
            mode = data.get("mode")
            if mode not in ("human", "agent"):
                raise Problem("Unbekannte Vertretung.")
            if p["modes"][side] == mode:
                return False
            if mode == "agent" and m is None:
                m = mandate(s, side, data.get("mandate"), 1)
                self.db.execute("UPDATE members SET mandate=? WHERE room=? AND side=?", (encode(m), room, side))
            p["modes"][side] = mode
            p["epochs"][side] += 1
            if mode == "agent" and p["status"] == "active":
                p["turn"] = side
            text = "hat an den eigenen Agenten übergeben." if mode == "agent" else "hat die Verhandlung selbst übernommen."
            event(p, now, "mode", side, "human", text)
        elif action == "mandate":
            current = m["version"] if m else 0
            if current != data.get("mandateVersion"):
                raise Problem("Ihr Mandat wurde inzwischen geändert.", 409)
            updated = mandate(s, side, data.get("mandate"), current + 1)
            self.db.execute("UPDATE members SET mandate=? WHERE room=? AND side=?", (encode(updated), room, side))
            p["approvals"].pop(side, None)
            rec = p["recommendation"]
            if rec and (rec["side"] == side or not assessment(s, side, updated, p["offers"][-1]["terms"])["valid"]):
                p.update(status="active", turn=side, recommendation=None)
        elif action == "message":
            text = plain(data.get("text"), "eine Nachricht", 2000)
            event(p, now, "message", side, "human", text)
            p.update(status="active", recommendation=None)
            p["turn"], p["turns"] = other(side), p["turns"] + 1
        elif action == "offer":
            terms = package(s, data.get("terms"))
            require_fit(s, side, m, terms)
            record_offer(s, p, now, side, "human", terms)
        elif action == "approve":
            if not version:
                raise Problem("Es liegt noch kein Angebot vor.", 409)
            require_fit(s, side, m, p["offers"][-1]["terms"])
            if p["approvals"].get(side) == version:
                return False
            p["approvals"][side] = version
            event(p, now, "approve", side, "human", f"hat Angebot V{version} persönlich freigegeben.", version=version)
            if all(p["approvals"].get(k) == version for k in ("A", "B")):
                p.update(status="agreed", agreement={"version": version, "at": now, "terms": p["offers"][-1]["terms"]})
                event(p, now, "agreement", None, "system", f"Beide Firmen haben V{version} freigegeben. Der simulierte Abschluss ist dokumentiert.")
        else:
            raise Problem("Unbekannte Aktion.")
        return True
