"""Conservative action permission independent of any model-generated instruction."""

import re


def action_policy(message: str, explicit: bool = False) -> dict:
    text = message.casefold().replace("don't", "do not").replace("’", "'")
    # Negation wins even if the caller sends prepare_actions=True.
    denied = bool(
        re.search(
            r"(?:\bdo not\b|\bnever\b|\bwithout\b|\bno\b|\bnot to\b|\bdon\x27t\b|\bne pas\b|\bsans\b|\baucun\b)[^.;\n]{0,100}"
            r"(?:action|task|write|creat|cr[eé]er|t[aâ]che|propos)",
            text,
        )
    )
    denied = denied or bool(
        re.search(r"(?:read.only|recommendations? only|analysis only|lecture seule)", text)
    )
    requested = explicit or bool(
        re.search(r"(?:prepare|create|follow.up|pr[eé]par)[^.;\n]{0,80}(?:action|task|t[aâ]che)", text)
    )
    return {
        "allow_proposals": bool(requested and not denied),
        "explicitly_suppressed": denied,
        "reason": "User prohibited writes/proposals" if denied else "Drafts require separate human approval",
    }


def selected_customers(message, catalogue, explicit=None):
    ids = list(dict.fromkeys(re.findall(r"\bC\d{3}\b", message.upper())))
    if explicit and explicit not in ids:
        ids.insert(0, explicit)
    for customer in catalogue:
        if customer["name"].casefold() in message.casefold() and customer["id"] not in ids:
            ids.append(customer["id"])
    known = {c["id"] for c in catalogue}
    if any(cid not in known for cid in ids):
        raise KeyError("Unknown customer in request")
    return ids
