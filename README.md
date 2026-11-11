# Flip 7 Telegram Bot

Play Flip 7 (The Op, 2024) with friends in a Telegram group. Pure Python 3
stdlib (bot + engine), game state in a local JSON file. No npm/pip needed
to run the bot itself.

## Rules used (researched online)

Sources: official rulebook (bghub.org/r/flip7.pdf), Asmodee "How to Play
Flip 7", The Ludarium academy guide.

- **Deck (94):** numbers `0×1, 1×1, 2×2 … 12×12` (79) · modifiers
  `+2 +4 +6 +8 +10 x2` (6) · actions `3× Freeze, Flip Three, Second Chance` (9).
- **Round:** dealer deals 1 face-up card to each player (actions are
  resolved as they are dealt). Then players in turn order choose
  **Hit** (flip another card) or **Stay** (bank points, sit out; needs ≥1 card).
- **Bust:** a second number card matching one you already have → out, **0 pts**.
  Modifiers/actions can never bust and don't count toward 7.
- **Flip 7:** 7 unique numbers → round ends immediately, **+15 bonus**.
- **Scoring:** sum numbers → `x2` doubles the *numbers only* → add `+` modifiers → +15 if Flip 7.
- **Actions** (the player who flips it picks any *active* player):
  - *Freeze* – that player banks and leaves the round.
  - *Flip Three* – that player flips the next 3 cards; stops on bust/Flip 7.
    A Second Chance works during it; Freeze/Flip Three drawn during it are
    deferred until after the 3 cards (and only used if not busted).
  - *Second Chance* – keep 1 max; on a later duplicate, discard both and stay in.
- **Between rounds:** round cards are set aside (not reshuffled), dealer
  rotates; discards are only reshuffled when the deck runs out. **First to
  200** wins; a tie at 200+ plays extra rounds until one unique winner.

*Bot adaptations:* cards are public/face-up (as in the physical game, so the
group sees every flip); minimum 2 players to start (official game is 3+ —
`/startgame` warns you); deferred Freeze/Flip Three are chosen by the
Flip-Three player; a Freeze during the initial deal removes that player
from the rest of the initial deal.

## 1. Create the bot (BotFather — the "new" API)

There is **no official HTTP BotFather API**. Bots are created two
programmatic ways, both via MTProto (a user login, `api_id`/`api_hash`
from https://my.telegram.org/apps), plus the manual chat:

| Path | How |
|---|---|
| **Managed bots (new)** | MTProto `bots.createBot` — a *user* creates a bot controlled by a manager bot that has `bot_can_manage_bots`. Requires an existing manager bot. Its token is then fetched with the Bot API `getManagedBotToken` (manager bot's token + managed bot's `user_id`); `replaceManagedBotToken` rotates it, `get/setManagedBotAccessSettings` control who may use it. `create_bot.py --managed` does this if `MANAGER_BOT_TOKEN` is set. |
| **Automate @BotFather** | MTProto user client sends `/newbot` to @BotFather and answers name/username (what `telegram-bot-manager`/GramJS does). **This is how `@flip7groupbot` was created** (api_id 56669, phone login + 2FA, token saved to `.env`). |

The managed-token endpoints **cannot** be used for a regular
BotFather-created bot: `getManagedBotToken` called with `@flip7groupbot`'s
own token returns an HTTP error (verified) — it requires a *manager* bot's
token and a managed bot's `user_id`. A regular bot already receives its
token in the BotFather chat.

Configuration of **either** kind of bot uses the bot's own token with the
Bot API `setMyName` / `setMyDescription` / `setMyShortDescription` /
`setMyCommands` endpoints (`create_bot.py --configure`, verified via
`getMyCommands` = 9 commands) — no BotFather chat needed for that step.

`create_bot.py` implements both:

```bash
pip install telethon
export TELEGRAM_API_ID=... TELEGRAM_API_HASH=...   # my.telegram.org/apps
python3 create_bot.py --name "Boardgame Bot" --username flip7groupbot
# first run asks for your phone + login code; token is saved to .env
python3 create_bot.py --managed @YourManagerBot --name "Boardgame Bot" --username flip7groupbot
```

No credentials? It prints the manual steps: @BotFather → `/newbot` →
name → username (must end in `bot`) → copy token. Then set it in `.env`.

## 2. Run

Start the bot:

```bash
set -a; . ./.env; set +a     # or: export TELEGRAM_BOT_TOKEN=...
python3 bot.py
```

Then start the Cloudflare tunnel in a second process so the Mini App is
reachable over HTTPS (the bot serves the page/API on `:8080`):

```bash
# Live/named tunnel — TUNNEL_TOKEN from .env (hostname configured in Cloudflare)
set -a; . ./.env; set +a
./cloudflared-bin tunnel run --token "$TUNNEL_TOKEN"

# or a throwaway quick tunnel (prints a https://<random>.trycloudflare.com URL)
./cloudflared-bin tunnel --url http://localhost:8080
```

Keep both processes running (e.g. `watch.sh`, which restarts the bot and the
tunnel on new commits or crashes). Long-polls `getUpdates` (no webhook/server
needed). Only one process per token. State: `state.json` next to `bot.py`
(override `FLIP7_STATE`), written atomically after every update; restart-safe.

## 3. Play in a group

Add the bot to the group and make it **admin** (or @BotFather →
`/setprivacy` → Disable) so it can read commands etc.

```
/games              list the games you can start (with live chat status)
/rules             how to play (reply to a board for that game's rules)
/cancel            reply to a game's board message to cancel that game
Flip 7 itself is played via Mini App buttons (Hit/Stay/Score/Rematch) and
in-game Telegram buttons; /flip7 text commands were removed (Mini App only).
```

Buttons enforce whose turn it is; action cards show target buttons to the
player who flipped them. A single board message is edited in place;
flip results are posted as event messages.

## HTML5 game option (`/web` Mini App button)

`web/flip7.html` + `web/flip7.js` is a dependency-free Flip 7 game with two modes:
**Synced (default)** — the bot process itself serves the page + JSON API on
`:8080` (`GET /api/games`, `GET /api/game?chat_id=`, `POST /api/move`
Hit/Stay/action/Next/Join) sharing the *same* in-memory state as Telegram
polling, so HTML and chat moves stay in sync (deck order never exposed).
Mini App `initData` is verified with the bot token (HMAC) to get the user's
id — **no user_id entry anywhere** (`/api/mygames` only returns your games,
`/api/game`/`/api/move` 403 without valid initData). Groups open the Main
Mini App via the `t.me/flip7groupbot?startapp=<chat_id>` URL button
(BotFather: Bot Settings → Configure Mini App → URL set; verified
"Success! Mini App settings updated"). Moves must be by the current
player/chooser, same as text buttons.
**Testing rule:** tests must use `FLIP7_STATE=/tmp/...` + a test port —
never the live `state.json` (a previous test overwrote it; `save_state`
now also keeps `state.json.bak`).
**Hot-seat (offline)** — the original localStorage game, still below the synced panel.
**Starting in groups from the Mini App:** open `/web` in the group (Main Mini App
link, auto-login) → if no game exists there, *Create game in this chat* →
friends tap *Join* (lobby seats show everyone) → anyone taps *Start game*.
Card piles use generated SVG images (`web/cards/*.svg`, `web/make_cards.py` —
numbers colour-coded 0–12, modifiers, Freeze/Flip Three/Second Chance, deck back). JS is external with `data-cfasync="false"` and no inline
`onclick` handlers, because Cloudflare Rocket Loader (on `xamin.it`) rewrites
inline scripts/handlers and breaks them — verified served HTML contains no
Rocket-Loader-transformed scripts. Three ways to offer it:

1. **File (always works):** `/web` or `/play` with no URL configured →
   the bot sends `flip7.html` via `sendDocument`; open it in any browser.
2. **Mini App (modern):** serve it over HTTPS and set `FLIP7_WEB_URL`:
   ```bash
   python3 web/server.py 8080        # or any static host
   cloudflare tunnel --url http://localhost:8080   # or ngrok https
   export FLIP7_WEB_URL=https://<tunnel>/flip7.html
   ```
   Restart `bot.py`: `/web` then shows a button. Telegram requires
   HTTPS for Mini Apps, so a plain `http://localhost` URL won't open in-client.
   **Groups:** `web_app` inline buttons are private-chats-only (Telegram
   rejects them in groups with `BUTTON_TYPE_INVALID`), so the bot sends a
   plain `url` button in groups/supergroups (opens the same page) and a
   `web_app` button in private chats.
    **Live instance:** a Cloudflare Tunnel (tunnel ID and `TUNNEL_TOKEN` in the
    server's `.env`, never committed) forwards the tunnel hostname to
    `http://localhost:8080`, exposing the game over HTTPS. `FLIP7_WEB_URL`
    is set in `.env`. (Host this yourself: create a tunnel with
    `cloudflared tunnel create`, point its hostname at `localhost:8080`,
    and set `FLIP7_WEB_URL` to that HTTPS URL.)
3. **Telegram HTML5 Game (legacy):** register a short name in @BotFather
   (`/newgame` → name/description/photo), host the HTML over HTTPS, set
   `FLIP7_GAME_URL=https://<tunnel>/flip7.html` and
   `FLIP7_GAME_SHORT_NAME=<short name>`, restart `bot.py`. `/play` calls
   `sendGame`; tapping Play triggers a callback that the bot answers with
   `answerCallbackQuery(url=FLIP7_GAME_URL)`. Scores can be posted
   server-side with `setGameScore` (not from the page).

## Regicide (same bot, second game)

Co-op vs 12 royals (J 10/20, Q 15/30, K 20/40), 2–4 players, hand limit 7/6/5.
Text commands (distinct from Flip 7): `/regicide` (create, also auto-creates from the
Mini App), `/regicide_join`, `/regicide_start` (anyone), `/regicide_play 7h` (played card
becomes public; combos/Ace-pairs/joker via Mini App private hand UI), `/regicide_yield`,
`/regicide_discard 4s`, `/regicide_rules`, `/regicide_cancel` (creator). Hands are private:
boards show only hand counts, the API returns only *your* hand (`/api/regicide/mygames`,
`/api/regicide/game`, `POST /api/regicide/move` + `/api/regicide/create`, initData-only).
Mini App: Flip 7 board button = `?startapp=<chat>` (Flip 7 view), Regicide board button =
`?startapp=regicide<chat>` — same Main Mini App, page routes by `start_param`. Engine:
`regicide.py` + `test_regicide.py` (setup counts, combo validation, exact-kill, discard/lose,
jester/yield).

## Yahtzee (same bot, dice scorecard)

Classic Yahtzee, 2–6 players: roll 5 dice up to 3 times (keep any dice
between rolls), then fill one of 13 boxes. Upper section 63+ earns a +35
bonus; Yahtzee is 50 and each extra Yahtzee after that is +100. Game ends
when everyone has filled all 13 boxes; highest total wins.
Text commands: `/yahtzee` (create), `/yahtzee_join`, `/yahtzee_start`,
`/yahtzee_roll [positions to keep]` (e.g. `/yahtzee_roll 1 3 5`),
`/yahtzee_score <category>` (or tap the buttons), `/yahtzee_rules`,
`/yahtzee_cancel` (creator), `/yahtzee_join_npc`.
Mini App: board button = `?startapp=yahtzee<chat>` (same Main Mini App,
routed by `start_param`). Engine: `yahtzee.py` + `test_yahtzee.py` (score
table, upper bonus, extra-Yahtzee bonus, full game to end).

## Files

- `game.py` – pure engine: deck, scoring, bust/Flip 7, actions, rounds.
- `yahtzee.py` – pure engine: dice, scorecard, turns, scoring.
- `bot.py` – Telegram polling, inline keyboards, commands, JSON state.
- `create_bot.py` – BotFather self-creation (MTProto, see above).
- `test_game.py` – unit tests: `python3 test_game.py`
- `test_yahtzee.py` – Yahtzee unit tests: `python3 test_yahtzee.py`
- `web/flip7.html` – standalone HTML5 Flip 7 game (hot-seat, Mini App-ready)
- `web/yahtzee.js` – Yahtzee Mini App view (synced)
- `web/server.py` – static server for the HTML game (needs HTTPS tunnel for in-Telegram use)
- `state.json` – created at runtime (per-chat games, decks, scores).

## Tests

```bash
python3 test_game.py        # 8 engine tests
python3 test_yahtzee.py     # 6 Yahtzee tests
```
A full 3-player game was also simulated end-to-end (hits/stays/actions/
round rotation → a winner at 200+ in 13 rounds) with the Telegram layer
mocked out.
