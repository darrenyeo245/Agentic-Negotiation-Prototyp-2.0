"""Repeated negotiations between two Claude agents on the real platform workflow.

A logical clock replaces waiting, and two simulated people approve a recommended package whenever it fits
their own mandate. Every run keeps each agent decision, its private note and the API usage behind it.
"""
import argparse
import contextlib
import hashlib
import json
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from paktwerk.claude import EFFORT, MODEL, SIDES, ClaudeAgents
from paktwerk.domain import assessment, unmet
from paktwerk.scenarios import SCENARIOS, STRATEGIES, STRATEGY_VERSIONS, euros
from paktwerk.store import Store
from paktwerk.templates import mandate_template

START = 1_800_000_000
SERIES = "verhandlungsserie/1.0"
PROFILES = ("flexibel", "eng")
# List prices in US$ per million input and output tokens (as of 2026-11). Only used for the cost estimate.
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}
OUTCOMES = {"agreed": "Einigung", "unfinished": "Agent ausgefallen", "error": "Laufzeitfehler"}


def fingerprint(m):
    content = json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def run_case(s, profile, strategy, repeat, agents):
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
        # A room that is still active has lost its agent: the platform handed the turn back to the firm.
        unfinished = view["room"]["status"] == "active"
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
                "status": "unfinished" if unfinished else p["status"],
                "failure": p["events"][-1]["text"] if unfinished else None,
                "agreed": bool(agreement), "terms": agreement["terms"] if agreement else None,
                "turns": p["turns"], "stopReason": p["stopReason"],
                "violations": violations, "blocked": sum(v["me"]["blocked"] for v in views.values()),
                "utility": {k: v["me"]["assessment"]["utility"] if agreement else 0 for k, v in views.items()},
                "events": p["events"], "offers": p["offers"]}
    finally:
        db.close()


def cases(scenario="all", profiles=PROFILES, strategies=tuple(STRATEGIES), repeats=1):
    if scenario != "all" and scenario not in SCENARIOS:
        raise ValueError("Unbekanntes Szenario.")
    if type(repeats) is not int or not 1 <= repeats <= 50:
        raise ValueError("Bitte 1 bis 50 Wiederholungen wählen.")
    scenarios = SCENARIOS.values() if scenario == "all" else [SCENARIOS[scenario]]
    return [(s, profile, strategy, i + 1) for s in scenarios
            for profile in profiles for strategy in strategies for i in range(repeats)]


def summary(runs):
    possible = [r for r in runs if r["solvable"]]
    return {"total": len(runs), "solvable": len(possible), "agreedSolvable": sum(r["agreed"] for r in possible),
            "violations": sum(r["violations"] for r in runs), "blocked": sum(r["blocked"] for r in runs)}


class Recorder:
    """Stands in front of one firm's API client. Keeps tokens, duration and the model that actually answered.

    The request itself passes through unchanged, so a traced run negotiates exactly like an untraced one.
    """

    def __init__(self, client):
        self.client, self.calls = client, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **request):
        started = time.monotonic()
        response = self.client.beta.messages.create(**request)
        usage = response.usage
        steps = getattr(usage, "iterations", None) or []
        retry = len(request["messages"]) > 1
        self.calls.append({
            "attempt": (len(request["messages"]) + 1) // 2,
            "rejected": request["messages"][-1]["content"] if retry else None,
            "model": response.model,
            "fallback": any(getattr(step, "type", None) == "fallback_message" for step in steps),
            "stopReason": response.stop_reason,
            "inputTokens": usage.input_tokens,
            "outputTokens": usage.output_tokens,
            "seconds": round(time.monotonic() - started, 1),
            "reply": next((b.text for b in response.content if b.type == "text"), None),
        })
        return response


class Trace:
    """The agents of one run. Keeps every decision with the private note and the API requests behind it."""

    def __init__(self, agents, recorders):
        self.agents, self.label, self.recorders, self.decisions = agents, agents.label, recorders, []

    def decide(self, ctx, note):
        calls = self.recorders[ctx.side].calls
        before = len(calls)
        entry = {"step": len(self.decisions) + 1, "side": ctx.side, "turnsBefore": ctx.shared["turns"]}
        try:
            action, note = self.agents.decide(ctx, note)
        except Exception as exc:
            self.decisions.append({**entry, "failure": str(exc), "requests": calls[before:]})
            raise
        self.decisions.append({**entry, "action": action, "privateNote": note, "requests": calls[before:]})
        return action, note


class ClaudeSeries:
    """Builds fresh, traced Claude agents for every run. Each firm keeps its own API client across all runs."""

    def __init__(self, model=MODEL, effort=EFFORT):
        base = ClaudeAgents(model=model, effort=effort)
        self.model, self.effort, self.label = model, effort, base.label
        self.clients = {side: base.negotiators[side].client for side in SIDES}

    def __call__(self):
        recorders = {side: Recorder(self.clients[side]) for side in SIDES}
        return Trace(ClaudeAgents(self.model, self.effort, clients=recorders), recorders)


def usage(calls):
    """Token totals and a list-price estimate. Unknown models leave the estimate empty instead of guessing."""
    prices = [PRICES.get(c["model"]) for c in calls]
    return {"requests": len(calls),
            "inputTokens": sum(c["inputTokens"] for c in calls),
            "outputTokens": sum(c["outputTokens"] for c in calls),
            "retries": sum(c["attempt"] > 1 for c in calls),
            "fallbacks": sum(c["fallback"] for c in calls),
            "models": sorted({c["model"] for c in calls}),
            "usd": None if None in prices else round(sum(
                (c["inputTokens"] * p[0] + c["outputTokens"] * p[1]) / 1e6 for c, p in zip(calls, prices)), 4)}


def outcome(r):
    if r["agreed"]:
        return "agreed"
    return r["stopReason"] or r["status"]


def spread(values):
    if not values:
        return None
    return {"min": min(values), "median": statistics.median(values), "max": max(values),
            "mean": round(statistics.fmean(values), 1)}


def conditions(runs):
    """How much the runs of one condition differ: outcomes, prices, steps and utility per firm."""
    groups = {}
    for r in runs:
        groups.setdefault((r["scenario"], r["profile"], r["strategy"]), []).append(r)
    rows = []
    for (scenario, profile, strategy), group in groups.items():
        deals = [r for r in group if r["agreed"]]
        rows.append({"scenario": scenario, "profile": profile, "strategy": strategy, "runs": len(group),
                     "agreed": len(deals), "failed": sum(r["failure"] is not None for r in group),
                     "distinctAgreements": len({json.dumps(r["terms"], sort_keys=True) for r in deals}),
                     "outcomes": dict(Counter(outcome(r) for r in group)),
                     "price": spread([r["terms"]["price"] for r in deals]),
                     "turns": spread([r["turns"] for r in group if r["status"] != "error"]),
                     "offers": spread([len(r["offers"]) for r in group if r["status"] != "error"]),
                     "utility": {side: spread([r["utility"][side] for r in group]) for side in SIDES}})
    return rows


def series(build, scenario="all", profiles=PROFILES, strategies=tuple(STRATEGIES), repeats=1, parallel=1,
           out=None, progress=None):
    """Repeat every condition and keep each run, even a failed one. Finished runs go to `out` immediately."""
    todo = cases(scenario, profiles, strategies, repeats)
    lock, done = threading.Lock(), []

    def one(case):
        s, profile, strategy, repeat = case
        agents = build()
        started = time.monotonic()
        try:
            r = run_case(s, profile, strategy, repeat, agents)
        except Exception as exc:  # One broken run must not discard the runs that were already paid for.
            r = {"scenario": s.key, "profile": profile, "strategy": strategy, "repeat": repeat, "solvable": None,
                 "status": "error", "failure": f"{type(exc).__name__}: {exc}", "agreed": False, "terms": None,
                 "turns": 0, "stopReason": None, "violations": 0, "blocked": 0, "utility": {"A": 0, "B": 0},
                 "events": [], "offers": []}
        r["agents"], r["effort"] = build.label, build.effort
        r["seconds"] = round(time.monotonic() - started, 1)
        r["decisions"] = agents.decisions
        r["usage"] = usage([c for d in agents.decisions for c in d["requests"]])
        with lock:
            done.append(r)
            if out:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
                out.flush()
            if progress:
                progress(len(done), len(todo), r)
        return r

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        runs = list(pool.map(one, todo))
    return {"seriesVersion": SERIES, "agents": build.label, "effort": build.effort, "logicalStart": START,
            "repeats": repeats, "runs": runs, "summary": summary(runs), "conditions": conditions(runs),
            "usage": usage([c for r in runs for d in r["decisions"] for c in d["requests"]])}


def german(number, digits=0):
    return f"{number:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def path(r):
    return " → ".join(f"{o['side']} {euros(o['terms']['price'])}{' (final)' if o['final'] else ''}" for o in r["offers"])


def report_progress(n, total, r):
    result = (f"Einigung zu {euros(r['terms']['price'])}" if r["agreed"]
              else OUTCOMES.get(outcome(r), f"Abbruch ({outcome(r)})"))
    cost = f", {german(r['usage']['usd'], 2)} US$" if r.get("usage", {}).get("usd") is not None else ""
    print(f"[{n}/{total}] {r['scenario']} · {r['profile']} · {r['strategy']} · #{r['repeat']}: {result} "
          f"nach {r['turns']} Schritten ({r['seconds']:.0f} s{cost})", file=sys.stderr, flush=True)


def range_text(x, fmt=str):
    if x is None:
        return "—"
    return fmt(x["min"]) if x["min"] == x["max"] else f"{fmt(x['min'])} … {fmt(x['median'])} … {fmt(x['max'])}"


def main():
    parser = argparse.ArgumentParser(description="Wiederholte Verhandlungen zweier Claude-Agenten. Jeder Lauf kostet API-Guthaben.")
    parser.add_argument("--scenario", default="all", choices=["all", *SCENARIOS])
    parser.add_argument("--profile", default="all", choices=["all", *PROFILES], help="Nur dieses Lieferantenprofil")
    parser.add_argument("--strategy", default="all", choices=["all", *STRATEGIES], help="Nur diese Strategie")
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 51), metavar="1–50")
    parser.add_argument("--json", action="store_true", help="Versionen, Nutzen, Pakete und Gesprächsprotokolle als JSON ausgeben.")
    parser.add_argument("--out", help="Jeden fertigen Lauf sofort als JSON-Zeile an diese Datei anhängen.")
    parser.add_argument("--parallel", type=int, default=1, choices=range(1, 9), metavar="1–8",
                        help="Läufe, die gleichzeitig verhandeln")
    parser.add_argument("--model", default=MODEL, help=f"Claude-Modell beider Agenten (Standard {MODEL})")
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default=EFFORT)
    args = parser.parse_args()
    try:
        build = ClaudeSeries(args.model, args.effort)
    except RuntimeError as exc:
        parser.exit(2, f"{exc}\n")
    profiles = PROFILES if args.profile == "all" else (args.profile,)
    strategies = tuple(STRATEGIES) if args.strategy == "all" else (args.strategy,)
    with open(args.out, "a", encoding="utf-8") if args.out else contextlib.nullcontext() as out:
        report = series(build, args.scenario, profiles, strategies, args.repeats, args.parallel, out, report_progress)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print("Szenario        Profil     Strategie   #  Schritte  Abschluss         Nutzen A     Nutzen B  Ergebnis")
    for r in report["runs"]:
        price = euros(r["terms"]["price"]) if r["agreed"] else "—"
        print(f"{r['scenario']:<15} {r['profile']:<10} {r['strategy']:<9} {r['repeat']:>3} {r['turns']:>7}  {price:>10}  "
              f"{euros(r['utility']['A']):>13} {euros(r['utility']['B']):>12}  {OUTCOMES.get(outcome(r), outcome(r))}")
        if r["offers"]:
            print(f"{'':<15} Angebote: {path(r)}")
    if report["repeats"] > 1:
        print("\nStreuung je Bedingung")
        for c in report["conditions"]:
            outcomes = ", ".join(f"{OUTCOMES.get(k, k)} {v}×" for k, v in c["outcomes"].items())
            print(f"{c['scenario']} · {c['profile']} · {c['strategy']}: {c['runs']} Läufe, {outcomes}. "
                  f"Preis {range_text(c['price'], euros)}, {c['distinctAgreements']} verschiedene Pakete. "
                  f"Schritte {range_text(c['turns'])}. Nutzen A {range_text(c['utility']['A'], euros)}, "
                  f"Nutzen B {range_text(c['utility']['B'], euros)}.")
    t = report["summary"]
    print(f"\n{t['agreedSolvable']}/{t['solvable']} lösbare Läufe abgeschlossen · {t['violations']} versandte "
          f"Mandatsverletzungen · {t['blocked']} blockierte Aktionen")
    u = report["usage"]
    cost = f", geschätzt {german(u['usd'], 2)} US$ zum Listenpreis" if u["usd"] is not None else ""
    print(f"{u['requests']} API-Anfragen ({u['retries']} Korrekturversuche, {u['fallbacks']} mit Ersatzmodell), "
          f"{german(u['inputTokens'])} Eingabe- und {german(u['outputTokens'])} Ausgabetokens{cost}. "
          f"Modelle: {', '.join(u['models']) or '—'}")


if __name__ == "__main__":
    main()
