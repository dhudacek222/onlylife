"""M1 hardcoded parser: text -> list[Action]. Replaced by a DecisionModel in M2.
Returns [] when any clause is not understood (the engine then reports "unparsed" and consumes nothing)."""
import re

from engine.actions import Action

PHRASES = {  # verb -> phrases that start a clause; outcome words map to intents ("kill" -> attack)
    "move": ["go to", "go into", "go", "walk to", "walk", "move to", "move", "enter", "head to", "travel to"],
    "look": ["look around", "look", "l", "search", "examine", "scan"],
    "take": ["pick up", "take", "grab", "get", "snatch", "loot"],
    "drop": ["put down", "drop", "discard"],
    "give": ["give", "hand"],
    "buy": ["buy", "purchase"],
    "offer": ["offer", "trade"],
    "accept": ["accept"],
    "decline": ["decline", "refuse", "reject"],
    "attack": ["attack", "kill", "murder", "stab", "hit", "punch", "strike", "slay", "fight"],
    "steal": ["steal", "pickpocket", "rob", "pinch"],
    "sneak": ["sneak", "hide"],
    "unhide": ["stop hiding", "unhide", "come out"],
    "open": ["open"],
    "close": ["close", "shut"],
    "unlock": ["unlock"],
    "lock": ["lock"],
    "force": ["force", "break open", "break", "kick in", "kick", "bash"],
    "talk": ["talk to", "speak to", "talk", "tell"],
    "say": ["say", "shout", "yell"],
    "use": ["use", "drink", "quaff", "eat", "apply"],
    "flee": ["flee", "run away", "run", "escape"],
    "wait": ["wait", "rest"],
}
# longest phrase first so "pick up" beats nothing and "go to" beats "go"
TABLE = sorted(((p.split(), v) for v, ps in PHRASES.items() for p in ps), key=lambda pv: -len(pv[0]))
SPLIT = re.compile(r"\s*(?:,|;|\band then\b|\bthen\b|\band\b)\s*", re.I)
FILLER = {"i", "please", "try", "to"}


def _verb(clause):
    words = clause.split()
    while words and words[0].lower() in FILLER:
        words = words[1:]
    low = [w.lower() for w in words]
    for phrase, verb in TABLE:
        if low[:len(phrase)] == phrase:
            return verb, " ".join(words[len(phrase):])
    return None, ""


def _goods(s):
    """'5 coins' -> (None, 5); 'knife' -> ('knife', 0); None -> (None, 0)."""
    if not s:
        return None, 0
    m = re.fullmatch(r"(\d+)\s*(?:coins?|gold)?", s.strip())
    return (None, int(m.group(1))) if m else (s.strip(), 0)


def _clause(clause):
    verb, rest = _verb(clause)
    if not verb:
        return None
    r = rest.lower().strip(" .!?")
    a = Action(verb, raw=clause.strip())
    if verb == "say":
        a.text = rest.strip().strip('"')
        return a
    if verb == "talk":  # "talk to bob: hello" / "tell bob hello"
        who, text = _talk(rest)
        a.target, a.text = who.lower().strip(), text.strip().strip('"')
        return a
    if verb in ("move", "flee"):
        a.target = re.sub(r"^(to|into|in|towards?)\s+", "", r) or None
    elif verb in ("take", "drop", "use"):
        a.item = re.split(r"\s+from\s+", r)[0] or None
    elif verb == "give":
        m = re.fullmatch(r"(.+?)\s+to\s+(.+)", r)
        a.item, a.target = (m.group(1), m.group(2)) if m else (r or None, None)
    elif verb == "buy":
        m = re.fullmatch(r"(.+?)\s+from\s+(.+)", r)
        a.item, a.target = (m.group(1), m.group(2)) if m else (r or None, None)
    elif verb == "attack":
        m = re.fullmatch(r"(.+?)\s+with\s+(.+)", r)
        a.target, a.item = (m.group(1), m.group(2)) if m else (r or None, None)
    elif verb == "steal":  # "steal watch from bob" / "steal from bob" / "rob bob"
        m = re.fullmatch(r"(?:(.+?)\s+)?from\s+(.+)", r)
        a.item, a.target = (m.group(1), m.group(2)) if m else (None, r or None)
    elif verb in ("open", "close", "unlock", "lock", "force"):
        a.target = re.split(r"\s+with\s+", r)[0] or None
    elif verb == "offer":  # "offer knife to bob for 5 coins"
        m = re.fullmatch(r"(.+?)\s+to\s+(\S+)(?:\s+for\s+(.+))?", r)
        if not m:
            return None
        (a.item, a.coins), a.target, (a.want_item, a.want_coins) = _goods(m.group(1)), m.group(2), _goods(m.group(3))
    elif verb in ("accept", "decline"):  # "accept", "accept trade #3", "accept offer from bob", "accept bob's offer"
        words = [w for w in re.findall(r"[a-z0-9_]+", r.replace("'s", "")) if w not in ("the", "offer", "trade", "from", "deal")]
        a.target = words[0] if words else None
    return a


def _talk(rest):
    rest = re.sub(r"^(to|with)\s+", "", rest.strip(), flags=re.I)
    if ":" in rest:
        who, text = rest.split(":", 1)
    else:
        who, _, text = rest.partition(" ")
    return who, text or "Hello."


def parse(text):
    clauses, rest = [], text.strip()
    while rest:
        head, *tail = SPLIT.split(rest, maxsplit=1)
        if _verb(head)[0] in ("say", "talk"):  # speech swallows the rest, "and" included
            clauses.append(rest)
            break
        if head:
            clauses.append(head)
        rest = tail[0] if tail else ""
    actions = [_clause(c) for c in clauses]
    return actions if actions and all(actions) else []
