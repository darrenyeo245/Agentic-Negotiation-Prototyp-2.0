"""Package validation, mandate evaluation and deterministic, role-local policies."""
from copy import deepcopy
from dataclasses import dataclass

from .scenarios import PRICE, STRATEGIES, euros, without_price


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class AgentFailure(Exception):
    """An agent could not produce an admissible turn. Its company represents itself again."""


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise Problem(f"{label} muss eine ganze Zahl zwischen {low} und {high} sein.")
    return value


def plain(value, label, maximum=400):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise Problem(f"Bitte {label} mit höchstens {maximum} Zeichen angeben.")
    return value.strip()


def package(s, raw):
    if not isinstance(raw, dict) or set(raw) != {f.key for f in s.fields}:
        raise Problem("Bitte alle Felder des Angebotspakets ausfüllen.")
    t = {}
    for f in s.fields:
        if f.nullable and raw[f.key] is None:
            t[f.key] = None
        else:
            t[f.key] = integer(raw[f.key], f.minimum, f.maximum, f.label)
    invalid = s.validate(t)
    if invalid:
        raise Problem(invalid)
    return t


def money(v, label, minimum=0):
    return integer(v, minimum, PRICE.maximum, label)


def mandate(s, side, raw, version):
    if not isinstance(raw, dict):
        raise Problem("Bitte zuerst ein privates Mandat erteilen.")
    if raw.get("strategy") not in tuple(STRATEGIES) or raw.get("priority") not in ("price", "time"):
        raise Problem("Bitte Strategie und Präferenz auswählen.")
    if type(raw.get("shareTerms")) is not bool:
        raise Problem("Bitte eine Offenlegungsregel wählen.")
    result = {"version": version, "strategy": raw["strategy"], "priority": raw["priority"],
              "shareTerms": raw["shareTerms"], "step": money(raw.get("step"), "Preisstufe", 1),
              "goal": plain(raw.get("goal"), "ein Ziel"), "batna": plain(raw.get("batna"), "eine Alternative"),
              "batnaValue": money(raw.get("batnaValue"), "Wert der Alternative")}
    if side == "A":
        result["limits"] = package(s, raw.get("limits"))
        result["preferred"] = money(raw.get("preferred"), "Zielpreis", 1)
        if result["preferred"] > result["limits"]["price"]:
            raise Problem("Der Zielpreis überschreitet das Budget.")
        return result
    options = raw.get("options")
    if not isinstance(options, list) or not 1 <= len(options) <= 8:
        raise Problem("Bitte ein bis acht leistbare Pakete festlegen.")
    result["options"] = []
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get("terms"), dict):
            raise Problem("Leistungspaket unvollständig.")
        target = money(option.get("target"), "Zielpreis", 1)
        floor = money(option.get("floor"), "Preisuntergrenze", 1)
        cost = money(option.get("cost"), "Kosten")
        terms = without_price(package(s, {**option["terms"], "price": target}))
        if not cost <= floor <= target:
            raise Problem("Die Untergrenze muss zwischen Kosten und Zielpreis liegen.")
        if any(item["terms"] == terms for item in result["options"]):
            raise Problem("Jedes Leistungspaket benötigt eigene Konditionen.")
        result["options"].append({"terms": terms, "cost": cost, "floor": floor, "target": target})
    return result


def unmet(s, terms, limits):
    effective = s.effective(terms, limits)
    failures = []
    for f in s.fields:
        bound = limits.get(f.key)
        if bound is None:
            continue
        actual = effective.get(f.key)
        if (actual is None or (f.rule == "exact" and actual != bound)
                or (f.rule == "min" and actual < bound) or (f.rule == "max" and actual > bound)):
            failures.append(f)
    return failures


def capacity(m, t):
    return next((o for o in m["options"] if o["terms"] == without_price(t)), None)


def assessment(s, side, m, t):
    if m is None:
        return {"valid": True, "utility": None, "reasons": ["Die Konditionen stehen zur persönlichen Prüfung bereit. Es ist noch kein Agentenmandat hinterlegt."]}
    if side == "A":
        failures = unmet(s, t, m["limits"])
        reasons = [f"{f.label} liegt außerhalb Ihrer harten Grenze." for f in failures]
        utility = m["batnaValue"] - t["price"]
        positive = f"Das Paket erfüllt Ihre Mengen- und Terminvorgaben. Vom Budget bleiben {euros(m['limits']['price'] - t['price'])} verfügbar."
    else:
        option = capacity(m, t)
        reasons = []
        if not option:
            reasons.append("Dieses Leistungspaket ist nicht als leistbar hinterlegt.")
        elif t["price"] < option["floor"]:
            reasons.append(f"Der Preis unterschreitet Ihre Untergrenze von {euros(option['floor'])}.")
        utility = t["price"] - option["cost"] - m["batnaValue"] if option else None
        positive = "Leistung, Termin und Preis sind durch Ihr Mandat gedeckt."
    valid = not reasons
    if valid:
        reasons = [positive, f"Ihr Nutzen gegenüber der Alternative beträgt {euros(utility)}."]
    return {"valid": valid, "utility": utility if valid else None, "reasons": reasons}


def require_fit(s, side, m, terms):
    result = assessment(s, side, m, terms)
    if not result["valid"]:
        raise Problem(" ".join(result["reasons"]), 422)


def compatible_facts(m, facts):
    if not facts or m is None:
        return True
    return any(all((value >= o["floor"] if k == "price" else o["terms"].get(k) == value)
                   for k, value in facts.items()) for o in m["options"])


@dataclass(frozen=True)
class Context:
    scenario: object
    side: str
    own: dict
    shared: dict
    remaining_seconds: int


def context(s, side, own, public, now):
    return Context(s, side, deepcopy(own), deepcopy(public), max(0, public["deadline"] - now))


def finish(code):
    return {"kind": "end", "reason": code}


def offer(terms, final=False):
    return {"kind": "offer", "terms": terms, "final": final}


def buyer_policy(ctx):
    s, m, p = ctx.scenario, ctx.own, ctx.shared
    current = p["offers"][-1] if p["offers"] else None
    last = next((e for e in reversed(p["events"]) if e["kind"] in ("message", "offer", "question")), None)
    limit = min(m["limits"]["price"], m["batnaValue"])
    if limit == 0:
        return finish("alternative")
    if last and last.get("topic") == "requirements" and last["side"] == "B":
        # The buyer can answer with a binding package without naming its private ceiling.
        return offer({**m["limits"], "price": min(m["preferred"], limit)})
    if last and last["side"] == "B" and last["kind"] == "message":
        return {"kind": "question", "missing": [k for k in s.focus if k not in p["facts"]]}
    if current and current["side"] == "B":
        t = current["terms"]
        failures = unmet(s, t, {**m["limits"], "price": limit})
        if not failures:
            return {"kind": "recommend", "version": current["version"]}
        if current["final"]:
            return finish("no_fit")
        if all(f.key == "price" for f in failures):
            previous = [o for o in p["offers"] if o["side"] == "A" and without_price(o["terms"]) == without_price(t)]
            target = m["preferred"] if m["priority"] == "price" else max(m["preferred"], t["price"] - m["step"])
            if m["strategy"] == "stufen":
                target = max(1, target - m["step"] + len(previous) * m["step"])
            target = min(limit, target)
            if previous and target <= previous[-1]["terms"]["price"]:
                return {"kind": "question", "topic": "price_concession", "missing": ["price"]}
            return offer({**t, "price": target})
    return {"kind": "question", "missing": [k for k in s.focus if k not in p["facts"]]}


def seller_policy(ctx):
    s, m, p = ctx.scenario, ctx.own, ctx.shared
    current = p["offers"][-1] if p["offers"] else None
    incoming = current if current and current["side"] == "A" else None
    buyer_offer = next((o for o in reversed(p["offers"]) if o["side"] == "A"), None)
    requested = without_price(buyer_offer["terms"]) if buyer_offer else p["request"]
    if incoming:
        o = capacity(m, incoming["terms"])
        if o and incoming["terms"]["price"] >= max(o["target"], o["cost"] + m["batnaValue"]):
            return {"kind": "recommend", "version": incoming["version"]}
    facts = without_price(p["facts"]) if p["factSource"] == "message" else {}
    if not requested and not facts:
        asked = any(e.get("topic") == "requirements" for e in p["events"])
        if not asked:
            return {"kind": "question", "topic": "requirements", "missing": [k for k in s.focus if k != "price"]}
    options = [o for o in m["options"] if all(o["terms"].get(k) == v for k, v in facts.items())]
    if not options:
        return finish("capacity")

    if not current and p["factSource"] != "message":
        opening = options[0]
        price = max(opening["target"], opening["cost"] + m["batnaValue"])
        if price <= PRICE.maximum:
            return offer({**opening["terms"], "price": price})

    def priority(o):
        terms = {**o["terms"], "price": o["target"]}
        timing = tuple(terms.get(k) or 10_000 for k in s.timing)
        preference = (o["target"], timing) if m["priority"] == "price" else (timing, o["target"])
        return len(unmet(s, terms, requested)), preference
    options.sort(key=priority)
    for o in options:
        floor = max(o["floor"], o["cost"] + m["batnaValue"])
        if floor > PRICE.maximum:
            continue
        previous = [x for x in p["offers"] if x["side"] == "B" and without_price(x["terms"]) == o["terms"]]
        if not previous:
            price = max(o["target"], floor) + (2 * m["step"] if m["strategy"] == "stufen" else 0)
        else:
            price = max(floor, previous[-1]["terms"]["price"] - m["step"])
        price = min(price, PRICE.maximum)
        # An explicitly confirmed total continues to bind the next proposal.
        if "price" in p["facts"] and p["factSource"] == "message":
            price = p["facts"]["price"]
            if price < floor:
                continue
        if incoming and without_price(incoming["terms"]) == o["terms"]:
            if incoming["terms"]["price"] >= price:
                return {"kind": "recommend", "version": incoming["version"]}
        if previous and price >= previous[-1]["terms"]["price"]:
            continue
        # A rejected operational package does not become feasible through a price cut.
        if previous and unmet(s, {**o["terms"], "price": price}, requested):
            continue
        return offer({**o["terms"], "price": price}, final=m["shareTerms"] and price == floor)
    return finish("no_fit")


def exhausted(ctx):
    """Deadline and step limit end the exchange for every kind of agent."""
    if ctx.remaining_seconds <= 0:
        return finish("deadline")
    if ctx.shared["turns"] >= ctx.shared["maxTurns"]:
        return finish("round_limit")
    return None


def decide(ctx):
    return exhausted(ctx) or (buyer_policy(ctx) if ctx.side == "A" else seller_policy(ctx))
