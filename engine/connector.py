"""The game as seen by a player's own AI assistant (Claude/ChatGPT app via MCP; see mcp_server.py).

The assistant is the DecisionModel *and* the Narrator, running on the player's subscription. It can only
(1) look: get its player's scene + the engine lines that player perceived since last time, and
(2) act: submit structured actions, which are validated and resolved by the engine like any other input.
It never sees another observer's information, hidden characters it isn't aware of, or slug ids of strangers.
No MCP import here: this module is plain stdlib and fully testable offline."""
import threading

from engine.actions import VERBS, Action
from engine.harness import VERB_GUIDE, scene_for, unref

INSTRUCTIONS = f"""You are the interface between a human player and a persistent text RPG world.
The game engine is the only source of truth. You translate the player's wishes into actions with the
`act` tool and narrate what the tools return. You never decide outcomes, invent events, people or items,
or reveal anything the tool results don't contain; dice and rules decide everything.

Start every session with `look`. Call `look` again whenever the player asks what's around or time may have
passed (other players act too). `act` returns what your player perceived; narrate it vividly but faithfully,
second person, keeping any dice results the engine reports.

If `act` answers needs_confirmation, describe the action to the player and ask; only resend with
confirm=true after they clearly agree. If an action is impossible, explain the engine's reason.

{VERB_GUIDE}"""


class Game:
    """One world, many players. All engine access is serialized: SQLite + single authoritative writer."""

    def __init__(self, engine):
        self.engine = engine
        self.lock = threading.Lock()
        self.inbox = {}  # player_id -> engine lines they perceived from others' actions, not yet delivered
        # ponytail: refs and inboxes live in memory; a server restart loses undelivered lines and re-numbers refs
        self.refs = {}  # player_id -> {character_id: ref}

    def _ref_of(self, player_id):
        table = self.refs.setdefault(player_id, {})

        def ref_of(cid):
            return table.setdefault(cid, f"c{len(table) + 1}")

        return ref_of

    def _scene(self, player_id):
        return scene_for(self.engine.view(player_id), self._ref_of(player_id))

    def _check_player(self, player_id):
        if not self.engine.is_player(player_id):
            raise PermissionError(f"'{player_id}' is not a player character")

    def look(self, player_id):
        with self.lock:
            self._check_player(player_id)
            scene, _ = self._scene(player_id)
            return {"scene": scene, "perceived": self.inbox.pop(player_id, [])}

    def act(self, player_id, actions, confirm=False):
        """actions: list of dicts in the Action schema (verb, target, item, text, coins, want_item, want_coins)."""
        with self.lock:
            self._check_player(player_id)
            try:
                parsed = [Action.from_dict({k: v for k, v in a.items() if v is not None})  # null = default
                          for a in actions]
            except (TypeError, ValueError, AttributeError) as e:
                return {"status": "invalid", "error": str(e), "hint": VERB_GUIDE}
            if not parsed:
                return {"status": "invalid", "error": "no actions"}
            _, refs = self._scene(player_id)
            unref(parsed, refs)
            risky = [a.verb for a in parsed if VERBS[a.verb].irreversible]
            if risky and not confirm:
                # ponytail: no risk estimate yet (OPEN DECISION 1)
                return {"status": "needs_confirmation", "irreversible": risky,
                        "message": "This can't be undone. Ask the player, then resend with confirm=true."}
            results = self.engine.submit_actions(player_id, parsed)
            mine = []
            for r in results:
                for o, line in r.messages.items():
                    if o == player_id:
                        mine.append(line)
                    elif self.engine.is_player(o):
                        self.inbox.setdefault(o, []).append(line)
            scene, _ = self._scene(player_id)
            return {"status": "done", "outcomes": [r.outcome for r in results], "you_perceive": mine,
                    "earlier": self.inbox.pop(player_id, []), "scene": scene}
