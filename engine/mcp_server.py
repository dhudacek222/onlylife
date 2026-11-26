"""MCP server: lets players play from their own Claude / ChatGPT app (their subscription runs the AI).

    pip install "mcp>=2,<3"
    python -m engine.mcp_server --db world.db --player player                      # stdio (local clients)
    python -m engine.mcp_server --db world.db --player player --http --port 8000   # remote connector URL /mcp

ponytail: one player per server process and no authentication. Before anyone else can reach the URL,
M5 must add per-player auth (MCP OAuth) and map the token to a character id."""
import argparse
import os

from mcp.server.mcpserver import MCPServer  # mcp 2.x; the one non-stdlib import, only this module needs it

from engine import fixtures
from engine.connector import INSTRUCTIONS, Game
from engine.engine import Engine


def build(game, player_id):
    mcp = MCPServer("ReadyOne", instructions=INSTRUCTIONS)

    @mcp.tool()
    def look() -> dict:
        """What your character perceives right now, plus what they noticed others do since you last looked."""
        return game.look(player_id)

    @mcp.tool()
    def act(actions: list[dict], confirm: bool = False) -> dict:
        """Attempt one or more actions, in order (a failed one stops the rest). Each action is an object:
        {"verb": ..., "target": ..., "item": ..., "text": ..., "coins": 0, "want_item": ..., "want_coins": 0}.
        Outcomes come from the engine's dice and rules, never from you. Irreversible verbs need confirm=true,
        which you may send only after the player agreed."""
        return game.act(player_id, actions, confirm)

    return mcp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="world.db")
    ap.add_argument("--player", default="player")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    eng = Engine.open(args.db) if os.path.exists(args.db) else Engine.create(args.db, seed=args.seed,
                                                                             world=fixtures.MILL_STREET)
    server = build(Game(eng), args.player)
    if args.http:
        server.run("streamable-http", host=args.host, port=args.port)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
