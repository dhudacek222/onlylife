# Set up on your PC

Needs Python 3.11+ (https://www.python.org/downloads/ — on Windows tick "Add python.exe to PATH") and git.

```
git clone https://github.com/dhudacek222/onlylife.git
cd onlylife
git checkout ccr-dc99b96c-k0zz4a
python -m pip install -r requirements.txt
python -m pytest -q
```
All tests should pass.

## Play in the terminal (no AI)
```
python -m engine
```
Try: `look`, `take knife`, `hide`, `steal from bob`, `go to street`. `:q` quits.

## Play from Claude or ChatGPT with your own subscription
1. Start the game server (the world is saved in `world.db`; delete the file for a fresh world):
   ```
   python -m engine.mcp_server --db world.db --http
   ```
   It listens on `http://127.0.0.1:8000/mcp`.
2. Claude and ChatGPT connect from their cloud, so the server needs a public HTTPS URL.
   Easiest: Cloudflare quick tunnel (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/):
   ```
   cloudflared tunnel --url http://127.0.0.1:8000
   ```
   It prints `https://<random>.trycloudflare.com`. Your connector URL is that plus `/mcp`.
3. Add the connector:
   - Claude: Settings → Connectors → Add custom connector → paste the URL.
   - ChatGPT: Settings → Apps & Connectors → enable developer mode → create a connector with the URL.
4. In a new chat, enable the connector and say: "Let's play. Look around."

**Warning:** there is no login yet. Anyone with the tunnel URL plays as your character. Close the tunnel
(Ctrl+C) when you stop playing, and don't share the URL.
