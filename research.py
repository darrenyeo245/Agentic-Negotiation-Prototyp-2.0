"""Run the same platform workflow with a logical clock and two simulated human signatories."""
import argparse
import hashlib
import json
from pathlib import Path

from paktwerk.claude import EFFORT, MODEL, ClaudeAgents
from paktwerk.domain import assessment, unmet
from paktwerk.env import load_env
from paktwerk.scenarios import SCENARIOS, STRATEGIES, STRATEGY_VERSIONS, euros
from paktwerk.store import Store
from paktwerk.templates import mandate_template

START = 1_800_000_000
BENCHMARK = "referenzvergleich/1.0"


def fingerprint(m):
    content = json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def run_case(s, profile, strategy, repeat, agents=None):
    db = Store(delay=1, agents=agents)
    try:
        now = START
        mandates = {k: mandate_template(s, k, profile) for k in ("A", "B")}
        for m in mandates.values():
            m["strategy"] = strategy
        a = db.create({"scenario": s.key, "demo": True, "mandate": mandates["A"]}, now)
        rid, at = a["room"], a["token"]
        invitation = db.invite(rid, at, now)
        bt = db.join(rid, invitation["invite"], now)["token"]
        db.act(rid, bt, {"action": "mode", "mode": "agent", "epoch": 0, "mandate": mandates["B"]}, now)
        for _ in range(25):
            now += 1
            db.prepare(now)
            db.dispatch(now)
            view = db.read(rid, at, now)
            if view["room"]["status"] != "active" or not view["preparing"]:
                break
        if view["room"]["status"] == "active":
            raise RuntimeError("Der Lauf hat keinen Endzustand erreicht: " + view["room"]["events"][-1]["text"])
        if view["room"]["status"] == "review":
            version = len(view["room"]["offers"])
            for key in (at, bt):
                if db.read(rid, key, now)["me"]["assessment"]["valid"]:
                    db.act(rid, key, {"action": "approve", "version": version}, now)
        views = {side: db.read(rid, key, now) for side, key in (("A", at), ("B", bt))}
        p = views["A"]["room"]
        agreement = p["agreement"]
        violations = 0
        for event in p["events"]:
            if event["actor"] == "agent" and event["kind"] in ("offer", "recommend"):
                proposal = p["offers"][event["version"] - 1]["terms"]
                if not assessment(s, event["side"], mandates[event["side"]], proposal)["valid"]:
                    violations += 1
        buyer, seller = mandates["A"], mandates["B"]
        limits = {**buyer["limits"], "price": min(buyer["limits"]["price"], buyer["batnaValue"])}
        solvable = any(not unmet(s, {**o["terms"], "price": max(o["floor"], o["cost"] + seller["batnaValue"])}, limits)
                       for o in seller["options"])
        return {"scenario": s.key, "scenarioVersion": s.version, "profile": profile, "strategy": strategy,
                "strategyVersion": STRATEGY_VERSIONS[strategy], "repeat": repeat, "solvable": solvable,
                "mandates": {k: {"version": v["version"], "fixtureHash": fingerprint(v)} for k, v in mandates.items()},
                "status": p["status"], "agreed": bool(agreement), "terms": agreement["terms"] if agreement else None,
                "turns": p["turns"], "stopReason": p["stopReason"],
                "violations": violations, "blocked": sum(v["me"]["blocked"] for v in views.values()),
                "utility": {k: v["me"]["assessment"]["utility"] if agreement else 0 for k, v in views.items()},
                "events": p["events"], "offers": p["offers"]}
    finally:
        db.close()


def benchmark(scenario="all", repeats=1, agents=None):
    if scenario != "all" and scenario not in SCENARIOS:
        raise ValueError("Unbekanntes Szenario.")
    if type(repeats) is not int or not 1 <= repeats <= 50:
        raise ValueError("Bitte 1 bis 50 Wiederholungen wählen.")
    scenarios = SCENARIOS.values() if scenario == "all" else [SCENARIOS[scenario]]
    runs = [run_case(s, profile, strategy, i + 1, agents) for s in scenarios
            for profile in ("flexibel", "eng") for strategy in STRATEGIES for i in range(repeats)]
    possible = [r for r in runs if r["solvable"]]
    return {"benchmarkVersion": BENCHMARK, "agents": agents.label if agents else "regeln",
            "logicalStart": START, "repeats": repeats, "runs": runs,
            "summary": {"total": len(runs), "solvable": len(possible), "agreedSolvable": sum(r["agreed"] for r in possible),
                        "violations": sum(r["violations"] for r in runs), "blocked": sum(r["blocked"] for r in runs)}}


def main():
    parser = argparse.ArgumentParser(description="Reproduzierbarer Vergleich zweier Paketstrategien.")
    parser.add_argument("--scenario", default="all", choices=["all", *SCENARIOS])
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 51), metavar="1–50")
    parser.add_argument("--json", action="store_true", help="Versionen, Nutzen, Pakete und Gesprächsprotokolle als JSON ausgeben.")
    parser.add_argument("--agents", choices=("regeln", "claude"), default="regeln",
                        help="Regelbasierte Agenten (Standard, deterministisch) oder zwei Claude-Agenten über die Claude API")
    parser.add_argument("--model", default=MODEL, help=f"Claude-Modell beider Agenten (Standard {MODEL})")
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default=EFFORT)
    args = parser.parse_args()
    agents = None
    if args.agents == "claude":
        load_env(Path(__file__).resolve().parent / ".env")
        try:
            agents = ClaudeAgents(model=args.model, effort=args.effort)
        except RuntimeError as exc:
            parser.exit(2, f"{exc}\n")
    report = benchmark(args.scenario, args.repeats, agents)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print("Szenario        Profil     Strategie  Schritte  Abschluss         Nutzen A     Nutzen B  Abbruchgrund")
    for r in report["runs"]:
        price = euros(r["terms"]["price"]) if r["agreed"] else "—"
        print(f"{r['scenario']:<15} {r['profile']:<10} {r['strategy']:<9} {r['turns']:>7}  {price:>10}  "
              f"{euros(r['utility']['A']):>13} {euros(r['utility']['B']):>12}  {r['stopReason'] or '—'}")
    t = report["summary"]
    print(f"\n{t['agreedSolvable']}/{t['solvable']} lösbare Läufe abgeschlossen · {t['violations']} versandte "
          f"Mandatsverletzungen · {t['blocked']} blockierte Aktionen")


if __name__ == "__main__":
    main()
