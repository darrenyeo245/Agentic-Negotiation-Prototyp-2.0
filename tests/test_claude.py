"""Two Claude agents, one per company, driven by scripted clients instead of the network."""
import json
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

from paktwerk.claude import MODEL, ClaudeAgents
from paktwerk.domain import context
from paktwerk.scenarios import Boxes
from paktwerk.store import Store
from paktwerk.templates import mandate_template


def turn(action, message="", terms=None, final=False, end=None, note=""):
    return {"action": action, "message": message, "terms": terms, "final": final, "endReason": end, "privateNote": note}


class Client:
    """Stands in for one company's own Anthropic client and records everything that company's agent is shown."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.requests.append(request)
        reply = self.replies.pop(0)
        reply = reply() if callable(reply) else reply
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="thinking", thinking=""),
                                                                SimpleNamespace(type="text", text=json.dumps(reply))])

    def seen(self):
        return json.dumps([[r["system"], r["messages"]] for r in self.requests], default=str, ensure_ascii=False)


class ClaudeNegotiation(unittest.TestCase):
    def setUp(self):
        self.now = 1_800_000_000

    def start(self, buyer=(), seller=(), mandate=None, join=True):
        self.clients = {"A": Client(*buyer), "B": Client(*seller)}
        self.agents = ClaudeAgents(clients=self.clients)
        self.db = Store(delay=2, agents=self.agents)
        self.addCleanup(self.db.close)
        created = self.db.create({"scenario": "boxes", "demo": True, **({"mandate": mandate} if mandate else {})}, self.now)
        self.room, self.a = created["room"], created["token"]
        if join:
            self.join()

    def join(self):
        invite = self.db.invite(self.room, self.a, self.now)["invite"]
        self.b = self.db.join(self.room, invite, self.now)["token"]

    def view(self, token=None):
        return self.db.read(self.room, token or self.a, self.now)

    def act(self, token, action, **data):
        v = self.view(token)
        base = {"action": action, "epoch": v["room"]["epochs"][v["me"]["side"]], "version": len(v["room"]["offers"])}
        return self.db.act(self.room, token, {**base, **data}, self.now)

    def tick(self):
        self.now += 3
        self.db.prepare(self.now)
        self.db.dispatch(self.now)

    def test_two_separate_agents_negotiate_with_only_their_own_mandate(self):
        buyer, seller = mandate_template(Boxes, "A"), mandate_template(Boxes, "B")
        buyer.update(goal="GEHEIMZIEL-A", batnaValue=33017)
        buyer["limits"]["price"] = 31973
        seller.update(goal="GEHEIMZIEL-B")
        seller["options"][1].update(cost=28437, floor=30111)
        self.start(
            buyer=[turn("offer", "Wir benötigen 40 Stück binnen fünf Werktagen.", {**Boxes.request, "price": 30500},
                        note="NOTIZ-A: höchstens noch eine Stufe"),
                   turn("accept", "Dieses Paket empfehlen wir zur Freigabe.", note="NOTIZ-A: empfohlen")],
            seller=[turn("offer", "Die frühe Teillieferung können wir einplanen.", {**Boxes.request, "price": 31000},
                         note="NOTIZ-B")],
            mandate=buyer)
        self.tick()
        self.act(self.b, "mode", mode="agent", mandate=seller)
        self.tick()
        self.tick()
        r = self.view()["room"]
        self.assertEqual(r["status"], "review")
        self.assertEqual(r["offers"][-1]["terms"], {**Boxes.request, "price": 31000})
        self.assertEqual([o["side"] for o in r["offers"]], ["B", "A", "B"])
        self.assertEqual(r["events"][-1]["note"], "Dieses Paket empfehlen wir zur Freigabe.")

        a, b = self.clients["A"], self.clients["B"]
        self.assertEqual((len(a.requests), len(b.requests)), (2, 1))
        self.assertIn("GEHEIMZIEL-A", a.requests[0]["system"])
        self.assertIn("GEHEIMZIEL-B", b.requests[0]["system"])
        for word in ("GEHEIMZIEL-B", "28437", "284,37", "30111", "301,11", "NOTIZ-B"):
            self.assertNotIn(word, a.seen())
        for word in ("GEHEIMZIEL-A", "31973", "319,73", "33017", "330,17", "NOTIZ-A"):
            self.assertNotIn(word, b.seen())
        self.assertIn("NOTIZ-A", a.requests[1]["messages"][0]["content"])
        self.assertEqual(self.view()["me"]["agentNote"], "NOTIZ-A: empfohlen")
        self.assertNotIn("NOTIZ-A", json.dumps(self.view(self.b)))

        request = a.requests[0]
        self.assertEqual(request["model"], MODEL)
        self.assertEqual(request["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(request["fallbacks"], "default")
        own = context(Boxes, "B", seller, r, self.now)
        with self.assertRaises(ValueError):
            self.agents.negotiators["A"].decide(own, "")

        self.act(self.a, "approve")
        self.act(self.b, "approve")
        self.assertEqual(self.view()["room"]["agreement"]["version"], 3)

    def test_inadmissible_offer_goes_back_to_its_agent_with_the_reason(self):
        self.start(buyer=[turn("offer", "", {**Boxes.request, "price": 32500}),
                          turn("offer", "Neuer Vorschlag.", {**Boxes.request, "price": 30500})])
        self.tick()
        retry = self.clients["A"].requests[1]["messages"]
        self.assertEqual([m["role"] for m in retry], ["user", "assistant", "user"])
        self.assertIn("Gesamtpreis liegt außerhalb Ihrer harten Grenze", retry[-1]["content"])
        v = self.view()
        self.assertEqual(v["room"]["offers"][-1]["terms"]["price"], 30500)
        self.assertEqual(v["me"]["blocked"], 0)
        self.assertNotIn("32500", json.dumps(v["room"]))

    def test_agent_without_admissible_turn_returns_representation(self):
        wrong = turn("accept")  # Accepting the seller's 290 € package violates the buyer's delivery limits.
        self.start(buyer=[wrong, wrong, wrong])
        self.tick()
        r = self.view()["room"]
        self.assertEqual((r["modes"]["A"], r["epochs"]["A"], len(r["offers"])), ("human", 1, 1))
        self.assertEqual((r["events"][-1]["kind"], r["events"][-1]["actor"]), ("mode", "system"))
        self.assertIn("Nach 3 Versuchen", r["events"][-1]["text"])
        self.assertIsNone(self.view()["preparing"])

    def test_unreachable_api_returns_representation(self):
        self.start(buyer=[ConnectionError("offline")])
        with self.assertLogs("paktwerk.store", "ERROR"):
            self.tick()
        r = self.view()["room"]
        self.assertEqual((r["modes"]["A"], len(r["offers"])), ("human", 1))
        self.act(self.a, "message", text="Wir melden uns persönlich.")
        self.assertEqual(self.view()["room"]["events"][-1]["actor"], "human")

    def test_takeover_while_the_agent_thinks_discards_its_answer(self):
        def takeover():
            self.act(self.a, "mode", mode="human")
            return turn("offer", "Zu spät.", {**Boxes.request, "price": 30500}, note="VERWORFEN")
        self.start(buyer=[takeover])
        self.tick()
        v = self.view()
        self.assertEqual((v["room"]["modes"]["A"], len(v["room"]["offers"]), v["preparing"]), ("human", 1, None))
        self.assertNotIn("Zu spät.", json.dumps(v["room"]))
        self.assertEqual(v["me"]["agentNote"], "")

    def test_guest_joining_while_the_agent_thinks_keeps_its_answer(self):
        def joined_meanwhile():
            self.join()
            return turn("offer", "", {**Boxes.request, "price": 30500})
        self.start(buyer=[joined_meanwhile], join=False)
        self.tick()
        self.tick()
        r = self.view()["room"]
        self.assertEqual(len(self.clients["A"].requests), 1)
        self.assertEqual((r["offers"][-1]["side"], r["offers"][-1]["terms"]["price"]), ("A", 30500))

    def test_messages_and_a_reasoned_exit(self):
        self.start(buyer=[turn("message", "Können Sie einen Teil früher liefern?"),
                          turn("end", "Wir beschaffen anderweitig.", end="alternative")])
        self.tick()
        r = self.view()["room"]
        self.assertEqual((r["events"][-1]["kind"], r["events"][-1]["actor"], r["turn"]), ("message", "agent", "B"))
        self.act(self.b, "message", text="Leider nein.")
        self.tick()
        r = self.view()["room"]
        self.assertEqual((r["status"], r["stopReason"]), ("ended", "alternative"))
        self.assertEqual(r["events"][-1]["note"], "Wir beschaffen anderweitig.")


class EnvFile(unittest.TestCase):
    def write(self, tmp, text):
        with open(tmp + "/.env", "w", encoding="utf-8") as f:
            f.write(text)
        return tmp + "/.env"

    def test_env_file_wins_over_a_stale_shell_variable(self):
        from unittest.mock import patch
        from paktwerk.claude import api_key
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-..."}):
            path = self.write(tmp, '# Kommentar\nexport ANTHROPIC_API_KEY="sk-ant-api03-echt" # Notiz\n')
            self.assertEqual(api_key(path), "sk-ant-api03-echt")

    def test_shell_applies_without_env_file_and_placeholders_are_refused(self):
        from unittest.mock import patch
        from paktwerk.claude import api_key
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-api03-shell"}):
                self.assertEqual(api_key(tmp + "/fehlt"), "sk-ant-api03-shell")
            with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(RuntimeError, "Platzhalter"):
                api_key(self.write(tmp, "ANTHROPIC_API_KEY=sk-ant-...\n"))


class Migration(unittest.TestCase):
    def test_queued_jobs_of_a_rule_only_database_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + "/rooms.sqlite3"
            old = sqlite3.connect(path)
            old.executescript("""
                CREATE TABLE rooms(id TEXT PRIMARY KEY, public TEXT NOT NULL, active_until INTEGER, invite_hash TEXT);
                CREATE TABLE jobs(room TEXT PRIMARY KEY REFERENCES rooms(id), side TEXT NOT NULL,
                    epoch INTEGER, revision INTEGER, version INTEGER, due INTEGER, action TEXT NOT NULL);
                INSERT INTO rooms VALUES('ABCDEF0123', '{}', NULL, NULL);
                INSERT INTO jobs VALUES('ABCDEF0123', 'A', 0, 1, 1, 5, '{"kind":"end","reason":"no_fit"}');
            """)
            old.close()
            db = Store(path)
            self.addCleanup(db.close)
            columns = {c["name"]: c["notnull"] for c in db.db.execute("PRAGMA table_info(jobs)")}
            self.assertEqual(columns["action"], 0)
            self.assertEqual(db.db.execute("SELECT action FROM jobs").fetchone()[0], '{"kind":"end","reason":"no_fit"}')


if __name__ == "__main__":
    unittest.main()
