"""Action schema: verb metadata and the Action / Roll / Result records."""
from dataclasses import asdict, dataclass, field, fields
from typing import NamedTuple


class Verb(NamedTuple):
    irreversible: bool = False  # M2 asks for confirmation
    hostile: bool = False  # ends the actor's hiding
    crime: str | None = None  # crime the verb always is; move/take add trespass/burglary/theft by context


VERBS = {
    "move": Verb(), "look": Verb(), "take": Verb(), "drop": Verb(),
    "give": Verb(irreversible=True), "buy": Verb(irreversible=True),
    "offer": Verb(), "accept": Verb(irreversible=True), "decline": Verb(),
    "attack": Verb(True, True, "assault"), "steal": Verb(True, False, "theft"),
    "sneak": Verb(), "unhide": Verb(),
    "open": Verb(), "close": Verb(), "unlock": Verb(), "lock": Verb(), "force": Verb(True, True),
    "talk": Verb(), "say": Verb(), "use": Verb(irreversible=True), "flee": Verb(), "wait": Verb(),
}


@dataclass
class Action:
    verb: str
    target: str | None = None  # character, door, destination or trade ref
    item: str | None = None
    text: str | None = None
    coins: int = 0  # offer: coins given
    want_item: str | None = None  # offer: item wanted in return
    want_coins: int = 0
    raw: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        """Strict: unknown verbs or fields raise ValueError (AI output is untrusted input)."""
        names = {f.name for f in fields(cls)}
        if set(d) - names:
            raise ValueError(f"unknown action fields: {sorted(set(d) - names)}")
        if d.get("verb") not in VERBS:
            raise ValueError(f"unknown verb: {d.get('verb')!r}")
        a = cls(**d)
        for f in ("target", "item", "text", "want_item", "raw"):
            v = getattr(a, f)
            if v is not None and not isinstance(v, str):
                raise ValueError(f"{f} must be a string")
        for f in ("coins", "want_coins"):
            v = getattr(a, f)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(f"{f} must be a non-negative integer")
        return a


@dataclass
class Roll:
    id: int
    purpose: str
    sides: int
    raw: list
    mode: str
    modifier: int
    total: int
    dc: int | None
    success: bool | None

    def __str__(self):
        mode = "" if self.mode == "normal" else f" {self.mode}"
        dc = "" if self.dc is None else f" vs DC {self.dc}"
        return f"{self.purpose} d{self.sides}{self.raw}{mode} {self.modifier:+d} = {self.total}{dc}"


@dataclass
class Result:
    action: Action
    outcome: str  # success | failure | impossible | ambiguous | unparsed | skipped
    reason: str = ""
    missing: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    rolls: list = field(default_factory=list)
    event_id: int | None = None
    messages: dict = field(default_factory=dict)
