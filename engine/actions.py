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
        return {k: v for k, v in asdict(self).items() if v not in (None, 0, "")}

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def to_command(a):
    """Canonical text the hardcoded parser maps back to exactly this action (used for buttons)."""
    t, i = a.target or "", a.item or ""
    if a.verb in ("say",):
        return f'say "{a.text}"'
    if a.verb == "talk":
        return f"talk to {t}: {a.text}"
    if a.verb in ("move", "flee"):
        return f"{'go to' if a.verb == 'move' else 'flee to'} {t}"
    if a.verb in ("take", "drop", "use"):
        return f"{a.verb} {i}"
    if a.verb == "give":
        return f"give {i} to {t}"
    if a.verb == "buy":
        return f"buy {i}" + (f" from {t}" if t else "")
    if a.verb == "attack":
        return f"attack {t}" + (f" with {i}" if i else "")
    if a.verb == "steal":
        return f"steal {i} from {t}" if i else f"steal from {t}"
    if a.verb == "offer":
        give = i or f"{a.coins} coins"
        want = a.want_item or (f"{a.want_coins} coins" if a.want_coins else "")
        return f"offer {give} to {t}" + (f" for {want}" if want else "")
    if a.verb in ("open", "close", "unlock", "lock", "force", "accept", "decline"):
        return f"{a.verb} {t}".strip()
    return a.verb  # look, sneak, unhide, wait


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
    outcome: str  # success | failure | impossible | ambiguous | unparsed | skipped | refused | confirm | clarify
    reason: str = ""
    missing: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    rolls: list = field(default_factory=list)
    event_id: int | None = None
    messages: dict = field(default_factory=dict)
    alternatives: list = field(default_factory=list)  # buttons: [{"label": str, "command": str, "confirm"?: bool}]
