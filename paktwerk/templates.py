"""Private fixture factories. The negotiation policies never import this module."""
from .scenarios import Boxes, Service, without_price


def box_options(profile):
    urgent = profile == "eng"
    return [
        {"terms": without_price(Boxes.opening), "cost": 26500, "floor": 27500, "target": 29000},
        {"terms": Boxes.request.copy(), "cost": 32500 if urgent else 28500,
         "floor": 33500 if urgent else 30000, "target": 33500 if urgent else 31000},
    ]


def service_options(profile):
    return [
        {"terms": without_price(Service.opening), "cost": 120000, "floor": 130000, "target": 140000},
        {"terms": Service.request.copy(), "cost": 197000 if profile == "eng" else 158000,
         "floor": 205000 if profile == "eng" else 168000, "target": 205000 if profile == "eng" else 175000},
    ]


def mandate_template(s, side, profile="flexibel"):
    goods = s is Boxes
    base = {"version": 1, "strategy": "direkt", "priority": "price", "shareTerms": True,
            "step": 1000 if goods else 10000}
    if side == "A":
        return {**base, "goal": "Termingerechte Versorgung zu einem tragfähigen Gesamtpreis.",
                "batna": "Vergleichbare Leistung kurzfristig anderweitig beschaffen.",
                "batnaValue": 33000 if goods else 200000, "preferred": 30500 if goods else 170000,
                "limits": {**s.request, "price": 32000 if goods else 190000}}
    return {**base, "goal": "Kapazitäten auslasten und einen kostendeckenden Auftrag gewinnen.",
            "batna": "Freie Kapazität für einen anderen Auftrag nutzen.",
            "batnaValue": 500 if goods else 5000, "options": (box_options(profile) if goods else service_options(profile))}
