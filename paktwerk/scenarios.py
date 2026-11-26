"""Public scenario descriptions and package semantics."""
from dataclasses import dataclass


def euros(cents):
    return f"{cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " €"


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    unit: str
    rule: str
    minimum: int = 1
    maximum: int = 100_000
    nullable: bool = False


PRICE = Field("price", "Gesamtpreis", "€", "max", 1, 100_000_000)


class Boxes:
    key = "boxes"
    label = "Versandboxen"
    title = "100 Versandboxen"
    version = "versandboxen/1.0"
    companies = {"A": "Nordlicht Handel", "B": "Kartonwerk Süd"}
    price_note = "inkl. Lieferung"
    fields = (Field("quantity", "Gesamtmenge", "Stück", "exact"),
              Field("early_qty", "Erste Teillieferung", "Stück", "min", 0),
              Field("early_day", "Termin der Teillieferung", "Werktage", "max", 1, 365, True),
              Field("final_day", "Vollständige Lieferung", "Werktage", "max", 1, 365), PRICE)
    request = {"quantity": 100, "early_qty": 40, "early_day": 5, "final_day": 10}
    opening = {"quantity": 100, "early_qty": 0, "early_day": None, "final_day": 10, "price": 29000}
    public_rule = "Gesamtpreise in Euro einschließlich Lieferung. Lieferfristen zählen in Werktagen ab beidseitiger Freigabe."
    package_hint = ("Ohne Teillieferung gilt early_qty = 0 und early_day = null. Eine Teillieferung benötigt eine Menge "
                    "und einen Termin early_day, der nicht nach final_day liegt. Eine vollständige Lieferung bis zum "
                    "geforderten Termin der Teillieferung erfüllt auch die geforderte Teillieferung.")

    @staticmethod
    def validate(t):
        if t["early_qty"] > t["quantity"]:
            return "Die Teillieferung übersteigt die Gesamtmenge."
        if (t["early_qty"] == 0) != (t["early_day"] is None):
            return "Eine Teillieferung benötigt eine Menge und einen Termin."
        if t["early_qty"] and t["early_day"] > t["final_day"]:
            return "Die Teillieferung muss spätestens mit der Gesamtlieferung eintreffen."
        return None

    @staticmethod
    def effective(t, limits):
        # An early complete delivery also fulfils an intermediate milestone.
        if "early_day" in limits and limits["early_day"] is not None and t["final_day"] <= limits["early_day"]:
            return {**t, "early_qty": t["quantity"], "early_day": t["final_day"]}
        return t

    @staticmethod
    def describe(t):
        when = f"alle bis zum {t['final_day']}. Werktag"
        if t["early_qty"]:
            when = f"{t['early_qty']} bis zum {t['early_day']}. Werktag, vollständig bis zum {t['final_day']}. Werktag"
        return f"{t['quantity']} Versandboxen für {euros(t['price'])} einschließlich Lieferung, {when}."

    @staticmethod
    def request_text(terms):
        when = f"Vollständig benötigen wir die Lieferung binnen {terms['final_day']} Werktagen."
        if terms["early_qty"]:
            when = f"Mindestens {terms['early_qty']} davon benötigen wir binnen {terms['early_day']} Werktagen, den Rest binnen {terms['final_day']} Werktagen."
        return f"Wir fragen {terms['quantity']} Versandboxen an. {when}"


class Service:
    key = "service"
    label = "Dienstleistung"
    title = "Wartung der Förderanlage"
    version = "wartung/1.0"
    companies = {"A": "Nordlicht Handel", "B": "Hanse Service"}
    price_note = "inkl. Nebenkosten"
    fields = (Field("hours", "Leistungsumfang", "Stunden", "min"),
              Field("due", "Fertigstellung", "Werktage", "max", 1, 365), PRICE)
    request = {"hours": 16, "due": 8}
    opening = {"hours": 12, "due": 12, "price": 140000}
    public_rule = "Das Paket umfasst Wartungsstunden vor Ort. Der Gesamtpreis enthält alle Nebenkosten. Termine zählen ab beidseitiger Freigabe."
    package_hint = "Mehr Stunden bis zu einem früheren Termin bedeuten mehr Leistung."

    @staticmethod
    def validate(t):
        return None

    @staticmethod
    def effective(t, limits):
        return t

    @staticmethod
    def describe(t):
        return f"{t['hours']} Wartungsstunden für {euros(t['price'])} einschließlich Nebenkosten, abgeschlossen bis zum {t['due']}. Werktag."

    @staticmethod
    def request_text(terms):
        return f"Wir benötigen mindestens {terms['hours']} Stunden Wartung vor Ort, abgeschlossen binnen {terms['due']} Werktagen."


def without_price(t):
    return {k: v for k, v in t.items() if k != "price"}


SCENARIOS = {s.key: s for s in (Boxes, Service)}
STRATEGIES = {"direkt": "Direktes Paket", "stufen": "Schrittweise Konzession"}
STRATEGY_VERSIONS = {k: f"{k}/1.0" for k in STRATEGIES}


def schema(s):
    return {"key": s.key, "label": s.label, "title": s.title, "version": s.version,
            "companies": s.companies, "priceNote": s.price_note, "rule": s.public_rule,
            "fields": [vars(f) for f in s.fields]}
