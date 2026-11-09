---
name: telegram-card-game
description: Create a new interactive Telegram card game (text bot + HTML5 Mini App synced to live group games, BGA sprite-sheet card art). Use when creating a new game or adding one to the bot, BotFather bot creation, Mini App group pitfalls, sprite sheets, and Cloudflare-tunnel hosting.
---

# Telegram Card Game — creating a new game

Distilled from Flip 7 + Regicide + Odin (`@flip7groupbot`). Use as a checklist to create a new game; Flip 7 (public hands, press-your-luck), Regicide (private hands, co-op) and Odin (private hands, ladder-climbing/shedding, play→pickup turn) are the reference implementations. Every section is a trap that already bit once.

## 1. Rules first, engine second (for the new game)

- Research the official rulebook before coding, and encode the engine as a pure module (`game.py` / `regicide.py`) separate from `bot.py`: state is plain serialisable dicts, every move validates phase/turn/ownership server-side and restores cards on error. Flip 7: deck 94 = numbers `0x1, 1x1, 2x2 … 12x12` (79) + modifiers `+2 +4 +6 +8 +10 x2` (6) + actions `3x Freeze/Flip Three/Second Chance` (9), first to 200, duplicate = bust, 7 unique = Flip 7 (+15), score = sum, `x2` doubles numbers only, then add `+` modifiers, then +15. Regicide: 12 royals J(10/20)→Q(15/30)→K(20/40), suit powers ♥ heal / ♦ draw / ♠ shield / ♣ double, enemy immune to its own suit, exact kill recruits the royal.
- **Auto-advance phases that need no human decision** (Flip 7 rounds: `end_round` scores then immediately deals the next round in the same render; Regicide next enemy after a kill). Never wait for a tap to progress such a phase; migrate persisted `round_end`-style games on startup/review.
- **Skip zero-effect phases**: if a phase's amount resolves to 0 (e.g. shield ≥ enemy attack = effective attack 0), don't enter it — pass the turn directly with an event. Entering e.g. `discard` with `needed 0` strands players having to waste cards.
- **Multi-card actions are batches**: play/discard accept all selected cards and resolve the total once (one-at-a-time rejection is a UX bug when totals are needed). Never resolve a batch card-by-card if an intermediate card can end the phase/advance the turn mid-batch.

## 2. Create the bot — there is no HTTP BotFather API

- No official `POST /createBot` exists. Programmatic routes are MTProto only:
  1. **Automate @BotFather chat** (default): MTProto user login → send `/newbot` → name → username (ends `bot`) → parse token from reply. This is what `telegram-bot-manager` (GramJS) does.
  2. **Managed bots (new)**: MTProto `bots.createBot` creates a user-owned bot controlled by a manager bot with `bot_can_manage_bots`. Only then do Bot API `getManagedBotToken`/`replaceManagedBotToken`/`get|setManagedBotAccessSettings` apply (called with the *manager* bot's token + managed `user_id`). They fail (HTTP error) on a regular BotFather-created bot — a regular bot already gets its token in the BotFather chat.
- MTProto needs `api_id`/`api_hash` from my.telegram.org/apps (env `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`, **not** a Bot API token — a bot token cannot create bots). Login needs phone + code + **2FA password** if enabled; session file (`*.session`) is a secret, gitignore it.
- Telethon ≥1.40 breaking change: `from telethon import TelegramClient` (no `telethon.asyncio`), TL classes are `*Request` (`CreateBotRequest`), and `async with TelegramClient(...)` auto-calls `start()` and prompts — use explicit `await client.connect()` + `disconnect()`. Support two-step login via `--request-code`/`--code`/`--password` so it works over chat without a TTY.
- BotFather config (name/description/about/commands) is 3-step button clicking (`/cmd → pick bot button → value`) and is fragile/racy. Prefer Bot API on the bot's own token: `setMyName`, `setMyDescription`, `setMyShortDescription`, `setMyCommands` (+ `getMyCommands` to verify). Register the **Main Mini App** in BotFather: `/mybots → bot → Bot Settings → Configure Mini App → Enable → URL` (verified "Success!").

## 3. Text bot (group play)

- Stdlib-only Python long polling (`getUpdates`, timeout 30), inline keyboards, state in one local JSON (`state.json`, atomic tmp+replace, keep `state.json.bak`), **one top-level key per game** (`games`, `regicide`) so clearing/adding a game never touches another. One process, one token (second poller → 409).
- Add bot to group as **admin** (or BotFather `/setprivacy` Disable) so it reads `/join` etc.
- **Ignore regular messages**: as admin the bot sees all group chat; if `text` doesn't start with `/`, return silently; also ignore `/cmd@otherbot`. Only commands + callbacks + `web_app_data` get replies.
- Turn enforcement server-side: action buttons only work for `current_index` player; action-target buttons only for the chooser and only eligible targets. Any player may start (needs ≥2; official minimums noted in rules). `/cancel` stays creator-only.
- **Public vs private info is a design decision per game.** Flip 7 is face-up, so the group board shows everyone's pile. Regicide hands are private: board text and the Mini App API must expose only the viewer's own hand plus other players' hand *counts* (a `*_board_json(g, viewer_id)` filter) — never serialise full state to the client or a group message.
- Turn pings: on every new turn, ping the player with `<a href="tg://user?id=…">` in the *new* events message (edits are silent) and the board; add an HTML button row to the playing/action keyboards (Mini App link in groups, `web_app` in private) so actions can be done in the Mini App too.
- Commands are namespaced per game (`/regicide_play`, `/odin_play`, `/spots_trick` …; Flip 7 is Mini-App-first with in-game buttons), and each game's button opens the correct Mini App view (§4 router). Telegram only auto-links `[a-z0-9_]` commands — never use kebab-case.

## 4. HTML5 Mini App synced to live games (the hard part)

Architecture that works: **the bot process also serves the page + JSON API on one port** (`:8080`, tunnel forwards to it), sharing the *same in-memory state* + lock with polling. A separate static server/process will race and overwrite state — never do that. Per game: `GET /api/<game>/mygames`, `GET /api/<game>/game?chat_id=`, `POST /api/<game>/move`, `POST /api/<game>/create`, `GET /<game>.html`, `GET /<game>.js`, `GET /<game>-cards.webp` (§4c). Deck order / hidden hands are never exposed.
- **Auth = Mini App `initData` only, never ask users for their user_id.** Verify HMAC: `key=HMAC_SHA256("WebAppData", bot_token)`, msg = sorted `k=v` pairs, compare `hash`. Extract `user.id`, `start_param`, `chat_instance`. `/mygames` returns only games containing that user; `/game` 403s non-players; `/move` 403s without valid initData. A user_id typed in a browser is spoofable and a privacy/UX failure — drop it.
- **One Main Mini App can serve all games.** Router in the shared JS: `startapp=<chat_id>` = Flip 7, `startapp=regicide<chat_id>` (or `?app=regicide` in private) = Regicide — show/hide the per-game `<div>`, set the single `<h1>` text. Keep **exactly one `<h1>`** in the HTML; a second per-game heading renders twice. Each game file self-starts (`rgLoad()`) only when its div is visible.
- **`web_app` inline buttons are private chats only** (groups → `400 BUTTON_TYPE_INVALID`). In groups use a URL button to the Main Mini App direct link `https://t.me/<bot>?startapp=<chat_id>` — opens as Mini App *in that chat* with initData + chat context. Raw HTTPS URL in a plain browser = no initData = synced mode must politely refuse.

## 4b. UX design (what players actually asked for, in order)

- **One screen, zero preamble.** On Mini App open: auto-login, auto-select the game for this chat (`startapp`/`chat_instance`, else first active), render the table immediately. No "Load my games" button, no game list, no header/rules blurb, no user_id entry — every extra tap/screen before the table was rejected as pointless.
- **BGA-style table, not a score list.** Green felt table; deck pile (card-back image + count, round, dealer) centred; players as **stacked full-width seats** (flex column — a 2-column grid was rejected), each with avatar initial, name, score pill, dealer 🎩 / turn ▶ badges, and their card pile as images. Busted/frozen seats get `filter:grayscale(100%)`. Lobby = same seats empty ("waiting…") + one lobby note.
- **Sort piles for reading** (display copy only — never mutate state order): Flip 7 numbers ascending (duplicates end up adjacent), modifiers by value with `x2` last, Second Chance last. Do the same in the Telegram board text.
- **Private-hand games** (Regicide pattern): other players sit in a **row** (flex-wrap) instead of stacked seats to save vertical space — name + hand *count* + overlapping card-back sprites (no ✋ emoji), turn label **below** the cards. Current enemy card left-aligned and large, with `⚔️ attack` / `❤️ lives` **stacked vertically** next to it; castle as a small card-back in the **top-right corner**, with `Castle (n)`, `Next: J/Q/K + remaining suits hint`, and Tavern/Discard/Kills stacked below it. Text info generally stacks vertically (`.vstack{flex-direction:column}`) instead of crammed side-by-side grey lines.
- **Preview before confirming.** Selecting cards shows a preview panel: for plays — total value, suit powers, resulting shield/attack, defeat or not, and `⛔ Blocked: <suit> blocked by <royal> immunity`; for discards — selected total and running total vs needed. The confirm button acts on exactly the previewed selection.
- **Buttons only when it's your turn.** Hit/Stay, Play/Yield/Discard and action-target buttons render *only* for the current player/chooser (everything else is view-only, polled every 3s). Lobby Start is the one exception (any seated player, not just creator).
- **Show the maths.** Per seat: `Hand X → total Y` (banked + hypothetical hand, bust = 0, ×2-then-+ and Flip 7 +15 included) plus last-round score. Players shouldn't do mental arithmetic to decide Hit/Stay.
- **Card animations, diffed — never on every poll.** `.card-in` (flip/slide in) is added by JS only to cards that newly appeared (multiset diff of card keys vs previous board: played pile, own hand, each player's pile, deck count drop), `.hit-shake` when enemy damage increases, `selPop` on select, `:active` press scale; honour `prefers-reduced-motion`. A 3s poll re-render that re-animates every card is constant flicker.
- **Ping the player, in the last message.** Turns are announced with a `tg://user?id=` mention — and it must be in a **new message**, because edits don't notify. So each turn sends **one combined message** (events + board + ping + keyboard) and deletes the old board message: the HTML/action buttons are always on the last message, never buried in an edited old one.
- **Silent bot in chat.** Ignore regular messages and `@otherbot` commands — as an admin the bot sees all group chat, and replying to chatter destroys the UX. Empty/loading states must say what to do in Telegram in one line.
- **Freshness is UX:** Mini App WebView caches aggressively — `Cache-Control: no-store` + JS `?v=` bump on every change, or players stare at yesterday's UI (and old bugs).

## 4c. Card art — BGA sprite sheets

Use the Board Game Arena sprite sheet as the card art source for a new game; generate own SVGs (`web/make_cards.py` → `web/cards/*.svg`) only as a fallback when no sheet exists.
1. **Find and view the sheet.** BGA release pattern: `https://x.boardgamearena.net/data/themereleases/current/games/<slug>/<release>/img/<sheet>.png` (the user often supplies the exact URL + layout). Download it and **actually view the image** — never trust a claimed grid size (Flip 7 was claimed as 6×4, it is really 7×4).
2. **Measure the grid.** `ffprobe` the dimensions, divide by columns/rows for the cell size. Then pick a display size and set CSS `background-size: <displayW×cols> <displayH×rows>px`; a card's position is `background-position: -<col×displayW>px -<row×displayH>px` from a JS `POS` map (`card → [col,row]`).
3. **Host locally.** Save as `web/<game>-cards.webp`, serve from `bot.py` (`GET /<game>-cards.webp`, `image/webp`, `cache: public, max-age=86400`), and reference it relatively in CSS. The card back is one specific cell — find it on the sheet empirically.
4. **Worked examples (copy these patterns):**
   - **Regicide — 14×4, cell 240×336** (sheet 3360×1344, `.../games/regicide/240926-1508/img/cards_0.png` → `web/regicide-cards.webp`, display 48×67 / big 72×101 / small 36×50): col 0 = Jesters/backs, cols 1–13 = A–K (`RG_COL`), rows ♠♥♣♦ (`RG_ROW`); Jester = col 0 row 0, hand backs = col 0 row 1, castle = col 0 small.
   - **Flip 7 — 7×4, cell 130×204** (sheet 910×816, `.../games/flipseven/260626-1817/img/spritesheet.png` → `web/flip7-cards.webp`, display 44×69): row 0 `0 1 10 11 12 2 +8`, row 1 `3 4 5 6 7 8 Second Chance`, row 2 `9 back +10 +2 +4 +6 Freeze`, row 3 `Flip Three x2 empty ---` (`F7_POS`); deck back = `[1,2]`. Release paths/dates in the URL change over time — re-find the current one when adding a game.
   - **Odin — 10×6, cell ~181×341** (sheet 1813×2048, `.../games/odin/260817-1157/img/odin_cards_minified.jpg` — content is WebP despite the `.jpg` name, serve it as `.webp`; display 44×83 / big 54×101): cols 1–9 = ranks, rows = colours blue/red/pink/green/black/orange (`OD_SUIT_ORDER`); col 10 is empty except `[9,5]` = Grumpy Goat bonus card (unused in the base game), and there is **no card back in the sheet** — backs come from a generated SVG. Crop-verify two cells before trusting the grid.
5. **Verify the map, not just the file.** Unit-check a few entries in Node (e.g. Flip 7 `12 → [4,0]`, `9 → [0,2]`, `x2 → [1,3]`; Regicide A♠/K♦ corners + Jester), curl the `.webp` via tunnel for 200, and eyeball enemy/hand/deck cards in the Mini App.

## 5. Hosting traps (all hit in production)

- **Cloudflare Rocket Loader** rewrites inline `<script>` to hashed types and `onclick` to `if(!window.__cfRLUnblockHandlers) return false; …` — dead buttons, especially dynamic ones. Fix: external JS with `<script data-cfasync="false" src=…>` (attribute before `src`), zero inline `onclick` (use `addEventListener`), external Telegram script also `data-cfasync="false"`. Verify served HTML via tunnel (grep for `rocket-loader` / `onclick` should be 0). No dashboard access needed with this workaround.
- **Telegram/WebView + edge caching**: clients cache Mini App resources; origin with no `Cache-Control` = stale versions. Send `Cache-Control: no-store` for HTML/JS/API, long cache only for card images (`.webp`/`.svg`), and **version-query the JS** (`flip7.js?v=N`, `regicide.js?v=N`) — Cloudflare edge-caches bare `.js` URLs, a version bump bypasses it (`cf-cache: BYPASS`). "Doesn't work" after an update is usually this cache, not the code.
- **Tunnel**: `cloudflared tunnel run <tunnel-id>` with `TUNNEL_TOKEN` env (id as positional arg in cloudflared ≥2026), ingress `hostname → http://localhost:8080`. Check `tunnel.log` config line confirms hostname. Sandbox DNS returns only unreachable IPv6 — test with `curl --resolve host:443:<Cloudflare-IPv4>` (get IPv4 from `nslookup host 1.1.1.1`). User-side `DNS_PROBE_FINISHED_NXDOMAIN` with globally-correct DNS (verify via `dns.google/resolve`) = local negative cache: clear Chrome `chrome://net-internals/#dns`, incognito, or mobile data (TTL 300s).
- Processes: bot (polling+API), tunnel, all via `nohup … >> *.log 2>&1 &`; static changes need no restart (served from disk + `no-store`), `bot.py` changes do. **Kill the bot by pid (`kill <pid>`), never `pkill -f bot.py`** — the pattern matches the shell running the command and kills it.

## 6. Testing discipline (learned the hard way)

- **Never let a test touch live `state.json`.** Always `FLIP7_STATE=/tmp/<test>.json` + a test port + mocked Telegram (`bot.send/edit/api` no-ops), and `md5sum state.json` before/after — a previous API test overwrote the live group game. `save_state` keeps `.bak` as a second defence. Test API move functions on a copied state dict, not the live file.
- Unit-test the engine separately (`game.py`: deck counts, x2-before-plus scoring, bust/Second Chance, Flip 7, Flip Three deferred, tie-at-200; `regicide.py`: validate plays, exact kill, multi-card discard batches, zero-attack skipping discard, lose-on-empty-hand). Simulate the Mini App headlessly (DOM shim in Node: layout, sprite-map entries, animation diffing = first render animates / same-board re-render animates nothing / one new card animates only itself, multi-select sends all selected cards, discard preview totals). Verify end-to-end via tunnel with `--resolve`, and craft valid initData with the bot token in tests only.
- Fixing a live game stuck by a bug: stop the bot first (it holds state in memory and will overwrite file edits), back up `state.json`, edit only that game's entry, restart, re-verify. Editing under a running bot silently does nothing.
- After any change: `py_compile`, engine tests, restart only if `bot.py` changed, re-check tunnel 200s.

## Quick start: create a new game

1. Rulebook → engine module + engine tests (§1); decide public vs private info (§3).
2. Bot via BotFather/MTProto + commands (§2).
3. `bot.py`: new state key, commands, group board text, `/api/<game>/*` endpoints, serve `<game>.html/js/<game>-cards.webp`.
4. Sprite sheet for the new game (§4c) + `<game>.js` view, and a router entry in the shared HTML (§4).
5. Tunnel up, verify via `--resolve`, test on isolated state, then play live (§5–§6).
