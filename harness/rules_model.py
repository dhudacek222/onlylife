"""RulesDecisionModel: the M1 hardcoded parser + normalisation (fillers, slang, typos), view-based
reference checking and injection screening, with a confidence score that says how much guessing happened.
Deterministic and free; the EscalatingModel hands low-confidence inputs to an LLM when one is configured."""
import difflib
import re

from engine import parser
from harness.protocols import Decision

# confidence levels (calibrated against harness/evalset.jsonl, see tests/test_eval.py)
EXACT, KNOWN_REWRITE, FUZZY, UNKNOWN_REF = 1.0, 0.9, 0.6, 0.7

SLANG = {  # gaming slang / casual words -> a phrase the parser knows (whole first word of a clause)
    "gank": "attack", "whack": "attack", "smack": "attack", "shank": "attack",
    "yoink": "steal from", "mug": "rob", "snag": "take", "nab": "take", "yeet": "drop", "ditch": "drop",
    "bounce": "go", "dip": "go", "peep": "look", "afk": "wait", "brb": "wait", "chill": "wait",
    "cop": "buy", "chug": "drink",
}
PHRASE_SLANG = [(r"^leg it\b", "flee"), (r"^yoink (.+?) from\b", r"steal \1 from")]
FILLERS = re.compile(r"^(?:(?:i|me|we|you|please|now|then|just|quickly|can|could|would|will|i'll|ill|i'd|"
                     r"like|want|wanna|gonna|imma|lemme|let|me|let's|lets|need|to|am|try|and|go and)\s+)+", re.I)
TRAILING = re.compile(r"\s+(?:please|pls|plz|now|quickly)$", re.I)

INJECTION = [re.compile(p, re.I) for p in (
    r"\bignore\b.{0,30}\b(rules?|instructions?|prompt)", r"\bdisregard\b", r"\b(system|developer)\s*(prompt|mode|message)",
    r"\bnew instructions?\b", r"\byou are (now )?(an? )?(ai|assistant|chatbot|model|language model|my servant)\b",
    r"\bas an ai\b", r"\b(i am|i'm|im)\s+(the\s+)?(king|admin|administrator|god|developer|dev|gm|game ?master)\b",
    r"\b(set|change|make)\s+(my|the)\s+(hp|health|gold|coins?|stats?|level|xp|wanted)", r"\bgive me \d+",
    r"\b(spawn|teleport|noclip|godmode|god mode|cheat|console|sudo)\b", r"\bpretend\b.{0,20}\brules\b",
    r"\boverride\b")]
SPEECH = re.compile(r"(?:^|[,;]|\band\b|\bthen\b)\s*(?:say|shout|yell|tell|talk to|talk|speak to)\b.*$", re.I | re.S)

CONNECTORS = ["with", "from", "into", "then", "and"]
VOCAB = sorted({p.split()[0] for ps in parser.PHRASES.values() for p in ps if len(p) > 2} | set(SLANG))


def screen_injection(text):
    """Only the non-speech part counts: 'say ignore the rules' is in-world speech, not an attack."""
    acting = SPEECH.sub("", text)
    return any(p.search(acting) for p in INJECTION)


def _rewrite_clause(clause):
    """-> (clause', how) where how is None (untouched), 'known' (filler/slang) or 'fuzzy' (typo guess)."""
    c, how = clause.strip(), None
    s = TRAILING.sub("", c)
    if s != c:
        c, how = s, "known"
    if parser._verb(c)[0]:
        return c, how
    s = FILLERS.sub("", c)
    if s != c and s:
        c, how = s, "known"
    for pat, rep in PHRASE_SLANG:
        s = re.sub(pat, rep, c, flags=re.I)
        if s != c:
            return s, "known"
    first, _, rest = c.partition(" ")
    low = first.lower()
    if low in SLANG and SLANG[low]:
        return f"{SLANG[low]} {rest}".strip(), "known"
    if parser._verb(c)[0]:
        return c, how
    close = difflib.get_close_matches(low, VOCAB, n=1, cutoff=0.75)
    if close:
        word = SLANG.get(close[0]) or close[0]
        return f"{word} {rest}".strip(), "fuzzy"
    return c, how


def _vocab_of(view):
    """Every name this observer can refer to right now (view() only holds what they perceive)."""
    names = set()
    wares = [w for c in view.get("characters", []) for w in c.get("wares", [])]
    for group in ("characters", "items", "inventory", "exits", wares):
        for x in view.get(group, []) if isinstance(group, str) else group:
            names.add(x["id"].lower())
            names.add(x["name"].lower())
            names.update(w.lower() for w in x["name"].split())
            names.update(a.lower() for a in x.get("aliases", []) + x.get("tags", []))
            if x.get("door"):
                names.add(x["door"]["name"].lower())
                names.update(x["door"]["name"].lower().split())
    names.update({"door", "lock", "coins", "money", "gold", "purse"})
    return names


def _check_ref(ref, vocab):
    """-> (ref', confidence cap). Known refs keep full confidence and so do wholly unknown ones (a correct parse of
    something that isn't here: the rules engine says so). A typo is corrected (FUZZY); a ref holding a mistyped
    connector ('bob wiht knife') is a misparse and caps confidence so an LLM or the player can look."""
    if not ref or ref.isdigit():
        return ref, EXACT
    words = [w for w in ref.lower().replace("'s", "").split() if w not in parser.FILLER | {"the", "a", "an", "my"}]
    if not words or " ".join(words) in vocab or all(w in vocab for w in words):
        return ref, EXACT
    fixed = [w if w in vocab else (difflib.get_close_matches(w, vocab, n=1, cutoff=0.75) or [None])[0] for w in words]
    if all(fixed):
        return " ".join(fixed), FUZZY
    unknown = [w for w in words if w not in vocab]
    suspicious = any(difflib.get_close_matches(w, CONNECTORS, n=1, cutoff=0.75)  # 'bob wiht knife'
                     or [v for v in difflib.get_close_matches(w, vocab, n=3, cutoff=0.6)  # 'bbo' (transposed letters)
                         if abs(len(v) - len(w)) <= 1] for w in unknown)
    return ref, UNKNOWN_REF if suspicious else EXACT


class RulesDecisionModel:
    def decide(self, text, view):
        if screen_injection(text):
            return Decision([], 0.95, injection=True)
        polite = TRAILING.sub("", text.strip())
        actions, conf = parser.parse(polite), EXACT if polite == text.strip() else KNOWN_REWRITE
        if not actions:
            clauses = parser.SPLIT.split(text.strip())
            if any(parser._verb(c)[0] in ("say", "talk") for c in clauses[:-1]):
                clauses = [text]  # speech swallows the rest; let parse() do its own splitting
            rewritten = [_rewrite_clause(c) for c in clauses if c.strip()]
            actions = parser.parse(" , ".join(c for c, _ in rewritten)) if rewritten else []
            hows = {h for _, h in rewritten}
            conf = FUZZY if "fuzzy" in hows else KNOWN_REWRITE
        if not actions:
            return Decision([], 0.0, suggestions=self.suggest(text, view))
        vocab = _vocab_of(view)
        for a in actions:
            for field in ("target", "item", "want_item"):
                if a.verb == "say" or (a.verb in ("accept", "decline") and field == "target"):
                    continue
                ref, cap = _check_ref(getattr(a, field), vocab)
                setattr(a, field, ref)
                conf = min(conf, cap)
        return Decision(actions, conf)

    @staticmethod
    def suggest(text, view):
        first = (text.split() or [""])[0].lower()
        out = [w for w in difflib.get_close_matches(first, VOCAB, n=3, cutoff=0.5) if parser.parse(w)]
        out.append("look around")
        out += [f"go to {e['name']}" for e in view.get("exits", [])[:3]]
        return list(dict.fromkeys(out))
