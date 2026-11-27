# Board games Telegram Bot

Play Board games with friends in a Telegram group. Pure Python 3
stdlib (bot + engine), game state in a local JSON file. No npm/pip needed
to run the bot itself.

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
`setMyCommands` endpoints (`create_bot.py --configure`, which registers the
25 commands in `COMMANDS` — one create command per game plus `/games`,
`/join_npc`, `/rules`, `/cancel`, `/start` and `/help`; verify with
`getMyCommands`) — no BotFather chat needed for that step.

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
/<game>             create a lobby, e.g. /flip7 /azul /odin (also /<game>_join /<game>_start /<game>_rules)
/rules             how to play (reply to a board for that game's rules)
/cancel            reply to a game's board message to cancel that game
/start /help       show the help text (all games and commands)
/join_npc          add a mock player anyone can control (Flip 7; other games: /<game>_join_npc)
```

Every game starts the same way: send its create command (or tap it in
`/games`), friends join with `/<game>_join` or the lobby's Join button, then
anyone taps Start (or `/<game>_start`). While a lobby has free seats it has
an "Add NPC" button (same as `/join_npc` and `/<game>_join_npc`) to seat
another mock player anyone can control; NPCs get unique negative ids and
distinct names. Every lobby also has a "🎥 How to play" button linking to a
tutorial video, and a Mini App button that opens the game in the Telegram
Mini App (see below) — lobbies can be joined and started from there too.
Flip 7 also has the bot's own Hit/Stay buttons in chat.

Buttons enforce whose turn it is; action cards show target buttons to the
player who flipped them. Lobby boards are sent as the game's box-art photo
(board text as the caption, when it fits in the 1024-character caption limit)
and re-sent when the lobby changes. During play the board message is edited
in place when a move produces no events; when a turn does produce events
(e.g. a Flip 7 flip result) the board is re-sent as a fresh message and the
old one deleted, so the newest message always carries the buttons.

## Mini App (Telegram, synced)

`assets/shared/flip7.html` is the single Mini App shell for all games
(each game has its own view script under `assets/<game>/scripts/`). The bot
process itself serves the page + JSON API on `:8080` (`GET /api/games`,
`GET /api/game?chat_id=`, `POST /api/create`, `POST /api/move`, plus
per-game `/api/<game>/...` endpoints) sharing the *same* in-memory state as
Telegram polling, so Mini App and chat moves stay in sync (deck order never
exposed). Mini App `initData` is verified with the bot token (HMAC) to get
the user's id — **no user_id entry anywhere** (`/api/mygames` only returns
your games, `/api/game`/`/api/move` 403 without valid initData). Moves must
be by the current player/chooser, same as text buttons.

There is no `/web` or `/play` command: the Mini App is opened from a board's
Mini App button or from `/games`. In groups the button is a plain URL to the
bot's Main Mini App direct link (`t.me/flip7groupbot?startapp=<chat_id>` for
Flip 7, `?startapp=<game><chat_id>` for the other games — BotFather: Bot
Settings → Configure Mini App → URL set; verified "Success! Mini App
settings updated"); in private chats it is a `web_app` button (`web_app`
inline buttons are private-chats-only — Telegram rejects them in groups with
`BUTTON_TYPE_INVALID`). Opening it in a group with no game yet auto-creates
one (you are the creator); friends tap *Join* in the lobby, anyone taps
*Start game*.
**Testing rule:** tests must use `FLIP7_STATE=/tmp/...` + a test port —
never the live `state.json` (a previous test overwrote it; `save_state`
now also keeps `state.json.bak`).
Card piles use generated SVG images (`assets/shared/images/cards/*.svg`, `web/make_cards.py` —
numbers colour-coded 0–12, modifiers, Freeze/Flip Three/Second Chance, deck back). JS is external with `data-cfasync="false"` and no inline
`onclick` handlers, because Cloudflare Rocket Loader (on `xamin.it`) rewrites
inline scripts/handlers and breaks them — verified served HTML contains no
Rocket-Loader-transformed scripts.

**Serving it:** the bot serves the Mini App itself on `:8080`, so the live
setup is just the Cloudflare Tunnel (tunnel ID and `TUNNEL_TOKEN` in the
server's `.env`, never committed) forwarding the tunnel hostname to
`http://localhost:8080`, with `FLIP7_WEB_URL` set in `.env` to that HTTPS
URL. (Host this yourself: create a tunnel with `cloudflared tunnel create`,
point its hostname at `localhost:8080`, and set `FLIP7_WEB_URL` to that
HTTPS URL.) Telegram requires HTTPS for Mini Apps, so a plain
`http://localhost` URL won't open in-client. `web/server.py` is only a
static-file server for local testing of the page — it does not serve the
`/api/*` endpoints, so synced play through it does not work.

**Legacy Telegram HTML5 Game:** `FLIP7_GAME_URL` +
`FLIP7_GAME_SHORT_NAME` are still read (register a short name in @BotFather
via `/newgame`), and the bot still answers `game_short_name` callbacks with
the game URL — but nothing sends a game message any more (there is no
`/play` command), so this path is currently unused.
## Flip 7 (2-6 players)

BGG: https://boardgamegeek.com/boardgame/420087/flip-7

Sources: official rulebook (bghub.org/r/flip7.pdf), Asmodee "How to Play
Flip 7", The Ludarium academy guide. The official rulebook is stored in
`assets/flip7/rulebook.pdf`.

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
`/flip7_start` just needs 2); deferred Freeze/Flip Three are chosen by the
Flip-Three player; a Freeze during the initial deal removes that player
from the rest of the initial deal.

Text commands: `/flip7` (create), `/flip7_join`, `/flip7_join_npc`,
`/flip7_start`, `/flip7_rules`, `/cancel` (reply to the board, creator).
Mini App: board button = `?startapp=<chat_id>` (same Main Mini App).
Engine: `game.py` + `tests/test_game.py`.

A full 3-player game was also simulated end-to-end (hits/stays/actions/
round rotation → a winner at 200+ in 13 rounds) with the Telegram layer
mocked out.

## Regicide (2-4 players)

BGG: https://boardgamegeek.com/boardgame/307002/regicide

Co-op vs 12 royals (J 10/20, Q 15/30, K 20/40), 2–4 players, hand limit 7/6/5.
The official rulebook is stored in `assets/regicide/rulebook.pdf`.
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

## Odin (2-6 players)

BGG: https://boardgamegeek.com/boardgame/406854/odin

Odin (Helvetiq), 2–6 players. A card-shedding game: lead with a set of
same-colour or same-number cards whose digits, sorted high to low, form a
number that beats the table — then take one card from the previous set.
Everyone starts at 15 points and loses 1 per card left in hand at the end
of each hand; first to 0 wins. The official rulebook is stored in
`assets/odin/rulebook.pdf`.
Text commands: `/odin` (create), `/odin_join`, `/odin_join_npc`,
`/odin_start`, `/odin_play <cards>`, `/odin_pickup <card>`, `/odin_pass`,
`/odin_score`, `/odin_cancel` (creator), `/odin_rules`. Mini App: board
button = `?startapp=odin<chat>` (same Main Mini App, routed by
`start_param`). Engine: `odin.py` + `tests/odin/test_odin.py` (setup and
deck, set values, lead/response rules, pickup and passing, going out and
scoring).

## 13 Leaves (3-6 players)

BGG: https://boardgamegeek.com/boardgame/434442/13-leaves

13 Leaves, 3–6 players. Shed your hand by playing sets onto the ends of the
row: the first lead plays any set of the same value, then you play onto the
left or right end — at least as many cards as that end stack, with a value
below the lowest (left) or above the highest (right). First to empty your
hand wins. The lobby shows the game's box art
(`assets/leaves/images/leaves-cover.jpg`).
Text commands: `/leaves` (create), `/leaves_join`, `/leaves_join_npc`,
`/leaves_start`, `/leaves_play <value> <count>` (e.g. `/leaves_play 5 2`),
`/leaves_pass`, `/leaves_cancel` (creator), `/leaves_rules`. Mini App:
board button = `?startapp=leaves<chat>` (same Main Mini App, routed by
`start_param`). Engine: `game_modules/leaves.py` +
`tests/leaves/test_leaves.py` (deck and deal, lead and play, stack
extension, passing, win on empty hand).

## Let's Summon Demons (2-5 players)

BGG: https://boardgamegeek.com/boardgame/325829/lets-summon-demons

Let's Summon Demons (Cryptozoic, 2021), 2–5 players. Roll 2d6 to activate
everyone's matching cards, buy Block cards for souls, and summon demons by
discarding Block cards — first to 3 summoned demons AND 10 souls wins.
The official rulebook is stored in `assets/lsd/rulebook.pdf`.
Text commands: `/lsd` (create), `/lsd_join`, `/lsd_join_npc`, `/lsd_start`,
`/lsd_roll`, `/lsd_buy <1-5>`, `/lsd_summon <demon> <sacrifices...>`,
`/lsd_end`, `/lsd_score`, `/lsd_cancel` (creator), `/lsd_rules`. Mini App:
board button = `?startapp=lsd<chat>` (same Main Mini App, routed by
`start_param`). Engine: `lsd.py` + `tests/lsd/test_lsd.py` (setup, roll
activations, buy and summon, win check).

## Spots (1-4 players)

BGG: https://boardgamegeek.com/boardgame/372559/spots

Spots (CMYK), 1–4 players. A push-your-luck dog dice game: do tricks to roll
dice and fill the spots on your dog cards, then score completed dogs — first
to 6 scored wins. Bury too many dice in your yard (over 7) and you bust,
losing the dice on your unscored dogs. The official rulebook is stored in
`assets/spots/rulebook.pdf`.
Text commands: `/spots` (create), `/spots_join`, `/spots_join_npc`,
`/spots_start`, `/spots_trick <tile>`, `/spots_place <die#> <dog> <spot#>`
(or `/spots_place <die#> yard`), `/spots_reroll`, `/spots_score`,
`/spots_cancel` (creator), `/spots_rules`. Mini App: board button =
`?startapp=spots<chat>` (same Main Mini App, routed by `start_param`).
Engine: `spots.py` + `tests/spots/test_spots.py` (setup, tricks/placement
and bust, scoring and auto-score, reroll and win).

## Yahtzee (2-6 players)

BGG: https://boardgamegeek.com/boardgame/2243/yahtzee

Classic Yahtzee, 2–6 players: roll 5 dice up to 3 times (keep any dice
between rolls), then fill one of 13 boxes. Upper section 63+ earns a +35
bonus; Yahtzee is 50 and each extra Yahtzee after that is +100. Game ends
when everyone has filled all 13 boxes; highest total wins. The official
rulebook is stored in `assets/yahtzee/rulebook.pdf`.
Text commands: `/yahtzee` (create), `/yahtzee_join`, `/yahtzee_start`,
`/yahtzee_roll [positions to keep]` (e.g. `/yahtzee_roll 1 3 5`),
`/yahtzee_score <category>` (or tap the buttons), `/yahtzee_rules`,
`/yahtzee_cancel` (creator), `/yahtzee_join_npc`.
Mini App: board button = `?startapp=yahtzee<chat>` (same Main Mini App,
routed by `start_param`). Engine: `yahtzee.py` + `test_yahtzee.py` (score
table, upper bonus, extra-Yahtzee bonus, full game to end).

## Fliptoons (2-4 players)

BGG: https://boardgamegeek.com/boardgame/449185/fliptoons

Fliptoons Season 1, 2–4 players. Each round you flip cards into a 3×2
grid, score its fame, then take 2 market actions (hire a market card, or
dismiss one of your own face-up cards). Hired cards go on top of your deck
for the next round. Reaching 30 fame triggers the Final Flip; most fame at
the end wins (Critic's Choice gives +3 to the leader). The official
rulebook is stored in `assets/fliptoons/rulebook.pdf`.
Text commands: `/fliptoons` (create), `/fliptoons_join`,
`/fliptoons_start`, `/fliptoons_hire <1-5>`, `/fliptoons_dismiss <card>`,
`/fliptoons_skip`, `/fliptoons_choose <option>` (for pending abilities),
`/fliptoons_rules`, `/fliptoons_cancel` (creator), `/fliptoons_join_npc`.
Mini App: board button = `?startapp=fliptoons<chat>` (same Main Mini App,
routed by `start_param`). Engine: `fliptoons.py` + `test_fliptoons.py`
(full card abilities, market, final flip).

## Castle Combo (2-5 players)

BGG: https://boardgamegeek.com/boardgame/416851/castle-combo

Castle Combo (Grégory Grard & Mathieu Roussel, 2024), 2–5 players. Recruit
characters from the Castle and Village markets into a 3×3 tableau: each
card grants an immediate ability and scores from shields, sets, positions
and stored gold, and the Messenger pawn decides which row you may buy from.
Most points wins. The official rulebook is stored in
`assets/castlecombo/rulebook.pdf`.
Text commands: `/castlecombo` (create), `/castlecombo_join`,
`/castlecombo_join_npc`, `/castlecombo_start`, `/castlecombo_buy <card id>`,
`/castlecombo_flip <card id>`, `/castlecombo_move`, `/castlecombo_renew`,
`/castlecombo_choose <value>`, `/castlecombo_cancel` (creator),
`/castlecombo_rules`. Mini App: board button =
`?startapp=castlecombo<chat>` (same Main Mini App, routed by `start_param`).
Engine: `castlecombo.py` + `tests/castlecombo/test_castlecombo.py` (deck and
start, messenger, placement, costs and discounts, buy and pending choices).

## Tornado Splash (2-5 players)

BGG: https://boardgamegeek.com/boardgame/444648/tornado-splash

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
points by finish. The official rulebook is stored in
`assets/tornado/rulebook.pdf`.
Text commands: `/tornado` (create), `/tornado_join`, `/tornado_start [gp]`,
`/tornado_pick <1-6>`, `/tornado_auto`, `/tornado_hand`, `/tornado_play
<card#...> [b]`, `/tornado_wait [card#...]`, `/tornado_next` (next GP race),
`/tornado_rules`, `/tornado_cancel` (creator), `/tornado_join_npc`.
Mini App: board button = `?startapp=tornado<chat>` (same Main Mini App,
routed by `start_param`). Engine: `tornado.py` + `test_tornado.py`.

## Abandon All Artichokes (2-4 players)

BGG: https://boardgamegeek.com/boardgame/302260

Abandon All Artichokes (Gamewright), 2–4 players. Everyone starts with 10
Artichokes in hand; a turn refills the 5-card Garden Row, harvests one row
card, plays any number of vegetable powers, then discards and redraws 5.
The turn auto-skips once the last vegetable is played (pending choices resolve first).
The Garden Stack holds 6 copies of each of the 10 vegetables; when 4+ of the
same vegetable appear in the row, that kind is reshuffled into the stack and
the row is refilled. Vegetables let you swap, draw, force discards, reveal
opponents' hands, and more. You win at the end of your turn only when the
refill leaves your hand with no Artichokes. The official rulebook is stored
in `assets/artichokes/rulebook.pdf`.
Text commands: `/artichokes` (create), `/artichokes_join`,
`/artichokes_join_npc`, `/artichokes_start`, `/artichokes_harvest <1-5>`,
`/artichokes_skip`, `/artichokes_play <card id or name>`, `/artichokes_end`,
`/artichokes_choose <value>`, `/artichokes_pass <card ids>`,
`/artichokes_rules`, `/artichokes_cancel` (creator), `/artichokes_rematch`.
Mini App: board button = `?startapp=artichokes<chat>` (same Main Mini App,
routed by `start_param`). Engine: `artichokes.py` + `test_artichokes.py`.

## Fellowship of the Ring (2-4 players)

BGG: https://boardgamegeek.com/boardgame/429293/the-fellowship-of-the-ring-trick-taking-game

The Lord of the Rings: The Fellowship of the Ring Trick-Taking Game
(Office Dog / Asmodee), 2–4 players, 18 chapters. Private hands, follow the
lead suit, Rings sealed until broken, and the 1 of Rings may claim a trick.
Each character has its own goal; the round is won only when all chosen
characters succeed. Chapters 1, 2 and 13 follow the published rules closely;
chapters 3–18 use simplified/approximated rosters and goals because the
printed chapter cards are not all available in digital form. The 2-player
mode also simplifies the printed "pyramid" hand into a normal two-handed game
(the One Ring is moved into a player's hand when it would be undealt). The
official rulebook is stored in `assets/fellowship/rulebook.pdf`.

Source reference: `sources/fellowship_of_the_ring_tts_scripted.tts`, a scripted
Tabletop Simulator mod save (v13.3) downloaded from
`https://cdn.steamusercontent.com/ugc/16687564503860619417/1E3511BEE3071CC159ABF49A2ECF013D501BDA2F/`.
The Mini App uses card and character art extracted from that save's sprite
sheets into `assets/fellowship/images/fellowship_cards/`; playable card names and character names
are taken from the save's card nicknames.

Text commands: `/fotr` (create), `/fotr_join`, `/fotr_join_npc`,
`/fotr_start [chapter]`, `/fotr_chapter <1-18>`, `/fotr_choose <key>`,
`/fotr_exchange <card> [target]`, `/fotr_back <card>`, `/fotr_play <card>`,
`/fotr_ring yes|no`, `/fotr_retry`, `/fotr_restart`, `/fotr_next`,
`/fotr_rules`, `/fotr_cancel` (creator). Mini App: board button =
`?startapp=fellowship<chat>` (same Main Mini App, routed by `start_param`).
Engine: `fellowship.py` + `test_fellowship.py`.

## Azul (2-4 players)

BGG: https://boardgamegeek.com/boardgame/230802/azul

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
decide the winner (ties break on completed rows). The official rulebook is
stored in `assets/azul/rulebook.pdf`.

Text commands: `/azul` (create), `/azul_join`, `/azul_join_npc`,
`/azul_start`, `/azul_take <factory N|center> <colour>`,
`/azul_place <1-5|floor>`, `/azul_rules`, `/azul_cancel` (creator),
`/azul_rematch`. Mini App: board button =
`?startapp=azul<chat>` (same Main Mini App, routed by `start_param`).
Engine: `azul.py` + `test_azul.py` (drafting, wall scoring/floor penalties,
final bonuses, full-game simulation).

## Toy Battle (2 players)

BGG: https://boardgamegeek.com/boardgame/434654/toy-battle

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
enemy HQ or reach 7 medals to win. Racks are private. The official rulebook
is stored in `assets/toybattle/rulebook.pdf`.

Board/troop/medal art is extracted from the BGA game client and the Castle
Field layout comes from the BGA tutorial data. Text commands: `/toybattle`
(create), `/toybattle_join`, `/toybattle_join_npc`, `/toybattle_start`,
`/toybattle_draw`, `/toybattle_place <troop#> <base>`,
`/toybattle_choose <value>`, `/toybattle_rules`, `/toybattle_cancel` (creator),
`/toybattle_rematch`. Mini App: board button = `?startapp=toybattle<chat>`
(same Main Mini App, routed by `start_param`). Engine: `toybattle.py` +
`test_toybattle.py`.

## Tokaido Duo (2 players)

BGG: https://boardgamegeek.com/boardgame/363183/tokaido-duo

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
the sprites are kept in `sources/tokaidoduo/bga/`. The official rulebook
is stored in `assets/tokaidoduo/rulebook.pdf`. Text commands:
`/tokaidoduo` (create), `/tokaidoduo_join`, `/tokaidoduo_join_npc`,
`/tokaidoduo_start`, `/tokaidoduo_pick <pilgrim|merchant|artist>`,
`/tokaidoduo_choose <value>`, `/tokaidoduo_rules`, `/tokaidoduo_cancel`
(creator), `/tokaidoduo_rematch`. Mini App: board button =
`?startapp=tokaidoduo<chat>` (same Main Mini App, routed by `start_param`).
Engine: `tokaidoduo.py` + `test_tokaidoduo.py`.

## Altay (2-4 players)

BGG: https://boardgamegeek.com/boardgame/334537/altay-dawn-of-civilization

A compact 2–4 player version of *Altay: Dawn of Civilization* (Simone Luciani,
2023). Factions keep their BGA starting decks; each turn you play action cards
to produce resources, acquire market cards, build settlements, fight Conquest
Markers or opponents, and invest in one achievement at a time. Final scoring
counts achievements, VP cards, settlements, VP markers, captured settlements,
and Conquest Markers (1 VP per three). Board, action-card, achievement-card,
marker and token art is extracted from the BGA client at version
`261121-1937`. The official rulebook and the Seafarers expansion rulebook
are stored in `assets/altay/rulebook.pdf` and
`assets/altay/seafarers-rulebook.pdf`.

The lobby includes a simplified BGA-compatible **Seafarers** option: two sea
zones and two island territories (conquest markers 3 and 2), 3 ships and 3
crews per player, ships/crews support for sea travel, sea-launched attacks,
coins as VP, Astronomy/Lighthouse achievements, Explorer/Sailor/Shipwright
cards, and one trade per turn (3 identical or 2 different resources for 1).
The Forgotten Sea board and Waterfolk are not implemented.

Text commands: `/altay`, `/altay_join`, `/altay_join_npc`,
`/altay_faction <name>`, `/altay_seafarers <on|off>` (creator, lobby),
`/altay_start`, `/altay_play <card#>`, `/altay_buy <card>`,
`/altay_build <territory>`, `/altay_attack <territory>`,
`/altay_develop <id>`, `/altay_trade <give[:count] ...> <receive>`,
`/altay_end`, `/altay_score`, `/altay_rules`, `/altay_cancel` (creator),
`/altay_rematch`. Mini App: board button = `?startapp=altay<chat>` (same Main
Mini App, routed by `start_param`). Engine: `altay.py` + `tests/altay/test_altay.py`.

## Black Flag! (4-8 players)

BGG: https://boardgamegeek.com/boardgame/472803/black-flag

A simplified digital version of *Black Flag!* (Emiliano Sciarra, 2026). Everyone gets a Captain, its Ship, a hidden Role and 4
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
component sheets into `assets/blackflag/images/blackflag-cards.webp`, `assets/blackflag/images/blackflag-ships.webp`,
`assets/blackflag/images/blackflag-board.webp` and `assets/blackflag/images/blackflag-cardback.webp`. The official rulebook is
stored in `assets/blackflag/rulebook.pdf`. Text commands:
`/blackflag`, `/blackflag_join`, `/blackflag_join_npc`, `/blackflag_start`,
`/blackflag_ship <row|deck>`, `/blackflag_play <card#> [target#]`,
`/blackflag_defend <card#>`, `/blackflag_pass`, `/blackflag_end`,
`/blackflag_ability`, `/blackflag_rules`, `/blackflag_cancel` (creator),
`/blackflag_rematch`. Mini App: board button = `?startapp=blackflag<chat>`
(same Main Mini App, routed by `start_param`). Engine: `blackflag.py`; tests
live in `tests/test_wiring.py`.

## Rumble Nation (2-4 players)

BGG: https://boardgamegeek.com/boardgame/266722/rumble-nation

A simplified 2–4 player digital version of *Rumble Nation* (S Renegade Games,
2022). Eleven castles (values 2-12) are shuffled face down. On your turn roll
3 dice, optionally reroll them all, then place each die's points as soldiers
in any area. Tactic cards can move/copy soldiers or swap dice before placing.
When every castle is revealed, wars are resolved from castle 2 to 12: the
player with the most soldiers plus reinforcements in adjacent areas wins the
castle; ties go to the higher sword chip. The winner sends reinforcements to
adjacent unresolved areas where they still have soldiers, and takes the
sword chip when winning castle 12. Most castles wins (tie: higher sword).
The 11th castle and half the sword chips are removed for 2 players, and only
3 tactic cards are in play.

Board, card, dice and token art is extracted from Board Game Arena into
`assets/rumblenation/images/rumblenation-board.webp`, `assets/rumblenation/images/rumblenation-cards.webp`,
`assets/rumblenation/images/rumblenation-dice.webp` and `assets/rumblenation/images/rumblenation-tokens.webp`. The official rulebook
is stored in `assets/rumblenation/rulebook.pdf`. Text commands:
`/rumblenation`, `/rumblenation_join`, `/rumblenation_join_npc`,
`/rumblenation_start`, `/rumblenation_roll`, `/rumblenation_reroll`,
`/rumblenation_deploy <die> <castle>`, `/rumblenation_tactic <option>`,
`/rumblenation_rules`, `/rumblenation_cancel` (creator),
`/rumblenation_rematch`. Mini App: board button = `?startapp=rumblenation<chat>`
(same Main Mini App, routed by `start_param`). Engine: `rumblenation.py`; tests in
`tests/rumblenation/test_rumblenation.py`.

## Fadenfroh (1-4 players)

BGG: https://boardgamegeek.com/boardgame/475685/fadenfroh

In Fadenfroh, you place fabric cards in your display. You receive victory points for the colors and symbols on the fabric cards in your display. When and for what exactly you receive victory points depends on the scoring cards of the current round.

However, your opponents are competing with you for fabric cards and useful materials. So, every round you have to decide anew: How long can I take materials before someone snatches up the ideal fabric cards?

Whoever has the most victory points at the end of the game wins! A solo mode
is included: start alone to play the rulebook's 1-player variant, rated by
total VP.

In this digital version of *Fadenfroh* (1 More Time Games): five rounds of drafting
fabric from a market of offers, threads, needles and the thimble. Players trade
three threads to draw and keep one card, stitch cards into three overlapping
rows (covering at least one placed half), and score rotating berry, animal,
flower and colour goals. Feather circles score for every active goal each
round; round five adds a B/C goal choice, remaining material and hoop points.
Ties are broken by the higher starting number. Solo games follow the rulebook
solo variant: a reveal after each shopping turn trims the market, passing
takes up to 2 adjacent cards, and the final VP total is rated 100+/130+/150+.
The engine resolves embroidery sequentially after the market for simpler bot play.

Fabric, scoring, starting-card, material and token art is extracted from Board
Game Arena into `assets/fadenfroh/images/fadenfroh-*.webp` (raw sheets also kept in
`sources/fadenfroh/bga/`). The official rulebook and scoring card overview are
stored in `assets/fadenfroh/rulebook.pdf` and
`assets/fadenfroh/scoring-overview.pdf`. Text commands: `/fadenfroh`,
`/fadenfroh_join`, `/fadenfroh_join_npc`, `/fadenfroh_start`,
`/fadenfroh_material <thread|needle|thimble>`, `/fadenfroh_pass <offer>` (solo: `<card#> [<card#>]`),
`/fadenfroh_keep <1-3>`, `/fadenfroh_place <card> <row> <left|right> <1|2> [needle]`,
`/fadenfroh_discard <cards>`, `/fadenfroh_bonus <B|C>`, `/fadenfroh_rules`,
`/fadenfroh_cancel` (creator) and `/fadenfroh_rematch`. Mini App: board button =
`?startapp=fadenfroh<chat>`. Engine: `fadenfroh.py`; tests in
`tests/fadenfroh/test_fadenfroh.py`.

## Popcorn (2-4 players)

BGG: https://boardgamegeek.com/boardgame/430563/popcorn

A digital version of *Popcorn* (Iello, 2024) — a bag-building game where
players buy movies, build theaters, advertise and seat Guests from a hidden
bag for Popcorn, money, theater trophies and awards. Nine rounds end with the
final Guest card; each theater's favorite color scores its trophies, and
unseated Guests in the exit become Primers for the next round. Ties are broken
by archived movies. Rules were checked against the
[official rulebook](https://iellogames.com/wp-content/uploads/2024/12/Popcorn_Rulebook_EN_V1_Light.pdf)
(stored in `assets/popcorn/rulebook.pdf` and `sources/popcorn/rulebook.pdf`)
and the [BGA rules summary](https://en.doc.boardgamearena.com/Gamehelppopcorn).
Board/cover art was extracted from [the BGA table](https://boardgamearena.com/tableview?table=953855470)
into `assets/popcorn/images/popcorn-board.webp`,
`assets/shared/images/covers/popcorn.jpg` and `sources/popcorn/bga/`.

Text commands: `/popcorn`, `/popcorn_join`, `/popcorn_join_npc`,
`/popcorn_start`, `/popcorn_move <button-code>`, `/popcorn_rules`,
`/popcorn_cancel` (creator) and `/popcorn_rematch`. Mini App: board button =
`?startapp=popcorn<chat>`. Engine: `popcorn.py`; tests in
`tests/popcorn/test_popcorn.py`.

## Files

- `game.py` – pure engine: deck, scoring, bust/Flip 7, actions, rounds.
- `azul.py` – pure engine: factories, pattern lines, wall scoring, final bonuses.
- `toybattle.py` – pure engine: Castle Field bases, stacks/connection, troop powers, medals, HQ win.
- `tokaidoduo.py` – pure engine: 37-station Pilgrim ring, Merchant trade routes, Artist zones, 1-2-1 dice draft, Wave tiles, Hot Spring, scoring.
- `altay.py` – pure engine: faction decks, production, market, settlement building, combat, achievements, final scoring, Seafarers ships/crews/routes/trade.
- `blackflag.py` – pure engine: Captains, Ships, hidden Roles, card combat, Treasure Chest, Doubloons, Hourglass and win checks.
- `fadenfroh.py` – pure engine: market drafting, three embroidered rows, 16 scoring cards, feather/hoop bonuses and final choice.
- `popcorn.py` – pure engine: bag-building movie market, theaters, seating, awards, audience draw and final scoring.
- `yahtzee.py` – pure engine: dice, scorecard, turns, scoring.
- `fliptoons.py` – pure engine: deck, grid, abilities, market, final flip.
- `tornado.py` – pure engine: boats, decks, courses, ranks, movement, Grand Prix.
- `artichokes.py` – pure engine: garden stack/row, harvesting, all vegetable powers, win check.
- `fellowship.py` – pure engine: 37-card deck, chapter rosters/goals, setup exchanges, trick play, One Ring.
- `regicide.py` – pure engine: co-op vs 12 royals, combos, jester, yield.
- `odin.py` – pure engine: card shedding, set numbers, pickup, points race to 0.
- `game_modules/leaves.py` – pure engine: 13 Leaves set shedding onto row ends.
- `lsd.py` – pure engine: Let's Summon Demons dice activations, souls, demons.
- `spots.py` – pure engine: Spots dog dice, tricks, buried dice, bust.
- `castlecombo.py` – pure engine: Castle Combo 3×3 tableau, messenger, shields, sets.
- `game_registry.py` – the game catalog: one spec per game (commands, players, covers, Mini App routing).
- `web_assets.py` – Mini App static assets served by the bot.
- `bot.py` – Telegram polling, inline keyboards, commands, JSON state.
- `create_bot.py` – BotFather self-creation (MTProto, see above).
- `tests/test_game.py` – unit tests: `python3 -m pytest tests/test_game.py`
- `tests/regicide/test_regicide.py` – Regicide engine tests: `python3 -m pytest tests/regicide/test_regicide.py`
- `tests/odin/test_odin.py` – Odin engine tests: `python3 -m pytest tests/odin/test_odin.py`
- `tests/leaves/test_leaves.py` – 13 Leaves engine tests: `python3 -m pytest tests/leaves/test_leaves.py`
- `tests/lsd/test_lsd.py` – Let's Summon Demons engine tests: `python3 -m pytest tests/lsd/test_lsd.py`
- `tests/spots/test_spots.py` – Spots engine tests: `python3 -m pytest tests/spots/test_spots.py`
- `tests/azul/test_azul.py` – Azul engine tests: `python3 -m pytest tests/azul/test_azul.py`
- `tests/castlecombo/test_castlecombo.py` – Castle Combo engine tests: `python3 -m pytest tests/castlecombo/test_castlecombo.py`
- `tests/yahtzee/test_yahtzee.py` – Yahtzee unit tests: `python3 -m pytest tests/yahtzee/test_yahtzee.py`
- `tests/fliptoons/test_fliptoons.py` – Fliptoons unit tests: `python3 -m pytest tests/fliptoons/test_fliptoons.py`
- `tests/tornado/test_tornado.py` – Tornado Splash unit tests: `python3 -m pytest tests/tornado/test_tornado.py`
- `tests/artichokes/test_artichokes.py` – Abandon All Artichokes unit tests: `python3 -m pytest tests/artichokes/test_artichokes.py`
- `tests/fellowship/test_fellowship.py` – Fellowship engine tests: `python3 -m pytest tests/fellowship/test_fellowship.py`
- `tests/toybattle/test_toybattle.py` – Toy Battle engine tests: `python3 -m pytest tests/toybattle/test_toybattle.py`
- `tests/tokaidoduo/test_tokaidoduo.py` – Tokaido Duo engine tests: `python3 -m pytest tests/tokaidoduo/test_tokaidoduo.py`
- `tests/altay/test_altay.py` – Altay engine tests: `python3 -m pytest tests/altay/test_altay.py`
- `tests/test_wiring.py` – registry, bot wiring and Black Flag engine tests: `python3 -m pytest tests/test_wiring.py`
- `tests/rumblenation/test_rumblenation.py` – Rumble Nation engine tests: `python3 -m pytest tests/rumblenation/test_rumblenation.py`
- `tests/fadenfroh/test_fadenfroh.py` – Fadenfroh engine tests: `python3 -m pytest tests/fadenfroh/test_fadenfroh.py`
- `tests/popcorn/test_popcorn.py` – Popcorn engine tests: `python3 -m pytest tests/popcorn/test_popcorn.py`
- `assets/shared/flip7.html` – Mini App shell for all games (synced; one page, per-game view scripts)
- `assets/yahtzee/scripts/yahtzee.js` – Yahtzee Mini App view (synced)
- `assets/regicide/scripts/regicide.js` – Regicide Mini App view (synced, viewer-filtered hands)
- `assets/odin/scripts/odin.js` – Odin Mini App view (synced)
- `assets/leaves/scripts/leaves.js` – 13 Leaves Mini App view (synced)
- `assets/lsd/scripts/lsd.js` – Let's Summon Demons Mini App view (synced)
- `assets/spots/scripts/spots.js` – Spots Mini App view (synced)
- `assets/castlecombo/scripts/castlecombo.js` (+ `castlecombo-faces.js`) – Castle Combo Mini App view (synced)
- `assets/fliptoons/scripts/fliptoons.js` – Fliptoons Mini App view (synced)
- `assets/tornado/scripts/tornado.js` – Tornado Splash Mini App view (synced)
- `assets/artichokes/scripts/artichokes.js` – Abandon All Artichokes Mini App view (synced)
- `assets/fellowship/scripts/fellowship.js` – Fellowship Mini App view (synced, viewer-filtered hands)
- `assets/fellowship/images/fellowship_cards/` – Fellowship card/character sprite sheets from the TTS save
- `assets/azul/scripts/azul.js` – Azul Mini App view (synced)
- `assets/toybattle/scripts/toybattle.js` – Toy Battle Mini App view (synced, viewer-filtered racks)
- `assets/toybattle/images/toybattle-board.webp`, `assets/toybattle/images/toybattle-tiles.webp`, `assets/toybattle/images/toybattle-medals.webp` – BGA-extracted Toy Battle art
- `assets/tokaidoduo/scripts/tokaidoduo.js` – Tokaido Duo Mini App view (synced, board + seats)
- `assets/tokaidoduo/images/tokaidoduo-board.webp` – BGA board art for Tokaido Duo
- `assets/altay/scripts/altay.js` – Altay Mini App view (synced, viewer-filtered hands)
- `assets/altay/images/altay-board.webp`, `assets/altay/images/altay-actions.webp`, `assets/altay/images/altay-achievements.webp`, `assets/altay/images/altay-markers.webp`, `assets/altay/images/altay-tokens.webp` – BGA-extracted Altay art
- `assets/altay/images/altay-seafarers-*.webp` – BGA Seafarers action/achievement/token/ship art served directly as WEBP
- `assets/blackflag/scripts/blackflag.js` – Black Flag Mini App view (synced, viewer-filtered hands)
- `assets/blackflag/images/blackflag-cards.webp`, `assets/blackflag/images/blackflag-ships.webp`, `assets/blackflag/images/blackflag-board.webp`, `assets/blackflag/images/blackflag-cardback.webp` – TTS-extracted Black Flag art
- `assets/rumblenation/scripts/rumblenation.js` – Rumble Nation Mini App view (synced, real BGA sprites)
- `assets/rumblenation/images/rumblenation-board.webp`, `assets/rumblenation/images/rumblenation-cards.webp`, `assets/rumblenation/images/rumblenation-dice.webp`, `assets/rumblenation/images/rumblenation-tokens.webp` – BGA-extracted Rumble Nation art
- `assets/fadenfroh/scripts/fadenfroh.js` – Fadenfroh Mini App view (synced, viewer-filtered hands and BGA sprites)
- `assets/fadenfroh/images/fadenfroh-*.webp` and `sources/fadenfroh/bga/` – BGA-extracted Fadenfroh fabric, scoring, starting-card and token art
- `assets/popcorn/scripts/popcorn.js` – Popcorn Mini App view (synced, bot-driven board)
- `assets/popcorn/images/popcorn-board.webp` and `assets/shared/images/covers/popcorn.jpg` – BGA-extracted Popcorn board and cover art
- `sources/popcorn/bga/` – BGA Popcorn box/banner/display screenshots
- `assets/popcorn/rulebook.pdf` and `sources/popcorn/rulebook.pdf` – official Popcorn rulebook
- `sources/tokaidoduo/bga/` – BGA sprite sheets for Tokaido Duo (dice, wares, waves, paintings, boutiques, character boards)
- `assets/artichokes/images/artichokes_cards/` – BGA card art (0–9 vegetables, 10–14 Artichokes, 15 Rhubarb, 16 back)
- `assets/shared/images/covers/*.{jpg,png}` – box art shown as the lobby photo for each game (13 Leaves' cover lives in `assets/leaves/images/leaves-cover.jpg`)
- `web/server.py` – static-file server for local testing of the Mini App page only (no `/api/*`, so no synced play; the live Mini App is served by `bot.py` itself on `:8080`)
- `state.json` – created at runtime (per-chat games, decks, scores).

## Tests

```bash
python3 -m pytest tests/    # full suite (pytest; tests live in tests/, per game)
```
