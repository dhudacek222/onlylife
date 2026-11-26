"""Narrators. TemplateNarrator is the free, deterministic default (button actions, tests);
an LLM narrator gets exactly the same per-observer facts and nothing else."""

YOU = {
    "move": "You go to {target}.", "flee": "You flee to {target}.", "flee:failure": "You try to flee.",
    "look": "You look around.", "take": "You take {item}.", "drop": "You drop {item}.",
    "give": "You give {item} to {target}.", "buy": "You buy {item} from {target} for {price} coins.",
    "offer": "You offer {target} {deal} (trade #{trade}).", "accept": "You accept trade #{trade} from {target}.",
    "accept:failure": "Trade #{trade} with {target} falls through.", "decline": "You decline trade #{trade}.",
    "attack": "You hit {target}{with} for {damage} damage.", "attack:failure": "You attack {target}{with}.",
    "steal": "You steal {loot} from {target}.", "steal:failure": "You try to steal from {target}.",
    "sneak": "You slip out of sight.", "unhide": "You step out of hiding.",
    "open": "You open {target}.", "close": "You close {target}.", "lock": "You lock {target}.",
    "unlock": "You unlock {target}.", "unlock:failure": "You try to pick {target}.",
    "force": "You force {target} open.", "force:failure": "You throw yourself against {target}.",
    "talk": 'You say to {target}: "{text}"', "say": 'You say: "{text}"', "use": "You use {item}.",
    "wait": "You wait.",
}
THEM = {
    "move": "{actor} goes to {target}.", "flee": "{actor} flees to {target}.",
    "flee:failure": "{actor} tries to flee but can't get away.", "look": "{actor} looks around.",
    "take": "{actor} takes {item}.", "drop": "{actor} drops {item}.", "give": "{actor} gives {item} to {target}.",
    "buy": "{actor} buys {item} from {target}.", "offer": "{actor} offers {target} {deal} (trade #{trade}).",
    "accept": "{actor} accepts a trade from {target}.",
    "accept:failure": "A trade between {actor} and {target} falls through.",
    "decline": "{actor} declines a trade with {target}.",
    "attack": "{actor} hits {target}{with} for {damage} damage.", "attack:failure": "{actor} attacks {target}{with} and misses.",
    "steal": "{actor} steals {loot} from {target}.", "steal:failure": "{actor} tries to steal from {target}!",
    "sneak": "{actor} tries to slip out of sight, but you keep track of them.",
    "unhide": "{actor} steps out of hiding.", "open": "{actor} opens {target}.", "close": "{actor} closes {target}.",
    "lock": "{actor} locks {target}.", "unlock": "{actor} unlocks {target}.",
    "unlock:failure": "{actor} fiddles with the lock of {target}.",
    "force": "CRASH! {actor} forces {target} open.", "force:failure": "BANG! {actor} throws themselves against {target}.",
    "talk": '{actor} says to {target}: "{text}"', "say": '{actor} says: "{text}"', "use": "{actor} uses {item}.",
    "wait": "{actor} waits.",
}


class _Blank(dict):
    def __missing__(self, key):
        return ""


def _cap(s):
    return s[:1].upper() + s[1:]


class TemplateNarrator:
    def narrate(self, facts):
        f = _Blank(facts)
        f["item"] = f"the {facts['item']}" if facts.get("item") else ""
        f["loot"] = f"{facts['coins']} coins" if facts.get("coins") is not None else f["item"]
        f["with"] = (f" with the {facts['weapon']}" if facts.get("weapon")
                     else " barehanded" if facts["verb"] == "attack" else "")
        table = YOU if facts["you_acted"] else THEM
        key = f"{facts['verb']}:failure" if facts["outcome"] == "failure" else facts["verb"]
        text = table.get(key, table[facts["verb"]]).format_map(f)
        if facts.get("killed"):
            text += " You die." if facts["target_is_you"] else f" {_cap(facts['target'])} dies."
        if facts["you_acted"]:
            text += f" {facts['reason']}" if facts.get("reason") else "".join(f" ({r})" for r in facts.get("rolls", []))
            if facts.get("found"):
                text += " You spot " + ", ".join(facts["found"]) + "!"
            if facts.get("healed") is not None:
                text += f" You recover {facts['healed']} hp."
            if facts.get("scene"):
                text += " " + facts["scene"]
        return _cap(text)
