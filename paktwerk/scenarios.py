"""Public scenario descriptions, package semantics and clarification grammar."""
import re
from dataclasses import dataclass
from decimal import Decimal


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
WORDS = {"ein": 1, "einen": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
         "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "vierzig": 40}
NUMBER = r"(?:[0-9]{1,5}|" + "|".join(WORDS) + r")"


def number(word):
    return int(word) if word.isdecimal() else WORDS[word]


def explicit_price(sentence):
    match = re.fullmatch(
        r"(?:der )?gesamtpreis(?: inkl(?:usive|\.)? (?:der )?(?:lieferung|nebenkosten))?"
        r"(?: beträgt| liegt bei| ist|:)?\s*(\d{1,6}(?:[,.]\d{1,2})?)\s*(?:€|euro)"
        r"(?: (?:inklusive|einschließlich) (?:lieferung|nebenkosten))?", sentence)
    return {"price": int(Decimal(match[1].replace(",", ".")) * 100)} if match else {}


def working_facts(s, text, known):
    """Merge explicit clauses, reopening terms that were qualified or contradicted."""
    facts = dict(known)
    seen, disputed = {}, set()
    for clause in re.split(r"(?<!inkl\.)(?<!\d\.)(?<=[.!?])\s+(?=[A-ZÄÖÜ])", text.strip()):
        parsed = s.facts(clause)
        uncertain = re.search(r"\b(?:nicht|kein\w*|vielleicht|eventuell|unklar|offen|falls|wenn|vorbehalt|unverbindlich)\b", clause, re.I)
        if uncertain:
            for key, pattern in s.references.items():
                if re.search(pattern, clause, re.I):
                    facts.pop(key, None)
        for key, value in parsed.items():
            if key in seen and seen[key] != value:
                disputed.add(key)
            seen[key] = facts[key] = value
    return {k: v for k, v in facts.items() if k not in disputed}


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
    focus = ("early_qty", "early_day", "price")
    timing = ("early_day", "final_day")
    references = {"early_qty": r"stück|boxen|teilmenge", "early_day": r"werktag|termin",
                  "price": r"preis|kosten|euro|€"}
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

    @staticmethod
    def facts(text):
        # Only affirmative, fully matched clauses become working facts.
        normalized = " ".join(text.lower().strip().rstrip(".!").split())
        prefix = r"(?:(?:wir (?:können|bestätigen|liefern|schaffen):?|ja,?) )?"
        qty = rf"({NUMBER})\s*(?:stück|boxen|versandboxen)"
        day = rf"(?:binnen|in|innerhalb von|spätestens in) ({NUMBER}) werktag(?:en|e)?"
        match = re.fullmatch(prefix + qty + " " + day + r"(?: (?:früher )?liefern| liefern wir| sind möglich)?", normalized)
        if match:
            return {"early_qty": number(match[1]), "early_day": number(match[2])}
        match = re.fullmatch(prefix + qty + r" (?:früher liefern|als teillieferung(?: liefern)?)", normalized)
        if match:
            return {"early_qty": number(match[1])}
        match = re.fullmatch(r"(?:die )?teillieferung (?:erfolgt |liefern wir )?" + day, normalized)
        if match:
            return {"early_day": number(match[1])}
        return explicit_price(normalized)

    @staticmethod
    def question(missing):
        names = {"early_qty": "die genaue Teilmenge", "early_day": "den Liefertermin in Werktagen",
                 "price": "den Gesamtpreis inklusive Lieferung"}
        return question_for(names, missing)


class Service:
    key = "service"
    label = "Dienstleistung"
    title = "Wartung der Förderanlage"
    version = "wartung/1.0"
    companies = {"A": "Nordlicht Handel", "B": "Hanse Service"}
    price_note = "inkl. Nebenkosten"
    fields = (Field("hours", "Leistungsumfang", "Stunden", "min"),
              Field("due", "Fertigstellung", "Werktage", "max", 1, 365), PRICE)
    focus = ("hours", "due", "price")
    timing = ("due",)
    references = {"hours": r"stunden|umfang", "due": r"werktag|termin", "price": r"preis|kosten|euro|€"}
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

    @staticmethod
    def facts(text):
        sentence = text.lower().strip().rstrip(".!").strip()
        m = re.fullmatch(rf"(?:wir bieten )?({NUMBER}) (?:wartungsstunden|stunden) (?:binnen|in) ({NUMBER}) werktagen", sentence)
        return {"hours": number(m[1]), "due": number(m[2])} if m else explicit_price(sentence)

    @staticmethod
    def question(missing):
        return question_for({"hours": "den Leistungsumfang in Stunden", "due": "den Fertigstellungstermin",
                             "price": "den Gesamtpreis inklusive Nebenkosten"}, missing)


def question_for(names, missing):
    if not missing:
        return "Können Sie die besprochenen Konditionen als vollständiges Angebot einstellen?"
    labels = [names[k] for k in missing]
    phrase = ", ".join(labels[:-1]) + " und " + labels[-1] if len(labels) > 1 else labels[0]
    return f"Können Sie uns {phrase} bestätigen?"


def without_price(t):
    return {k: v for k, v in t.items() if k != "price"}


SCENARIOS = {s.key: s for s in (Boxes, Service)}
STRATEGIES = {"direkt": "Direktes Paket", "stufen": "Schrittweise Konzession"}
STRATEGY_VERSIONS = {k: f"{k}/1.0" for k in STRATEGIES}


def schema(s):
    return {"key": s.key, "label": s.label, "title": s.title, "version": s.version,
            "companies": s.companies, "priceNote": s.price_note, "rule": s.public_rule,
            "fields": [vars(f) for f in s.fields]}
