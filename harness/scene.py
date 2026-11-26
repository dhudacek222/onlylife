"""What an outside model may know: the acting player's view with opaque character refs, and the verb guide.
Used by the MCP connector, where the player's own AI is decision model and narrator."""

VERB_GUIDE = """Verbs and their fields (unused fields are null, coins 0):
- move(target=destination exit), flee(target=destination exit), look, wait
- take(item), drop(item), use(item)            e.g. drink/eat/apply -> use
- give(item, target), buy(item, target=merchant or null)
- offer(target, item and/or coins, want_item and/or want_coins), accept(target=trade number or person or null), decline(same)
- attack(target, item=weapon or null)          outcome words become intents: "kill/stab/murder X" -> attack(X)
- steal(target, item or null for coins)        "rob/pickpocket X" -> steal(X)
- sneak (hide), unhide
- open/close/unlock/lock/force(target=door or the place it leads to)
- talk(target, text), say(text)
Refer to characters by their `ref` from the scene (or a name the player knows); items and exits by name."""


def scene_for(view, ref_of=None):
    """The acting player's view with character ids replaced by opaque refs (default c1, c2, ... per call).
    Slug ids would name strangers the player has never been introduced to. `ref_of(cid)` supplies refs
    that stay stable across calls (the MCP connector needs that: someone may arrive between look and act)."""
    if ref_of is None:
        n = iter(range(1, 1 << 30))
        ref_of = lambda cid: f"c{next(n)}"  # noqa: E731
    refs, chars = {}, []
    for c in view["characters"]:
        ref = ref_of(c["id"])
        refs[ref] = c["id"]
        chars.append({"ref": ref, "name": c["name"], "status": c["status"]})
    scene = {
        "location": view["location"]["name"],
        "exits": [e["name"] + (f" (through the {e['door']['name']})" if e["door"] else "") for e in view["exits"]],
        "characters": chars,
        "items_here": [i["name"] for i in view["items"]],
        "inventory": [i["name"] for i in view["inventory"]],
        "coins": view["you"]["coins"],
        "hidden": view["you"]["hidden"],
    }
    return scene, refs


def unref(actions, refs):
    for a in actions:
        if a.target in refs:
            a.target = refs[a.target]
    return actions
