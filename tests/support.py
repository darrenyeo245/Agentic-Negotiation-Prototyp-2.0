"""Simulated Claude API clients. The AI agents run their real code path; only the network is replaced."""
import json
from types import SimpleNamespace

from paktwerk.claude import ClaudeAgents


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
        return SimpleNamespace(stop_reason="end_turn", model=request["model"],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=50, iterations=None),
                               content=[SimpleNamespace(type="thinking", thinking=""),
                                        SimpleNamespace(type="text", text=json.dumps(reply))])

    def seen(self):
        return json.dumps([[r["system"], r["messages"]] for r in self.requests], default=str, ensure_ascii=False)


def scripted(buyer=(), seller=()):
    """Two Claude agents, one per company, whose API clients answer with the given turns in order."""
    clients = {"A": Client(*buyer), "B": Client(*seller)}
    return ClaudeAgents(clients=clients), clients
