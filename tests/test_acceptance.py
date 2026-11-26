"""The platform's guarantees with two AI agents whose API answers are scripted."""
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from paktwerk.domain import Problem, assessment, context
from paktwerk.scenarios import Boxes, Service
from paktwerk.store import Store
from paktwerk.templates import mandate_template
from tests.support import scripted, turn

REQUESTED = {**Boxes.request, "price": 31000}


class NegotiationCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1_800_000_000
        self.db = None

    def tearDown(self):
        if self.db:
            self.db.close()

    def start(self, buyer=(), seller=(), **options):
        self.agents, self.clients = scripted(buyer, seller)
        self.db = Store(self.tmp.name + "/rooms.sqlite", delay=2, agents=self.agents)
        self.open_room(**options)

    def open_room(self, **options):
        a = self.db.create({"scenario": "boxes", "demo": True, **options}, self.now)
        self.room, self.a = a["room"], a["token"]
        invite = self.db.invite(self.room, self.a, self.now)["invite"]
        self.b = self.db.join(self.room, invite, self.now)["token"]

    def view(self, token=None):
        return self.db.read(self.room, token or self.a, self.now)

    def act(self, token, action, **data):
        v = self.view(token)
        base = {"action": action, "epoch": v["room"]["epochs"][v["me"]["side"]],
                "version": len(v["room"]["offers"])}
        return self.db.act(self.room, token, {**base, **data}, self.now)

    def tick(self):
        self.now += 3
        self.db.prepare(self.now)
        self.db.dispatch(self.now)

    def handover(self, profile="flexibel", s=Boxes):
        """The supplier hands over to its agent. Both agents then negotiate until the room waits for people."""
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(s, "B", profile))
        for _ in range(12):
            v = self.view()
            if v["room"]["status"] != "active" or not v["preparing"]:
                break
            self.tick()
        return self.view()["room"]

    def test_two_agents_complete_package_and_two_people_approve(self):
        self.start(buyer=[turn("accept", "Dieses Paket empfehlen wir zur Freigabe.")],
                   seller=[turn("offer", "Die Teillieferung können wir einplanen.", REQUESTED)])
        r = self.handover()
        self.assertEqual(r["status"], "review")
        self.assertEqual(r["offers"][-1]["terms"], REQUESTED)
        self.assertFalse(r["approvals"])
        for token in (self.a, self.b):
            self.assertTrue(self.view(token)["me"]["assessment"]["valid"])
        self.act(self.a, "approve")
        self.assertIsNone(self.view()["room"]["agreement"])
        self.act(self.b, "approve")
        self.assertEqual(self.view()["room"]["agreement"]["version"], 2)

    def test_person_negotiates_against_the_other_firms_agent(self):
        self.start(buyer=[turn("message", "Können Sie Menge und Termin der Teillieferung nennen?"),
                          turn("accept", "Dieses Paket passt für uns.")])
        self.act(self.b, "message", text="Wir können einen Teil früher liefern")
        self.tick()
        last = self.view()["room"]["events"][-1]
        self.assertEqual((last["kind"], last["side"], last["actor"]), ("message", "A", "agent"))
        self.act(self.b, "offer", terms={**Boxes.request, "price": 30850})
        self.tick()
        r = self.view()["room"]
        self.assertEqual((r["status"], r["recommendation"]["side"]), ("review", "A"))
        self.act(self.b, "approve")
        self.act(self.a, "approve")
        self.assertEqual(self.view()["room"]["status"], "agreed")

    def test_handover_keeps_history_deadline_and_offers(self):
        self.start(buyer=[turn("message", "Welchen Gesamtpreis bieten Sie dafür an?"), turn("accept")],
                   seller=[turn("offer", "", REQUESTED)])
        self.act(self.b, "message", text="Wir können 40 Stück binnen fünf Werktagen liefern.")
        self.tick()
        before = self.view()["room"]
        after = self.handover()
        self.assertEqual(after["events"][:len(before["events"])], before["events"])
        self.assertEqual(after["offers"][0], before["offers"][0])
        self.assertEqual(after["deadline"], before["deadline"])
        self.assertEqual((after["status"], after["offers"][-1]["terms"]), ("review", REQUESTED))

    def test_takeover_discards_a_prepared_reply_even_across_restart(self):
        self.start(buyer=[turn("message", "Wir warten auf Ihr Paket.")],
                   seller=[turn("offer", "VORBEREITET", REQUESTED)])
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.db.prepare(self.now)  # The answer is ready but not yet due.
        self.assertEqual(self.view()["preparing"], "B")
        self.db.close()
        self.db = Store(self.tmp.name + "/rooms.sqlite", delay=2, agents=self.agents)
        with self.assertRaises(Problem):
            self.act(self.b, "message", text="Ein zweiter Absender")
        self.act(self.b, "mode", mode="human")
        self.act(self.b, "message", text="Ich prüfe den Aufpreis persönlich.")
        self.tick()
        r = self.view()["room"]
        self.assertFalse([e for e in r["events"] if e["side"] == "B" and e["actor"] == "agent"])
        self.assertEqual(sum(e["text"] == "Ich prüfe den Aufpreis persönlich." for e in r["events"]), 1)
        self.assertEqual(len(r["offers"]), 1)
        self.assertNotIn("VORBEREITET", json.dumps(r))

    def test_unsolvable_case_ends_with_a_documented_reason(self):
        self.start(buyer=[turn("accept"), turn("end", "Wir beschaffen anderweitig.", end="no_fit")],
                   seller=[turn("offer", "Früher geht nur mit Zusatzschicht.", {**Boxes.request, "price": 33500},
                                final=True)])
        r = self.handover("eng")
        self.assertEqual((r["status"], r["stopReason"]), ("ended", "no_fit"))
        self.assertIsNone(r["agreement"])
        self.assertIn("Verhandlungsfrist", r["events"][-1]["text"])
        # The platform refused the buyer agent's recommendation above its budget and told it why.
        self.assertIn("außerhalb Ihrer harten Grenze", self.clients["A"].requests[1]["messages"][-1]["content"])

    def test_private_context_and_versioned_idempotent_approval(self):
        self.start(buyer=[turn("accept")], seller=[turn("offer", "", REQUESTED)])
        m = mandate_template(Boxes, "A")
        m["goal"], m["limits"]["price"] = "VERTRAULICH-ALPHA", 31973
        self.act(self.a, "mandate", mandate=m, mandateVersion=1)
        r = self.handover()
        b = self.view(self.b)
        ctx = context(Boxes, "B", b["me"]["mandate"], r, self.now)
        for data in (json.dumps(b), json.dumps(vars(ctx)["shared"]), json.dumps(vars(ctx)["own"]),
                     self.clients["B"].seen()):
            self.assertNotIn("VERTRAULICH-ALPHA", data)
            self.assertNotIn("31973", data)
        self.act(self.a, "approve")
        self.act(self.b, "mode", mode="human")
        self.act(self.b, "offer", terms={**Boxes.request, "price": 31500})
        self.assertFalse(self.view()["room"]["approvals"])
        with self.assertRaises(Problem):
            self.act(self.a, "approve", version=2)
        self.act(self.b, "approve")
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(lambda _: self.act(self.a, "approve"), range(4)))
        result = self.view()["room"]
        self.assertEqual(result["agreement"]["version"], 3)
        self.assertEqual(sum(e["kind"] == "agreement" for e in result["events"]), 1)

    def test_deadline_and_round_limit(self):
        self.start(minutes=1)
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.now += 61
        self.db.dispatch(self.now)
        self.assertEqual(self.view()["room"]["stopReason"], "deadline")
        self.clients["B"].replies.append(turn("offer", "", REQUESTED))
        self.clients["A"].replies.append(turn("offer", "", {**Boxes.request, "price": 30500}))
        self.open_room(maxTurns=3)
        self.assertEqual(self.handover()["stopReason"], "round_limit")

    def test_roles_and_one_time_invites(self):
        self.start()
        a = self.db.create({"scenario": "service"}, self.now)
        invite = self.db.invite(a["room"], a["token"], self.now)["invite"]
        self.db.join(a["room"], invite, self.now)
        with self.assertRaises(Problem):
            self.db.join(a["room"], invite, self.now)
        with self.assertRaises(Problem):
            self.db.read(a["room"], self.a, self.now)
        with self.assertRaises(Problem):
            self.db.invite(self.room, self.b, self.now)
        with self.assertRaises(Problem):
            self.db.invite(a["room"], a["token"], self.now)

    def test_service_uses_same_workflow(self):
        package = {"hours": 16, "due": 8, "price": 175000}
        self.start(buyer=[turn("accept")], seller=[turn("offer", "", package)], scenario="service")
        r = self.handover(s=Service)
        self.assertEqual(r["offers"][-1]["terms"], package)
        self.act(self.b, "approve")
        self.act(self.a, "approve")
        self.assertEqual(self.view()["room"]["status"], "agreed")

    def test_hard_limits_checked_for_sending_and_approval(self):
        self.start()
        self.act(self.a, "mode", mode="human")
        with self.assertRaises(Problem):
            self.act(self.a, "offer", terms={**Boxes.request, "price": 32100})
        with self.assertRaises(Problem):
            self.act(self.a, "approve")
        self.assertEqual(len(self.view()["room"]["offers"]), 1)
        self.assertFalse(self.view()["room"]["approvals"])
        self.act(self.b, "offer", terms=REQUESTED)
        self.act(self.a, "approve")
        self.assertIn("A", self.view()["room"]["approvals"])

    def test_withheld_requirements_stay_private(self):
        buyer = mandate_template(Boxes, "A")
        buyer["shareTerms"] = False
        self.start(seller=[turn("message", "Welche Mengen und Termine benötigen Sie?")], demo=False, mandate=buyer)
        self.assertEqual(self.view()["room"]["request"], {})
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.tick()
        last = self.view()["room"]["events"][-1]
        self.assertEqual((last["kind"], last["side"], last["actor"]), ("message", "B", "agent"))
        for word in ("32000", "320,00", "30500", "305,00"):
            self.assertNotIn(word, self.clients["B"].seen())

    def test_queued_terms_checked_again_at_dispatch(self):
        self.start()
        cheap = {"kind": "offer", "terms": {**Boxes.request, "price": 19000}, "final": False, "note": ""}
        with patch.object(self.agents, "decide", return_value=(cheap, "")):
            self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
            self.tick()
        v = self.view(self.b)
        self.assertEqual((v["room"]["stopReason"], v["me"]["blocked"]), ("validation", 1))
        self.assertEqual(len(v["room"]["offers"]), 1)
        self.assertNotIn("19000", json.dumps(self.view()["room"]))

    def test_old_human_epoch_is_rejected_after_round_trip_through_agent(self):
        self.start()
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.act(self.b, "mode", mode="human")
        with self.assertRaises(Problem):
            self.act(self.b, "message", epoch=0, text="Alter Entwurf")
        self.assertNotIn("Alter Entwurf", json.dumps(self.view()["room"]))

    def test_agent_inputs_are_recipient_scoped(self):
        buyer, seller = mandate_template(Boxes, "A"), mandate_template(Boxes, "B")
        buyer.update(goal="Privates Einkaufsziel Q", preferred=30373)
        seller.update(goal="Private Verkaufsalternative Z")
        seller["options"][1].update(target=31275, floor=30223)
        self.start(buyer=[turn("accept")], seller=[turn("offer", "", {**Boxes.request, "price": 31275})],
                   mandate=buyer)
        captured, decide = [], self.agents.decide

        def observe(ctx, note):
            captured.append((ctx.side, json.dumps([ctx.own, ctx.shared])))
            return decide(ctx, note)
        with patch.object(self.agents, "decide", side_effect=observe):
            self.act(self.b, "mode", mode="agent", mandate=seller)
            self.tick()
            self.tick()
        self.assertEqual(self.view()["room"]["offers"][-1]["terms"]["price"], 31275)
        self.assertEqual({side for side, _ in captured}, {"A", "B"})
        for side, payload in captured + [(k, c.seen()) for k, c in self.clients.items()]:
            hidden = ("Privates Einkaufsziel Q", "30373") if side == "B" else ("Private Verkaufsalternative Z", "30223")
            self.assertTrue(all(word not in payload for word in hidden))

    def test_deadline_also_ends_unsigned_review(self):
        self.start(buyer=[turn("accept")], seller=[turn("offer", "", REQUESTED)])
        self.handover()
        self.act(self.a, "approve")
        self.now = self.view()["room"]["deadline"]
        with self.assertRaises(Problem):
            self.db.act(self.room, self.b, {"action": "approve", "version": 2}, self.now)
        self.assertEqual(self.view()["room"]["stopReason"], "deadline")
        self.assertIsNone(self.view()["room"]["agreement"])

    def test_early_complete_delivery_covers_both_milestones(self):
        buyer = mandate_template(Boxes, "A")
        self.assertTrue(assessment(Boxes, "A", buyer, {**Boxes.opening, "final_day": 4})["valid"])
        self.assertFalse(assessment(Boxes, "A", buyer, Boxes.opening)["valid"])
