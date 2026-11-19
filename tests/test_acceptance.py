import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from paktwerk.domain import Problem, context
from paktwerk.scenarios import Boxes, Service
from paktwerk.store import Store
from paktwerk.templates import mandate_template


class NegotiationCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(self.tmp.name + "/rooms.sqlite", delay=2)
        self.now = 1_800_000_000
        self.open_room()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

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
        self.db.dispatch(self.now)

    def agents(self, profile="flexibel", s=Boxes):
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(s, "B", profile))
        for _ in range(28):
            if self.view()["room"]["status"] != "active":
                break
            self.tick()
        return self.view()["room"]

    def test_two_agents_complete_package_and_two_people_approve(self):
        r = self.agents()
        self.assertEqual(r["status"], "review")
        self.assertEqual(r["offers"][-1]["terms"], {**Boxes.request, "price": 31000})
        self.assertFalse(r["approvals"])
        for token in (self.a, self.b):
            self.assertTrue(self.view(token)["me"]["assessment"]["valid"])
        self.act(self.a, "approve")
        self.assertIsNone(self.view()["room"]["agreement"])
        self.act(self.b, "approve")
        self.assertEqual(self.view()["room"]["agreement"]["version"], 2)

    def test_guest_free_text_clarification_and_manual_offer(self):
        self.act(self.b, "message", text="Wir können einen Teil früher liefern")
        self.tick()
        r = self.view()["room"]
        self.assertEqual(r["events"][-1]["missing"], ["early_qty", "early_day", "price"])
        self.assertFalse(r["facts"])
        self.act(self.b, "offer", terms={**Boxes.request, "price": 30850})
        self.tick()
        self.assertEqual(self.view()["room"]["status"], "review")
        self.act(self.b, "approve")
        self.act(self.a, "approve")
        self.assertEqual(self.view()["room"]["status"], "agreed")

    def test_handover_keeps_history_and_negotiates_only_missing_price(self):
        self.act(self.b, "message", text="Wir können 40 Stück binnen fünf Werktagen liefern.")
        self.tick()
        before = self.view()["room"]
        self.assertEqual(before["events"][-1]["missing"], ["price"])
        self.assertEqual(before["facts"], {"early_qty": 40, "early_day": 5})
        after = self.agents()
        self.assertEqual(after["events"][:len(before["events"])], before["events"])
        self.assertEqual(after["offers"][0], before["offers"][0])
        self.assertEqual(after["deadline"], before["deadline"])
        self.assertEqual(after["offers"][-1]["terms"], {**Boxes.request, "price": 31000})

    def test_takeover_cancels_prepared_reply_even_across_restart(self):
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.assertEqual(self.view()["preparing"], "B")
        self.db.close()
        self.db = Store(self.tmp.name + "/rooms.sqlite", delay=2)
        with self.assertRaises(Problem):
            self.act(self.b, "message", text="Ein zweiter Absender")
        self.act(self.b, "mode", mode="human")
        self.act(self.b, "message", text="Ich prüfe den Aufpreis persönlich.")
        self.tick()
        events = self.view()["room"]["events"]
        self.assertFalse([e for e in events if e["side"] == "B" and e["actor"] == "agent" and e["kind"] in ("message", "offer", "question")])
        self.assertEqual(sum(e["text"] == "Ich prüfe den Aufpreis persönlich." for e in events), 1)
        self.assertEqual(len(self.view()["room"]["offers"]), 1)

    def test_no_acceptable_timely_package(self):
        r = self.agents("eng")
        self.assertEqual((r["status"], r["stopReason"]), ("ended", "no_fit"))
        self.assertIsNone(r["agreement"])
        self.assertTrue(all(o["terms"]["price"] <= 32000 for o in r["offers"] if o["side"] == "A"))
        self.assertIn("Verhandlungsfrist", r["events"][-1]["text"])

    def test_private_context_and_versioned_idempotent_approval(self):
        m = mandate_template(Boxes, "A")
        m["goal"], m["limits"]["price"] = "VERTRAULICH-ALPHA", 31973
        self.act(self.a, "mandate", mandate=m, mandateVersion=1)
        r = self.agents()
        b = self.view(self.b)
        ctx = context(Boxes, "B", b["me"]["mandate"], r, self.now)
        for data in (b, vars(ctx)["shared"], vars(ctx)["own"]):
            self.assertNotIn("VERTRAULICH-ALPHA", json.dumps(data))
            self.assertNotIn("31973", json.dumps(data))
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
        self.open_room(minutes=1)
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.now += 61
        self.db.dispatch(self.now)
        self.assertEqual(self.view()["room"]["stopReason"], "deadline")
        self.open_room(maxTurns=3)
        self.assertEqual(self.agents()["stopReason"], "round_limit")

    def test_roles_and_one_time_invites(self):
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
        self.open_room(scenario="service")
        r = self.agents(s=Service)
        self.assertEqual(r["offers"][-1]["terms"], {"hours": 16, "due": 8, "price": 175000})
        self.act(self.b, "approve")
        self.act(self.a, "approve")
        self.assertEqual(self.view()["room"]["status"], "agreed")

    def test_ambiguous_text_does_not_become_a_commitment(self):
        for text in ("Wir können keine 40 Stück binnen fünf Werktagen liefern.",
                     "Können 40 Stück binnen fünf Werktagen eintreffen?",
                     "Der Aufpreis beträgt 20 Euro.", "Vielleicht 40 Stück binnen fünf Werktagen."):
            self.assertEqual(Boxes.facts(text), {})
        self.assertEqual(Service.facts("Wir bieten 16 Stunden binnen acht Werktagen."), {"hours": 16, "due": 8})

    def test_hard_limits_checked_for_sending_and_approval(self):
        self.act(self.a, "mode", mode="human")
        with self.assertRaises(Problem):
            self.act(self.a, "offer", terms={**Boxes.request, "price": 32100})
        with self.assertRaises(Problem):
            self.act(self.a, "approve")
        self.assertEqual(len(self.view()["room"]["offers"]), 1)
        self.assertFalse(self.view()["room"]["approvals"])
        self.act(self.b, "offer", terms={**Boxes.request, "price": 31000})
        self.act(self.a, "approve")
        self.assertIn("A", self.view()["room"]["approvals"])

    def test_fresh_room_opens_with_sellers_own_first_package(self):
        self.open_room(demo=False)
        self.assertEqual(self.view()["room"]["offers"], [])
        r = self.agents()
        self.assertEqual([o["terms"]["price"] for o in r["offers"]], [29000, 31000])
        self.assertEqual(r["status"], "review")

    def test_seller_asks_for_withheld_operational_requirements(self):
        buyer = mandate_template(Boxes, "A")
        buyer["shareTerms"] = False
        self.open_room(demo=False, mandate=buyer)
        self.assertEqual(self.view()["room"]["request"], {})
        r = self.agents()
        self.assertTrue(any(e.get("topic") == "requirements" and e["side"] == "B" for e in r["events"]))
        self.assertEqual(r["status"], "review")
        self.assertNotIn("32000", json.dumps(r))

    def test_partial_details_across_messages_and_qualified_terms(self):
        self.act(self.b, "message", text="Wir können 40 Stück früher liefern.")
        self.tick()
        self.assertEqual(self.view()["room"]["events"][-1]["missing"], ["early_day", "price"])
        self.act(self.b, "message", text="Die Teillieferung erfolgt binnen fünf Werktagen. Der Gesamtpreis beträgt 309,50 €.")
        self.tick()
        self.assertEqual(self.view()["room"]["facts"], {"early_qty": 40, "early_day": 5, "price": 30950})
        self.act(self.b, "message", text="Der Gesamtpreis ist noch offen.")
        self.tick()
        self.assertEqual(self.view()["room"]["events"][-1]["missing"], ["price"])
        self.assertEqual(len(self.view()["room"]["offers"]), 1)

    def test_queued_terms_checked_again_at_dispatch(self):
        from unittest.mock import patch
        with patch("paktwerk.store.decide", return_value={"kind": "offer", "terms": {**Boxes.request, "price": 19000}, "final": False}):
            self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.tick()
        v = self.view(self.b)
        self.assertEqual((v["room"]["stopReason"], v["me"]["blocked"]), ("validation", 1))
        self.assertEqual(len(v["room"]["offers"]), 1)
        self.assertNotIn("19000", json.dumps(self.view()["room"]))

    def test_old_human_epoch_is_rejected_after_round_trip_through_agent(self):
        self.act(self.b, "mode", mode="agent", mandate=mandate_template(Boxes, "B"))
        self.act(self.b, "mode", mode="human")
        with self.assertRaises(Problem):
            self.act(self.b, "message", epoch=0, text="Alter Entwurf")
        self.assertNotIn("Alter Entwurf", json.dumps(self.view()["room"]))

    def test_actual_policy_inputs_are_recipient_scoped(self):
        from unittest.mock import patch
        from paktwerk.domain import decide
        captured = []
        def observe(ctx):
            captured.append((ctx.side, json.dumps([ctx.own, ctx.shared])))
            return decide(ctx)
        buyer = mandate_template(Boxes, "A")
        seller = mandate_template(Boxes, "B")
        buyer.update(goal="Privates Einkaufsziel Q", preferred=30373)
        seller.update(goal="Private Verkaufsalternative Z")
        seller["options"][1].update(target=31275, floor=30223)
        self.open_room(mandate=buyer)
        with patch("paktwerk.store.decide", side_effect=observe):
            self.act(self.b, "mode", mode="agent", mandate=seller)
            self.tick()
            self.tick()
        self.assertEqual(self.view()["room"]["offers"][-1]["terms"]["price"], 31275)
        self.assertEqual({k for k,_ in captured}, {"A", "B"})
        for side, payload in captured:
            hidden = ("Privates Einkaufsziel Q", "30373") if side == "B" else ("Private Verkaufsalternative Z", "30223")
            self.assertTrue(all(word not in payload for word in hidden))

    def test_deadline_also_ends_unsigned_review(self):
        self.agents()
        self.act(self.a, "approve")
        self.now = self.view()["room"]["deadline"]
        with self.assertRaises(Problem):
            self.db.act(self.room, self.b, {"action": "approve", "version": 2}, self.now)
        self.assertEqual(self.view()["room"]["stopReason"], "deadline")
        self.assertIsNone(self.view()["room"]["agreement"])

    def test_early_complete_delivery_covers_both_milestones(self):
        self.act(self.b, "offer", terms={**Boxes.opening, "final_day": 4})
        self.tick()
        self.assertEqual(self.view()["room"]["status"], "review")

    def test_agent_considers_cheaper_outside_option(self):
        buyer = mandate_template(Boxes, "A")
        buyer["batnaValue"] = 28000
        self.open_room(mandate=buyer)
        r = self.agents()
        self.assertEqual(r["status"], "ended")
        self.assertTrue(all(o["terms"]["price"] <= 28000 for o in r["offers"] if o["side"] == "A"))


class ResearchCases(unittest.TestCase):
    def test_matrix_is_reproducible_and_reports_safety_and_utility(self):
        from research import benchmark
        report = benchmark()
        self.assertEqual(report, benchmark())
        self.assertEqual(report["summary"], {"total": 8, "solvable": 4, "agreedSolvable": 4, "violations": 0, "blocked": 0})
        for r in report["runs"]:
            self.assertTrue(r["strategyVersion"] and r["scenarioVersion"] and r["mandates"]["B"]["fixtureHash"])
            self.assertEqual(r["solvable"], r["agreed"])
            self.assertEqual(bool(r["stopReason"]), not r["agreed"])
        direct, stepwise = report["runs"][:2]
        self.assertEqual(direct["utility"], {"A": 2000, "B": 2000})
        self.assertEqual(stepwise["terms"]["price"], 32000)
        self.assertGreater(stepwise["turns"], direct["turns"])
