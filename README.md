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
/flip7              create a Flip 7 lobby (also /flip7_join /flip7_start /flip7_rules)
/rules             how to play (reply to a board for that game's rules)
/cancel            reply to a game's board message to cancel that game
Flip 7 lobbies can also be joined/started from the Mini App button; the bot's
own Hit/Stay/Score buttons work too. Every lobby has an "Add NPC" button (same
as /join_npc and /<game>_join_npc) to seat a mock player anyone can control.
```

Buttons enforce whose turn it is; action cards show target buttons to the
player who flipped them. Lobby boards are sent as box-art photos (board text
as the caption) and re-sent when the lobby changes; after that a single board
message is edited in place and flip results are posted as event messages.

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

## Fliptoons (same bot, grid-building card market)

Fliptoons Season 1, 2–4 players. Each round you flip cards into a 3×2
grid, score its fame, then take 2 market actions (hire a market card, or
dismiss one of your own face-up cards). Hired cards go on top of your deck
for the next round. Reaching 30 fame triggers the Final Flip; most fame at
the end wins (Critic's Choice gives +3 to the leader).
Text commands: `/fliptoons` (create), `/fliptoons_join`,
`/fliptoons_start`, `/fliptoons_hire <1-5>`, `/fliptoons_dismiss <card>`,
`/fliptoons_skip`, `/fliptoons_choose <option>` (for pending abilities),
`/fliptoons_rules`, `/fliptoons_cancel` (creator), `/fliptoons_join_npc`.
Mini App: board button = `?startapp=fliptoons<chat>` (same Main Mini App,
routed by `start_param`). Engine: `fliptoons.py` + `test_fliptoons.py`
(full card abilities, market, final flip).

## Tornado Splash (same bot, jet-ski racing)

Tornado Splash (Arclight Games, 2025), 2–5 players. Each racer picks one of
6 jet skis (each with its own 20-card deck of straight/curve cards worth 1–2
spaces; boats differ in Speed/Handling stars and weight). Every round:
rank racers by proximity to the finish (ties → lighter boat), replenish
hands (1st draws to 4, last to 6, others 5; an empty deck returns your
played cards earliest-first), then play cards in rank order — max 3 spaces
per round, or 4 with the once-per-race boost. Passing a checkpoint requires
a curve card that turn; stopping exactly on it is free. The first racer to
reach or cross the finish wins, and the race runs until all but one are
finished. An optional Grand Prix runs 3 races over 4 courses with 5/3/2/0
points by finish.
Text commands: `/tornado` (create), `/tornado_join`, `/tornado_start [gp]`,
`/tornado_pick <1-6>`, `/tornado_auto`, `/tornado_hand`, `/tornado_play
<card#...> [b]`, `/tornado_wait [card#...]`, `/tornado_next` (next GP race),
`/tornado_rules`, `/tornado_cancel` (creator), `/tornado_join_npc`.
Mini App: board button = `?startapp=tornado<chat>` (same Main Mini App,
routed by `start_param`). Engine: `tornado.py` + `test_tornado.py`.

## Abandon All Artichokes (same bot, deck-wrecking veggies)

Abandon All Artichokes (Gamewright), 2–4 players. Everyone starts with 10
Artichokes in hand; a turn refills the 5-card Garden Row, harvests one row
card, plays any number of vegetable powers, then discards and redraws 5.
The turn auto-skips once the last vegetable is played (pending choices resolve first).
The Garden Stack holds 6 copies of each of the 10 vegetables; when 4+ of the
same vegetable appear in the row, that kind is reshuffled into the stack and
the row is refilled. Vegetables let you swap, draw, force discards, reveal
opponents' hands, and more. You win at the end of your turn only when the
refill leaves your hand with no Artichokes.
Text commands: `/artichokes` (create), `/artichokes_join`,
`/artichokes_join_npc`, `/artichokes_start`, `/artichokes_harvest <1-5>`,
`/artichokes_skip`, `/artichokes_play <card id or name>`, `/artichokes_end`,
`/artichokes_choose <value>`, `/artichokes_pass <card ids>`,
`/artichokes_rules`, `/artichokes_cancel` (creator), `/artichokes_rematch`.
Mini App: board button = `?startapp=artichokes<chat>` (same Main Mini App,
routed by `start_param`). Engine: `artichokes.py` + `test_artichokes.py`.

## Fellowship of the Ring (same bot, co-op trick-taking)

The Lord of the Rings: The Fellowship of the Ring Trick-Taking Game
(Office Dog / Asmodee), 2–4 players, 18 chapters. Private hands, follow the
lead suit, Rings sealed until broken, and the 1 of Rings may claim a trick.
Each character has its own goal; the round is won only when all chosen
characters succeed. Chapters 1, 2 and 13 follow the published rules closely;
chapters 3–18 use simplified/approximated rosters and goals because the
printed chapter cards are not all available in digital form. The 2-player
mode also simplifies the printed "pyramid" hand into a normal two-handed game
(the One Ring is moved into a player's hand when it would be undealt).

Source reference: `sources/fellowship_of_the_ring_tts_scripted.tts`, a scripted
Tabletop Simulator mod save (v13.3) downloaded from
`https://cdn.steamusercontent.com/ugc/16687564503860619417/1E3511BEE3071CC159ABF49A2ECF013D501BDA2F/`.
The Mini App uses card and character art extracted from that save's sprite
sheets into `web/fellowship_cards/`; playable card names and character names
are taken from the save's card nicknames.

Text commands: `/fotr` (create), `/fotr_join`, `/fotr_join_npc`,
`/fotr_start [chapter]`, `/fotr_chapter <1-18>`, `/fotr_choose <key>`,
`/fotr_exchange <card> [target]`, `/fotr_back <card>`, `/fotr_play <card>`,
`/fotr_ring yes|no`, `/fotr_retry`, `/fotr_restart`, `/fotr_next`,
`/fotr_rules`, `/fotr_cancel` (creator). Mini App: board button =
`?startapp=fellowship<chat>` (same Main Mini App, routed by `start_param`).
Engine: `fellowship.py` + `test_fellowship.py`.

## Azul (same bot, tile-drafting wall builder)

Azul (Michael Kiesling, 2017), 2–4 players. Each round 5/7/9 factory displays
(2/3/4 players) are filled with four tiles; on your turn you take every tile
of one colour from a factory (the rest slide into the centre) or from the
centre (also taking the ⭐ first-player marker; a centre holding only ⭐ is not a
pick). Tiles go onto one of your pattern
lines (1–5 spaces, one colour per line, never a colour already on that wall
row); overflow lands on the floor line, whose seven spaces cost
-1,-1,-2,-2,-2,-3,-3 at the end of the round. Full lines tile the wall and
score the connected row + column groups; the game ends after the round in
which anyone completes a wall row, then +2/row, +7/column, +10/colour set
decide the winner (ties break on completed rows).

Text commands: `/azul` (create), `/azul_join`, `/azul_join_npc`,
`/azul_start`, `/azul_take <factory N|center> <colour>`,
`/azul_place <1-5|floor>`, `/azul_rules`, `/azul_cancel` (creator),
`/azul_rematch`. Mini App: board button =
`?startapp=azul<chat>` (same Main Mini App, routed by `start_param`).
Engine: `azul.py` + `test_azul.py` (drafting, wall scoring/floor penalties,
final bonuses, full-game simulation).

## Toy Battle (same bot, 2-player troops and medals)

Toy Battle (Repos Production, 2024), 2 players on the Castle Field board.
Each player has 20 troops (3 each of 8 types, 4 removed unseen); the first
player draws 3, then 4. A turn is either **draw 2** (rack limit 8) or **place
1 troop**. A troop needs a continuous line of your troops from your HQ (the
enemy HQ still needs connection); you may stack on your own troops freely,
and on an enemy troop only with a higher number. Kwak is a joker for enemy
troops. Effects: Skully draw 2, Cap'N place 1 extra, Jumbo discard an adjacent
enemy troop, Hook ignore connection for bases, XB-42 discard a random enemy
rack troop, Star draw 1, Roxy none. Special bases return one of your troops to
your rack. Surround a region to permanently claim its medals; capture the
enemy HQ or reach 7 medals to win. Racks are private.

Board/troop/medal art is extracted from the BGA game client and the Castle
Field layout comes from the BGA tutorial data. Text commands: `/toybattle`
(create), `/toybattle_join`, `/toybattle_join_npc`, `/toybattle_start`,
`/toybattle_draw`, `/toybattle_place <troop#> <base>`,
`/toybattle_choose <value>`, `/toybattle_rules`, `/toybattle_cancel` (creator),
`/toybattle_rematch`. Mini App: board button = `?startapp=toybattle<chat>`
(same Main Mini App, routed by `start_param`). Engine: `toybattle.py` +
`test_toybattle.py`.

## Tokaido Duo (same bot, 2-player Shikoku journey)

Tokaido Duo (Antoine Bauza, Funforge/Stonemaier, 2022), 2 players. Each
player controls a Pilgrim, a Merchant and an Artist. Each round the first
picker rolls 3 dice (Pilgrim 1/2/3/4/2/3, Merchant 1/2/3/1/2/3, Artist
1/2/3/1/1/2) and the draft is 1-2-1, first picker alternating. A chosen
character must move the exact die value. Pilgrim: clockwise around the
37-station ring (8 Coastal, 13 Temple, 7 Garden, 5 Hot Spring, 4 Seashore);
Temple x Garden = Faith, Temple 9 or Garden 6 ends the game. Merchant:
along Trade routes between 4 Mountain towns (draw 4/3/3/2 Wares) and 8
Coastal towns (sell for the Boutique price); 10 coins = 1 gold slab, 6th
slab ends the game, Commerce = 0/5/11/18/26/35/45. Artist: through 8 zones
(Paint or Gift a Painting); Culture = 0/2/4/7/10/14/18/23/28/34/40 for
0-10 Paintings gifted, 10th gift ends the game. Wave tiles (Hasty/Tranquil,
Crafty/Robust, Proficient/Inspired) and the Hot Spring token (repeat a move)
come from Seashore / Hot Spring stations.

Dice, Culture table, Boutique set (Pottery-3/4, Fan-3/2, Doll-3 x2,
Kimono-4 x2), ring order and zone adjacency were verified from a live BGA
table (spectated, no login) and the BGA sprite sheets, release 261120-2009;
the sprites are kept in `sources/tokaidoduo/bga/`. Text commands:
`/tokaidoduo` (create), `/tokaidoduo_join`, `/tokaidoduo_join_npc`,
`/tokaidoduo_start`, `/tokaidoduo_pick <pilgrim|merchant|artist>`,
`/tokaidoduo_choose <value>`, `/tokaidoduo_rules`, `/tokaidoduo_cancel`
(creator), `/tokaidoduo_rematch`. Mini App: board button =
`?startapp=tokaidoduo<chat>` (same Main Mini App, routed by `start_param`).
Engine: `tokaidoduo.py` + `test_tokaidoduo.py`.

## Altay (same bot, 2-player civilization card game)

A compact two-player version of *Altay: Dawn of Civilization* (Simone Luciani,
2023). Factions keep their BGA starting decks; each turn you play action cards
to produce resources, acquire market cards, build settlements, fight Conquest
Markers or opponents, and invest in one achievement at a time. Final scoring
counts achievements, VP cards, settlements, VP markers, captured settlements,
and Conquest Markers (1 VP per three). Board, action-card, achievement-card,
marker and token art is extracted from the BGA client at version
`261121-1937`. Text commands: `/altay`, `/altay_join`, `/altay_join_npc`,
`/altay_faction <name>`, `/altay_start`, `/altay_play <card#>`, `/altay_buy
<card>`, `/altay_build <territory>`, `/altay_attack <territory>`,
`/altay_develop <id>`, `/altay_end`, `/altay_score`, `/altay_rules`,
`/altay_cancel` (creator), `/altay_rematch`. Mini App: board button =
`?startapp=altay<chat>` (same Main Mini App, routed by `start_param`). Engine:
`altay.py` + `test_altay.py`.

## Black Flag! (same bot, 4-8 player naval card game)

A simplified digital version of *Black Flag!* (Robert Burke, Matt Forbeck and
James Ernest, 2018). Everyone gets a Captain, its Ship, a hidden Role and 4
cards (6th-8th players get 5); the Admiral is revealed. On your turn take a
Ship if you have none, draw 2, play any number of cards, then keep at most 5.
Shots hit within your Ship's Range; Sails add 1 to your effective distance,
while Telescope/Map add Range. Sailor and Parley can be played out of turn to
stop a Shot. Sinking a Ship moves the Treasure Chest toward the enemy flag,
discards its Equipment and earns the sinker a Doubloon. A Privateer/Pirate
with 4 Doubloons wins immediately, a nation wins when the Chest reaches its
flag, and an empty Hourglass forces a revealed symbol answer or elimination.
Some card and ship abilities are deliberately simplified; this is a
playable approximation, not a full rules conversion.

Card, Captain, Ship and board art is extracted from the Tabletop Simulator
component sheets into `web/blackflag-cards.webp`, `web/blackflag-ships.webp`,
`web/blackflag-board.webp` and `web/blackflag-cardback.webp`. Text commands:
`/blackflag`, `/blackflag_join`, `/blackflag_join_npc`, `/blackflag_start`,
`/blackflag_ship <row|deck>`, `/blackflag_play <card#> [target#]`,
`/blackflag_defend <card#>`, `/blackflag_pass`, `/blackflag_end`,
`/blackflag_ability`, `/blackflag_rules`, `/blackflag_cancel` (creator),
`/blackflag_rematch`. Mini App: board button = `?startapp=blackflag<chat>`
(same Main Mini App, routed by `start_param`). Engine: `blackflag.py`; tests
live in `test_wiring.py`.

## Files

- `game.py` – pure engine: deck, scoring, bust/Flip 7, actions, rounds.
- `azul.py` – pure engine: factories, pattern lines, wall scoring, final bonuses.
- `toybattle.py` – pure engine: Castle Field bases, stacks/connection, troop powers, medals, HQ win.
- `tokaidoduo.py` – pure engine: 37-station Pilgrim ring, Merchant trade routes, Artist zones, 1-2-1 dice draft, Wave tiles, Hot Spring, scoring.
- `altay.py` – pure engine: faction decks, production, market, settlement building, combat, achievements, final scoring.
- `blackflag.py` – pure engine: Captains, Ships, hidden Roles, card combat, Treasure Chest, Doubloons, Hourglass and win checks.
- `yahtzee.py` – pure engine: dice, scorecard, turns, scoring.
- `fliptoons.py` – pure engine: deck, grid, abilities, market, final flip.
- `tornado.py` – pure engine: boats, decks, courses, ranks, movement, Grand Prix.
- `artichokes.py` – pure engine: garden stack/row, harvesting, all vegetable powers, win check.
- `fellowship.py` – pure engine: 37-card deck, chapter rosters/goals, setup exchanges, trick play, One Ring.
- `bot.py` – Telegram polling, inline keyboards, commands, JSON state.
- `create_bot.py` – BotFather self-creation (MTProto, see above).
- `test_game.py` – unit tests: `python3 test_game.py`
- `test_yahtzee.py` – Yahtzee unit tests: `python3 test_yahtzee.py`
- `test_fliptoons.py` – Fliptoons unit tests: `python3 test_fliptoons.py`
- `test_tornado.py` – Tornado Splash unit tests: `python3 test_tornado.py`
- `test_artichokes.py` – Abandon All Artichokes unit tests: `python3 test_artichokes.py`
- `test_fellowship.py` – Fellowship engine tests: `python3 test_fellowship.py`
- `test_toybattle.py` – Toy Battle engine tests: `python3 test_toybattle.py`
- `test_tokaidoduo.py` – Tokaido Duo engine tests: `python3 test_tokaidoduo.py`
- `test_altay.py` – Altay engine tests: `python3 test_altay.py`
- `test_wiring.py` – registry, bot wiring and Black Flag engine tests: `python3 test_wiring.py`
- `web/flip7.html` – standalone HTML5 Flip 7 game (hot-seat, Mini App-ready)
- `web/yahtzee.js` – Yahtzee Mini App view (synced)
- `web/fliptoons.js` – Fliptoons Mini App view (synced)
- `web/tornado.js` – Tornado Splash Mini App view (synced)
- `web/artichokes.js` – Abandon All Artichokes Mini App view (synced)
- `web/fellowship.js` – Fellowship Mini App view (synced, viewer-filtered hands)
- `web/fellowship_cards/` – Fellowship card/character sprite sheets from the TTS save
- `web/azul.js` – Azul Mini App view (synced)
- `web/toybattle.js` – Toy Battle Mini App view (synced, viewer-filtered racks)
- `web/toybattle-board.webp`, `web/toybattle-tiles.webp`, `web/toybattle-medals.webp` – BGA-extracted Toy Battle art
- `web/tokaidoduo.js` – Tokaido Duo Mini App view (synced, board + seats)
- `web/tokaidoduo-board.webp` – BGA board art for Tokaido Duo
- `web/altay.js` – Altay Mini App view (synced, viewer-filtered hands)
- `web/altay-board.webp`, `web/altay-actions.webp`, `web/altay-achievements.webp`, `web/altay-markers.webp`, `web/altay-tokens.webp` – BGA-extracted Altay art
- `web/blackflag.js` – Black Flag Mini App view (synced, viewer-filtered hands)
- `web/blackflag-cards.webp`, `web/blackflag-ships.webp`, `web/blackflag-board.webp`, `web/blackflag-cardback.webp` – TTS-extracted Black Flag art
- `sources/tokaidoduo/bga/` – BGA sprite sheets for Tokaido Duo (dice, wares, waves, paintings, boutiques, character boards)
- `web/artichokes_cards/` – BGA card art (0–9 vegetables, 10–14 Artichokes, 15 Rhubarb, 16 back)
- `web/covers/*.jpg` – box art shown as the lobby photo for each game
- `web/server.py` – static server for the HTML game (needs HTTPS tunnel for in-Telegram use)
- `state.json` – created at runtime (per-chat games, decks, scores).

## Tests

```bash
python3 test_game.py        # 8 engine tests
python3 test_yahtzee.py     # 6 Yahtzee tests
python3 test_fliptoons.py   # Fliptoons engine/ability tests
python3 test_tornado.py     # Tornado Splash engine tests
python3 test_artichokes.py  # Abandon All Artichokes engine tests
python3 test_fellowship.py  # Fellowship engine tests
python3 test_azul.py        # Azul engine tests
python3 test_toybattle.py   # Toy Battle engine tests
python3 test_tokaidoduo.py  # Tokaido Duo engine tests
python3 test_altay.py       # Altay engine tests
python3 test_wiring.py      # registry, bot wiring and Black Flag tests
```
A full 3-player game was also simulated end-to-end (hits/stays/actions/
round rotation → a winner at 200+ in 13 rounds) with the Telegram layer
mocked out.
