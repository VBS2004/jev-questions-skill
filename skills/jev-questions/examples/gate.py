#!/usr/bin/env python3
"""A small System One gate showing the shape SKILL.md argues for. Standard library only.

    OPENROUTER_API_KEY=... python examples/gate.py "My card was charged twice and I need it fixed today"
    python examples/gate.py --dry "..."          # canned answers, no key, no request

The domain is support-ticket triage; the structure is the point:

  * §1  criteria describe situations, never words
  * §3  a Choice has an escape option; Nouls and the Choice are never compared
  * §5  every question about one message goes in ONE request
  * §7  `judge` returns what the model said; `verdict` applies thresholds, separately, so
        recalibrating never invalidates stored judgments. The policy is ordered by
        repairability: check what can never be fine first, then what a caller can fix.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"  # pinned: a threshold tuned on one version is not valid on the next
NONE = "none_of_these"
TOPICS = ["billing", "bug", "how_to", "feature_request"]


def noul(instructions: str, true: str, false: str) -> dict:
    return {"type": "noul", "instructions": instructions,
            "criteria": {"true": true, "false": false}}


QUESTIONS = {
    # Situations, not words: nothing here lists phrases a ticket might contain.
    "is_not_a_request": noul(
        "Is `ticket.text` something other than a person asking for help with the product?",
        true="Advertising, a bulk or automated message, or abuse with no problem behind it",
        false="A person describing a problem or asking for something, however rudely"),
    "needs_account_access": noul(
        "Does resolving `ticket.text` require looking at or changing the sender's own "
        "account or payments?",
        true="Resolving it requires seeing or changing this person's own account or payments",
        false="It can be answered or fixed from general knowledge about the product"),
    "is_urgent": noul(
        "Does `ticket.text` describe something that is costing the sender money or work "
        "right now, rather than something merely inconvenient?",
        true="Something is currently broken or charged wrongly and the sender is blocked or losing money",
        false="A question, a wish, or a problem the sender can live with for a few days"),
    # A Choice over options code enumerated, with an escape: it must not pick the least-bad.
    "topic": {"type": "choice",
              "instructions": "What is `ticket.text` mainly about? Choose `none_of_these` if "
                              "it fits none of the listed topics.",
              "criteria": {**{t: None for t in TOPICS}, NONE: "It fits none of these topics"}},
}

# Thresholds live here and only here. They are guesses until calibrated on labeled tickets
# (scripts/threshold.py); changing one must not require re-asking the model.
THRESHOLDS = {"is_not_a_request": 0.5, "needs_account_access": 0.5, "is_urgent": 0.5,
              "topic_min_weight": 0.5}


def ask_openrouter(state: dict, questions: dict) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("set OPENROUTER_API_KEY, or use --dry")
    body = json.dumps({"model": MODEL, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["answers"]


def canned(state: dict, questions: dict) -> dict:
    """Plausible answers for --dry, so the policy below can be read and run offline."""
    text = state["ticket"]["text"].lower()
    charged = "charge" in text
    return {
        "is_not_a_request": {"type": "noul", "noul": 0.04},
        "needs_account_access": {"type": "noul", "noul": 0.9 if charged else 0.2},
        "is_urgent": {"type": "noul", "noul": 0.8 if "today" in text else 0.2},
        "topic": {"type": "choice", "choice": "billing" if charged else NONE,
                  "probabilities": {"billing": 0.9, "bug": 0.05, "how_to": 0.02,
                                    "feature_request": 0.02, NONE: 0.01}
                  if charged else {"billing": 0.1, "bug": 0.1, "how_to": 0.1,
                                   "feature_request": 0.1, NONE: 0.6}},
    }


def judge(ticket: str, ask) -> dict:
    """What the model said. No decisions: the raw numbers, ready to store and re-threshold."""
    answers = ask({"ticket": {"text": ticket}}, QUESTIONS)  # one request, every question
    return {
        "is_not_a_request": answers["is_not_a_request"]["noul"],
        "needs_account_access": answers["needs_account_access"]["noul"],
        "is_urgent": answers["is_urgent"]["noul"],
        "topic": answers["topic"]["choice"],
        "topic_weights": answers["topic"]["probabilities"],
    }


def verdict(j: dict, t: dict = THRESHOLDS) -> dict:
    """Policy over a judgment. Ordered by repairability: irreparable first, then fixable."""
    if j["is_not_a_request"] >= t["is_not_a_request"]:
        return {"action": "drop", "why": "not a request; nothing a reply could fix"}
    topic = j["topic"] if (j["topic"] != NONE
                           and j["topic_weights"].get(j["topic"], 0) >= t["topic_min_weight"]) else None
    todo = []  # what a caller can fix, returned as instructions rather than a bare no
    if topic is None:
        todo.append("ask which area this is about")
    if j["needs_account_access"] >= t["needs_account_access"]:
        todo.append("verify the sender before touching their account")
    return {"action": "escalate" if j["is_urgent"] >= t["is_urgent"] else "queue",
            "topic": topic, "todo": todo}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ticket")
    ap.add_argument("--dry", action="store_true", help="canned answers; no key, no request")
    a = ap.parse_args(argv)
    j = judge(a.ticket, canned if a.dry else ask_openrouter)
    print(json.dumps({"judgment": j, "verdict": verdict(j)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
