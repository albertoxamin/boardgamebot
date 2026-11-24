#!/usr/bin/env python3
"""Flip 7 Telegram bot - group play, stdlib only, state in local JSON.

Run:  TELEGRAM_BOT_TOKEN=<token from @BotFather> python3 bot.py
Add the bot to a group, make it admin (or disable privacy via @BotFather
/setprivacy) so it reads commands, then: /games.
State file: state.json next to this script (override with FLIP7_STATE).
"""
import hashlib, hmac, html, json, os, re, sys, threading, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game as G
import artichokes as AT
import regicide as R
import odin as O
import lsd as D
import spots as SP
import yahtzee as Y
import fliptoons as FT
import castlecombo as CC
import tornado as TS
import fellowship as FTR
import azul as AZ
import toybattle as TB
import tokaidoduo as TD
import altay as AL
import game_registry as GR
import web_assets
from game_modules.leaves import LEAVES_MODULE

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
STATE_FILE = os.environ.get("FLIP7_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "state.json")
# HTML5 options (see web/ and README):
#  FLIP7_WEB_URL      https URL of web/flip7.html -> /web opens it as a Mini App
#  FLIP7_GAME_URL + FLIP7_GAME_SHORT_NAME (registered via @BotFather /newgame)
#                     -> /play sends a Telegram HTML5 Game (sendGame)
WEB_URL = os.environ.get("FLIP7_WEB_URL", "")
WEB_VER = 32
GAME_URL = os.environ.get("FLIP7_GAME_URL", "")
GAME_SHORT_NAME = os.environ.get("FLIP7_GAME_SHORT_NAME", "")
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "web", "flip7.html")
JS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "web", "flip7.js")
WEB_PORT = int(os.environ.get("FLIP7_WEB_PORT", "8080"))
HEALTH_PATHS = ("/healthz", "/health")
GAME_JS_FILES = {
    route: os.path.join(os.path.dirname(JS_PATH), name)
    for route, name in GR.WEB_JS_ROUTES.items()
}
STATE_LOCK = threading.Lock()  # polling loop + HTTP API share one state
_STATE = {"state": None}

HELP = GR.help_text(tail=(
    "/rules - how to play (reply to a board for that game's rules)   /cancel - reply to a board to cancel that game",
    "🤖 /join_npc (or /&lt;game&gt;_join_npc) - add a mock player anyone can control, in the lobby",
    "Play: on your turn tap <b>Hit</b> to flip a card or <b>Stay</b> to bank.",
    "Duplicate number = bust (0 pts). 7 unique numbers = Flip 7 (+15), round ends.",
    "First to 200 wins. Cards are face-up/public, just like the physical game.",
))

RULES = """<b>Flip 7 rules</b> (deck 94: numbers 0×1,1×1,2×2…12×12; +2/+4/+6/+8/+10/x2; 3× Freeze, Flip Three, Second Chance)
• Dealer deals 1 face-up to each (actions resolved as dealt). Then in turn order: <b>Hit</b> or <b>Stay</b> (Stay needs ≥1 card, banks and sits out).
• 2nd card with same number = <b>bust</b>, 0 pts. Modifiers/actions can't bust.
• <b>7 unique numbers = Flip 7</b>: round ends at once, +15 bonus.
• Score: sum numbers → x2 doubles numbers only → add +modifiers → +15 Flip 7. Bust = 0.
• <b>Freeze</b>: chosen active player banks &amp; leaves. <b>Flip Three</b>: chosen player flips next 3 (stops on bust/Flip 7; Second Chance usable, Freeze/Flip Three deferred). <b>Second Chance</b>: keep 1; saves you from one duplicate.
• Round ends when all stayed/busted/frozen or someone Flip 7s. Round cards are set aside, dealer rotates; reshuffle discards only when deck empties.
• First to <b>200</b> (unique highest; tie = extra rounds) wins."""


# ---------- Telegram API (stdlib) ----------
# Read-only/idempotent methods: safe to retry when Telegram's reply times out.
RETRY_METHODS = {"getUpdates", "getMe", "deleteWebhook", "answerCallbackQuery",
                 "deleteMessage", "editMessageText"}


def api(method, **params):
    if not API:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN (create a bot with @BotFather or python3 create_bot.py)")
    data = json.dumps(params).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data,
                                 headers={"Content-Type": "application/json"})
    attempts = 3 if method in RETRY_METHODS else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=35) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            print(f"Telegram {method} HTTP {e.code}: {e.read()[:300]}", file=sys.stderr)
            return {"ok": False}
        except (urllib.error.URLError, OSError) as e:
            if attempt + 1 < attempts:
                time.sleep(1 + attempt)
                continue
            print(f"Telegram {method} network error: {e} (after {attempts} tries)",
                  file=sys.stderr)
            return {"ok": False}


def send(chat_id, text, kb=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb:
        p["reply_markup"] = {"inline_keyboard": kb}
    r = api("sendMessage", **p)
    if not r.get("ok"):
        # Last-resort fallback: never drop a message because of an HTML
        # entity/parse error. Send it as plain text with tags stripped.
        p.pop("parse_mode", None)
        p["text"] = html.unescape(re.sub(r"</?[^>]+>", "", text))
        r = api("sendMessage", **p)
    return r


COVERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "covers")
COVERS = {"flip7": "flip7.jpg"}
COVERS.update({spec.key: spec.cover for spec in GR.GAME_SPECS if spec.cover})


def cover_path(game):
    """Local box-art file for a game, or None when it has not been added."""
    name = COVERS.get(game)
    if not name:
        return None
    path = os.path.join(COVERS_DIR, name)
    return path if os.path.exists(path) else None


def send_photo(chat_id, path, caption="", kb=None):
    """sendPhoto via multipart/form-data (stdlib only)."""
    import uuid
    boundary = "----flip7" + uuid.uuid4().hex
    with open(path, "rb") as f:
        file_bytes = f.read()
    name = os.path.basename(path)
    ctype = "image/png" if name.lower().endswith(".png") else "image/jpeg"

    def field(key, value):
        return (f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{key}"\r\n\r\n{value}\r\n').encode()
    body = field("chat_id", chat_id)
    body += field("parse_mode", "HTML")
    if caption:
        body += field("caption", caption)
    if kb:
        body += field("reply_markup", json.dumps({"inline_keyboard": kb}))
    body += (f"--{boundary}\r\nContent-Disposition: form-data; "
             f'name="photo"; filename="{name}"\r\n'
             f"Content-Type: {ctype}\r\n\r\n").encode() + file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/sendPhoto", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"sendPhoto HTTP {e.code}: {e.read()[:300]}", file=sys.stderr)
        return {"ok": False}
    except (urllib.error.URLError, OSError) as e:
        print(f"sendPhoto network error: {e}", file=sys.stderr)
        return {"ok": False}


def send_board(g, game, text, kb=None):
    """Send the board. Lobbies show the game's box art as a photo with the
    board text as caption; during play boards stay plain text messages."""
    path = cover_path(game) if g.get("phase") == "lobby" else None
    # Caption limit is 1024 chars and must stay valid HTML: fall back to a
    # normal text message when the accumulated events would overflow it.
    if path and len(text) <= 1024:
        r = send_photo(g["chat_id"], path, text, kb)
        if r.get("ok"):
            return r
    return send(g["chat_id"], text, kb)


def edit(chat_id, msg_id, text, kb=None):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text,
         "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb:
        p["reply_markup"] = {"inline_keyboard": kb}
    r = api("editMessageText", **p)
    if not r.get("ok"):  # message unchanged etc. -> send fresh board
        return send(chat_id, text, kb)
    return r


def answer_cb(cb_id, text=""):
    api("answerCallbackQuery", callback_query_id=cb_id, text=text[:200],
        show_alert=bool(text and len(text) > 0 and text.startswith("⛔")))


def send_document(chat_id, path, caption=""):
    """sendDocument via multipart/form-data (stdlib only)."""
    import uuid
    boundary = "----flip7" + uuid.uuid4().hex
    with open(path, "rb") as f:
        file_bytes = f.read()
    def field(name, value):
        return (f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"\r\n\r\n{value}\r\n').encode()
    body = field("chat_id", chat_id)
    if caption:
        body += field("caption", caption)
    body += (f"--{boundary}\r\nContent-Disposition: form-data; "
             f'name="document"; filename="flip7.html"\r\n'
             f"Content-Type: text/html\r\n\r\n").encode() + file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/sendDocument", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"sendDocument HTTP {e.code}: {e.read()[:300]}", file=sys.stderr)
        return {"ok": False}
    except (urllib.error.URLError, OSError) as e:
        print(f"sendDocument network error: {e}", file=sys.stderr)
        return {"ok": False}


def web_keyboard(chat_type="private", chat_id=None, game="flip7"):
    """Inline keyboard opening the HTML game.
    web_app buttons are PRIVATE chats only (Telegram rejects them in groups
    with BUTTON_TYPE_INVALID). In groups use a URL button to the bot's
    Main Mini App direct link (t.me/flip7groupbot?startapp=<chat_id>) -
    that opens as a Mini App in the current chat with verified initData,
    so users never enter a user_id. Falls back to the raw HTTPS URL.
    game='regicide'/'odin' routes the same Mini App to that game's view via
    startapp=<game><chat_id> (no second BotFather app needed)."""
    if not WEB_URL:
        return None
    label = GR.keyboard_label(game)
    if chat_type in ("group", "supergroup", "channel"):
        if chat_id:
            start = GR.GAMES_BY_KEY.get(game, GR.GAMES_BY_KEY["games"]).start_param(chat_id)
            url = f"https://t.me/flip7groupbot?startapp={start}&v={WEB_VER}"
        else:
            url = f"{WEB_URL}?v={WEB_VER}"
        btn = {"text": label, "url": url}
    else:
        url = WEB_URL + f"?v={WEB_VER}" + (f"&app={game}" if GR.supports_web_routing(game) else "")
        if chat_id:
            url += ("&" if "?" in url else "?") + f"chat_id={chat_id}"
        btn = {"text": label, "web_app": {"url": url}}
    return [[btn]]


def open_lobbies(state, chat_id):
    """Joinable lobbies for one chat, in catalog order."""
    rows = []
    for spec in GR.GAME_SPECS:
        game = state.get(spec.key, {}).get(str(chat_id))
        if game and game.get("phase") == "lobby":
            rows.append({"key": spec.key, "name": spec.name,
                         "join": spec.join_command,
                         "players": len(game.get("players") or [])})
    return rows


def game_chat_status(key, game):
    """Short status of one game in the current chat."""
    if game is None:
        return "not started here"
    if game.get("phase") == "lobby":
        return f"lobby ({len(game.get('players') or [])} in)"
    if game.get("phase") in ("game_end", "won", "lost") or (
            key == "tornado" and game.get("phase") == "race_end" and not game.get("gp")):
        return "finished - start a new one"
    return "in progress"


def games_text_message(state, chat_id):
    lines = ["🎮 <b>Games you can start:</b>"]
    for key, name, new, join, desc in GR.CATALOG_ROWS:
        game = state.get(key, {}).get(str(chat_id))
        status = game_chat_status(key, game)
        if status.startswith("lobby"):
            status += f" - {join}"
        lines.append(f"• {name} — {new} ({desc}) · {status}")
    lines.append("🟢 <b>Open lobbies in this chat:</b>")
    lobbies = open_lobbies(state, chat_id)
    for lobby in lobbies:
        lines.append(f"• {lobby['name']} — {lobby['players']} in · {lobby['join']}")
    if not lobbies:
        lines.append("none — start one above")
    lines.append("🤖 Add a mock player: tap Add NPC in a lobby, or use /join_npc (Flip 7) / /&lt;game&gt;_join_npc.")
    return "\n".join(lines)


def games_rich_table(cols, rows):
    cells = [[{"text": c, "is_header": True} for c in cols]]
    cells.extend([{"text": c} for c in row] for row in rows)
    return {"type": "table", "cells": cells, "is_bordered": True,
            "is_striped": True, "is_compact": True}


def games_rich_message(state, chat_id):
    """Rich /games catalog using the Castle Combo scorecard table style."""
    rows = []
    for key, name, new, join, _desc in GR.CATALOG_ROWS:
        game = state.get(key, {}).get(str(chat_id))
        status = game_chat_status(key, game)
        if status.startswith("lobby"):
            status += f" - {join}"
        rows.append([name, new, status])
    blocks = [
        {"type": "paragraph", "text": ["🎮 ", {"type": "bold", "text": "Games you can start"}]},
        games_rich_table(["Game", "Start", "In this chat"], rows),
        {"type": "paragraph", "text": ["🟢 ", {"type": "bold", "text": "Open lobbies in this chat"}]},
    ]
    lobbies = open_lobbies(state, chat_id)
    if lobbies:
        blocks.append(games_rich_table(
            ["Game", "Players", "Join"],
            [[l["name"], str(l["players"]), l["join"]] for l in lobbies]))
    else:
        blocks.append({"type": "paragraph",
                       "text": ["No open lobbies here - start one with a command above."]})
    blocks.append({"type": "paragraph",
                   "text": ["🤖 Add a mock player: tap Add NPC in a lobby, "
                            "or use /join_npc (Flip 7) / /<game>_join_npc."]})
    return {"blocks": blocks}


def games_spectate_keyboard(state, chat_id, chat_type="private"):
    """Mini App spectate buttons for games currently in progress here."""
    rows = []
    for key, name, _new, _join, _desc in GR.CATALOG_ROWS:
        game = state.get(key, {}).get(str(chat_id))
        if game_chat_status(key, game) != "in progress":
            continue
        row = web_keyboard(chat_type, chat_id, game=key)
        if not row or not row[0]:
            continue
        btn = dict(row[0][0])
        btn["text"] = f"👁 Spectate {name}"
        rows.append([btn])
    return rows or None


# ---------- State ----------
def load_state():
    s = {key: {} for key in GR.GAME_KEYS}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                s.update(json.load(f))
        except Exception:
            pass
    for key in GR.GAME_KEYS:
        s.setdefault(key, {})
    return s


def _state_json_default(o):
    if isinstance(o, set):
        return list(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def save_state(state):
    import shutil
    if os.path.exists(STATE_FILE):
        shutil.copy2(STATE_FILE, STATE_FILE + ".bak")  # last-good backup
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, default=_state_json_default)
    os.replace(tmp, STATE_FILE)


NPC_ID = -1  # sentinel Telegram user_id for the mock NPC player


def _npc_player():
    return {"user_id": NPC_ID, "name": "🤖 NPC", "npc": True}


def _is_npc(player):
    return bool(player.get("npc") or player.get("user_id") == NPC_ID)


NPC_MAX = dict(GR.NPC_MAX)
NPC_FULL = dict(GR.NPC_FULL)


def _games_npc():
    p = G.new_player(NPC_ID, "🤖 NPC")
    p["npc"] = True
    return p


def _fliptoons_npc():
    p = _ft_player(NPC_ID, "🤖 NPC")
    p["npc"] = True
    return p


def _castlecombo_npc():
    p = CC.new_player(NPC_ID, "🤖 NPC")
    p["npc"] = True
    return p


def _artichokes_npc():
    p = AT.new_player(NPC_ID, "🤖 NPC")
    p["npc"] = True
    return p


def _fellowship_npc():
    p = FTR.new_player(NPC_ID, "🤖 NPC")
    p["npc"] = True
    return p


NPC_PLAYERS = {
    "games": _games_npc,
    "regicide": lambda: {**_npc_player(), "hand": []},
    "odin": lambda: {**_npc_player(), "hand": [], "score": O.START_SCORE},
    "leaves": LEAVES_MODULE.npc_player,
    "lsd": lambda: {**_npc_player(), "souls": 5, "candle": None,
                    "in_play": [], "demons": [], "demon_hand": []},
    "spots": lambda: {**_npc_player(), "dogs": [], "scored": [], "yard": [], "treats": 1},
    "yahtzee": lambda: {**_npc_player(), **Y.new_player(NPC_ID, "🤖 NPC")},
    "tornado": lambda: {**_npc_player(), **TS.new_player(NPC_ID, "🤖 NPC")},
    "fliptoons": _fliptoons_npc,
    "castlecombo": _castlecombo_npc,
    "artichokes": _artichokes_npc,
    "fellowship": _fellowship_npc,
    "azul": lambda: {**AZ.new_player(NPC_ID, "🤖 NPC"), **_npc_player()},
    "toybattle": lambda: {**TB.new_player(NPC_ID, "🤖 NPC"), **_npc_player()},
    "tokaidoduo": lambda: {**TD.new_player(NPC_ID, "🤖 NPC"), **_npc_player()},
    "altay": lambda: {**AL.new_player(NPC_ID, "🤖 NPC"), **_npc_player()},
}


def add_npc(key, g):
    """Seat the shared mock player in a lobby (command or lobby button).
    Returns an error string, or None on success."""
    if g["phase"] != "lobby":
        return "⛔ Game already started."
    if any(_is_npc(p) for p in g["players"]):
        return "🤖 NPC is already in this game."
    if len(g["players"]) >= NPC_MAX[key]:
        return NPC_FULL[key]
    g["players"].append(NPC_PLAYERS[key]())
    return None


def _actor_idx(g, user_id, ref):
    """Index to act as: your own, or the reference player's if it is the
    NPC (anyone may control the NPC)."""
    if _is_npc(g["players"][ref]):
        return ref
    return next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)


# ---------- Orchestration (loops until a human must act) ----------
def end_turn(g, events):
    nxt = G.next_active(g, g["current_index"] + 1)
    if nxt is None:
        G.end_round(g, events)
    else:
        g["current_index"] = nxt


def after_action_resolved(g, events):
    """pending_action just finished (Freeze/SC): queue or resume context."""
    if G.pop_next_action(g, events) == "action":
        if g["flip3"] is None:
            g["pending_action"]["resume"] = g.get("resume_phase", "playing")
        return
    resume = g.get("resume_phase", "playing")
    g["resume_phase"] = None
    if resume == "playing":
        if G.round_over(g):
            G.end_round(g, events)
        else:
            end_turn(g, events)
    else:
        g["phase"] = "dealing"
        advance(g, events)


def advance(g, events):
    """Run dealing / Flip Three / deferred actions until waiting for input."""
    while True:
        if g["pending_action"]:
            # No eligible target (e.g. Second Chance, everyone has one): discard.
            if not G.eligible_targets(g, g["pending_action"]["action"]):
                events.append(f"🗑 {g['pending_action']['action']} discarded - nobody can take it.")
                g["pending_action"] = None
                after_action_resolved(g, events)
                continue
            g["phase"] = g.get("resume_phase") or g["phase"]
            return
        if g["flip3"]:
            outcome = G.run_flip3_step(g, events)
            if outcome == "bust":
                g["flip3"] = None
                if G.round_over(g):
                    G.end_round(g, events)
                elif g.get("resume_phase") == "dealing":
                    g["phase"] = "dealing"
                else:
                    end_turn(g, events)
                return
            if outcome == "flip7":
                G.end_round(g, events)
                return
            if outcome == "done":
                resume = g["flip3"].get("resume", "playing")
                g["resume_phase"] = resume
                if G.finish_flip3(g, events) == "action":
                    g["pending_action"]["resume"] = resume
                    return
                g["resume_phase"] = resume
                after_action_resolved(g, events)
                return
            continue  # next of the 3
        if g["phase"] == "dealing":
            if not g["deal_queue"]:
                g["phase"] = "playing"
                nxt = G.next_active(g, g["dealer_index"])
                g["current_index"] = nxt if nxt is not None else 0
                if nxt is None:
                    G.end_round(g, events)
                return
            idx = g["deal_queue"].pop(0)
            if g["players"][idx]["status"] != "active":
                continue  # frozen before their initial card
            card = G.draw(g)
            if card is None:
                G.end_round(g, events)
                return
            outcome = G.apply_card(g, idx, card, events)
            if outcome == "action":
                g["resume_phase"] = "dealing"
                g["pending_action"]["resume"] = "dealing"
                return
            if outcome == "flip7":
                G.end_round(g, events)
                return
            continue
        return  # playing / lobby / round_end / game_end: wait for input


def do_hit(g, idx, events):
    card = G.draw(g)
    if card is None:
        G.end_round(g, events)
        return
    outcome = G.apply_card(g, idx, card, events)
    if outcome == "action":
        g["resume_phase"] = "playing"
        g["pending_action"]["resume"] = "playing"
    elif outcome == "flip7":
        G.end_round(g, events)
    elif outcome == "bust":
        if G.round_over(g):
            G.end_round(g, events)
        else:
            end_turn(g, events)
    else:  # ok / saved
        end_turn(g, events)


def do_stay(g, idx, events):
    p = g["players"][idx]
    if not (p["numbers"] or p["modifiers"] or p["second_chance"]):
        events.append(f"⛔ {p['name']} has no cards yet - must Hit.")
        return False
    p["status"] = "stayed"
    events.append(f"✅ {p['name']} stays and banks their cards.")
    if G.round_over(g):
        G.end_round(g, events)
    else:
        end_turn(g, events)
    return True


def do_action_choice(g, target_idx, events):
    pa = g["pending_action"]
    resume = pa.get("resume") or g.get("resume_phase") or "playing"
    g["resume_phase"] = resume
    result = G.resolve_action(g, target_idx, events)
    if result == "flip3":
        g["flip3"]["resume"] = resume
        advance(g, events)
        return
    after_action_resolved(g, events)
    # after_action_resolved may have returned to dealing/playing or queued
    # another action; if it queued, pending_action is set and advance isn't
    # needed. If it resumed dealing, it already called advance().
    if g["pending_action"] and g["pending_action"].get("resume") is None:
        g["pending_action"]["resume"] = resume


# ---------- Rendering ----------
def mention(g, user_id):
    """Telegram ping link for a player (tg://user?id= opens their chat)."""
    return f'<a href="tg://user?id={user_id}">{html.escape(G.name_of(g, user_id))}</a>'


def player_mention(g, user_id):
    """Telegram ping link by player name, usable by any game board."""
    name = next((p["name"] for p in g.get("players", []) if p["user_id"] == user_id), "?")
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


def turn_ping(g):
    """Who must act now (action chooser, else current player), or None."""
    if g["pending_action"]:
        uid = g["pending_action"]["chooser_id"]
        cp = next((p for p in g["players"] if p["user_id"] == uid), None)
        if cp and cp.get("npc"):
            return f"❓ 🤖 NPC chooses who gets <b>{g['pending_action']['action']}</b> - anyone can tap!"
        return f"❓ {mention(g, uid)} - choose who gets <b>{g['pending_action']['action']}</b>"
    if g["phase"] == "playing":
        p = g["players"][g["current_index"]]
        if p.get("npc"):
            return "👉 🤖 NPC's turn - anyone can play for it: Hit or Stay?"
        return f"👉 {mention(g, p['user_id'])} - your turn: Hit or Stay?"
    return None


def keyboard(g):
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join game", "callback_data": "f7:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "f7:npc"}])
        ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
        wk = web_keyboard(ct, g["chat_id"])
        if wk:
            kb.extend(wk)
        return kb
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    if g["phase"] == "playing" and not g["pending_action"]:
        cur = g["players"][g["current_index"]]["name"]
        kb = [[{"text": f"🎴 Hit ({cur})", "callback_data": "f7:hit"},
               {"text": "✅ Stay", "callback_data": "f7:stay"}]]
        wk = web_keyboard(ct, g["chat_id"])  # HTML button to do actions there
        if wk:
            kb.extend(wk)
        return kb
    if g["pending_action"]:
        kb = []
        for i in G.eligible_targets(g, g["pending_action"]["action"]):
            kb.append([{"text": f"➡️ {g['players'][i]['name']}",
                        "callback_data": f"f7:act:{i}"}])
        wk = web_keyboard(ct, g["chat_id"])
        if wk:
            kb.extend(wk)
        return kb or None
    if g["phase"] == "round_end":
        return [[{"text": "▶️ Next round", "callback_data": "f7:next"}]]
    if g["phase"] == "game_end":
        return [[{"text": "🔄 New game", "callback_data": "f7:new"}]]
    return None


def prompt_text(g):
    if g["phase"] == "lobby":
        return (f"🎴 <b>Flip 7 lobby</b> - {len(g['players'])} player(s). "
                f"Friends: /flip7_join, anyone: /flip7_start "
                f"(or use the Mini App). (Official game: 3+ players, first to 200.)")
    if g["pending_action"]:
        return f"{G.board_lines(g)}\n\n{turn_ping(g)}"
    if g["phase"] == "playing":
        return f"{G.board_lines(g)}\n\n{turn_ping(g)}"
    if g["phase"] == "round_end":
        return f"{G.board_lines(g)}\n\nRound scored! Tap Next round when ready."
    if g["phase"] == "game_end":
        w = G.name_of(g, g["winner_id"])
        return f"{G.board_lines(g)}\n\n🏆 <b>{w} wins!</b> Tap New game to play again."
    return G.board_lines(g)


def render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    if g["phase"] == "dealing":  # auto-next: deal the new round right away
        advance(g, events)
    text = prompt_text(g)
    kb = keyboard(g)
    if events:
        # One fresh message per turn: events + board + ping + buttons, so
        # the LAST message always carries the HTML/action buttons (and the
        # ping notifies). Old board message is deleted to keep chat clean.
        lines = [html.escape(e) for e in events]
        ping = turn_ping(g)
        if ping:
            lines.append(ping)
        r = send_board(g, "games", "\n".join(lines) + "\n\n" + text, kb)
        if r.get("ok"):
            old = g.get("board_message_id")
            g["board_message_id"] = r["result"]["message_id"]
            if old:
                api("deleteMessage", chat_id=chat_id, message_id=old)
        return
    if g.get("board_message_id") and g.get("phase") != "lobby":
        r = edit(chat_id, g["board_message_id"], text, kb)
        if r.get("ok"):
            return
    r = send_board(g, "games", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


# ---------- Regicide (co-op, same bot, separate state) ----------
REGICIDE_RULES = """⚔️ <b>Regicide</b> (co-op, 2-4 players): defeat 12 royals (Jacks→Queens→Kings).
Castle: J atk10/hp20, Q 15/30, K 20/40. Tavern: 2-10+Aces(+Jesters by player count).
Hand limit 7/6/5 (2/3/4 players). Turn: play card(s) → suit power → damage → suffer discard.
Play: single card, same-number combo ≤10, or Ace+one card. Jester alone: cancel immunity, no attack, pick next.
♥ heal from discard under Tavern · ♦ draw · ♣ double damage · ♠ shield (cumulative).
Enemy immune to its own suit. Kill exact → royal goes on Tavern top as ally (J=10/Q=15/K=20).
Enemy attack: discard cards ≥ attack or team loses. Yield: skip (not if all just yielded).
Win: defeat last King. Hands are private - only played cards are public (/regicide_play reveals only the played card)."""


def rg_get(state, chat_id):
    return state.setdefault("regicide", {}).get(str(chat_id))


def rg_board_text(g):
    if g["phase"] == "lobby":
        names = ", ".join(html.escape(p["name"]) for p in g["players"])
        return (f"⚔️ <b>Regicide lobby</b> - {len(g['players'])}/4 players: {names}\n"
                f"Anyone: /regicide_join, /regicide_start (needs 2+)")
    e = g["enemy"]
    if e:
        atk, hp = R.enemy_stats(g)
        head = (f"⚔️ <b>Regicide</b> vs <b>{R.card_str(e)}</b> atk {atk} hp {hp} "
                f"(damage {g['enemy_damage']}, shield {g['spade_shield']}, effective atk {R.effective_attack(g)})"
                f"{' (immunity cancelled)' if g['immune_off'] else ' (immune: ' + e['suit'] + ')'}")
    elif g["phase"] == "won":
        head = "🏆 Regicide WON - all 12 royals defeated!"
    else:
        head = "💀 Regicide LOST."
    # Castle suits are hidden (face-down): only rank order/counts are public.
    from collections import Counter
    counts = Counter(c["rank"] for c in g["castle"])
    castle_list = ", ".join(
        f"{r}×{counts[r]} ({R.ROYAL[r][0]}/{R.ROYAL[r][1]})"
        for r in ("J", "Q", "K") if counts.get(r)) or "-"
    lines = [head,
             f"Tavern {len(g['tavern'])} · Castle {len(g['castle'])} · Discard {len(g['discard'])} · Kills {g['kills']}/12",
             f"Castle (atk/hp each): {castle_list}",
             f"Played vs enemy: {' '.join(R.card_str(c) for c in g['played']) or '-'}"]
    for i, p in enumerate(g["players"]):
        turn = " 👈" if i == g["current_index"] and g["phase"] in ("playing", "discard") else ""
        lines.append(f"• {html.escape(p['name'])}: hand {len(p['hand'])}{turn}")
    return "\n".join(lines)


def rg_keyboard(g):
    if g["phase"] in ("won", "lost"):
        return [[{"text": "🔄 Rematch!", "callback_data": "rg:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="regicide")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Regicide", "callback_data": "rg:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "rg:npc"}])
        return kb + (wk or [])
    kb = []
    cur = g["players"][g["current_index"]] if g["players"] else None
    if g["phase"] == "playing" and cur:
        kb.append([{"text": "⏭ Yield", "callback_data": "rg:yield"}])
    if g["phase"] == "jester_next":
        for i, p in enumerate(g["players"]):
            kb.append([{"text": f"🎯 Next: {p['name']}", "callback_data": f"rg:next:{i}"}])
    if wk:
        kb.extend(wk)
    return kb or None


def rg_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    # ping player to act
    ping = None
    if g["phase"] in ("playing", "discard") and g["players"]:
        p = g["players"][g["current_index"]]
        ping = ("👉 🤖 NPC's turn - anyone can play for it!"
                if p.get("npc") else f"👉 {mention_rg(g, p['user_id'])} - your turn")
        if g["phase"] == "discard" and not p.get("npc"):
            ping += f" (discard ≥{g.get('discard_needed', 0)}, done {g.get('discard_total', 0)})"
    if g["phase"] == "jester_next" and g.get("jester_player") is not None:
        _jp = g['players'][g['jester_player']]
        ping = ("🎯 🤖 NPC picks who goes next - anyone can tap!"
                if _jp.get("npc") else f"🎯 {mention_rg(g, _jp['user_id'])} - pick who goes next")
    if ping:
        lines.append(ping)
    text = "\n".join(lines + [rg_board_text(g)]) if lines else rg_board_text(g)
    kb = rg_keyboard(g)
    r = send_board(g, "regicide", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def mention_rg(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(R.name_of_rg(g, user_id))}</a>'


def parse_card(token):
    token = token.strip()
    if token.lower() in ("joker", "jester", "j"):
        return {"suit": "Joker", "rank": "Jester"}
    suitmap = {"h": "♥", "d": "♦", "c": "♣", "s": "♠", "♥": "♥", "♦": "♦", "♣": "♣", "♠": "♠"}
    suit = suitmap.get(token[-1].lower())
    rank = token[:-1].upper()
    if rank == "A":
        rank = "A"
    if suit is None or rank not in R.RANKS:
        return None
    return {"suit": suit, "rank": rank}


def rg_take_cards(g, idx, cards):
    """Remove cards from hand; returns (removed, error)."""
    hand = g["players"][idx]["hand"]
    removed = []
    for c in cards:
        match = next((h for h in hand if h["suit"] == c["suit"] and h["rank"] == c["rank"]), None)
        if match is None:
            for r in removed:
                hand.append(r)
            return [], f"you don't have {R.card_str(c)}"
        hand.remove(match)
        removed.append(match)
    return removed, None


def handle_regicide(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = rg_get(state, chat_id)
    if cmd == "/regicide_rules":
        send(chat_id, REGICIDE_RULES)
        return True
    if cmd == "/regicide":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = R.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("regicide", {})[str(chat_id)] = g
            rg_render(g, [f"⚔️ Regicide game created by {name}!"])
        else:
            rg_render(g)
        return True
    if not g:
        send(chat_id, "No Regicide game here yet - send /regicide to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/regicide_join_npc":
        err = add_npc("regicide", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            rg_render(g)
        return True
    if cmd == "/regicide_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= 4:
            send(chat_id, "⛔ Regicide is 2-4 players (full).")
        else:
            g["players"].append({"user_id": uid, "name": msg.get("from", {}).get("first_name") or "Player", "hand": []})
            send(chat_id, f"🙋 <b>{name}</b> joined Regicide ({len(g['players'])} players).")
            rg_render(g)
        return True
    if cmd == "/regicide_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            ev = []
            err = R.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                rg_render(g, ev)
        return True
    if cmd == "/regicide_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["regicide"][str(chat_id)]
            send(chat_id, "🗑 Regicide game cancelled.")
        return True
    if cmd in ("/regicide_play", "/regicide_discard", "/regicide_yield", "/regicide_score"):
        idx = _actor_idx(g, uid, g["current_index"])
        if idx is None:
            send(chat_id, "⛔ You're not in this Regicide game - /regicide_join in lobby.")
            return True
        ev = []
        if cmd == "/regicide_score":
            rg_render(g, ["📊 Regicide board:"])
            return True
        if cmd == "/regicide_yield":
            err = R.yield_turn(g, idx, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                rg_render(g, ev)
            return True
        parts = text.split()[1:]
        if not parts:
            if (cmd == "/regicide_discard" and g["phase"] == "discard"
                    and not g["players"][idx]["hand"]):
                err = R.discard_cards(g, idx, [], ev)
                if err:
                    send(chat_id, f"⛔ {err}")
                else:
                    rg_render(g, ev)
                return True
            send(chat_id, "Usage: /regicide_play 7h  (or 10s, A♠, joker) - played card becomes public; use Mini App for private selection.")
            return True
        cards = [parse_card(t) for t in parts]
        if any(c is None for c in cards):
            send(chat_id, "⛔ Bad card notation - use e.g. 7h, 10s, A♠, joker.")
            return True
        removed, err = rg_take_cards(g, idx, cards)
        if err:
            send(chat_id, f"⛔ {err}")
            return True
        if cmd == "/regicide_play":
            err = R.play_cards(g, idx, removed, ev)
        else:
            err = R.discard_cards(g, idx, removed, ev)
        if err:
            for r in removed:
                g["players"][idx]["hand"].append(r)
            send(chat_id, f"⛔ {err}")
        else:
            rg_render(g, ev)
        return True
    return False


# ---------- Odin (ladder-climbing card shedding, private hands) ----------
ODIN_RULES = """🛡️ <b>Odin rules</b> (Helvetiq, 2-6 players): shed your hand fastest, first to 0 wins.
Deck 54 = numbers 1-9 in 6 colours (blue/red/pink/green/black/orange); with 2 players 2 colours are removed. Deal 9 each.
• <b>Lead</b> a round with 1 card — or all your hand if it is a single colour/number (that ends the hand).
• <b>Respond</b> with the same number of cards as the table, or one more, as a same-colour or same-number set. The set's digits sorted high→low form its number (6+3 blue = 63) and must beat the table.
• After playing (unless you go out), <b>take 1 card</b> from the previous set; the rest are discarded.
• <b>Pass</b> any time (you can play again next turn). When everyone else has passed, the table is discarded and the last player leads a new round.
• Going out ends the hand immediately (no pickup). Everyone starts at 15 points and subtracts 1 per card left in hand at the end of each hand — first to 0 wins (ties share victory).
Card notation: <code>6b</code> = 6 blue, <code>3o</code> = 3 orange, <code>8k</code> = 8 black (b/r/p/g/k/o)."""


def odin_get(state, chat_id):
    return state.setdefault("odin", {}).get(str(chat_id))


def odin_board_text(g):
    if g["phase"] == "lobby":
        return (f"🛡️ <b>Odin lobby</b> - {len(g['players'])} player(s). "
                f"Friends: /odin_join, anyone: /odin_start")
    if g["phase"] == "game_end":
        w = ", ".join(g["players"][i]["name"] for i in g["winners"])
        scores = " · ".join(f"{p['name']} {p['score']}" for p in g["players"])
        return f"🏆 <b>Odin game over</b> - first to 0 wins: <b>{html.escape(w)}</b>\nScores: {scores}"
    lines = [f"🛡️ <b>Odin</b> - Hand {g.get('hand_no', 1)} · Table: "
             + (f"{g['table_value']} ({' '.join(O.card_str(c) for c in g['table'])})"
                if g["table"] else "- (lead)")]
    if g["phase"] == "pickup":
        pk = g["players"][g["pickup_player"]]
        lines.append(f"✋ {html.escape(pk['name'])} just played "
                     f"{O.set_value(g['pending_play'])} - take 1 from: "
                     f"{' '.join(O.card_str(c) for c in g['table'])}")
    lines.append(f"Deck {len(g['deck'])} · Discard {len(g['discard'])}")
    for i, p in enumerate(g["players"]):
        turn = " 👈" if i == g["current_index"] and g["phase"] == "playing" else ""
        lines.append(f"• {html.escape(p['name'])}: hand {len(p['hand'])} · score {p['score']}{turn}")
    return "\n".join(lines)


def odin_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "od:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="odin")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Odin", "callback_data": "od:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "od:npc"}])
        return kb + (wk or [])
    kb = []
    if g["phase"] == "playing" and g["table"]:
        kb.append([{"text": "⏭ Pass", "callback_data": "od:pass"}])
    if g["phase"] == "pickup":
        for c in g["table"]:
            kb.append([{"text": f"✋ Take {O.card_str(c)}",
                        "callback_data": f"od:pickup:{c['suit']}:{c['rank']}"}])
    if wk:
        kb.extend(wk)
    return kb or None


def odin_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    ping = None
    if g["players"] and g["phase"] in ("playing", "pickup"):
        who = g["pickup_player"] if g["phase"] == "pickup" else g["current_index"]
        p = g["players"][who]
        ping = ("👉 🤖 NPC to move - anyone can play for it!" if p.get("npc")
                else f"👉 {odin_mention(g, p['user_id'])} - " + (
            "take 1 card from the previous set" if g["phase"] == "pickup" else "your turn"))
    if ping:
        lines.append(ping)
    text = "\n".join(lines + [odin_board_text(g)]) if lines else odin_board_text(g)
    kb = odin_keyboard(g)
    r = send_board(g, "odin", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def odin_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(O.name_of(g, user_id))}</a>'


ODIN_SUIT_LETTER = {"b": "blue", "r": "red", "p": "pink", "g": "green", "k": "black", "o": "orange"}


def parse_odin_card(token):
    token = token.strip().lower()
    if len(token) < 2 or not token[0].isdigit():
        return None
    rank, rest = int(token[0]), token[1:]
    suit = ODIN_SUIT_LETTER.get(rest) or (rest if rest in O.SUITS else None)
    return {"suit": suit, "rank": rank} if suit and rank in O.RANKS else None


def odin_take_cards(g, idx, cards):
    """Remove cards from hand; returns (removed, error)."""
    hand = g["players"][idx]["hand"]
    removed = []
    for c in cards:
        match = next((h for h in hand if h["suit"] == c["suit"] and h["rank"] == c["rank"]), None)
        if match is None:
            for r in removed:
                hand.append(r)
            return [], f"you don't have {O.card_str(c)}"
        hand.remove(match)
        removed.append(match)
    return removed, None


def handle_odin(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = odin_get(state, chat_id)
    if cmd == "/odin_rules":
        send(chat_id, ODIN_RULES)
        return True
    if cmd == "/odin":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = O.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("odin", {})[str(chat_id)] = g
            odin_render(g, [f"🛡️ Odin game created by {name}!"])
        else:
            odin_render(g)
        return True
    if not g:
        send(chat_id, "No Odin game here yet - send /odin to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/odin_join_npc":
        err = add_npc("odin", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            odin_render(g)
        return True
    if cmd == "/odin_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= 6:
            send(chat_id, "⛔ Odin is 2-6 players (full).")
        else:
            g["players"].append({"user_id": uid, "name": msg.get("from", {}).get("first_name") or "Player", "hand": [], "score": O.START_SCORE})
            send(chat_id, f"🙋 <b>{name}</b> joined Odin ({len(g['players'])} players).")
            odin_render(g)
        return True
    if cmd == "/odin_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            ev = []
            err = O.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                odin_render(g, ev)
        return True
    if cmd == "/odin_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["odin"][str(chat_id)]
            send(chat_id, "🗑 Odin game cancelled.")
        return True
    if cmd == "/odin_score":
        odin_render(g)
        return True
    if cmd == "/odin_pass":
        idx = _actor_idx(g, uid, g["current_index"])
        if idx is None:
            send(chat_id, "⛔ You're not in this Odin game - /odin_join in lobby.")
            return True
        ev = []
        err = O.pass_turn(g, idx, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            odin_render(g, ev)
        return True
    if cmd in ("/odin_play", "/odin_pickup"):
        _ref = g["pickup_player"] if cmd == "/odin_pickup" and g.get("pickup_player") is not None else g["current_index"]
        idx = _actor_idx(g, uid, _ref)
        if idx is None:
            send(chat_id, "⛔ You're not in this Odin game - /odin_join in lobby.")
            return True
        parts = text.split()[1:]
        if cmd == "/odin_pickup":
            if len(parts) != 1 or parse_odin_card(parts[0]) is None:
                send(chat_id, "Usage: /odin_pickup 6b  (or tap a Take button)")
                return True
            ev = []
            err = O.choose_pickup(g, idx, parse_odin_card(parts[0]), ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                odin_render(g, ev)
            return True
        if not parts:
            send(chat_id, "Usage: /odin_play 6b 3b  (cards you play; notation: number+colour letter, e.g. 6b = 6 blue)")
            return True
        cards = [parse_odin_card(t) for t in parts]
        if any(c is None for c in cards):
            send(chat_id, "⛔ Bad card notation - use e.g. 6b, 3o, 8k (number + colour letter b/r/p/g/k/o).")
            return True
        removed, err = odin_take_cards(g, idx, cards)
        if err:
            send(chat_id, f"⛔ {err}")
            return True
        ev = []
        err = O.play_cards(g, idx, removed, ev)
        if err:
            g["players"][idx]["hand"].extend(removed)
            send(chat_id, f"⛔ {err}")
        else:
            odin_render(g, ev)
        return True
    return False



# ---------- 13 Leaves (I'm Out style) ----------
LEAVES_RULES = LEAVES_MODULE.rules()


def leaves_get(state, chat_id):
    return state.setdefault("leaves", {}).get(str(chat_id))


def leaves_board_text(g):
    if g.get("phase") == "lobby":
        return f"🍃 <b>13 Leaves lobby</b> - {len(g['players'])} player(s). Friends: /leaves_join, anyone: /leaves_start"
    if g.get("phase") == "game_end":
        w = next((p["name"] for p in g["players"] if p["user_id"] == g.get("winner_id")), "?")
        return f"🏆 <b>13 Leaves</b> - winner: <b>{html.escape(w)}</b>"
    row = g.get("row") or []
    row_s = " · ".join([f"{s['value']}×{s['count']}" for s in row]) if row else "(empty, lead any set)"
    lines = [f"🍃 <b>13 Leaves</b> — row: {row_s}"]
    for i, p in enumerate(g["players"]):
        mark = " 👈" if i == g.get("current_index") and g.get("phase") == "playing" else ""
        passed = " (passed)" if p["user_id"] in (g.get("passed") or set()) else ""
        lines.append(f"• {html.escape(p['name'])}: {len(p['hand'])} cards{passed}{mark}")
    return "\n".join(lines)


def leaves_keyboard(g):
    if g.get("phase") == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "lv:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="leaves")
    if g.get("phase") == "lobby":
        kb = [[{"text": "🙋 Join 13 Leaves", "callback_data": "lv:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "lv:npc"}])
        return kb + (wk or [])
    kb = []
    if g.get("phase") == "playing":
        row = g.get("row") or []
        if row:
            # one button per stack to take from (1..len)
            for i, sst in enumerate(row):
                kb.append([{"text": f"⏭ Pass (take {sst['value']} from #{i+1})", "callback_data": f"lv:pass{i}"}])
        else:
            kb.append([{"text": "⏭ Pass", "callback_data": "lv:pass"}])
    if wk:
        kb.extend(wk)
    return kb or None


def leaves_render(g, events=None):
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    if g.get("players") and g.get("phase") == "playing":
        cur = g["players"][g["current_index"]]
        ping = "👉 🤖 NPC to move" if cur.get("npc") else f"👉 {player_mention(g, cur['user_id'])} - your turn"
        lines.append(ping)
    text = "\n".join(lines + [leaves_board_text(g)]) if lines else leaves_board_text(g)
    kb = leaves_keyboard(g)
    r = send_board(g, "leaves", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=g["chat_id"], message_id=old)


def handle_leaves(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = leaves_get(state, chat_id)
    if cmd == "/leaves_rules":
        send(chat_id, LEAVES_RULES)
        return True
    if cmd == "/leaves":
        if not g:
            g = LEAVES_MODULE.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("leaves", {})[str(chat_id)] = g
            leaves_render(g, [f"🍃 13 Leaves created by {name}!"])
        else:
            leaves_render(g)
        return True
    if not g:
        send(chat_id, "No 13 Leaves game here - send /leaves to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/leaves_join_npc":
        err = add_npc("leaves", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined!")
            leaves_render(g)
        return True
    if cmd == "/leaves_join":
        if g.get("phase") != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= GR.GAMES_BY_KEY["leaves"].max_players:
            send(chat_id, GR.NPC_FULL["leaves"])
        else:
            g["players"].append(LEAVES_MODULE.new_player(uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined ({len(g['players'])}).")
            leaves_render(g)
        return True
    if cmd == "/leaves_start":
        if g.get("phase") != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < GR.GAMES_BY_KEY["leaves"].min_players:
            send(chat_id, f"⛔ Need at least {GR.GAMES_BY_KEY['leaves'].min_players} players.")
        else:
            ev = []
            err = LEAVES_MODULE.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                leaves_render(g, ev)
        return True
    if cmd == "/leaves_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["leaves"][str(chat_id)]
            send(chat_id, "🗑 13 Leaves cancelled.")
        return True
    if cmd == "/leaves_pass":
        idx = _actor_idx(g, uid, g["current_index"])
        if idx is None:
            send(chat_id, "⛔ Not in this game.")
            return True
        parts = text.split()[1:]
        take_index = None
        if parts:
            try:
                take_index = int(parts[0]) - 1
            except Exception:
                send(chat_id, "Usage: /leaves_pass [row_stack_number] (1 = leftmost).")
                return True
        ev = []
        err = LEAVES_MODULE.pass_turn(g, idx, ev, take_index=take_index)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            leaves_render(g, ev)
        return True
    if cmd == "/leaves_play":
        idx = _actor_idx(g, uid, g["current_index"])
        if idx is None:
            send(chat_id, "⛔ Not in this game.")
            return True
        parts = text.split()[1:]
        if len(parts) < 2:
            send(chat_id, "Usage: /leaves_play <value> <count>  e.g. /leaves_play 5 2")
            return True
        try:
            val = int(parts[0]); cnt = int(parts[1])
        except Exception:
            send(chat_id, "Usage: /leaves_play <value> <count>")
            return True
        ev = []
        err = LEAVES_MODULE.play(g, idx, val, cnt, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            leaves_render(g, ev)
        return True
    return False


def handle_leaves_callback(state, cb, chat_id, uid):
    data = cb.get("data", "")
    parts = data.split(":")
    g = leaves_get(state, chat_id)
    if not g:
        return answer_cb(cb["id"], "No 13 Leaves game here.")
    if parts == ["lv", "join"]:
        if g["phase"] != "lobby":
            return answer_cb(cb["id"], "Game already started.")
        if any(p["user_id"] == uid for p in g["players"]):
            return answer_cb(cb["id"], "Already in!")
        if len(g["players"]) >= GR.GAMES_BY_KEY["leaves"].max_players:
            return answer_cb(cb["id"], "Full.")
        name = cb["from"].get("first_name") or "Player"
        g["players"].append(LEAVES_MODULE.new_player(uid, name))
        leaves_render(g, [f"🙋 {name} joined."])
        save_state(state)
        return answer_cb(cb["id"], "Joined!")
    if parts == ["lv", "start"]:
        if g["phase"] != "lobby":
            return answer_cb(cb["id"], "Already started.")
        if len(g["players"]) < GR.GAMES_BY_KEY["leaves"].min_players:
            return answer_cb(cb["id"], "Need >=3 players.")
        ev = []
        err = LEAVES_MODULE.start_game(g, ev)
        if err:
            return answer_cb(cb["id"], err)
        leaves_render(g, ev)
        save_state(state)
        return answer_cb(cb["id"], "Started!")
    if parts[0] == "lv" and len(parts) == 2 and parts[1].startswith("pass"):
        idx = _actor_idx(g, uid, g.get("current_index", 0))
        if idx is None:
            return answer_cb(cb["id"], "Not in game.")
        take_index = None
        if parts[1] != "pass":
            try:
                take_index = int(parts[1][4:])
            except ValueError:
                take_index = None
        ev = []
        err = LEAVES_MODULE.apply_action(g, idx, "pass", {"take_index": take_index}, ev)
        if err:
            return answer_cb(cb["id"], err)
        leaves_render(g, ev)
        save_state(state)
        return answer_cb(cb["id"], "Passed.")
    if parts == ["lv", "rematch"]:
        ev, err = rematch_game(state, "leaves", chat_id, uid)
        answer_cb(cb["id"], err or "Rematch!")
        if not err:
            save_state(state)
        return
    return answer_cb(cb["id"], "Unknown button.")


# ---------- The Fellowship of the Ring (cooperative trick-taking) ----------
FTR_RULES = """💍 <b>Fellowship of the Ring rules</b> (short):
• 2–4 players, 18 chapters. Shuffle 37 cards (Hills/Mountains/Forests/Shadows 1–8, Rings 1–5). Turn one face-up as the <b>lost card</b> (never the 1 of Rings), deal 12 each (2–3p) or 9 each (4p). Whoever holds the <b>1 of Rings</b> is Frodo and leads; the One Ring cannot be exchanged.
• Follow the lead suit; highest rank of that suit wins the trick. Rings cannot be led until someone plays a Ring off-suit (or Rings is your only suit). When you play the <b>1 of Rings</b> you may choose to win the trick — it must still follow suit.
• Start to Frodo's left: characters with a 🔨 perform setup (draw the lost card, draw a threat, or exchange one card). Exchange targets choose the card passed back.
• Each character has a goal (win N tricks, win Rings, win the last trick, avoid a threat number, etc.). Win a round only if <b>every chosen character</b> succeeds. Short chapters end when all goals are met; long chapters repeat rounds until all roster goals are met or fail and retry.
• Commands: <code>/fotr_chapter N</code>, <code>/fotr_choose key</code>, <code>/fotr_exchange CARD TARGET</code>, <code>/fotr_back CARD</code>, <code>/fotr_play CARD</code>, <code>/fotr_ring yes|no</code>, <code>/fotr_retry</code>, <code>/fotr_next</code>.
• Later chapter rosters/goals are simplified approximations of the printed campaign."""


def fotr_get(state, chat_id):
    return state.setdefault("fellowship", {}).get(str(chat_id))


def fotr_actor(g, uid, ref):
    """Only the referenced seat (or anyone controlling the NPC) may act."""
    if ref is None or not (0 <= ref < len(g["players"])):
        return None
    p = g["players"][ref]
    if p.get("npc"):
        return ref
    return ref if p["user_id"] == uid else None


def fotr_apply(g, uid, action, params=None):
    """Apply one Fellowship action. Returns (events, error)."""
    params = params or {}
    ev = []

    def want_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    if action == "join":
        if g.get("phase") != "lobby":
            return ev, "game already started"
        if any(p["user_id"] == uid for p in g["players"]):
            return ev, None
        if len(g["players"]) >= FTR.MAX_PLAYERS:
            return ev, f"Fellowship is {FTR.MIN_PLAYERS}-{FTR.MAX_PLAYERS} players (full)."
        g["players"].append(FTR.new_player(uid, params.get("name") or "Player"))
        ev.append(f"🙋 {html.escape(params.get('name') or 'Player')} joined.")
        return ev, None
    if action == "npc":
        err = add_npc("fellowship", g)
        if not err:
            ev.append("🤖 NPC joined - anyone can play for it.")
        return ev, err
    if action == "start":
        err = FTR.start_game(g, ev, params.get("chapter"))
        return ev, err
    if action == "chapter":
        err = FTR.set_chapter(g, params.get("chapter"), ev)
        return ev, err
    if action == "choose":
        idx = fotr_actor(g, uid, FTR.selection_actor(g))
        if idx is None:
            return ev, "not your turn to choose"
        err = FTR.choose_character(g, idx, params.get("character") or params.get("key"), ev)
        return ev, err
    if action == "out":
        idx = fotr_actor(g, uid, FTR.pending_actor(g))
        if idx is None:
            return ev, "not your exchange"
        target = want_int(params.get("target"))
        if target is None:
            return ev, "bad exchange target"
        err = FTR.exchange_cards(g, idx, params.get("card"), target, ev)
        return ev, err
    if action == "back":
        idx = fotr_actor(g, uid, FTR.pending_actor(g))
        if idx is None:
            return ev, "not your exchange"
        err = FTR.exchange_back(g, idx, params.get("card"), ev)
        return ev, err
    if action == "play":
        idx = fotr_actor(g, uid, g.get("current"))
        if idx is None:
            return ev, "not your turn"
        err = FTR.play_card(g, idx, params.get("card"), ev)
        return ev, err
    if action == "ring":
        idx = fotr_actor(g, uid, FTR.pending_actor(g))
        if idx is None:
            return ev, "no Ring choice for you"
        use_it = params.get("use")
        if isinstance(use_it, str):
            use_it = use_it.lower() in ("1", "yes", "y", "true", "on")
        err = FTR.ring_choice(g, idx, bool(use_it), ev)
        return ev, err
    if action == "retry":
        err = FTR.retry_round(g, ev)
        return ev, err
    if action == "restart":
        err = FTR.restart_chapter(g, ev)
        return ev, err
    if action == "next":
        err = FTR.next_chapter(g, ev)
        return ev, err
    return ev, "unknown action"


def fotr_board_text(g):
    title = FTR.chapter_name(g["chapter"])
    ch = FTR.chapter(g["chapter"])
    head = f"💍 <b>Fellowship</b> — {html.escape(title)} · round {g.get('round', 1)}"
    if ch:
        head += f" · {html.escape(ch['victory'])}"
    lines = [head]
    for i, p in enumerate(g["players"]):
        mark = ""
        if i == g.get("ring_holder"):
            mark += " 💍"
        if i == FTR.current_player(g) and g.get("phase") not in ("lobby", "game_end"):
            mark += " 👈"
        chname = FTR.CHARACTERS.get(p["character"], {}).get("name", "?")
        lines.append(f"• {html.escape(p['name'])} — {html.escape(chname)} · {len(p['hand'])} cards{mark}")
    phase = g.get("phase")
    if phase == "lobby":
        lines.append(f"🪑 Lobby ({len(g['players'])}/{FTR.MAX_PLAYERS}). /fotr_join, /fotr_join_npc, /fotr_start [chapter].")
        lines.append(f"📖 Now: {html.escape(title)}. /fotr_chapter N to choose another chapter.")
    elif phase == "choosing":
        opts = FTR.available_characters(g)
        lines.append("🎭 Choose your character: " + ", ".join(
            f"<code>{c}</code> {html.escape(FTR.CHARACTERS[c]['name'])}" for c in opts))
    elif phase == "setup":
        pend = g.get("pending") or {}
        if pend.get("kind") == "exchange_out":
            lines.append(f"🔨 Exchange one card with {html.escape(g['players'][pend['targets'][0]]['name'])} (or choose a target), then they pass one back.")
        elif pend.get("kind") == "exchange_in":
            lines.append("🔨 Pass a card back to complete the exchange (the same card is allowed).")
        else:
            lines.append("🔨 Setup actions in progress...")
    elif phase == "playing":
        trick = g.get("trick")
        lead = f"lead {html.escape(trick['suit'])}" if trick and trick["suit"] else "lead any suit"
        plays = ", ".join(
            f"{html.escape(g['players'][pl['player']]['name'])}:{FTR.cshort(pl['card'])}"
            for pl in (trick["plays"] if trick else [])) or "—"
        lines.append(f"🃏 Trick {g.get('trick_no', 1)} · {lead} · plays: {plays}")
        lines.append(f"🃏 Lost: {FTR.cname(g['lost']) if g.get('lost') else 'taken'}"
                     f" · Rings {'BROKEN' if g.get('ring_broken') else 'sealed'}")
        goals = FTR.goal_status(g)
        if goals:
            lines.append("🎯 Goals: " + " · ".join(
                f"{html.escape(goal['name'])} {'✅' if goal['ok'] else '❌'}"
                for goal in goals))
    elif phase in ("round_end", "chapter_end", "game_end"):
        res = g.get("result") or phase
        lines.append(f"🏁 Result: <b>{html.escape(str(res))}</b>")
        if phase != "game_end":
            lines.append("Buttons below: retry round / restart chapter / next chapter.")
        else:
            lines.append("🏆 Campaign complete! Pick any chapter with /fotr_chapter N.")
    return "\n".join(lines)


def fotr_keyboard(g):
    kb = []
    phase = g.get("phase")
    if phase == "lobby":
        kb.append([{"text": "🙋 Join", "callback_data": "fotr:join"}])
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "fr:npc"}])
        kb.append([{"text": "🎮 Start", "callback_data": "fotr:start"}])
    elif phase == "choosing":
        row = []
        for c in FTR.available_characters(g):
            row.append({"text": FTR.CHARACTERS[c]["name"], "callback_data": f"fotr:choose:{c}"})
            if len(row) == 2:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
    elif phase == "setup":
        pend = g.get("pending") or {}
        idx = pend.get("actor")
        if pend.get("kind") == "exchange_out" and idx is not None:
            hand = [c for c in g["players"][idx]["hand"]
                    if not (idx == g["ring_holder"] and c == "R1")]
            for t in pend.get("targets", []):
                tname = g["players"][t]["name"]
                row = [{"text": f"{FTR.cshort(c)} → {html.unescape(tname)[:8]}",
                        "callback_data": f"fotr:out:{c}:{t}"} for c in hand[:12]]
                for i in range(0, len(row), 4):
                    kb.append(row[i:i + 4])
        elif pend.get("kind") == "exchange_in" and idx is not None:
            hand = [c for c in g["players"][idx]["hand"]
                    if not (idx == g["ring_holder"] and c == "R1")]
            row = [{"text": FTR.cshort(c), "callback_data": f"fotr:back:{c}"} for c in hand]
            for i in range(0, len(row), 5):
                kb.append(row[i:i + 5])
    elif phase == "playing":
        pend = g.get("pending") or {}
        if pend.get("kind") == "ring_choice":
            kb.append([
                {"text": "💍 Claim with R1", "callback_data": "fotr:ring:1"},
                {"text": "⏭ Let it lose", "callback_data": "fotr:ring:0"},
            ])
        else:
            idx = g.get("current")
            if idx is not None:
                row = [{"text": FTR.cshort(c), "callback_data": f"fotr:play:{c}"}
                       for c in FTR.legal_cards(g, idx)]
                for i in range(0, len(row), 5):
                    kb.append(row[i:i + 5])
    if phase in ("round_end", "chapter_end"):
        kb.append([
            {"text": "🔁 Retry round", "callback_data": "fotr:retry"},
            {"text": "↺ Restart chapter", "callback_data": "fotr:restart"},
        ])
        if phase == "chapter_end":
            kb.append([{"text": "📖 Next chapter", "callback_data": "fotr:next"}])
    if phase in ("chapter_end", "game_end"):
        kb.append([{"text": "🔄 New game", "callback_data": "fotr:rematch"}])
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="fellowship")
    if wk:
        kb.extend(wk)
    return kb or None


def fotr_render(g, events=None):
    lines = list(events or [])
    if g.get("players") and g.get("phase") not in ("lobby", "game_end"):
        idx = FTR.current_player(g)
        if idx is not None:
            who = g["players"][idx]
            lines.append("👉 🤖 NPC to move" if who.get("npc") else f"👉 {player_mention(g, who['user_id'])} - your turn")
    text = "\n".join(lines + [fotr_board_text(g)])
    r = send_board(g, "fellowship", text, fotr_keyboard(g))
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=g["chat_id"], message_id=old)


def handle_fellowship(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = fotr_get(state, chat_id)
    if cmd in ("/fotr_rules", "/fellowship_rules"):
        send(chat_id, FTR_RULES)
        return True
    if cmd in ("/fotr", "/fellowship"):
        if not g:
            g = FTR.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("fellowship", {})[str(chat_id)] = g
            fotr_render(g, ["💍 Fellowship created! Use /fotr_join, then /fotr_start."])
        else:
            fotr_render(g)
        return True
    if not g:
        send(chat_id, "No Fellowship game here - send /fotr to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    parts = text.split()
    arg = parts[1] if len(parts) > 1 else None
    rest = parts[2:] if len(parts) > 2 else []
    if cmd in ("/fotr_join", "/fellowship_join"):
        ev, err = fotr_apply(g, uid, "join", {"name": name})
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_join_npc", "/fellowship_join_npc"):
        ev, err = fotr_apply(g, uid, "npc")
        send(chat_id, err or "🤖 NPC joined!")
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_start", "/fellowship_start"):
        ev, err = fotr_apply(g, uid, "start", {"chapter": arg})
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_chapter", "/fellowship_chapter"):
        if not arg:
            send(chat_id, "Usage: /fotr_chapter <1-18>")
        else:
            ev, err = fotr_apply(g, uid, "chapter", {"chapter": arg})
            send(chat_id, f"⛔ {err}" if err else "📖 Chapter set.")
            if not err:
                fotr_render(g, ev)
        return True
    if cmd in ("/fotr_choose", "/fellowship_choose"):
        ev, err = fotr_apply(g, uid, "choose", {"character": arg})
        send(chat_id, f"⛔ {err}" if err else f"🎭 Chose {arg}.")
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_exchange", "/fellowship_exchange"):
        if len(rest) < 1:
            send(chat_id, "Usage: /fotr_exchange <card> [target_index]")
        else:
            pend = g.get("pending") or {}
            target = rest[0] if rest else (pend.get("targets") or [0])[0]
            ev, err = fotr_apply(g, uid, "out", {"card": arg, "target": target})
            send(chat_id, f"⛔ {err}" if err else "🔄 Card passed.")
            if not err:
                fotr_render(g, ev)
        return True
    if cmd in ("/fotr_back", "/fellowship_back"):
        ev, err = fotr_apply(g, uid, "back", {"card": arg})
        send(chat_id, f"⛔ {err}" if err else "🔄 Exchange complete.")
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_play", "/fellowship_play"):
        ev, err = fotr_apply(g, uid, "play", {"card": arg})
        send(chat_id, f"⛔ {err}" if err else f"🃏 Played {arg}.")
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_ring", "/fellowship_ring"):
        use = (arg or "").lower() in ("yes", "y", "1", "true", "on")
        ev, err = fotr_apply(g, uid, "ring", {"use": use})
        send(chat_id, f"⛔ {err}" if err else ("💍 Claimed the trick." if use else "⏭ Let it pass."))
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_retry", "/fellowship_retry"):
        ev, err = fotr_apply(g, uid, "retry")
        send(chat_id, f"⛔ {err}" if err else "🔁 Round re-dealt.")
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_restart", "/fellowship_restart"):
        ev, err = fotr_apply(g, uid, "restart")
        send(chat_id, f"⛔ {err}" if err else "↺ Chapter restarted.")
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_next", "/fellowship_next"):
        ev, err = fotr_apply(g, uid, "next")
        send(chat_id, f"⛔ {err}" if err else "📖 Next chapter.")
        if not err:
            fotr_render(g, ev)
        return True
    if cmd in ("/fotr_cancel", "/fellowship_cancel"):
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["fellowship"][str(chat_id)]
            send(chat_id, "🗑 Fellowship cancelled.")
        return True
    return False


def fotr_board_json(g, viewer_id=None):
    board = FTR.public_board(g, viewer_id)
    board["chat_type"] = g.get("chat_type", "private")
    return board


def fotr_api_move(state, chat_id, user_id, body):
    g = fotr_get(state, chat_id)
    if not g:
        return [], "no Fellowship game in that chat"
    action = body.get("action")
    if action == "rematch":
        return rematch_game(state, "fellowship", chat_id, user_id)
    params = dict(body)
    if params.get("character") is None and params.get("key") is not None:
        params["character"] = params["key"]
    ev, err = fotr_apply(g, user_id, action, params)
    if err:
        return ev, err
    fotr_render(g, ev)
    return ev, None


# ---------- Let's Summon Demons (dice activation, market, demons) ----------
LSD_RULES = """😈 <b>Let's Summon Demons rules</b> (Cryptozoic, 2-5 players): be first to 3 summoned Demons AND 10 Souls.
Setup: 5 Souls each, a Candle in play (collects 1 Soul on any of its numbers), 3 hidden Demon cards in hand, 5 cards face-up on THE BLOCK.
On your turn, once each in any order: <b>roll 2d6</b> (mandatory), <b>buy 1 Block card for 3 Souls</b>, <b>summon a Demon</b> by discarding 3 of your Block cards (4 if an opponent has Baphometal).
Every roll activates all matching cards in play for everyone (Demons only on their owner's rolls), in turn order from the roller. Candles never leave play.
Win check runs after every effect. Full card texts are shown in the Mini App / on each card."""


def lsd_get(state, chat_id):
    return state.setdefault("lsd", {}).get(str(chat_id))


def lsd_board_text(g):
    if g["phase"] == "lobby":
        return (f"😈 <b>Let's Summon Demons lobby</b> - {len(g['players'])} player(s). "
                f"Friends: /lsd_join, anyone: /lsd_start")
    if g["phase"] == "game_end":
        w = D.name_of(g, g["winner"])
        scores = " · ".join(f"{p['name']} {p['souls']}👻/{len(p['demons'])}😈" for p in g["players"])
        return f"🏆 <b>{html.escape(w)} is the ultimate Demon Summoner!</b>\nScores: {scores}"
    lines = ["😈 <b>Let's Summon Demons</b>"]
    lines.append("THE BLOCK: " + " · ".join(f"{i+1}:{c['name']}({c['num']})" for i, c in enumerate(g["market"])))
    if g.get("dice"):
        lines.append(f"Last roll: {g['dice'][0]}+{g['dice'][1]}={g['last_total']}")
    for i, p in enumerate(g["players"]):
        turn = " 👈" if i == g["current_index"] else ""
        lines.append(f"• {html.escape(p['name'])}: {p['souls']}👻 · {len(p['demons'])}😈 · "
                     + ", ".join(f"{c['name']}({c['num'] if c['num'] is not None else '∞'})" for c in p["in_play"])
                     + (f" + candle {p['candle']['name']}" if p["candle"] else "") + turn)
    if g["pending"]:
        lines.append("⏳ Choice needed - tap a button below.")
    return "\n".join(lines)


def lsd_pending_options(g):
    """Human-labelled options for the current pending choice (shared by
    Telegram buttons and the Mini App)."""
    pend = g.get("pending")
    if not pend:
        return []
    kind, pl = pend["kind"], pend["player"]

    def card_label(iid):
        _, c = D.find_card(g, iid)
        if c:
            return c["name"]
        c = next((c for c in g["market"] if c["iid"] == iid), None)
        return c["name"] if c else f"card#{iid}"

    def player_label(j):
        return g["players"][j]["name"]

    if kind == "reroll":
        return [{"choice": "reroll", "label": "🔁 Re-roll"}, {"choice": "keep", "label": "Keep roll"}]
    if kind == "optional":
        return [{"choice": "do", "label": f"✅ Do it (discard {pend['name']})"},
                {"choice": "skip", "label": "Skip"}]
    if kind == "steal_souls":
        return [{"choice": j, "label": player_label(j)} for j in pend["options"] if j != "supply"] + \
               ([{"choice": "supply", "label": "Supply"}] if "supply" in pend["options"] else [])
    if kind in ("steal_card", "alligator"):
        opts = [{"choice": {"player": o["player"], "iid": o["iid"]},
                 "label": f"{player_label(o['player'])}: {card_label(o['iid'])}"} for o in pend["options"]]
        if kind == "alligator":
            opts.append({"choice": "done", "label": "✅ Done"})
        return opts
    if kind == "gain_block":
        return [{"choice": iid, "label": card_label(iid)} for iid in pend["options"]]
    if kind == "activate_choice":
        return [{"choice": iid, "label": card_label(iid)} for iid in pend["options"]]
    if kind == "replace_block":
        return [{"choice": iid, "label": card_label(iid)} for iid in pend["options"]] + \
               [{"choice": "done", "label": "✅ Done"}]
    if kind in ("goat_boy", "goat_girl", "sam_animal"):
        return [{"choice": iid, "label": card_label(iid)} for iid in pend["options"]]
    if kind == "rosemary":
        return [{"choice": iid, "label": card_label(iid)} for iid in pend["options"]]
    if kind == "gross_book":
        return [{"choice": iid, "label": card_label(iid)} for iid in pend["options"]]
    if kind in ("glen_player", "steal_player"):
        return [{"choice": j, "label": player_label(j)} for j in pend["options"]]
    if kind == "annie_branch":
        return [{"choice": "steal", "label": "😈 Steal a BOY/GIRL"},
                {"choice": "gain", "label": "🛒 Gain from THE BLOCK"}]
    return []


def lsd_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "lsd:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="lsd")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Summon Demons", "callback_data": "lsd:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "lsd:npc"}])
        return kb + (wk or [])
    kb = []
    if g["pending"]:
        opts = lsd_pending_options(g)
        # Telegram callbacks encode the choice compactly; Mini App sends JSON.
        for o in opts:
            ch = o["choice"]
            if isinstance(ch, dict):
                data = f"lsd:c:{g['pending']['kind']}:{ch['player']}:{ch['iid']}"
            else:
                data = f"lsd:c:{g['pending']['kind']}:{ch}"
            kb.append([{"text": o["label"][:60], "callback_data": data}])
    else:
        if g["phase"] == "playing":
            kb.append([{"text": "🎲 Roll dice", "callback_data": "lsd:roll"},
                       {"text": "🏁 End turn", "callback_data": "lsd:end"}])
            for i in range(len(g["market"])):
                kb.append([{"text": f"🛒 Buy #{i+1} {g['market'][i]['name']}",
                            "callback_data": f"lsd:buy:{i}"}])
    if wk:
        kb.extend(wk)
    return kb or None


def lsd_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    ping = None
    if g["players"] and g["phase"] == "playing":
        if g["pending"]:
            who = g["pending"]["player"]
            _pp = g["players"][who]
            ping = ("👉 🤖 NPC to choose - anyone can tap below!"
                    if _pp.get("npc") else f"👉 {lsd_mention(g, _pp['user_id'])} - make the choice shown below")
        else:
            who = g["current_index"]
            _cp = g["players"][who]
            ping = ("👉 🤖 NPC's turn - anyone can play for it!"
                    if _cp.get("npc") else f"👉 {lsd_mention(g, _cp['user_id'])} - your turn (roll, buy, summon, end)")
    if ping:
        lines.append(ping)
    text = "\n".join(lines + [lsd_board_text(g)]) if lines else lsd_board_text(g)
    kb = lsd_keyboard(g)
    r = send_board(g, "lsd", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def lsd_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(D.name_of(g, user_id))}</a>'


def _lsd_by_slug(g, idx, slug):
    """Find a card by slug in a player's in-play / demon hand / market."""
    for c in g["players"][idx]["in_play"] + g["players"][idx]["demons"] + g["players"][idx]["demon_hand"]:
        if c["slug"] == slug:
            return c
    return None


def handle_lsd(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = lsd_get(state, chat_id)
    if cmd == "/lsd_rules":
        send(chat_id, LSD_RULES)
        return True
    if cmd == "/lsd":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = D.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("lsd", {})[str(chat_id)] = g
            lsd_render(g, [f"😈 Let's Summon Demons game created by {name}!"])
        else:
            lsd_render(g)
        return True
    if not g:
        send(chat_id, "No Summon Demons game here yet - send /lsd to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/lsd_join_npc":
        err = add_npc("lsd", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            lsd_render(g)
        return True
    if cmd == "/lsd_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= 5:
            send(chat_id, "⛔ Let's Summon Demons is 2-5 players (full).")
        else:
            g["players"].append({"user_id": uid, "name": msg.get("from", {}).get("first_name") or "Player",
                                 "souls": 5, "candle": None, "in_play": [], "demons": [], "demon_hand": []})
            send(chat_id, f"🙋 <b>{name}</b> joined Let's Summon Demons ({len(g['players'])} players).")
            lsd_render(g)
        return True
    if cmd == "/lsd_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            ev = []
            err = D.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                lsd_render(g, ev)
        return True
    if cmd == "/lsd_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["lsd"][str(chat_id)]
            send(chat_id, "🗑 Summon Demons game cancelled.")
        return True
    if cmd == "/lsd_score":
        lsd_render(g)
        return True
    _ref = g["pending"]["player"] if g.get("pending") else g["current_index"]
    idx = _actor_idx(g, uid, _ref)
    if idx is None:
        send(chat_id, "⛔ You're not in this game - /lsd_join in lobby.")
        return True
    ev = []
    if cmd == "/lsd_roll":
        err = D.roll_dice(g, idx, ev)
    elif cmd == "/lsd_end":
        if g["pending"]:
            err = "resolve the pending choice first"
        elif not g["turn"]["rolled"]:
            err = "you must roll the dice first"
        else:
            D.end_turn(g, ev)
            err = None
    elif cmd.startswith("/lsd_buy"):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit() or not (1 <= int(parts[1]) <= len(g["market"])):
            send(chat_id, "Usage: /lsd_buy <1-5> (market position)")
            return True
        err = D.buy_card(g, idx, g["market"][int(parts[1]) - 1]["iid"], ev)
    elif cmd == "/lsd_summon":
        parts = text.split()[1:]
        if len(parts) < 2:
            send(chat_id, "Usage: /lsd_summon <demon-slug> <sacrifice-slugs...> e.g. /lsd_summon porkus adam eve jane")
            return True
        demon = _lsd_by_slug(g, idx, parts[0].lower())
        if demon is None or demon["kind"] != "demon":
            send(chat_id, "⛔ That Demon is not in your hand.")
            return True
        sac = []
        for s in parts[1:]:
            c = _lsd_by_slug(g, idx, s.lower())
            if c is None:
                send(chat_id, f"⛔ You don't have {s} in play.")
                return True
            sac.append(c["iid"])
        err = D.summon(g, idx, sac, demon["iid"], ev)
    else:
        return False
    if err:
        send(chat_id, f"⛔ {err}")
    else:
        lsd_render(g, ev)
    return True


# ---------- Spots (push-your-luck dog dice) ----------
SPOTS_RULES = """🐶 <b>Spots rules</b> (CMYK, 2-4 players): fill the spots on your dog cards to score them. First to 6 scored wins.
Setup: 2 dog cards each (gray side up), 1 treat, 1 die buried in your yard. Highest opening die starts.
On your turn either <b>do a trick</b> (choose a face-up trick tile, flip it down, follow its steps: roll dice, place each die on a matching open spot on your dogs or bury it in your yard; spend treats to reroll a whole roll before placing) or <b>score</b> all your completed dogs (needs at least 1 complete; flip them, draw replacements up to 6 total cards).
Buried total over 7 = <b>bust</b>: all dice on your unscored dogs and in your yard are discarded, turn ends. Completing all your dogs mid-trick auto-scores them instantly.
Dog cards are public. Trick set in play: Adoption Event (Howl, Roll Over, Walk, Run, Fetch, Beg)."""


def spots_get(state, chat_id):
    return state.setdefault("spots", {}).get(str(chat_id))


def spots_board_text(g):
    if g["phase"] == "lobby":
        return (f"🐶 <b>Spots lobby</b> - {len(g['players'])} player(s). "
                f"Friends: /spots_join, anyone: /spots_start")
    if g["phase"] == "game_end":
        w = SP.name_of(g, g["winner"])
        scores = " · ".join(f"{p['name']} {len(p['scored'])}🏅" for p in g["players"])
        return f"🏆 <b>{html.escape(w)} wins Spots!</b>\nScores: {scores}"
    lines = ["🐶 <b>Spots</b> · Tricks: " + " ".join(
        f"{SP.TILE_NAMES[t['slug']]}{' ×'+str(t['treat_on']) if t.get('treat_on') else ''}" if t["faceup"] else f"[{SP.TILE_NAMES[t['slug']]}↓]"
        for t in g["tiles"])]
    if g.get("last_roll"):
        lines.append(f"🎲 Last roll: {', '.join(map(str, g['last_roll']))}")
    if g.get("trick"):
        t = g["trick"]
        lines.append(f"🎪 Trick: {SP.TILE_NAMES[t['tile']]} · Dice to place: "
                     f"{', '.join(map(str, t['dice'])) or '-'}")
    for i, p in enumerate(g["players"]):
        turn = " 👈" if i == g["current_index"] and g["phase"] == "playing" else ""
        dogs = "; ".join(
            f"{d['name']}[{','.join(str(s) for s in d['spots'])}]"
            f"{'{'+','.join(str(v) for v in d.get('placed', {}).values())+'}' if d.get('placed') else ''}"
            for d in p["dogs"])
        lines.append(f"• {html.escape(p['name'])}: {len(p['scored'])}🏅 · {p['treats']}🦴 · "
                     f"yard {p['yard']} = {SP.yard_total(p)} · dogs {dogs or '-'}{turn}")
    if g["pending"]:
        lines.append("⏳ Choice needed - tap a button below or use /spots_place.")
    return "\n".join(lines)


def spots_pending_options(g):
    pend = g.get("pending")
    if not pend:
        return []
    kind = pend["kind"]

    def dog_label(iid):
        for p in g["players"]:
            d = next((d for d in p["dogs"] if d["iid"] == iid), None)
            if d:
                return d["name"]
        return f"dog#{iid}"

    def yard_label(o):
        this = f"{g['players'][o['player']]['name']}'s yard die #{o['yard'] + 1}"
        return this

    if kind == "choose_number":
        if (g.get("trick") or {}).get("tile") == "fetch":
            rolled = (g.get("trick") or {}).get("fetch_rolled") or []
            return [{"choice": n, "label": f"Number {n} ×{rolled.count(n)}"} for n in pend["options"]]
        return [{"choice": n, "label": f"Number {n}"} for n in pend["options"]]
    if kind == "optional_roll":
        return [{"choice": "roll", "label": "🎲 Roll 1 more die"},
                {"choice": "done", "label": "✅ Done"}]
    if kind == "repeat":
        return [{"choice": "repeat", "label": "🔁 Repeat this step"},
                {"choice": "done", "label": "✅ Done"}]
    if kind == "bolt_count":
        return [{"choice": n, "label": f"{n} dice"} for n in pend["options"]]
    if kind == "trot":
        return [{"choice": o, "label": f"{dog_label(o['from_dog'])}♢{o['from_spot'] + 1} → "
                 f"{dog_label(o['to_dog'])}♢{o['to_spot'] + 1}"} for o in pend["options"]]
    if kind == "dig":
        return [{"choice": o, "label": f"{yard_label(o)} {'+1' if o['delta'] > 0 else '-1'}"}
                for o in pend["options"]] + [{"choice": "done", "label": "✅ Done"}]
    if kind == "scavenge":
        dice = (g.get("trick") or {}).get("dice", [])
        return [{"choice": i, "label": f"Discard die #{i + 1}"
                 + (f" ({dice[i]})" if i < len(dice) else "")} for i in pend["options"]] + \
               [{"choice": "done", "label": "✅ Done discarding"}]
    if kind == "dogpile_take":
        opts = []
        for o in pend["options"]:
            if o["src"] == "yard":
                opts.append({"choice": o, "label": yard_label(o)})
            else:
                opts.append({"choice": o, "label": f"{dog_label(o['dog'])} die"})
        return opts
    return []


def spots_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "spots:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="spots")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Spots", "callback_data": "spots:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "spots:npc"}])
        return kb + (wk or [])
    kb = []
    if g["pending"]:
        kind = g["pending"]["kind"]
        for o in spots_pending_options(g):
            ch = o["choice"]
            if kind == "trot":
                data = f"spots:c:trot:{ch['from_dog']}:{ch['from_spot']}:{ch['to_dog']}:{ch['to_spot']}"
            elif kind == "dig":
                data = "spots:c:dig:done" if ch == "done" else f"spots:c:dig:{ch['player']}:{ch['yard']}:{ch['delta']}"
            elif kind == "dogpile_take":
                data = f"spots:c:dogpile_take:yard:{ch['yard']}" if ch["src"] == "yard" else f"spots:c:dogpile_take:dog:{ch['dog']}:{ch['spot']}"
            else:
                data = f"spots:c:{kind}:{ch}"
            kb.append([{"text": o["label"][:60], "callback_data": data}])
    elif g["phase"] == "playing" and not g["trick"]:
        for t in g["tiles"]:
            if t["faceup"]:
                kb.append([{"text": f"🎪 {SP.TILE_NAMES[t['slug']]}{' ×'+str(t['treat_on']) if t.get('treat_on') else ''}",
                            "callback_data": f"spots:trick:{t['slug']}"}])
        kb.append([{"text": "🏅 Score dogs", "callback_data": "spots:score"}])
    if wk:
        kb.extend(wk)
    return kb or None


def spots_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    ping = None
    if g["players"] and g["phase"] == "playing":
        who = g["pending"]["player"] if g["pending"] else g["current_index"]
        _pp = g["players"][who]
        ping = ("👉 🤖 NPC to move - anyone can play for it!"
                if _pp.get("npc") else f"👉 {spots_mention(g, _pp['user_id'])} - your turn")
    if ping:
        lines.append(ping)
    text = "\n".join(lines + [spots_board_text(g)]) if lines else spots_board_text(g)
    kb = spots_keyboard(g)
    r = send_board(g, "spots", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def spots_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(SP.name_of(g, user_id))}</a>'


def handle_spots(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = spots_get(state, chat_id)
    if cmd == "/spots_rules":
        send(chat_id, SPOTS_RULES)
        return True
    if cmd == "/spots":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = SP.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("spots", {})[str(chat_id)] = g
            spots_render(g, [f"🐶 Spots game created by {name}!"])
        else:
            spots_render(g)
        return True
    if not g:
        send(chat_id, "No Spots game here yet - send /spots to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/spots_join_npc":
        err = add_npc("spots", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            spots_render(g)
        return True
    if cmd == "/spots_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= 4:
            send(chat_id, "⛔ Spots is 1-4 players (full).")
        else:
            g["players"].append({"user_id": uid, "name": msg.get("from", {}).get("first_name") or "Player",
                                 "dogs": [], "scored": [], "yard": [], "treats": 1})
            send(chat_id, f"🙋 <b>{name}</b> joined Spots ({len(g['players'])} players).")
            spots_render(g)
        return True
    if cmd == "/spots_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            ev = []
            err = SP.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                spots_render(g, ev)
        return True
    if cmd == "/spots_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["spots"][str(chat_id)]
            send(chat_id, "🗑 Spots game cancelled.")
        return True
    if cmd == "/spots_score":
        _ref = g["pending"]["player"] if g.get("pending") else g["current_index"]
        idx = _actor_idx(g, uid, _ref)
        if idx is None:
            send(chat_id, "⛔ You're not in this game - /spots_join in lobby.")
            return True
        ev = []
        err = SP.score_action(g, idx, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            spots_render(g, ev)
        return True
    if cmd.startswith("/spots_trick"):
        _ref = g["pending"]["player"] if g.get("pending") else g["current_index"]
        idx = _actor_idx(g, uid, _ref)
        if idx is None:
            send(chat_id, "⛔ You're not in this game - /spots_join in lobby.")
            return True
        parts = text.split()
        if len(parts) != 2 or parts[1].lower() not in SP.ALL_TILES:
            send(chat_id, "Usage: /spots_trick <tile> (e.g. walk, run, fetch, beg, howl, roll-over)")
            return True
        ev = []
        err = SP.choose_trick(g, idx, parts[1].lower(), ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            spots_render(g, ev)
        return True
    if cmd.startswith("/spots_place"):
        _ref = g["pending"]["player"] if g.get("pending") else g["current_index"]
        idx = _actor_idx(g, uid, _ref)
        if idx is None:
            send(chat_id, "⛔ You're not in this game - /spots_join in lobby.")
            return True
        parts = text.split()
        ev = []
        err = None
        if len(parts) == 3 and parts[2] == "yard" and parts[1].isdigit():
            err = SP.do_place(g, idx, int(parts[1]) - 1, ("yard",), ev)
        elif len(parts) == 5 and parts[1].isdigit():
            dog = next((d for d in g["players"][idx]["dogs"] if d["slug"] == parts[3].lower()), None)
            if dog is None or not parts[4].isdigit():
                err = "usage: /spots_place <die#> <dog-slug> <spot#> | /spots_place <die#> yard"
            else:
                err = SP.do_place(g, idx, int(parts[1]) - 1, ("dog", dog["iid"], int(parts[4]) - 1), ev)
        else:
            err = "usage: /spots_place <die#> <dog-slug> <spot#> | /spots_place <die#> yard"
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            spots_render(g, ev)
        return True
    if cmd.startswith("/spots_reroll"):
        _ref = g["pending"]["player"] if g.get("pending") else g["current_index"]
        idx = _actor_idx(g, uid, _ref)
        if idx is None:
            send(chat_id, "⛔ You're not in this game - /spots_join in lobby.")
            return True
        parts = text.split()[1:]
        if parts and parts[0] == "all":
            indices = None
        else:
            indices = [int(x) - 1 for x in parts if x.isdigit()] or None
        ev = []
        err = SP.do_reroll(g, idx, indices, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            spots_render(g, ev)
        return True
    return False


# ---------- Yahtzee (dice scorecard) ----------
YAHTZEE_RULES = """🎲 <b>Yahtzee rules</b> (2-6 players): fill all 13 boxes on your scorecard; highest total wins.
• Each turn roll 5 dice, then reroll any you don't want to keep (up to <b>3 rolls</b> total), then score one open box.
• Upper: Ones…Sixes = sum of those dice. Score <b>63+</b> in the upper section for a <b>+35</b> bonus.
• Three/Four of a Kind = sum of all dice (need 3/4 alike). Full House = 25. Small Straight = 30. Large Straight = 40. Yahtzee = 50. Chance = sum.
• Extra Yahtzee (after the Yahtzee box is filled with 50): <b>+100</b> each.
• Game ends when every player has filled all 13 boxes."""


def yahtzee_get(state, chat_id):
    return state.setdefault("yahtzee", {}).get(str(chat_id))


def yahtzee_board_text(g):
    if g["phase"] == "lobby":
        return (f"🎲 <b>Yahtzee lobby</b> - {len(g['players'])} player(s). "
                f"Friends: /yahtzee_join, anyone: /yahtzee_start")
    if g["phase"] == "game_end":
        if g.get("winners"):
            names = ", ".join(g["players"][i]["name"] for i in g["winners"])
        else:
            names = "nobody"
        scores = " · ".join(f"{p['name']} {Y.total_score(p)}" for p in g["players"])
        return f"🏆 <b>Yahtzee game over</b> - winner: <b>{html.escape(names)}</b>\n{scores}"
    lines = ["🎲 <b>Yahtzee</b>"]
    for i, p in enumerate(g["players"]):
        turn = " 👈" if i == g["current_index"] else ""
        upper = Y.upper_subtotal(p)
        bonus = " · upper bonus ✓" if Y.has_upper_bonus(p) else f" · upper {upper}/63"
        lines.append(f"• {html.escape(p['name'])}: <b>{Y.total_score(p)}</b> pts "
                     f"({Y.filled_count(p)}/{len(Y.CATEGORIES)}){bonus}{turn}")
    t = g.get("turn")
    if t and t["dice"]:
        dice = " ".join(str(d) for d in t["dice"])
        kept = [str(i + 1) for i, k in enumerate(t["keep"]) if k]
        extra = f" · kept {', '.join(kept)}" if kept else ""
        lines.append(f"🎲 Dice: [{dice}] · roll {t['rolls']}/{Y.MAX_ROLLS}{extra}")
    return "\n".join(lines)


def yahtzee_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "yz:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="yahtzee")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Yahtzee", "callback_data": "yz:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "yz:npc"}])
        return kb + (wk or [])
    kb = []
    t = g.get("turn")
    if t and t["dice"]:
        kb.append([{"text": f"{'✅' if t['keep'][i] else ''}{d}",
                    "callback_data": f"yz:keep:{i}"}
                   for i, d in enumerate(t["dice"])])
    if t and t["rolls"] < Y.MAX_ROLLS:
        label = ("🎲 Roll dice" if t["rolls"] == 0
                 else f"🎲 Reroll ({Y.MAX_ROLLS - t['rolls']} left)")
        kb.append([{"text": label, "callback_data": "yz:roll"}])
    if t and t["rolls"] >= 1:
        cur = g["players"][g["current_index"]]
        avail = [(k, lbl) for k, lbl in Y.CATEGORIES if cur["scores"][k] is None]
        if t["dice"]:  # preview: points the current dice would score there
            avail = [(k, f"{lbl} · {Y.score_for(k, t['dice'])}") for k, lbl in avail]
        for j in range(0, len(avail), 2):
            kb.append([{"text": lbl, "callback_data": f"yz:score:{k}"}
                       for k, lbl in avail[j:j + 2]])
    if wk:
        kb.extend(wk)
    return kb or None


def yahtzee_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    if g["phase"] == "playing" and g["players"]:
        p = g["players"][g["current_index"]]
        ping = ("👉 🤖 NPC's turn - anyone can play for it!" if p.get("npc")
                else f"👉 {yahtzee_mention(g, p['user_id'])} - your turn")
        lines.append(ping)
    text = "\n".join(lines + [yahtzee_board_text(g)]) if lines else yahtzee_board_text(g)
    kb = yahtzee_keyboard(g)
    r = send_board(g, "yahtzee", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def yahtzee_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(Y.name_of(g, user_id))}</a>'


def parse_yahtzee_category(token):
    token = token.strip().lower()
    if token in Y.CAT_KEY:
        return Y.CAT_KEY[token]
    if token in Y.CAT_LABEL:
        return token
    for key, label in Y.CATEGORIES:
        if label.lower().replace(" ", "_").replace("-", "_") == token:
            return key
    return None


def handle_yahtzee(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = yahtzee_get(state, chat_id)
    if cmd == "/yahtzee_rules":
        send(chat_id, YAHTZEE_RULES)
        return True
    if cmd == "/yahtzee":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = Y.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("yahtzee", {})[str(chat_id)] = g
            yahtzee_render(g, [f"🎲 Yahtzee game created by {name}!"])
        else:
            yahtzee_render(g)
        return True
    if not g:
        send(chat_id, "No Yahtzee game here yet - send /yahtzee to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/yahtzee_join_npc":
        err = add_npc("yahtzee", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            yahtzee_render(g)
        return True
    if cmd == "/yahtzee_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= Y.MAX_PLAYERS:
            send(chat_id, f"⛔ Yahtzee is 2-{Y.MAX_PLAYERS} players (full).")
        else:
            g["players"].append(Y.new_player(uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Yahtzee ({len(g['players'])} players).")
            yahtzee_render(g)
        return True
    if cmd == "/yahtzee_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            ev = []
            err = Y.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                yahtzee_render(g, ev)
        return True
    if cmd == "/yahtzee_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["yahtzee"][str(chat_id)]
            send(chat_id, "🗑 Yahtzee game cancelled.")
        return True
    if cmd == "/yahtzee_score":
        parts = text.split()[1:]
        if not parts:
            yahtzee_render(g)
            return True
        idx = _actor_idx(g, uid, g["current_index"])
        if idx is None:
            send(chat_id, "⛔ You're not in this Yahtzee game - /yahtzee_join in lobby.")
            return True
        cat = parse_yahtzee_category(parts[0])
        if not cat:
            send(chat_id, "⛔ Unknown category. Try: ones twos threes fours fives sixes "
                          "three_kind four_kind full_house small_straight large_straight yahtzee chance")
            return True
        ev = []
        err = Y.score_category(g, idx, cat, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            yahtzee_render(g, ev)
        return True
    if cmd in ("/yahtzee_roll", "/yahtzee_keep"):
        idx = _actor_idx(g, uid, g["current_index"])
        if idx is None:
            send(chat_id, "⛔ You're not in this Yahtzee game - /yahtzee_join in lobby.")
            return True
        parts = [p for p in text.split()[1:] if p.isdigit()]
        keep = [False] * Y.DICE_COUNT
        for p in parts:
            i = int(p) - 1
            if 0 <= i < Y.DICE_COUNT:
                keep[i] = True
        ev = []
        err = Y.roll_dice(g, idx, keep, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            yahtzee_render(g, ev)
        return True
    if cmd == "/yahtzee_put":
        send(chat_id, "Use /yahtzee_score &lt;category&gt; to fill a box.")
        return True
    return False


TORNADO_RULES = """🛥️ <b>Tornado Splash rules</b> (2-5 players, Arclight 2025): pick one of 6 jet skis (each with its own 20-card deck of ➡️ straight / 🌊 curve cards worth 1-2 spaces) and race to the finish gate.
• <b>Boat selection</b>: a random player picks first, then clockwise. Boats differ in Speed/Handling stars and weight (the lightest boat lines up first and draws 4, the heaviest draws 6).
• Every round: 1) <b>Rank racers</b> - turn order by proximity to the finish (ties → lighter boat). 2) <b>Replenish hand</b> - draw up to your rank's limit: 1st 4, last 6, others 5; deck empty → your played cards come back, earliest first. 3) <b>Make waves</b> - in rank order, play cards and move their total in spaces: <b>max 3/round</b>, 4 on your once-per-race ⚡ boost.
• <b>Checkpoints</b>: passing one requires a 🌊 curve card in that move; stopping exactly on it is free.
• First to reach or cross the finish wins; the race continues until all but one have finished. Optional <b>Grand Prix</b>: 3 races over 4 courses, points 5/3/2/0 by finish - most points is champion.
• Commands: /tornado_pick &lt;boat 1-6&gt; · /tornado_play &lt;card#...&gt; [b] · /tornado_hand · /tornado_wait [card#...] (discard &amp; wait) · /tornado_next (next GP race)."""


def tornado_get(state, chat_id):
    return state.setdefault("tornado", {}).get(str(chat_id))


def tornado_board_text(g):
    if g["phase"] == "lobby":
        return (f"🛥️ <b>Tornado Splash lobby</b> - {len(g['players'])} racer(s). "
                f"Friends: /tornado_join, anyone: /tornado_start (add 'gp' for Grand Prix)")
    if g["phase"] == "picking":
        c = TS.course(g)
        lines = [f"🛥️ <b>Tornado Splash</b> - boat selection "
                 f"({'Grand Prix, 3 races' if g['gp'] else 'single race'})",
                 f"🌊 Course: {c['name']} - {c['length']} spaces, checkpoints at "
                 + ", ".join(f"{cp} ({d})" for cp, d in c["checkpoints"])]
        for k, idx in enumerate(g["picking_order"]):
            p = g["players"][idx]
            if p["boat"] is not None:
                b = TS.BOATS[p["boat"]]
                lines.append(f"• {html.escape(p['name'])}: {b['name']}")
            elif k == g["picking_index"]:
                lines.append(f"👉 {html.escape(p['name'])} is picking a boat...")
        lines.append("🎲 /tornado_auto - auto-assign the rest and start")
        return "\n".join(lines)
    if g["phase"] == "game_end":
        names = " & ".join(html.escape(TS.name_of(g, u)) for u in g.get("winners", []))
        scores = " · ".join(f"{html.escape(p['name'])} {p['points']} pts" for p in g["players"])
        return f"🏆 <b>Grand Prix over</b> - champion: <b>{names}</b>\n{scores}"
    c = TS.course(g)
    head = (f"🛥️ <b>Tornado Splash</b> - Race {g['race_number']}/{TS.total_races(g)}: "
            if g["gp"] else f"🛥️ <b>Tornado Splash</b>: ") + f"{c['name']} ({c['length']} spaces)"
    lines = [head,
             "Checkpoints: " + ", ".join(f"{cp} ({d})" for cp, d in c["checkpoints"])]
    cur = g["turn_order"][g["current_index"]] if g["turn_order"] else None
    for i in TS.compute_ranks(g):
        p = g["players"][i]
        b = TS.BOATS[p["boat"]] if p["boat"] is not None else None
        nm = html.escape(p["name"]) + (f" ({b['name']})" if b else "")
        if p["finished"]:
            lines.append(f"• {p['finish_rank']}{TS._ord(p['finish_rank'])} {nm} 🏁"
                         + (f" · {p['points']} pts" if g["gp"] else ""))
        else:
            arrow = " 👈" if i == cur else ""
            boost = " ⚡" if not p["boost_used"] else ""
            lines.append(f"• {nm}: {p['pos']}/{c['length']}{boost}{arrow}")
    if g["phase"] == "race_end":
        if g["gp"]:
            lines.append(f"Race {g['race_number']} done - anyone: /tornado_next")
        else:
            by = TS.compute_ranks(g)
            pod = ", ".join(f"{k+1}. {html.escape(g['players'][i]['name'])}" for k, i in enumerate(by[:3]))
            lines.append(f"🏆 Podium: {pod}")
    return "\n".join(lines)


def tornado_keyboard(g):
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="tornado")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Tornado Splash", "callback_data": "ts:join"}]]
        if len(g["players"]) >= 2:
            kb.append([{"text": "🏁 Start race", "callback_data": "ts:start"},
                       {"text": "🏆 Grand Prix", "callback_data": "ts:gp"}])
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "ts:npc"}])
        return kb + (wk or [])
    if g["phase"] == "picking":
        kb = []
        row = []
        for bi, b in enumerate(TS.BOATS):
            taken = any(p["boat"] == bi for p in g["players"])
            row.append({"text": ("✅ " if taken else "") + b["name"],
                        "callback_data": f"ts:pick:{bi}"})
            if len(row) == 3:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        kb.append([{"text": "🎲 Auto-assign & start", "callback_data": "ts:auto"}])
        kb.extend(wk or [])
        return kb
    if g["phase"] == "playing":
        kb = [[{"text": "🃏 My hand", "callback_data": "ts:hand"}],
              [{"text": "⏳ Wait", "callback_data": "ts:wait"}]]
        kb.extend(wk or [])
        return kb
    if g["phase"] == "race_end":
        kb = ([[{"text": "▶️ Next race", "callback_data": "ts:next"}]] if g["gp"]
              else [[{"text": "🔄 Rematch!", "callback_data": "ts:rematch"}]])
        kb.extend(wk or [])
        return kb
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "ts:rematch"}]] + (wk or [])
    return wk


def tornado_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    if g["phase"] == "playing" and g["turn_order"]:
        p = g["players"][g["turn_order"][g["current_index"]]]
        ping = ("👉 🤖 NPC's turn - anyone can play for it!" if p.get("npc")
                else f"👉 {tornado_mention(g, p['user_id'])} - your turn (3 spaces max)")
        lines.append(ping)
    text = "\n".join(lines + [tornado_board_text(g)]) if lines else tornado_board_text(g)
    kb = tornado_keyboard(g)
    r = send_board(g, "tornado", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def tornado_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(TS.name_of(g, user_id))}</a>'


def tornado_hand_str(g, idx):
    p = g["players"][idx]
    cap = TS.max_move(g, idx, boost=False)
    cap_b = TS.max_move(g, idx, boost=True)
    c = TS.course(g)
    cp_ahead = [cp for cp, _ in c["checkpoints"] if cp > p["pos"]]
    lines = [f"🃏 Your hand ({TS.BOATS[p['boat']]['name']}, space {p['pos']}/{c['length']}):"]
    if p["hand"]:
        lines.append(" · ".join(f"{h+1}.{TS.card_str(cd)}" for h, cd in enumerate(p["hand"])))
    else:
        lines.append("(empty)")
    lines.append(f"Max {cap} spaces this turn"
                 + (f" ({cap_b} with ⚡ boost)" if not p["boost_used"] else "")
                 + (f" · next checkpoint at {cp_ahead[0]} (needs 🌊)" if cp_ahead else ""))
    lines.append("Play: /tornado_play 1 3 (add b for boost) · /tornado_wait")
    return "\n".join(lines)


def handle_tornado(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = tornado_get(state, chat_id)
    if cmd == "/tornado_rules":
        send(chat_id, TORNADO_RULES)
        return True
    if cmd == "/tornado":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = TS.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("tornado", {})[str(chat_id)] = g
            tornado_render(g, [f"🛥️ Tornado Splash game created by {name}!"])
        else:
            tornado_render(g)
        return True
    if not g:
        send(chat_id, "No Tornado Splash game here yet - send /tornado to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/tornado_join_npc":
        err = add_npc("tornado", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            tornado_render(g)
        return True
    if cmd == "/tornado_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= TS.MAX_PLAYERS:
            send(chat_id, f"⛔ Tornado Splash is 2-{TS.MAX_PLAYERS} players (full).")
        else:
            g["players"].append(TS.new_player(uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Tornado Splash ({len(g['players'])} racers).")
            tornado_render(g)
        return True
    if cmd == "/tornado_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 racers.")
        else:
            gp = any(a in ("gp", "grandprix", "grand_prix", "prix")
                     for a in text.lower().split()[1:])
            ev = []
            err = TS.start_picking(g, ev, gp=gp if gp else None)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                tornado_render(g, ev)
        return True
    if cmd == "/tornado_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["tornado"][str(chat_id)]
            send(chat_id, "🗑 Tornado Splash game cancelled.")
        return True
    if cmd == "/tornado_pick":
        idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
        if idx is None and g["phase"] == "picking" and g["picking_order"]:
            idx = _actor_idx(g, uid, g["picking_order"][g["picking_index"]])
        if idx is None:
            send(chat_id, "⛔ You're not in this game - /tornado_join in lobby.")
            return True
        parts = [p for p in text.split()[1:] if p.isdigit()]
        if not parts:
            send(chat_id, "Pick a boat: /tornado_pick 1-6")
            return True
        ev = []
        err = TS.pick_boat(g, idx, int(parts[0]) - 1, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            tornado_render(g, ev)
        return True
    if cmd == "/tornado_auto":
        if not any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "⛔ You're not in this game - /tornado_join in lobby.")
            return True
        ev = []
        err = TS.auto_assign_boats(g, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            tornado_render(g, ev)
        return True
    if cmd == "/tornado_hand":
        idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
        if idx is None:
            send(chat_id, "⛔ You're not in this game.")
        elif g["players"][idx]["boat"] is None:
            send(chat_id, "Pick a boat first.")
        else:
            send(chat_id, tornado_hand_str(g, idx))
        return True
    if cmd in ("/tornado_play", "/tornado_wait"):
        cur = g["turn_order"][g["current_index"]] if g["turn_order"] else None
        idx = _actor_idx(g, uid, cur if cur is not None else 0)
        if idx is None:
            send(chat_id, "⛔ You're not in this game - /tornado_join in lobby.")
            return True
        toks = text.split()[1:]
        boost = any(t.lower() in ("b", "boost") for t in toks)
        pos = [int(t) - 1 for t in toks
               if t.isdigit() and 0 < int(t) <= 20]
        ev = []
        if cmd == "/tornado_play":
            err = TS.do_play(g, idx, pos, boost=boost, events=ev)
        else:
            err = TS.do_wait(g, idx, discard=pos, events=ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            tornado_render(g, ev)
        return True
    if cmd == "/tornado_next":
        ev = []
        err = TS.next_race(g, uid, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            tornado_render(g, ev)
        return True
    return False


FLIPTOONS_RULES = """🦋 <b>Fliptoons rules</b> (2-4 players): build a 3×2 grid of toon cards each round and earn fame; the first player to reach <b>30</b> fame triggers the Final Flip.
• <b>Flip</b>: each player automatically reveals cards into their grid (abilities resolve).
• <b>Check Fame</b>: add up the fame of every face-up card in your grid.
• <b>Market</b> (clockwise): <b>2 actions</b> each — hire a market card (cost = slot: 3/4/7/10/15) or dismiss one of your own face-up cards (5 fame; Caterpillar 3). Hired cards go on top of your deck for next round.
• <b>Cleanup</b>: grids return to decks; the first-player marker rotates. At <b>30+</b> fame the leader takes Critic's Choice (+3 at the Final Flip) and one final round is played.
• Most fame at the Final Flip wins. If the toon deck and market run out, the Final Flip also triggers."""


def fliptoons_get(state, chat_id):
    return state.setdefault("fliptoons", {}).get(str(chat_id))


def _ft_player(user_id, name):
    return {"user_id": int(user_id), "name": name, "deck": [], "grid": [[] for _ in range(6)], "extra": [],
            "discarded": [], "fame": 0, "fame_bonus": 0, "bonus_actions": 0,
            "actions": 0, "last_placed": None, "ostrich_queue": [],
            "eagle_pending": False, "after_flip": [], "in_flip": False}


def fliptoons_actor(g):
    """Index of the player who must act now, or None (auto flip/end)."""
    if g.get("pending"):
        return g["pending"]["player"]
    if g["phase"] == "playing" and g["stage"] == "market":
        return g.get("market_idx")
    return None


def _ft_card_label(c):
    return "?" if c["fd"] else FT.card_name(c)


def _ft_stack_label(st):
    if not st:
        return "·"
    s = _ft_card_label(st[-1])
    if len(st) > 1:
        s += f"×{len(st)}"
    return s


def fliptoons_board_text(g):
    if g["phase"] == "lobby":
        return (f"🦋 <b>Fliptoons lobby</b> - {len(g['players'])}/4 players. "
                f"Friends: /fliptoons_join, anyone: /fliptoons_start")
    if g["phase"] == "game_end":
        if g.get("winner") is not None:
            w = g["players"][g["winner"]]
            return (f"🏆 <b>Fliptoons game over</b> - winner: "
                    f"<b>{html.escape(w['name'])}</b> with {w['fame']} fame!")
        return "🤝 <b>Fliptoons game over</b> - it's a draw!"
    actor = fliptoons_actor(g)
    lines = [f"🦋 <b>Fliptoons</b> · round {g['round']} · "
             f"{g['stage'].replace('_', ' ')} · target {FT.FAME_TARGET} fame"]
    for i, p in enumerate(g["players"]):
        mark = " 👈" if i == actor else ""
        cells = [_ft_stack_label(st) for st in p["grid"]]
        while len(cells) < 6:
            cells.append("·")
        budget = ""
        if g["stage"] == "market" and i == g.get("market_idx"):
            budget = f" · budget {p['fame'] + p['fame_bonus']}"
        lines.append(f"• <b>{html.escape(p['name'])}</b> - fame {FT.grid_fame(g, p)} · "
                     f"deck {len(p['deck'])}{budget}{mark}")
        for r in range(2):
            lines.append("  " + " ".join(f"[{cells[r * 3 + c]}]" for c in range(3)))
        for e in p["extra"]:
            lines.append("  + " + " ".join(f"[{_ft_stack_label([c])}]" for c in e["cards"]))
    market = " · ".join(
        (f"{FT.PRICES[i]}:{_ft_card_label(c)}" if c else f"{FT.PRICES[i]}:—")
        for i, c in enumerate(g["market"]))
    lines.append(f"🛒 Market: {market}")
    if g.get("pending"):
        lines.append(f"❓ {html.escape(g['pending']['prompt'])}")
    return "\n".join(lines)


def fliptoons_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "ft:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="fliptoons")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Fliptoons", "callback_data": "ft:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "ft:npc"}])
        return kb + (wk or [])
    kb = []
    pend = g.get("pending")
    if pend:
        opts = pend["options"]
        for j in range(0, len(opts), 2):
            kb.append([{"text": o["label"][:60], "callback_data": f"ft:ch:{o['v']}"}
                       for o in opts[j:j + 2]])
    elif g["stage"] == "market" and g.get("market_idx") is not None:
        for slot, card in enumerate(g["market"]):
            if card:
                kb.append([{"text": f"{FT.PRICES[slot]}💰 {_ft_card_label(card)}",
                            "callback_data": f"ft:hire:{slot}"}])
        p = g["players"][g["market_idx"]]
        dismiss = []
        for cell in FT._reading_cells(p):
            for c in FT._stack_at(p, cell):
                if c["fd"] or c["r"] in FT.UNDISMISSABLE:
                    continue
                cost = 3 if c["s"] == FT.CATERPILLAR else FT.DISMISS_COST
                dismiss.append((c, cost))
        for j in range(0, len(dismiss), 2):
            kb.append([{"text": f"🗑 {_ft_card_label(c)} ({cost})",
                        "callback_data": f"ft:dismiss:{c['id']}"}
                       for c, cost in dismiss[j:j + 2]])
        kb.append([{"text": "⏭ Skip / end market", "callback_data": "ft:skip"}])
    if wk:
        kb.extend(wk)
    return kb or None


def fliptoons_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    if g["phase"] == "playing":
        idx = fliptoons_actor(g)
        if idx is not None:
            p = g["players"][idx]
            if g.get("pending"):
                lines.append(f"👉 {fliptoons_mention(g, p['user_id'])} - "
                             f"{html.escape(g['pending']['prompt'])}")
            else:
                ping = ("👉 🤖 NPC's turn - anyone can play for it!" if p.get("npc")
                        else f"👉 {fliptoons_mention(g, p['user_id'])} - market turn")
                lines.append(ping)
    text = "\n".join(lines + [fliptoons_board_text(g)]) if lines else fliptoons_board_text(g)
    kb = fliptoons_keyboard(g)
    r = send_board(g, "fliptoons", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def fliptoons_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(FT.name_of(g, user_id))}</a>'


def _ft_dismissables(p):
    out = []
    for cell in FT._reading_cells(p):
        for c in FT._stack_at(p, cell):
            if not c["fd"] and c["r"] not in FT.UNDISMISSABLE:
                out.append(c)
    return out


def handle_fliptoons(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = fliptoons_get(state, chat_id)
    if cmd == "/fliptoons_rules":
        send(chat_id, FLIPTOONS_RULES)
        return True
    if cmd == "/fliptoons":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = FT.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("fliptoons", {})[str(chat_id)] = g
            fliptoons_render(g, [f"🦋 Fliptoons game created by {name}!"])
        else:
            fliptoons_render(g)
        return True
    if not g:
        send(chat_id, "No Fliptoons game here yet - send /fliptoons to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/fliptoons_join_npc":
        err = add_npc("fliptoons", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            fliptoons_render(g)
        return True
    if cmd == "/fliptoons_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= 4:
            send(chat_id, "⛔ Fliptoons is 2-4 players (full).")
        else:
            g["players"].append(_ft_player(
                uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Fliptoons ({len(g['players'])} players).")
            fliptoons_render(g)
        return True
    if cmd == "/fliptoons_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            ev = []
            err = FT.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                fliptoons_render(g, ev)
        return True
    if cmd == "/fliptoons_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["fliptoons"][str(chat_id)]
            send(chat_id, "🗑 Fliptoons game cancelled.")
        return True
    if cmd in ("/fliptoons_hire", "/fliptoons_dismiss", "/fliptoons_skip",
               "/fliptoons_choose"):
        ref = fliptoons_actor(g)
        if ref is None:
            send(chat_id, "⛔ Nothing to do right now (flip phase).")
            return True
        idx = _actor_idx(g, uid, ref)
        if idx is None:
            send(chat_id, "⛔ You're not in this Fliptoons game - /fliptoons_join in lobby.")
            return True
        parts = text.split()[1:]
        ev = []
        if cmd == "/fliptoons_hire":
            if not parts or not parts[0].isdigit():
                send(chat_id, "Usage: /fliptoons_hire &lt;1-5&gt; (market slot)")
                return True
            err = FT.do_market(g, idx, "hire", int(parts[0]) - 1, ev)
        elif cmd == "/fliptoons_dismiss":
            want = " ".join(parts).lower()
            card = next((c for c in _ft_dismissables(g["players"][idx])
                         if FT.card_name(c).lower() == want), None)
            if card is None and want.isdigit():
                card = next((c for c in _ft_dismissables(g["players"][idx])
                             if c["id"] == int(want)), None)
            if card is None:
                send(chat_id, "Usage: /fliptoons_dismiss &lt;card name&gt; "
                              "(or use the dismiss buttons)")
                return True
            err = FT.do_market(g, idx, "dismiss", card["id"], ev)
        elif cmd == "/fliptoons_skip":
            err = FT.do_market(g, idx, "skip", None, ev)
        else:
            pend = g.get("pending")
            if not pend:
                send(chat_id, "No pending choice right now.")
                return True
            want = " ".join(parts).lower()
            opt = next((o for o in pend["options"]
                        if str(o["v"]).lower() == want or o["label"].lower() == want), None)
            if opt is None:
                send(chat_id, "⛔ Unknown choice. Options: " +
                     ", ".join(str(o["v"]) for o in pend["options"]))
                return True
            err = FT.apply_choice(g, idx, str(opt["v"]), ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            fliptoons_render(g, ev)
        return True
    return False


def _ft_card_json(c):
    return {"id": c["id"],
            "name": "?" if c["fd"] else FT.card_name(c),
            "fame": 0 if c["fd"] else FT.base_fame(c),
            "fd": c["fd"], "starter": c["s"] is not None,
            "s": c["s"], "r": c["r"],
            "dismissable": (not c["fd"]) and c["r"] not in FT.UNDISMISSABLE,
            "dismiss_cost": 3 if c["s"] == FT.CATERPILLAR else FT.DISMISS_COST}


def fliptoons_board_json(g, viewer_id=None):
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    actor = fliptoons_actor(g)
    can_act = bool(actor is not None and (
        g["players"][actor]["user_id"] == viewer_id or g["players"][actor].get("npc")))
    players = []
    for i, p in enumerate(g["players"]):
        players.append({
            "user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")),
            "fame": FT.grid_fame(g, p), "budget": p["fame"] + p["fame_bonus"],
            "deck": len(p["deck"]), "discarded": len(p["discarded"]),
            "grid": [[_ft_card_json(c) for c in st] for st in p["grid"]],
            "extra": [{"below": e["below"],
                       "cards": [_ft_card_json(c) for c in e["cards"]]}
                      for e in p["extra"]],
            "is_current": i == actor,
        })
    market = [{"slot": slot, "price": FT.PRICES[slot],
               "card": _ft_card_json(c) if c else None}
              for slot, c in enumerate(g["market"])]
    pend = g.get("pending")
    pending = None
    if pend:
        pending = {"kind": pend["kind"], "player": pend["player"],
                   "prompt": pend["prompt"],
                   "options": [{"v": o["v"], "label": o["label"]} for o in pend["options"]]}
    return {
        "chat_id": g["chat_id"], "phase": g["phase"], "stage": g["stage"],
        "round": g["round"], "first": g["first"],
        "critic_holder": g["critic_holder"],
        "end_triggered": g.get("end_triggered", False),
        "actor": actor, "can_act": can_act, "is_player": me is not None,
        "winner": g.get("winner"), "market": market, "pending": pending,
        "target": FT.FAME_TARGET,
        "players": players,
    }


def fliptoons_api_move(state, chat_id, user_id, body):
    g = fliptoons_get(state, chat_id)
    if not g:
        return [], "no fliptoons game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= 4:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(_ft_player(user_id, iu_name))
        ev.append("🙋 joined Fliptoons.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = FT.start_game(g, ev)
        if err:
            return [], err
    elif action == "rematch":
        return rematch_game(state, "fliptoons", chat_id, user_id)
    else:
        ref = fliptoons_actor(g)
        if ref is None:
            return [], "nothing to do right now"
        idx = _actor_idx(g, user_id, ref)
        if idx is None:
            return [], "not in this game"
        if action == "hire":
            try:
                slot = int(body.get("slot"))
            except (TypeError, ValueError):
                return [], "bad slot"
            err = FT.do_market(g, idx, "hire", slot, ev)
        elif action == "dismiss":
            try:
                iid = int(body.get("iid"))
            except (TypeError, ValueError):
                return [], "bad card"
            err = FT.do_market(g, idx, "dismiss", iid, ev)
        elif action == "skip":
            err = FT.do_market(g, idx, "skip", None, ev)
        elif action == "choose":
            err = FT.apply_choice(g, idx, str(body.get("choice", "")), ev)
        else:
            return [], "unknown action"
        if err:
            return [], err
    fliptoons_render(g, ev)
    return ev, None


# ============================================================ Castle Combo
CASTLECOMBO_RULES = """🏰 <b>Castle Combo rules</b> (2-5 players): a deck-building tableau game. Build a 3×3 grid of cards and score points from shields, sets, positions and stored gold.

• Each player starts with <b>15 gold</b> and <b>2 keys</b>. On your turn take exactly <b>one</b> card from the <b>messenger's</b> display (the Castle 🏰 or Village 🏘️ row it points to) and place it in your 3×3 grid, or spend a key.
• <b>Buy</b> a card face-up for its gold cost, then resolve its ability. <b>Flip</b> it face-down instead: gain <b>+6 gold and +2 keys</b>, but it has no ability, no shields, no purse and scores 0.
• Cards with a pennant 🚩 move the <b>messenger to the opposite row</b> of their own deck (Castle→Village, Village→Castle).
• Spend a key to either <b>move</b> the messenger to the other row or <b>renew</b> the current display (discard it and draw 3 fresh cards).
• Placement: cards must be orthogonally adjacent to one you own and never make a 4th card in a row/column; your first card goes anywhere.
• After everyone has taken <b>9 cards</b> each (or both displays run out), the game ends. Leftover gold is stored on your purses (largest capacity first).
• <b>Scoring:</b> 1 point per key left + each face-up card's printed value (shields in its row/column, position bonuses, sets, purses…).
• Most points wins; ties break on leftover (unstored) gold."""

CC_LOC_EMOJI = {CC.CASTLE: "🏰", CC.VILLAGE: "🏘️"}
CC_LOC_NAME = {CC.CASTLE: "Castle", CC.VILLAGE: "Village"}


def castlecombo_get(state, chat_id):
    g = state.setdefault("castlecombo", {}).get(str(chat_id))
    return CC.normalize(g) if g else None


def _cc_card_label(inst):
    if inst.get("fd"):
        return "?"
    return CC.card_of(inst)["name"]


def castlecombo_actor(g):
    """Index of the player who must act now, or None (game over)."""
    if g.get("pending"):
        return g["pending"]["player"]
    if g["phase"] == "playing":
        return g.get("current")
    return None


def _cc_tableau_lines(p):
    if not p["tableau"]:
        return ["  (empty)"]
    xs = [c["x"] for c in p["tableau"]]
    ys = [c["y"] for c in p["tableau"]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    out = []
    for y in range(y0, y1 + 1):
        cells = []
        for x in range(x0, x1 + 1):
            inst = next((c for c in p["tableau"]
                         if c["x"] == x and c["y"] == y), None)
            if inst is None:
                cells.append("[·]")
            elif inst["fd"]:
                cells.append("[?]")
            else:
                nm = CC.card_of(inst)["name"]
                cells.append(f"[{nm}]")
        out.append("  " + " ".join(cells))
    return out


def _cc_display_line(g, loc):
    row = g["rows"][loc]
    if not g["mm_live"][loc]:
        return "— (out of cards)"
    if not row:
        return "(empty)"
    parts = []
    for inst in row:
        card = CC.card_of(inst)
        mm = "🚩" if card["mm"] else ""
        pur = f"💰{card['purse']}" if card["purse"] else ""
        parts.append(f"{card['name']} {card['cost']}g{mm}{pur}")
    return " · ".join(parts)


CC_ROUND_ARROWS = ["↖️", "⬆️", "↗️", "⬅️", "*️⃣", "➡️", "↙️", "⬇️", "↘️"]


def send_rich(chat_id, rich, kb=None):
    p = {"chat_id": chat_id, "rich_message": rich}
    if kb:
        p["reply_markup"] = {"inline_keyboard": kb}
    return api("sendRichMessage", **p)


def castlecombo_score_md(g):
    res = g.get("results") or []
    if not res:
        return ""
    by_idx = {r["idx"]: r for r in res}
    players = g["players"]
    head = ["Round"] + [html.escape(p["name"]) for p in players]
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join(["---"] * len(head)) + "|"]
    for i, arrow in enumerate(CC_ROUND_ARROWS):
        cells = [arrow]
        for idx in range(len(players)):
            entries = (by_idx.get(idx, {}).get("entries") or [])
            cells.append(str(entries[i]) if i < len(entries) else "")
        lines.append("| " + " | ".join(cells) + " |")
    for label, key in (("Keys", "keys"), ("Total", "score")):
        cells = [label] + [str(by_idx.get(idx, {}).get(key, ""))
                           for idx in range(len(players))]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def castlecombo_rich_message(g, events=None):
    blocks = [{"type": "paragraph", "text": str(e)} for e in (events or [])]
    if g.get("winner") is not None:
        w = g["players"][g["winner"]]
        res = g.get("results") or []
        score = next((r["score"] for r in res if r["idx"] == g["winner"]), "?")
        head = ["🏆 ", {"type": "bold", "text": "Castle Combo game over"},
                " - winner: ", {"type": "bold", "text": w["name"]},
                f" with {score} points!"]
    else:
        head = ["🤝 ", {"type": "bold", "text": "Castle Combo game over"},
                " - it's a draw!"]
    blocks.append({"type": "paragraph", "text": head})
    res = g.get("results") or []
    if res:
        by_idx = {r["idx"]: r for r in res}
        players = g["players"]
        cols = ["Round"] + [p["name"] for p in players]
        cells = [[{"text": c, "is_header": True} for c in cols]]
        for i, arrow in enumerate(CC_ROUND_ARROWS):
            row = [arrow]
            for idx in range(len(players)):
                entries = (by_idx.get(idx, {}).get("entries") or [])
                row.append(str(entries[i]) if i < len(entries) else "")
            cells.append([{"text": c} for c in row])
        for label, key in (("Keys", "keys"), ("Total", "score")):
            row = [label] + [str(by_idx.get(idx, {}).get(key, ""))
                             for idx in range(len(players))]
            cells.append([{"text": c} for c in row])
        blocks.append({"type": "table", "cells": cells, "is_bordered": True,
                       "is_striped": True, "is_compact": True})
    return {"blocks": blocks}


def castlecombo_board_text(g):
    if g["phase"] == "lobby":
        return (f"🏰 <b>Castle Combo lobby</b> - {len(g['players'])}/"
                f"{CC.MAX_PLAYERS} players. Friends: /castlecombo_join, "
                f"anyone: /castlecombo_start")
    if g["phase"] == "game_end":
        table = castlecombo_score_md(g)
        suffix = "\n\n" + table if table else ""
        if g.get("winner") is not None:
            w = g["players"][g["winner"]]
            res = g.get("results") or []
            score = next((r["score"] for r in res if r["idx"] == g["winner"]),
                         "?")
            return (f"🏆 <b>Castle Combo game over</b> - winner: "
                    f"<b>{html.escape(w['name'])}</b> with {score} points!" + suffix)
        return "🤝 <b>Castle Combo game over</b> - it's a draw!" + suffix
    actor = castlecombo_actor(g)
    cur = CC_LOC_NAME[g["messenger"]]
    lines = [f"🏰 <b>Castle Combo</b> · round {g['round']}/9 · "
             f"messenger at {CC_LOC_EMOJI[g['messenger']]} {cur}"]
    for i, p in enumerate(g["players"]):
        mark = " 👈" if i == actor else ""
        loc_txt = (f"{CC_LOC_EMOJI[CC.CASTLE]} Castle: {_cc_display_line(g, CC.CASTLE)}"
                   f" · {CC_LOC_EMOJI[CC.VILLAGE]} Village: "
                   f"{_cc_display_line(g, CC.VILLAGE)}")
        lines.append(f"• <b>{html.escape(p['name'])}</b> · "
                     f"{p['gold']} gold · {p['keys']} keys · "
                     f"{len(p['tableau'])}/9 cards{mark}")
        lines.extend(_cc_tableau_lines(p))
    lines.append("🛒 " + loc_txt)
    if g.get("pending"):
        lines.append(f"❓ {html.escape(g['pending']['prompt'])}")
    return "\n".join(lines)


def castlecombo_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "cc:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="castlecombo")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Castle Combo", "callback_data": "cc:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "cc:npc"}])
        return kb + (wk or [])
    kb = []
    pend = g.get("pending")
    if pend:
        if pend.get("kind") != "place":
            for j in range(0, len(pend["options"]), 2):
                kb.append([{"text": o["label"][:60], "callback_data": f"cc:ch:{o['v']}"}
                           for o in pend["options"][j:j + 2]])
    else:
        row = g["rows"][g["messenger"]]
        p = g["players"][g["current"]]
        for inst in row:
            card = CC.card_of(inst)
            cost = CC.cost_for(g, g["current"], card)
            afford = p["gold"] >= cost
            label = f"{card['name']} ({cost}g)"
            kb.append([
                {"text": f"🛒 {label}" if afford else f"🚫 {label}",
                 "callback_data": f"cc:buy:{inst['id']}"},
                {"text": f"🔄 Flip {card['name']}",
                 "callback_data": f"cc:flip:{inst['id']}"},
            ])
        if p["keys"] > 0:
            kb.append([
                {"text": "🔑 Move messenger",
                 "callback_data": "cc:move"},
                {"text": "🔑 Renew display",
                 "callback_data": "cc:renew"},
            ])
    if wk:
        kb.extend(wk)
    return kb or None


def castlecombo_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(CC.name_of(g, user_id))}</a>'


def castlecombo_render(g, events=None):
    chat_id = g["chat_id"]
    if events is None:
        events = []
    lines = [html.escape(e) for e in events]
    if g["phase"] == "playing":
        idx = castlecombo_actor(g)
        if idx is not None:
            p = g["players"][idx]
            if g.get("pending"):
                lines.append(f"👉 {castlecombo_mention(g, p['user_id'])} - "
                             f"{html.escape(g['pending']['prompt'])}")
            else:
                ping = ("👉 🤖 NPC's turn - anyone can play for it!" if p.get("npc")
                        else f"👉 {castlecombo_mention(g, p['user_id'])} - your turn")
                lines.append(ping)
    text = "\n".join(lines + [castlecombo_board_text(g)]) if lines else castlecombo_board_text(g)
    kb = castlecombo_keyboard(g)
    if g["phase"] == "game_end":
        r = send_rich(chat_id, castlecombo_rich_message(g, events), kb)
        if not r.get("ok"):
            r = send_board(g, "castlecombo", text, kb)
    else:
        r = send_board(g, "castlecombo", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def handle_castlecombo(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = castlecombo_get(state, chat_id)
    if cmd == "/castlecombo_rules":
        send(chat_id, CASTLECOMBO_RULES)
        return True
    if cmd == "/castlecombo":
        if not g:
            name = msg.get("from", {}).get("first_name") or "Player"
            g = CC.new_game(chat_id, uid, name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("castlecombo", {})[str(chat_id)] = g
            castlecombo_render(g, [f"🏰 Castle Combo game created by {name}!"])
        else:
            castlecombo_render(g)
        return True
    if not g:
        send(chat_id, "No Castle Combo game here yet - send /castlecombo to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/castlecombo_join_npc":
        err = add_npc("castlecombo", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            castlecombo_render(g)
        return True
    if cmd == "/castlecombo_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= CC.MAX_PLAYERS:
            send(chat_id, NPC_FULL["castlecombo"])
        else:
            g["players"].append(CC.new_player(
                uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Castle Combo "
                          f"({len(g['players'])} players).")
            castlecombo_render(g)
        return True
    if cmd == "/castlecombo_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            ev = []
            err = CC.start_game(g, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                castlecombo_render(g, ev)
        return True
    if cmd == "/castlecombo_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["castlecombo"][str(chat_id)]
            send(chat_id, "🗑 Castle Combo game cancelled.")
        return True
    if cmd in ("/castlecombo_buy", "/castlecombo_flip", "/castlecombo_move",
               "/castlecombo_renew", "/castlecombo_choose"):
        ref = castlecombo_actor(g)
        if ref is None:
            send(chat_id, "⛔ Nothing to do right now.")
            return True
        idx = _actor_idx(g, uid, ref)
        if idx is None:
            send(chat_id, "⛔ You're not in this Castle Combo game - /castlecombo_join in lobby.")
            return True
        parts = text.split()[1:]
        ev = []
        if cmd == "/castlecombo_move":
            err = CC.do_key(g, idx, "move", ev)
        elif cmd == "/castlecombo_renew":
            err = CC.do_key(g, idx, "renew", ev)
        elif cmd == "/castlecombo_buy":
            if not parts or not parts[0].isdigit():
                send(chat_id, "Usage: /castlecombo_buy &lt;card id&gt;")
                return True
            err = CC.do_take(g, idx, int(parts[0]), False, ev)
        elif cmd == "/castlecombo_flip":
            if not parts or not parts[0].isdigit():
                send(chat_id, "Usage: /castlecombo_flip &lt;card id&gt;")
                return True
            err = CC.do_take(g, idx, int(parts[0]), True, ev)
        else:
            pend = g.get("pending")
            if not pend:
                send(chat_id, "No pending choice right now.")
                return True
            want = " ".join(parts).lower()
            opt = next((o for o in pend["options"]
                        if str(o["v"]).lower() == want
                        or o["label"].lower() == want), None)
            if opt is None:
                send(chat_id, "⛔ Unknown choice. Options: " +
                     ", ".join(str(o["v"]) for o in pend["options"]))
                return True
            err = CC.apply_choice(g, idx, str(opt["v"]), ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            castlecombo_render(g, ev)
        return True
    return False


def _cc_card_json(g, inst, hidden=False):
    card = CC.card_of(inst)
    if hidden:
        return {"iid": inst["id"], "cid": 0, "name": "?", "fd": True,
                "x": inst["x"], "y": inst["y"], "gold": 0, "purse": 0,
                "loc": card["loc"], "cost": card["cost"], "txt": ""}
    return {"iid": inst["id"], "cid": card["id"], "name": card["name"],
            "fd": inst["fd"], "x": inst["x"], "y": inst["y"],
            "gold": inst["gold"], "purse": card["purse"], "loc": card["loc"],
            "cost": card["cost"], "sh": card["sh"], "disc": card["disc"],
            "mm": card["mm"], "txt": card["txt"]}


def castlecombo_board_json(g, viewer_id=None):
    CC.normalize(g)
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    actor = castlecombo_actor(g)
    can_act = bool(actor is not None and (
        g["players"][actor]["user_id"] == viewer_id
        or g["players"][actor].get("npc")))
    players = []
    for i, p in enumerate(g["players"]):
        players.append({
            "user_id": p["user_id"], "name": p["name"],
            "npc": bool(p.get("npc")), "gold": p["gold"], "keys": p["keys"],
            "cards": len(p["tableau"]),
            "tableau": [_cc_card_json(g, c, c["fd"]) for c in p["tableau"]],
            "is_current": i == actor,
        })
    rows = {}
    for loc in (CC.CASTLE, CC.VILLAGE):
        rows[str(loc)] = {
            "live": g["mm_live"][loc],
            "deck": len(g["decks"][loc]),
            "deck_total": len(CC.CASTLE_IDS if loc == CC.CASTLE else CC.VILLAGE_IDS),
            "cards": [{"iid": c["id"], "cid": CC.card_of(c)["id"],
                       "name": CC.card_of(c)["name"],
                       "cost": CC.cost_for(g, g["current"], CC.card_of(c))
                       if g["phase"] == "playing" else CC.card_of(c)["cost"],
                       "mm": CC.card_of(c)["mm"],
                       "purse": CC.card_of(c)["purse"],
                       "txt": CC.card_of(c)["txt"]}
                      for c in g["rows"][loc]]
            if g["mm_live"][loc] else [],
        }
    pend = g.get("pending")
    pending = None
    if pend:
        pending = {"kind": pend["kind"], "player": pend["player"],
                   "prompt": pend["prompt"],
                   "options": [{"v": o["v"], "label": o["label"]}
                               for o in pend["options"]]}
    results = None
    if g.get("results"):
        results = [{"idx": r["idx"], "name": r["name"], "score": r["score"],
                    "leftover": r["leftover"], "keys": r.get("keys", 0),
                    "entries": r.get("entries")} for r in g["results"]]
    return {
        "chat_id": g["chat_id"], "phase": g["phase"],
        "round": g["round"], "messenger": g["messenger"],
        "mm_live": {str(k): v for k, v in g["mm_live"].items()},
        "actor": actor, "can_act": can_act, "is_player": me is not None,
        "winner": g.get("winner"), "pending": pending,
        "rows": rows, "players": players, "results": results,
        "max_players": CC.MAX_PLAYERS,
    }


def castlecombo_api_move(state, chat_id, user_id, body):
    g = castlecombo_get(state, chat_id)
    if not g:
        return [], "no castlecombo game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= CC.MAX_PLAYERS:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(CC.new_player(user_id, iu_name))
        ev.append("🙋 joined Castle Combo.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = CC.start_game(g, ev)
        if err:
            return [], err
    elif action == "rematch":
        return rematch_game(state, "castlecombo", chat_id, user_id)
    else:
        ref = castlecombo_actor(g)
        if ref is None:
            return [], "nothing to do right now"
        idx = _actor_idx(g, user_id, ref)
        if idx is None:
            return [], "not in this game"
        if action == "buy":
            try:
                iid = int(body.get("iid"))
            except (TypeError, ValueError):
                return [], "bad card"
            err = CC.do_take(g, idx, iid, False, ev)
        elif action == "flip":
            try:
                iid = int(body.get("iid"))
            except (TypeError, ValueError):
                return [], "bad card"
            err = CC.do_take(g, idx, iid, True, ev)
        elif action == "move":
            err = CC.do_key(g, idx, "move", ev)
        elif action == "renew":
            err = CC.do_key(g, idx, "renew", ev)
        elif action == "choose":
            err = CC.apply_choice(g, idx, str(body.get("choice", "")), ev)
        else:
            return [], "unknown action"
        if err:
            return [], err
    castlecombo_render(g, ev)
    return ev, None


# ============================================================ Abandon All Artichokes
ARTICHOKES_RULES = """🥬 <b>Abandon All Artichokes rules</b> (2-4 players): a deck-wrecking game. First to draw a hand with <b>no Artichokes</b> at the end of their turn wins.
• Setup: everyone starts with a 10-Artichoke personal deck and draws 5. The shared Garden Stack has 6 of each of the 10 vegetables; 5 are face-up in the Garden Row.
• Your turn: <b>1</b> refill the row to 5 (4+ matching cards are reshuffled); <b>2</b> harvest 1 row card into your hand; <b>3</b> play any number of vegetables (the turn auto-skips when none remain, after any pending choice); <b>4</b> discard your hand; <b>5</b> draw 5. If that new hand has no Artichokes, shout it and win!
• You can never play an Artichoke unless a card says so. Composted cards are out for good.
• <b>Beet</b> swap a random card with an opponent (two Artichokes = both composted). <b>Broccoli</b> compost 1 if you have 3+ Artichokes. <b>Carrot</b> compost 2 (your only play that turn). <b>Corn</b> discard an Artichoke, put a row card on your deck. <b>Eggplant</b> compost 1, everyone passes 2 cards left. <b>Leek</b> reveal an opponent's top deck card and take it or discard it. <b>Onion</b> compost 1, send the Onion to someone's discard. <b>Pepper</b> move a card from your discard to your deck. <b>Peas</b> send one of the top 2 stack cards to your discard and one to an opponent. <b>Potato</b> reveal your top card: compost it if it's an Artichoke.
• <i>Bot adaptation:</i> in private chats the active player's hand is shown on the board so they can act from Telegram; in groups and in the Mini App only your own hand is shown (counts only for others). The Mini App shows each viewer only their own hand."""


def artichokes_get(state, chat_id):
    return state.setdefault("artichokes", {}).get(str(chat_id))


def artichokes_actor(g):
    if g["phase"] not in ("harvest", "play"):
        return None
    pend = g.get("pending")
    if pend:
        if pend["kind"] == "eggplant":
            pos = pend["pos"]
            return pend["order"][pos] if pos < len(pend["order"]) else g["current_index"]
        return pend["by"]
    return g["current_index"]


def artichokes_actor_idx(g, uid):
    ref = artichokes_actor(g)
    if ref is None:
        return None
    if g.get("pending") and g["pending"]["kind"] == "eggplant":
        return ref if (g["players"][ref]["user_id"] == uid or g["players"][ref].get("npc")) else None
    return _actor_idx(g, uid, ref)


def _at_card_json(c):
    return {"id": c["id"], "v": c["v"], "name": AT.card_name(c),
            "label": AT.card_label(c), "icon": AT.ICONS.get(c["v"], "🥬"),
            "desc": AT.card_desc(c)}


def _at_hand_text(p):
    return ", ".join(f"{i + 1}:{AT.card_label(c)}" for i, c in enumerate(p["hand"])) or "empty"


def artichokes_board_text(g):
    if g["phase"] == "lobby":
        return (f"🥬 <b>Abandon All Artichokes lobby</b> - {len(g['players'])}/{AT.MAX_PLAYERS} players. "
                f"Friends: /artichokes_join, anyone: /artichokes_start")
    if g["phase"] == "game_end":
        winner = next((p for p in g["players"] if p["user_id"] == g.get("winner_id")), None)
        return (f"🏆 <b>Abandon All Artichokes game over</b> - winner: "
                f"<b>{html.escape(winner['name']) if winner else '?'}</b>! "
                f"{len(g['compost'])} cards composted in {g['round']} turns.")
    actor = artichokes_actor(g)
    lines = [f"🥬 <b>Abandon All Artichokes</b> · turn {g['round']} · "
             f"garden stack {len(g['garden_stack'])} · compost {len(g['compost'])}"]
    row = " · ".join(f"{i + 1}:{AT.card_label(c)}" for i, c in enumerate(g["garden_row"])) or "empty"
    lines.append(f"🌱 Garden row: {row}")
    for i, p in enumerate(g["players"]):
        mark = " 👈" if i == actor else ""
        mine = ""
        if i == actor and p["hand"] and int(g.get("chat_id", 0)) > 0:
            mine = f" · hand: {_at_hand_text(p)}"
        lines.append(f"• <b>{html.escape(p['name'])}</b> - 🥬 {AT.artichokes(p)} · "
                     f"hand {len(p['hand'])} · deck {len(p['deck'])} · discard {len(p['discard'])}{mine}{mark}")
    pend = g.get("pending")
    if pend:
        lines.append(f"❓ {html.escape(pend['prompt'])}")
        if pend.get("kind") == "eggplant":
            lines.append("   Pass privately via the Mini App or /artichokes_pass &lt;card ids&gt;.")
        elif pend.get("options"):
            lines.append("   " + " · ".join(str(o["v"]) + ":" + html.escape(o["label"])
                                            for o in pend["options"][:12]))
            lines.append("   /artichokes_choose &lt;value&gt;")
    elif g["phase"] == "harvest":
        if g["garden_row"]:
            lines.append("🌾 Harvest: /artichokes_harvest &lt;1-5&gt; (or tap a row card).")
        else:
            lines.append("🌾 Garden row empty - /artichokes_skip.")
    else:
        play = sorted(set(AT.playable(g, actor)))
        lines.append("▶️ Your hand: " + ", ".join(
            f"{c['id']}:{AT.card_label(c)}" for c in g["players"][actor]["hand"]) if g["players"][actor]["hand"] else "▶️ Empty hand.")
        seen = []
        for c in g["players"][actor]["hand"]:
            if c["v"] not in seen and AT.card_desc(c):
                seen.append(c["v"])
        if seen:
            lines.append("📖 " + " · ".join(
                f"<b>{html.escape(AT.card_name({'v': v}))}</b>: {html.escape(AT.card_desc({'v': v}))}"
                for v in seen))
        lines.append(f"Play: /artichokes_play &lt;card id or name&gt; (playable: {', '.join(map(str, play)) or 'none'}) · /artichokes_end (auto-skips when no vegetables remain)")
    return "\n".join(lines)


def artichokes_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "at:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="artichokes")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Artichokes", "callback_data": "at:join"}]]
        if not any(p.get("npc") for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "at:npc"}])
        kb.append([{"text": "▶️ Start game", "callback_data": "at:start"}])
        return kb + (wk or [])
    kb = []
    pend = g.get("pending")
    if pend:
        if pend.get("kind") != "eggplant":
            opts = pend["options"]
            for j in range(0, len(opts), 2):
                kb.append([{"text": o["label"][:60], "callback_data": f"at:ch:{o['v']}"}
                           for o in opts[j:j + 2]])
    elif g["phase"] == "harvest":
        row = []
        for i, c in enumerate(g["garden_row"]):
            row.append({"text": f"{i + 1}:{AT.card_label(c)}", "callback_data": f"at:h:{i}"})
            if len(row) == 2:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        if not g["garden_row"]:
            kb.append([{"text": "⏭ Nothing to harvest", "callback_data": "at:skip"}])
    else:
        if ct == "private":
            actor = artichokes_actor(g)
            playable = set(AT.playable(g, actor))
            row = []
            for c in g["players"][actor]["hand"]:
                if c["id"] in playable:
                    row.append({"text": AT.card_label(c), "callback_data": f"at:p:{c['id']}"})
                    if len(row) == 2:
                        kb.append(row)
                        row = []
            if row:
                kb.append(row)
        kb.append([{"text": "⏭ End turn", "callback_data": "at:end"}])
    if wk:
        kb.extend(wk)
    return kb or None


def artichokes_render(g, events=None):
    chat_id = g["chat_id"]
    lines = [html.escape(e) for e in (events or [])]
    idx = artichokes_actor(g)
    if idx is not None:
        p = g["players"][idx]
        pend = g.get("pending")
        ping = ("👉 🤖 NPC's turn - anyone can play for it!" if p.get("npc")
                else f"👉 {artichokes_mention(g, p['user_id'])} - "
                     + (html.escape(pend["prompt"]) if pend else "your turn"))
        lines.append(ping)
    text = "\n".join(lines + [artichokes_board_text(g)])
    kb = artichokes_keyboard(g)
    r = send_board(g, "artichokes", text, kb)
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def artichokes_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(AT.name_of(g, user_id))}</a>'


def handle_artichokes(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = artichokes_get(state, chat_id)
    if cmd == "/artichokes_rules":
        send(chat_id, ARTICHOKES_RULES)
        return True
    if cmd == "/artichokes":
        if not g:
            _name = msg.get("from", {}).get("first_name") or "Player"
            g = AT.new_game(chat_id, uid, _name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("artichokes", {})[str(chat_id)] = g
            artichokes_render(g, [f"🥬 Abandon All Artichokes game created by {html.escape(_name)}!"])
        else:
            artichokes_render(g)
        return True
    if not g:
        send(chat_id, "No Abandon All Artichokes game here yet - send /artichokes to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/artichokes_join_npc":
        err = add_npc("artichokes", g)
        send(chat_id, err or "🤖 NPC joined - anyone can play for it!")
        if not err:
            artichokes_render(g)
        return True
    if cmd == "/artichokes_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= AT.MAX_PLAYERS:
            send(chat_id, f"⛔ Abandon All Artichokes is 2-{AT.MAX_PLAYERS} players (full).")
        else:
            g["players"].append(AT.new_player(uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Abandon All Artichokes ({len(g['players'])} players).")
            artichokes_render(g)
        return True
    if cmd == "/artichokes_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < AT.MIN_PLAYERS:
            send(chat_id, f"⛔ Need at least {AT.MIN_PLAYERS} players.")
        else:
            ev = []
            err = AT.start_game(g, ev)
            send(chat_id, f"⛔ {err}" if err else "🥬 Game started!")
            if not err:
                artichokes_render(g, ev)
        return True
    if cmd == "/artichokes_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["artichokes"][str(chat_id)]
            send(chat_id, "🗑 Abandon All Artichokes game cancelled.")
        return True
    if cmd == "/artichokes_rematch":
        ev, err = rematch_game(state, "artichokes", chat_id, uid)
        send(chat_id, f"⛔ {err}" if err else "🔄 Rematch!")
        return True
    actions = ("/artichokes_harvest", "/artichokes_skip", "/artichokes_play",
               "/artichokes_end", "/artichokes_choose", "/artichokes_pass")
    if cmd not in actions:
        return False
    idx = artichokes_actor_idx(g, uid)
    if idx is None:
        send(chat_id, "⛔ You're not in this game (or it isn't your turn).")
        return True
    parts = text.split()[1:]
    ev = []
    err = None
    if cmd == "/artichokes_harvest":
        if not parts or not parts[0].isdigit():
            err = "Usage: /artichokes_harvest &lt;1-5&gt;"
        else:
            err = AT.harvest(g, idx, int(parts[0]) - 1, ev)
    elif cmd == "/artichokes_skip":
        err = AT.skip_harvest(g, idx, ev)
    elif cmd == "/artichokes_play":
        want = " ".join(parts).lower()
        target = None
        for c in g["players"][idx]["hand"]:
            if str(c["id"]) == want or AT.card_name(c).lower() == want or AT.card_label(c).lower() == want:
                target = c["id"]
                break
        err = "Usage: /artichokes_play &lt;card id or name&gt;" if target is None else AT.do_play(g, idx, target, ev)
    elif cmd == "/artichokes_end":
        err = AT.end_turn(g, idx, ev)
    elif cmd == "/artichokes_pass":
        try:
            ids = [int(x) for x in parts]
        except ValueError:
            ids = []
        err = "Usage: /artichokes_pass &lt;card id card id&gt;" if not ids else AT.apply_choice(g, idx, ids, ev)
    else:
        pend = g.get("pending")
        if not pend:
            err = "No pending choice right now."
        else:
            want = " ".join(parts)
            opt = next((o for o in pend["options"] if str(o["v"]).lower() == want.lower()
                        or o["label"].lower() == want.lower()), None)
            if opt is None:
                err = "Unknown choice. Options: " + ", ".join(str(o["v"]) for o in pend["options"])
            else:
                err = AT.apply_choice(g, idx, opt["v"], ev)
    if err:
        send(chat_id, f"⛔ {err}")
    else:
        artichokes_render(g, ev)
    return True


def artichokes_board_json(g, viewer_id=None):
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    actor = artichokes_actor(g)
    can_act = bool(actor is not None and me is not None and
                   (g["players"][actor]["user_id"] == viewer_id or g["players"][actor].get("npc")))
    players = []
    for i, p in enumerate(g["players"]):
        entry = {"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")),
                 "artichokes": AT.artichokes(p), "hand_count": len(p["hand"]),
                 "deck": len(p["deck"]), "discard": len(p["discard"]),
                 "is_current": i == actor}
        if p["user_id"] == viewer_id:
            entry["my_hand"] = [_at_card_json(c) for c in p["hand"]]
        players.append(entry)
    pend = g.get("pending")
    pending = None
    if pend:
        viewer_idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
        opts = [{"v": o["v"], "label": o["label"]} for o in pend["options"]]
        if pend.get("kind") == "eggplant" and viewer_idx != pend.get("by"):
            opts = []
        pending = {"kind": pend["kind"], "by": pend.get("by"),
                   "prompt": pend["prompt"], "options": opts,
                   "chosen": pend.get("answers", {}).get(viewer_idx, []) if pend["kind"] == "eggplant" else []}
    return {"chat_id": g["chat_id"], "phase": g["phase"], "round": g["round"],
            "descriptions": AT.DESCRIPTIONS,
            "garden_row": [{"pos": i, **_at_card_json(c)} for i, c in enumerate(g["garden_row"])],
            "garden_stack": len(g["garden_stack"]), "compost": len(g["compost"]),
            "actor": actor, "can_act": can_act, "is_player": me is not None,
            "winner_id": g.get("winner_id"), "pending": pending,
            "playable": AT.playable(g, actor) if can_act else [], "players": players}


def artichokes_api_move(state, chat_id, user_id, body):
    g = artichokes_get(state, chat_id)
    if not g:
        return [], "no artichokes game in that chat"
    action = body.get("action")
    ev = []
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= AT.MAX_PLAYERS:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(AT.new_player(user_id, iu_name))
        ev.append("🙋 joined Abandon All Artichokes.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = AT.start_game(g, ev)
        if err:
            return [], err
    elif action == "rematch":
        return rematch_game(state, "artichokes", chat_id, user_id)
    else:
        idx = artichokes_actor_idx(g, user_id)
        if idx is None:
            return [], "not in this game"
        if action == "harvest":
            try:
                pos = int(body.get("pos", body.get("row", -1)))
            except (TypeError, ValueError):
                return [], "bad row position"
            err = AT.harvest(g, idx, pos, ev)
        elif action == "skip":
            err = AT.skip_harvest(g, idx, ev)
        elif action == "play":
            try:
                iid = int(body.get("iid", body.get("card", -1)))
            except (TypeError, ValueError):
                return [], "bad card"
            err = AT.do_play(g, idx, iid, ev)
        elif action == "end":
            err = AT.end_turn(g, idx, ev)
        elif action == "choose":
            err = AT.apply_choice(g, idx, body.get("choice"), ev)
        elif action == "pass":
            ids = body.get("ids", body.get("cards", []))
            if not isinstance(ids, list):
                return [], "bad cards"
            try:
                ids = [int(x) for x in ids]
            except (TypeError, ValueError):
                return [], "bad cards"
            err = AT.apply_choice(g, idx, ids, ev)
        else:
            return [], "unknown action"
        if err:
            return [], err
    artichokes_render(g, ev)
    return ev, None


AZUL_RULES = """🔷 <b>Azul rules</b> (2-4 players, by Michael Kiesling): draft colourful tiles to decorate your wall. The game ends after the round in which someone completes a wall row; most points wins.
• <b>Factory offer:</b> 5 factories with 2 players, 7 with 3, 9 with 4. Take ALL tiles of one colour from a factory (the rest slide to the centre) or from the centre. Taking from the centre also takes the ⭐ if it's there; a centre holding only ⭐ is not a pick, and the round's first player keeps it if nobody takes centre tiles.
• Put the tiles on one pattern line (row 1 holds 1 tile … row 5 holds 5). A line takes one colour only, and never a colour already in that row of your wall. Extra tiles fall onto your floor line; when its 7 spaces are full, further tiles are discarded. The ⭐ also goes on your floor and makes you first player next round.
• <b>Wall-tiling</b> happens automatically at the end of the round: every full line moves its rightmost tile to the matching wall space. Score the connected group in its row plus the connected group in its column (1 point if isolated). Other line tiles and all floor tiles are discarded.
• <b>Floor penalties:</b> the 7 spaces cost -1,-1,-2,-2,-2,-3,-3 (⭐ counts as a tile). Your score can't drop below 0.
• <b>Final scoring:</b> +2 per complete row, +7 per complete column, +10 per colour with all five tiles on the wall. Ties break on completed rows, otherwise the win is shared.
• Commands: /azul_take &lt;factory N|center&gt; &lt;colour&gt; then /azul_place &lt;1-5|floor&gt;, or use the buttons/Mini App."""


def azul_get(state, chat_id):
    return state.setdefault("azul", {}).get(str(chat_id))


def azul_actor_idx(g, uid):
    if g["phase"] != "draft":
        return None
    return _actor_idx(g, uid, g["current"])


def azul_board_text(g):
    if g["phase"] == "lobby":
        return (f"🔷 <b>Azul lobby</b> - {len(g['players'])}/{AZ.MAX_PLAYERS} players. "
                "Friends: /azul_join, anyone: /azul_start")
    if g["phase"] == "game_end":
        winners = " & ".join(html.escape(g["players"][i]["name"]) for i in g["winners"])
        return (f"🏆 <b>Azul game over</b> - winner: <b>{winners}</b>! "
                f"Scores after {g['round']} rounds.")
    lines = [AZ.board_lines(g)]
    lines.append("🎨 /azul_take &lt;factory N|center&gt; &lt;colour&gt; "
                 "· /azul_place &lt;1-5|floor&gt; (or tap the buttons).")
    return "\n".join(lines)


def _az_choice_text(opt):
    icon = AZ.SYMBOLS.get(opt["color"], "⭐")
    label = "C" if opt["source"] == "center" else "F" + str(opt["index"] + 1)
    return f"{label} {icon}×{opt['count']}"


def azul_keyboard(g):
    if g["phase"] == "game_end":
        return [[{"text": "🔄 Rematch!", "callback_data": "az:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="azul")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Azul", "callback_data": "az:join"}]]
        if not any(_is_npc(p) for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "az:npc"}])
        kb.append([{"text": "▶️ Start game", "callback_data": "az:start"}])
        return kb + (wk or [])
    kb = []
    pend = g.get("pending")
    if pend:
        color = pend["color"]
        rows = AZ.rows_for(g, pend["by"], color) if color else []
        for r in rows:
            kb.append([{"text": f"📏 Line {r + 1} ({r + 1} slot{'s' if r else ''})",
                        "callback_data": f"az:r:{r}"}])
        extra = ""
        if pend["marker"]:
            extra = " + ⭐"
        n = len(pend["tiles"]) + (1 if pend["marker"] else 0)
        kb.append([{"text": f"🧹 Floor ({n} tile{'s' if n != 1 else ''}{extra})",
                    "callback_data": "az:r:-1"}])
    else:
        opts = AZ.take_options(g)
        row = []
        for opt in opts:
            row.append({"text": _az_choice_text(opt),
                        "callback_data": f"az:t:{'f' if opt['source'] == 'factory' else 'c'}:"
                                         f"{opt['index']}:{opt['color']}"})
            if len(row) == 3:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
    if wk:
        kb.extend(wk)
    return kb or None


def azul_render(g, events=None):
    chat_id = g["chat_id"]
    lines = [html.escape(e) for e in (events or [])]
    if g["phase"] == "draft":
        p = g["players"][g["current"]]
        pend = g.get("pending")
        if _is_npc(p):
            ping = "👉 🤖 NPC's turn - anyone can play for it!"
        else:
            ping = f"👉 {azul_mention(g, p['user_id'])} - " + (
                "choose a line for your tiles." if pend else "pick a colour.")
        lines.append(ping)
    text = "\n".join(lines + [azul_board_text(g)])
    r = send_board(g, "azul", text, azul_keyboard(g))
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=chat_id, message_id=old)


def azul_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(AZ.name_of(g, user_id))}</a>'


def handle_azul(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = azul_get(state, chat_id)
    if cmd == "/azul_rules":
        send(chat_id, AZUL_RULES)
        return True
    if cmd == "/azul":
        if not g:
            _name = msg.get("from", {}).get("first_name") or "Player"
            g = AZ.new_game(chat_id, uid, _name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("azul", {})[str(chat_id)] = g
            azul_render(g, [f"🔷 Azul game created by {html.escape(_name)}!"])
        else:
            azul_render(g)
        return True
    if not g:
        send(chat_id, "No Azul game here yet - send /azul to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/azul_join_npc":
        err = add_npc("azul", g)
        send(chat_id, err or "🤖 NPC joined - anyone can play for it!")
        if not err:
            azul_render(g)
        return True
    if cmd == "/azul_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= AZ.MAX_PLAYERS:
            send(chat_id, f"⛔ Azul is {AZ.MIN_PLAYERS}-{AZ.MAX_PLAYERS} players (full).")
        else:
            g["players"].append(AZ.new_player(uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Azul ({len(g['players'])} players).")
            azul_render(g)
        return True
    if cmd == "/azul_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < AZ.MIN_PLAYERS:
            send(chat_id, f"⛔ Need at least {AZ.MIN_PLAYERS} players.")
        else:
            ev = []
            err = AZ.start_game(g, ev)
            send(chat_id, f"⛔ {err}" if err else "🔷 Azul started!")
            if not err:
                azul_render(g, ev)
        return True
    if cmd == "/azul_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["azul"][str(chat_id)]
            send(chat_id, "🗑 Azul game cancelled.")
        return True
    if cmd == "/azul_rematch":
        ev, err = rematch_game(state, "azul", chat_id, uid)
        send(chat_id, f"⛔ {err}" if err else "🔄 Rematch!")
        return True
    if cmd not in ("/azul_take", "/azul_pick", "/azul_place"):
        return False
    idx = azul_actor_idx(g, uid)
    if idx is None:
        send(chat_id, "⛔ You're not in this game (or it isn't your turn).")
        return True
    parts = text.split()[1:]
    ev = []
    take_usage = ("Usage: /azul_take &lt;factory 1-" + str(len(g["factories"])) +
                  "|center&gt; &lt;colour&gt;")
    if cmd in ("/azul_take", "/azul_pick"):
        if not parts:
            err = take_usage
        else:
            src, color = parts[0].lower(), (parts[1].lower() if len(parts) > 1 else "")
            if src in ("center", "c", "middle", "m"):
                err = AZ.take_tiles(g, idx, "center", 0, color, ev)
            elif src.isdigit():
                err = AZ.take_tiles(g, idx, "factory", int(src) - 1, color, ev)
            else:
                err = take_usage
    else:
        raw = parts[0].lower() if parts else ""
        if raw in ("floor", "f", "-1"):
            err = AZ.place_tiles(g, idx, -1, ev)
        elif raw.isdigit():
            err = AZ.place_tiles(g, idx, int(raw) - 1, ev)
        else:
            err = "Usage: /azul_place &lt;1-5|floor&gt;"
    if err:
        send(chat_id, f"⛔ {err}")
    else:
        azul_render(g, ev)
    return True


def azul_board_json(g, viewer_id=None):
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    actor = g["current"] if g["phase"] == "draft" else None
    can_act = bool(actor is not None and me is not None and
                   (g["players"][actor]["user_id"] == viewer_id or _is_npc(g["players"][actor])))
    players = []
    for i, p in enumerate(g["players"]):
        players.append({
            "user_id": p["user_id"], "name": p["name"], "npc": _is_npc(p),
            "score": p["score"], "wall": p["wall"], "pattern": p["pattern"],
            "floor": p["floor"], "last_round": p["last_round"], "winner": p["winner"],
            "rows": AZ.complete_rows(p), "cols": AZ.complete_columns(p),
            "sets": AZ.complete_colors(p), "is_current": i == actor,
        })
    board = {
        "chat_id": g["chat_id"], "phase": g["phase"], "round": g["round"],
        "current": g["current"], "first_player": g["first_player"],
        "bag": len(g["bag"]), "lid": len(g["lid"]),
        "factories": [{"index": i, "tiles": f} for i, f in enumerate(g["factories"]) if f],
        "center": {"tiles": g["center"], "marker": g["marker_center"]},
        "players": players, "actor": actor, "can_act": can_act,
        "is_player": me is not None, "winner_id": g.get("winner_id"),
        "winners": g.get("winners", []), "symbols": AZ.SYMBOLS,
        "colors": list(AZ.COLORS), "options": [], "pending": None,
    }
    if can_act:
        board["options"] = AZ.take_options(g)
    pend = g.get("pending")
    if pend and (can_act or (me and me["user_id"] == g["players"][pend["by"]]["user_id"])):
        color = pend["color"]
        board["pending"] = {
            "color": color, "tiles": pend["tiles"], "marker": pend["marker"],
            "rows": AZ.rows_for(g, pend["by"], color) if color else [],
        }
    return board


def azul_api_move(state, chat_id, user_id, body):
    g = azul_get(state, chat_id)
    if not g:
        return [], "no azul game in that chat"
    action = body.get("action")
    ev = []
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= AZ.MAX_PLAYERS:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(AZ.new_player(user_id, iu_name))
        ev.append("🙋 joined Azul.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = AZ.start_game(g, ev)
        if err:
            return [], err
    elif action == "rematch":
        return rematch_game(state, "azul", chat_id, user_id)
    else:
        idx = azul_actor_idx(g, user_id)
        if idx is None:
            return [], "not in this game"
        if action == "take":
            src = str(body.get("source", "")).lower()
            color = str(body.get("color", "")).lower()
            if src in ("center", "c", "middle", "m"):
                source = "center"
            elif src in ("factory", "f"):
                source = "factory"
            else:
                return [], "bad source"
            try:
                index = int(body.get("index", body.get("factory", 0)))
            except (TypeError, ValueError):
                return [], "bad factory"
            err = AZ.take_tiles(g, idx, source, index, color, ev)
        elif action == "place":
            raw = str(body.get("row", "floor")).lower()
            if raw in ("floor", "f", "-1"):
                row = -1
            else:
                try:
                    row = int(raw)
                except ValueError:
                    return [], "bad row"
            err = AZ.place_tiles(g, idx, row, ev)
        elif action == "move":
            move = body.get("move") or body
            err = AZ.do_move(g, idx, move, ev)
        else:
            return [], "unknown action"
        if err:
            return [], err
    azul_render(g, ev)
    return ev, None


ALTAY_RULES = """🏜️ <b>Altay: Dawn of Civilization</b> (2 players, simplified): win the most VP when someone places their last settlement.
• Each turn: play action cards, use resources to acquire market cards, build settlements, attack, and invest in an achievement in any order.
• Played cards produce resources or give swords/builds. Unspent resources are discarded at turn end. You can acquire each market card only once per turn.
• Build costs 2 food and needs a Village/Architect/City build token. Build in a territory with your settlements (max 4 there) or in a free territory adjacent to your settlements.
• Attack from an adjacent territory you control. Defeat a Conquest Marker by having more settlements+swords than its number, or capture an enemy settlement if your strength beats their settlements+shields. Played sword cards are redrawn after an attack.
• Develop: invest one resource per action in one achievement at a time. Completing it scores its VP. Secret/deluxe variants are not used.
• Final score: achievements + VP action cards + 1 per settlement + VP markers held + 1 per captured settlement + 1 per 3 Conquest Markers. Ties break by achievements, cards, then settlements.
• Commands: /altay_play &lt;card number&gt;, /altay_buy &lt;card&gt;, /altay_build &lt;territory&gt;, /altay_attack &lt;territory&gt;, /altay_develop &lt;id&gt;, /altay_end (or use buttons/Mini App)."""

TOYBATTLE_RULES = """🎯 <b>Toy Battle rules</b> (2 players, Castle Field): win by placing a troop on the enemy HQ, or by being first to 7 medals.
• On your turn choose ONE action: <b>draw 2 troops</b> (rack holds at most 8) or <b>place 1 troop</b>.
• A troop must be placed on a base connected to your HQ by a continuous line of bases topped by YOUR troops. Empty bases, enemy bases and the enemy HQ do not conduct connection. <b>Hook</b> may ignore this for bases, but not for the HQ.
• You may stack on your own troops freely, and on an enemy troop only with a higher number. <b>Kwak</b> is a joker: it can cover any enemy troop and can be covered by any troop.
• Troop effects: <b>Skully</b> draw 2, <b>Cap'N</b> place 1 extra troop, <b>Jumbo</b> discard an adjacent enemy troop, <b>Hook</b> ignore connection, <b>XB-42</b> discard a random enemy rack troop, <b>Star</b> draw 1, <b>Roxy</b> none, <b>Kwak</b> none.
• Special bases (marked on the board) let you return one of your other troops to your rack; troop effects resolve before special bases.
• When your troops surround a whole region you permanently take its medals (they stay yours even if the region is later broken). Medals are private to no one; the board shows each player's count.
• Commands: /toybattle_draw, /toybattle_place &lt;troop number&gt; &lt;base&gt;, /toybattle_choose &lt;value&gt; (or use buttons/Mini App)."""


TOYBATTLE_RULES = """🎯 <b>Toy Battle rules</b> (2 players, Castle Field): win by placing a troop on the enemy HQ, or by being first to 7 medals.
• On your turn choose ONE action: <b>draw 2 troops</b> (rack holds at most 8) or <b>place 1 troop</b>.
• A troop must be placed on a base connected to your HQ by a continuous line of bases topped by YOUR troops. Empty bases, enemy bases and the enemy HQ do not conduct connection. <b>Hook</b> may ignore this for bases, but not for the HQ.
• You may stack on your own troops freely, and on an enemy troop only with a higher number. <b>Kwak</b> is a joker: it can cover any enemy troop and can be covered by any troop.
• Troop effects: <b>Skully</b> draw 2, <b>Cap'N</b> place 1 extra troop, <b>Jumbo</b> discard an adjacent enemy troop, <b>Hook</b> ignore connection, <b>XB-42</b> discard a random enemy rack troop, <b>Star</b> draw 1, <b>Roxy</b> none, <b>Kwak</b> none.
• Special bases (marked on the board) let you return one of your other troops to your rack; troop effects resolve before special bases.
• When your troops surround a whole region you permanently take its medals (they stay yours even if the region is later broken). Medals are private to no one; the board shows each player's count.
• Commands: /toybattle_draw, /toybattle_place &lt;troop number&gt; &lt;base&gt;, /toybattle_choose &lt;value&gt; (or use buttons/Mini App)."""


def toybattle_get(state, chat_id):
    return state.setdefault("toybattle", {}).get(str(chat_id))


def toybattle_actor_idx(g, uid):
    if g["phase"] != "play":
        return None
    ref = g["pending"]["by"] if g.get("pending") else g["current"]
    return _actor_idx(g, uid, ref)


def toybattle_board_text(g):
    if g["phase"] == "lobby":
        return "\n".join(TB.board_lines(g))
    lines = list(TB.board_lines(g))
    if g.get("pending"):
        lines.append("⚡ Choose: " + " · ".join(
            o["label"] for o in TB.pending_options(g, g["pending"]["by"])))
    else:
        lines.append("🎮 /toybattle_draw or /toybattle_place &lt;troop#&gt; &lt;base&gt; (or tap buttons).")
    return "\n".join(lines)


def toybattle_keyboard(g):
    if g["phase"] == "game_end":
        kb = [[{"text": "🔄 Rematch!", "callback_data": "tb:rematch"}]]
    else:
        ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
        wk = web_keyboard(ct, g["chat_id"], game="toybattle")
        if g["phase"] == "lobby":
            kb = [[{"text": "🙋 Join Toy Battle", "callback_data": "tb:join"}]]
            if not any(_is_npc(p) for p in g["players"]):
                kb.append([{"text": "🤖 Add NPC", "callback_data": "tb:npc"}])
            kb.append([{"text": "▶️ Start game", "callback_data": "tb:start"}])
            return kb + (wk or [])
        kb = []
        pend = g.get("pending")
        if pend:
            for opt in TB.pending_options(g, pend["by"]):
                kb.append([{"text": opt["label"][:60],
                            "callback_data": f"tb:c:{opt['value']}"}])
        else:
            kb.append([{"text": "🎁 Draw 2 troops", "callback_data": "tb:draw"}])
            legal = TB.legal_placements(g, g["current"])
            sel = g.get("selected") or {}
            idx = sel.get("index")
            if sel.get("by") == g["current"] and idx in legal and legal[idx]:
                for b in legal[idx][:15]:
                    kb.append([{"text": f"📍 Base {b}",
                                "callback_data": f"tb:p:{idx}:{b}"}])
                kb.append([{"text": "↩️ Back", "callback_data": "tb:back"}])
            else:
                row = []
                for i, bases in legal.items():
                    if bases:
                        row.append({"text": f"🪖 {i + 1} ({len(bases)})",
                                    "callback_data": f"tb:s:{i}"})
                        if len(row) == 4:
                            kb.append(row)
                            row = []
                if row:
                    kb.append(row)
        if wk:
            kb.extend(wk)
    return kb or None


def toybattle_render(g, events=None):
    lines = [html.escape(e) for e in (events or [])]
    if g["phase"] == "play":
        ref = g["pending"]["by"] if g.get("pending") else g["current"]
        p = g["players"][ref]
        if _is_npc(p):
            lines.append("👉 🤖 NPC's turn - anyone can play for it!")
        else:
            lines.append(f"👉 {toybattle_mention(g, p['user_id'])} - your move.")
    text = "\n".join(lines + [toybattle_board_text(g)])
    r = send_board(g, "toybattle", text, toybattle_keyboard(g))
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=g["chat_id"], message_id=old)


def toybattle_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(TB.name_of(g, user_id) if user_id in [p["user_id"] for p in g["players"]] else "player")}</a>'


def handle_toybattle(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = toybattle_get(state, chat_id)
    if cmd == "/toybattle_rules":
        send(chat_id, TOYBATTLE_RULES)
        return True
    if cmd == "/toybattle":
        if not g:
            _name = msg.get("from", {}).get("first_name") or "Player"
            g = TB.new_game(chat_id, uid, _name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("toybattle", {})[str(chat_id)] = g
            toybattle_render(g, [f"🎯 Toy Battle game created by {html.escape(_name)}!"])
        else:
            toybattle_render(g)
        return True
    if not g:
        send(chat_id, "No Toy Battle game here yet - send /toybattle to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/toybattle_join_npc":
        err = add_npc("toybattle", g)
        send(chat_id, err or "🤖 NPC joined - anyone can play for it!")
        if not err:
            toybattle_render(g)
        return True
    if cmd == "/toybattle_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= TB_LEN:
            send(chat_id, "⛔ Toy Battle is 2 players (full).")
        else:
            g["players"].append(TB.new_player(uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Toy Battle.")
            toybattle_render(g)
        return True
    if cmd == "/toybattle_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        else:
            ev = []
            err = TB.start_game(g, ev)
            send(chat_id, f"⛔ {err}" if err else "🎯 Toy Battle started!")
            if not err:
                toybattle_render(g, ev)
        return True
    if cmd == "/toybattle_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["toybattle"][str(chat_id)]
            send(chat_id, "🗑 Toy Battle game cancelled.")
        return True
    if cmd == "/toybattle_rematch":
        ev, err = rematch_game(state, "toybattle", chat_id, uid)
        send(chat_id, f"⛔ {err}" if err else "🔄 Rematch!")
        return True
    idx = toybattle_actor_idx(g, uid)
    if idx is None:
        send(chat_id, "⛔ You're not in this game (or it isn't your turn).")
        return True
    parts = text.split()[1:]
    ev = []
    if cmd == "/toybattle_draw":
        err = TB.draw(g, idx, ev)
    elif cmd == "/toybattle_place":
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            err = "Usage: /toybattle_place &lt;troop number&gt; &lt;base&gt;"
        else:
            err = TB.place(g, idx, int(parts[0]) - 1, int(parts[1]), ev)
    elif cmd in ("/toybattle_choose", "/toybattle_skip"):
        err = TB.choose(g, idx, "skip" if cmd == "/toybattle_skip" else
                        (parts[0] if parts else "skip"), ev)
    else:
        return False
    if err:
        send(chat_id, f"⛔ {err}")
    else:
        g["selected"] = None
        toybattle_render(g, ev)
    return True


TB_LEN = 2


def toybattle_board_json(g, viewer_id=None):
    me_idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
    actor = g["current"] if g["phase"] == "play" else None
    can_act = bool(actor is not None and me_idx is not None and
                   (me_idx == actor or _is_npc(g["players"][actor])))
    pend = g.get("pending")
    if pend:
        actor = pend["by"]
        can_act = bool(me_idx is not None and
                       (me_idx == actor or _is_npc(g["players"][actor])))
    players = []
    for i, p in enumerate(g["players"]):
        players.append({
            "user_id": p["user_id"], "name": p["name"], "npc": _is_npc(p),
            "color": p["color"], "hq": p["hq"], "medals": p["medals"],
            "reserve": len(p["reserve"]), "discard": len(p["discard"]),
            "rack_count": len(p["rack"]),
            "rack": list(p["rack"]) if i == me_idx or _is_npc(p) else [],
            "is_current": i == actor,
        })
    bases = {}
    for b, (top, left, adj, special) in TB.BASES.items():
        stack = g["stacks"].get(str(b)) or []
        bases[str(b)] = {
            "top": stack[-1] if stack else None, "height": len(stack),
            "special": special, "top_pos": top, "left_pos": left,
            "adj": adj,
        }
    board = {
        "chat_id": g["chat_id"], "phase": g["phase"], "turn": g["turn"],
        "board_name": TB.BOARD_NAME, "medal_target": TB.MEDAL_TARGET,
        "rack_limit": TB.RACK_LIMIT, "troop_names": TB.TROOP_NAMES,
        "players": players, "actor": actor, "can_act": can_act,
        "is_player": me_idx is not None, "winner": g["winner"],
        "end_reason": g["end_reason"], "log": g["log"][-12:],
        "bases": bases, "legal": {}, "options": [], "pending": None,
        "regions": {str(r): {"bases": v[0], "medals": v[1], "claimed": g["claimed"][str(r)]}
                    for r, v in TB.REGIONS.items()},
        "medal_spots": {str(m): {"top": v[0], "left": v[1], "region": v[2],
                                 "owner": g["medals"][str(m)]}
                        for m, v in TB.MEDAL_SPOTS.items()},
    }
    if can_act:
        board["legal"] = {str(k): v for k, v in TB.legal_placements(g, actor).items()}
        if pend:
            board["options"] = TB.pending_options(g, actor)
            board["pending"] = {"kind": pend["kind"], "base": pend["base"]}
    return board


def toybattle_api_move(state, chat_id, user_id, body):
    g = toybattle_get(state, chat_id)
    if not g:
        return [], "no Toy Battle game in that chat"
    action = body.get("action")
    ev = []
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= TB_LEN:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(TB.new_player(user_id, iu_name))
        ev.append("🙋 joined Toy Battle.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = TB.start_game(g, ev)
        if err:
            return [], err
    elif action == "rematch":
        return rematch_game(state, "toybattle", chat_id, user_id)
    else:
        actor = toybattle_actor_idx(g, user_id)
        if actor is None:
            return [], "not in this game"
        if action == "draw":
            err = TB.draw(g, actor, ev)
        elif action == "place":
            try:
                err = TB.place(g, actor, int(body.get("index", -1)), int(body.get("base", 0)), ev)
            except (TypeError, ValueError):
                return [], "bad placement"
        elif action == "choose":
            err = TB.choose(g, actor, body.get("value", "skip"), ev)
        else:
            return [], "unknown action"
        if err:
            return [], err
    g["selected"] = None
    toybattle_render(g, ev)
    return ev, None


TOKAIDODUO_RULES = """🗾 <b>Tokaido Duo rules</b> (2 players, Shikoku): each player controls a Pilgrim, a Merchant and an Artist. Score Faith + Commerce + Culture; highest total wins (tie: more coins, then shared).
• Each round the first picker rolls 3 dice (one per character). Draft is 1-2-1: first picker takes one, the other takes one, first picker takes the last. First picker alternates each round. A chosen character <b>must</b> move the exact die value.
• <b>Pilgrim ⛩️</b> moves clockwise around the 37-station ring. May pass occupied stations, but may not land on one - jumps to the next empty station. Coastal Town: gain the boutique coins (2-4). Temple: +1 Temple (9 ends the game). Garden: +1 Garden (6 ends the game). Hot Spring: take the token (steal it from your opponent); use it on a future pick to repeat a move. Seashore: take a Wave tile from the board (or steal one).
• <b>Merchant 💰</b> moves along orange Trade routes (Mountain &lt;-&gt; Coastal towns), exactly the die value; if no path of that length exists, no move. Mountain town: draw 2-4 Wares (store at most 5). Coastal town: sell matching Wares for the boutique price each. 10 coins = 1 gold slab (6th slab ends the game). Commerce = 0/5/11/18/26/35/45 for 0-6 slabs.
• <b>Artist 🎨</b> moves through zones (never revisiting a zone, never through a Mountain town). Then Paint (reveal as many Painting tiles as other meeples in the arrival zone) OR Gift (if the arrival zone matches the topmost revealed Painting, remove it; 10th gift ends the game). Culture = points for Paintings gifted.
• <b>Wave tiles</b>: Pilgrim Hasty (+1 move) / Tranquil (-1), Merchant Crafty (+1 coin per Ware) / Robust (+1 Ware drawn, store 6), Artist Proficient (+1 tile when Painting) / Inspired (Gift any icon on your path). Side is random at setup and fixed.
• Game ends at the end of the round when a trigger fires. Faith = Temple x Garden.
• Commands: /tokaidoduo_pick &lt;pilgrim|merchant|artist&gt;, /tokaidoduo_choose &lt;value&gt; (or use buttons/Mini App)."""


def tokaidoduo_get(state, chat_id):
    return state.setdefault("tokaidoduo", {}).get(str(chat_id))


def tokaidoduo_actor_idx(g, uid):
    if g["phase"] != "play":
        return None
    ref = TD.current_picker(g)
    if ref is None:
        return None
    return _actor_idx(g, uid, ref)


def tokaidoduo_board_text(g):
    if g["phase"] == "lobby":
        return "\n".join(TD.board_lines(g))
    lines = list(TD.board_lines(g))
    if g.get("pending"):
        lines.append("⚡ Choose: " + " · ".join(
            o["label"] for o in TD.pending_options(g, g["pending"]["by"])))
    else:
        lines.append("🎮 /tokaidoduo_pick &lt;pilgrim|merchant|artist&gt; (or tap buttons / Mini App).")
    return "\n".join(lines)


def tokaidoduo_keyboard(g):
    if g["phase"] == "game_end":
        kb = [[{"text": "🔄 Rematch!", "callback_data": "td:rematch"}]]
    else:
        ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
        wk = web_keyboard(ct, g["chat_id"], game="tokaidoduo")
        if g["phase"] == "lobby":
            kb = [[{"text": "🙋 Join Tokaido Duo", "callback_data": "td:join"}]]
            if not any(_is_npc(p) for p in g["players"]):
                kb.append([{"text": "🤖 Add NPC", "callback_data": "td:npc"}])
            kb.append([{"text": "▶️ Start game", "callback_data": "td:start"}])
            return kb + (wk or [])
        kb = []
        pend = g.get("pending")
        if pend:
            for opt in TD.pending_options(g, pend["by"]):
                kb.append([{"text": opt["label"][:60],
                            "callback_data": f"td:c:{opt['value']}"}])
        elif g["phase"] == "play":
            for ch in TD.available_dice(g):
                kb.append([{"text": f"{TD.CHAR_EMOJI[ch]} {ch.title()} ({g['dice'][ch]})",
                            "callback_data": f"td:pick:{ch}"}])
        if wk:
            kb.extend(wk)
    return kb or None


def tokaidoduo_render(g, events=None):
    lines = [html.escape(e) for e in (events or [])]
    if g["phase"] == "play":
        ref = TD.current_picker(g)
        if ref is not None:
            p = g["players"][ref]
            if _is_npc(p):
                lines.append("👉 🤖 NPC's turn - anyone can play for it!")
            else:
                lines.append(f"👉 {tokaidoduo_mention(g, p['user_id'])} - your move.")
    text = "\n".join(lines + [tokaidoduo_board_text(g)])
    r = send_board(g, "tokaidoduo", text, tokaidoduo_keyboard(g))
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=g["chat_id"], message_id=old)


def tokaidoduo_mention(g, user_id):
    return f'<a href="tg://user?id={user_id}">{html.escape(TD.name_of(g, user_id) if user_id in [p["user_id"] for p in g["players"]] else "player")}</a>'


def handle_tokaidoduo(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = tokaidoduo_get(state, chat_id)
    if cmd == "/tokaidoduo_rules":
        send(chat_id, TOKAIDODUO_RULES)
        return True
    if cmd == "/tokaidoduo":
        if not g:
            _name = msg.get("from", {}).get("first_name") or "Player"
            g = TD.new_game(chat_id, uid, _name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("tokaidoduo", {})[str(chat_id)] = g
            tokaidoduo_render(g, [f"🗾 Tokaido Duo game created by {html.escape(_name)}!"])
        else:
            tokaidoduo_render(g)
        return True
    if not g:
        send(chat_id, "No Tokaido Duo game here yet - send /tokaidoduo to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/tokaidoduo_join_npc":
        err = add_npc("tokaidoduo", g)
        send(chat_id, err or "🤖 NPC joined - anyone can play for it!")
        if not err:
            tokaidoduo_render(g)
        return True
    if cmd == "/tokaidoduo_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= TD_LEN:
            send(chat_id, "⛔ Tokaido Duo is 2 players (full).")
        else:
            g["players"].append(TD.new_player(uid, msg.get("from", {}).get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Tokaido Duo.")
            tokaidoduo_render(g)
        return True
    if cmd == "/tokaidoduo_start":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        else:
            ev = []
            err = TD.start_game(g, ev)
            send(chat_id, f"⛔ {err}" if err else "🗾 Tokaido Duo started!")
            if not err:
                tokaidoduo_render(g, ev)
        return True
    if cmd == "/tokaidoduo_cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["tokaidoduo"][str(chat_id)]
            send(chat_id, "🗑 Tokaido Duo game cancelled.")
        return True
    if cmd == "/tokaidoduo_rematch":
        ev, err = rematch_game(state, "tokaidoduo", chat_id, uid)
        send(chat_id, f"⛔ {err}" if err else "🔄 Rematch!")
        return True
    idx = tokaidoduo_actor_idx(g, uid)
    if idx is None:
        send(chat_id, "⛔ You're not in this game (or it isn't your turn).")
        return True
    parts = text.split()[1:]
    ev = []
    if cmd == "/tokaidoduo_pick":
        if not parts or parts[0] not in TD.CHARACTERS:
            err = "Usage: /tokaidoduo_pick &lt;pilgrim|merchant|artist&gt;"
        else:
            err = TD.pick_die(g, idx, parts[0], ev)
    elif cmd in ("/tokaidoduo_choose", "/tokaidoduo_skip"):
        if cmd == "/tokaidoduo_skip":
            pend = g.get("pending") or {}
            value = "done" if pend.get("kind") == "sell" else "skip"
        else:
            value = parts[0] if parts else "skip"
        err = TD.choose(g, idx, value, ev)
    else:
        return False
    if err:
        send(chat_id, f"⛔ {err}")
    else:
        tokaidoduo_render(g, ev)
    return True


TD_LEN = 2


def tokaidoduo_board_json(g, viewer_id=None):
    me_idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
    actor = TD.current_picker(g) if g["phase"] == "play" else None
    can_act = bool(actor is not None and me_idx is not None and
                   (me_idx == actor or _is_npc(g["players"][actor])))
    pend = g.get("pending")
    players = []
    for i, p in enumerate(g["players"]):
        paintings = []
        for t in p["paintings"]:
            if i == me_idx or t["revealed"] or t["gifted"]:
                paintings.append({"icon": t["icon"], "revealed": t["revealed"],
                                  "gifted": t["gifted"]})
            else:
                paintings.append({"icon": None, "revealed": False, "gifted": False})
        players.append({
            "user_id": p["user_id"], "name": p["name"], "npc": _is_npc(p),
            "color": p["color"], "pilgrim_pos": p["pilgrim_pos"],
            "temple": p["temple"], "garden": p["garden"],
            "merchant_pos": p["merchant_pos"], "artist_zone": p["artist_zone"],
            "wares": list(p["wares"]), "coins": p["coins"], "gold": p["gold"],
            "paintings": paintings, "gifted": p["gifted"],
            "waves": dict(p["waves"]),
            "faith": TD.faith_score(p), "commerce": TD.commerce_score(p),
            "culture": TD.culture_score(p),
            "is_current": i == actor,
        })
    board = {
        "chat_id": g["chat_id"], "phase": g["phase"], "round": g["round"],
        "first_picker": g["first_picker"], "pick_index": g["pick_index"],
        "dice": dict(g["dice"]), "dice_taken": list(g["dice_taken"]),
        "pick_char": g.get("pick_char"), "pick_value": g.get("pick_value"),
        "players": players, "actor": actor, "can_act": can_act,
        "is_player": me_idx is not None, "winner": g["winner"],
        "end_reason": g["end_reason"], "end_triggered": g["end_triggered"],
        "scores": g.get("scores"), "log": g["log"][-12:],
        "hot_spring": g.get("hot_spring"),
        "waves_board": list(g.get("waves_board", [])),
        "boutiques": dict(g.get("boutiques", {})),
        "stations": list(TD.STATIONS),
        "zones": [{"icon": z["icon"], "name": z["name"]} for z in TD.ZONES],
        "zone_adj": {str(k): v for k, v in TD.ZONE_ADJ.items()},
        "zone_pos": TD.ZONE_POS,
        "town_pos": TD.TOWN_POS,
        "town_adj": {k: v for k, v in TD.TOWN_ADJ.items()},
        "mountain_draw": TD.MOUNTAIN_DRAW,
        "gold_points": TD.GOLD_POINTS, "culture_points": TD.CULTURE_POINTS,
        "ware_emoji": TD.WARE_EMOJI, "char_emoji": TD.CHAR_EMOJI,
        "zone_icon_emoji": TD.ZONE_ICON_EMOJI,
        "legal": {}, "options": [], "pending": None,
    }
    if can_act:
        board["legal"] = {"dice": TD.available_dice(g)}
        if pend:
            board["options"] = TD.pending_options(g, actor)
            board["pending"] = {"kind": pend["kind"], "by": pend["by"]}
    return board


def tokaidoduo_api_move(state, chat_id, user_id, body):
    g = tokaidoduo_get(state, chat_id)
    if not g:
        return [], "no Tokaido Duo game in that chat"
    action = body.get("action")
    ev = []
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= TD_LEN:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(TD.new_player(user_id, iu_name))
        ev.append("🙋 joined Tokaido Duo.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = TD.start_game(g, ev)
        if err:
            return [], err
    elif action == "rematch":
        return rematch_game(state, "tokaidoduo", chat_id, user_id)
    else:
        actor = tokaidoduo_actor_idx(g, user_id)
        if actor is None:
            return [], "not in this game"
        if action == "pick":
            err = TD.pick_die(g, actor, str(body.get("char", "")), ev)
        elif action == "choose":
            err = TD.choose(g, actor, str(body.get("value", "skip")), ev)
        else:
            return [], "unknown action"
        if err:
            return [], err
    tokaidoduo_render(g, ev)
    return ev, None


ALTAY_LEN = 2


def altay_get(state, chat_id):
    return state.setdefault("altay", {}).get(str(chat_id))


def altay_actor_idx(g, uid):
    if g["phase"] != "playing":
        return None
    return _actor_idx(g, uid, g["current"])


def altay_mention(g, user_id):
    name = next((p["name"] for p in g["players"] if p["user_id"] == user_id), "player")
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


def _altay_resources(player):
    return " ".join(f"{AL.RESOURCE_ICONS[key]} {amount}"
                    for key, amount in player["resources"].items() if amount) or "none"


def altay_board_text(g):
    if g["phase"] == "lobby":
        lines = ["🏜️ <b>Altay</b> lobby:"]
        for index, player in enumerate(g["players"]):
            faction = AL.FACTIONS.get(player.get("faction"), {}).get("name", "auto")
            lines.append(f"• {html.escape(player['name'])} — {faction}")
        lines.append("Need 2 players. /altay_join to join, /altay_join_npc for a mock player, /altay_start to begin.")
        return "\n".join(lines)
    if g["phase"] == "over":
        scores = ", ".join(f"{html.escape(p['name'])} {value}"
                           for p, value in zip(g["players"], g["scores"] or []))
        winner = g["players"][g["winner"]] if g.get("winner") is not None else None
        return (f"🏁 <b>Altay finished</b>: {scores}. "
                + (f"Winner: <b>{html.escape(winner['name'])}</b>." if winner else "Draw."))
    current = g["current"]
    player = g["players"][current]
    lines = [f"🎲 Turn {g['turn'] + 1}: {altay_mention(g, player['user_id'])} — your move."]
    lines.append("🏆 " + " · ".join(f"{html.escape(p['name'])} {AL.score(g, i)}"
                                   for i, p in enumerate(g["players"])))
    lines.append(f"🎒 {_altay_resources(player)} · ⚔️ {player['swords']} · 🏠 builds {player['builds']}")
    cards = [f"{i + 1}. {AL.CARDS[card]['name']}" for i, card in enumerate(player["hand"])]
    lines.append("🃏 " + (", ".join(cards) or "empty hand"))
    builds = AL.legal_build(g, current)
    attacks = AL.attack_options(g, current)
    affordable = [card for card in AL.MARKET
                  if AL._can_pay(player["resources"], AL.CARDS[card].get("cost", {}))
                  and card not in player["bought"]]
    lines.append(f"🏠 Build: {', '.join(str(region) for region in builds) or 'none'}")
    lines.append(f"⚔️ Attack: {', '.join(str(o['region']) for o in attacks) or 'none'}")
    lines.append(f"💰 Buy: {', '.join(affordable) or 'none'}")
    lines.append("📜 Develop: " + (player["achievement"] or "choose one"))
    lines.extend(html.escape(line) for line in (g.get("logs") or [])[-3:])
    return "\n".join(lines)


def altay_keyboard(g):
    if g["phase"] == "over":
        return [[{"text": "🔄 Rematch!", "callback_data": "al:rematch"}]]
    ct = g.get("chat_type") or ("supergroup" if int(g["chat_id"]) < 0 else "private")
    wk = web_keyboard(ct, g["chat_id"], game="altay")
    if g["phase"] == "lobby":
        kb = [[{"text": "🙋 Join Altay", "callback_data": "al:join"}]]
        if not any(_is_npc(p) for p in g["players"]):
            kb.append([{"text": "🤖 Add NPC", "callback_data": "al:npc"}])
        kb.append([{"text": btn["text"], "callback_data": f"al:f:{code}"}
                   for code, btn in zip(AL.FACTION_ORDER, [
                       {"text": "🌍 Earthfolk"}, {"text": "🌿 Elvenfolk"},
                       {"text": "🔥 Firefolk"}, {"text": "🧚 Smallfolk"}])])
        kb.append([{"text": "▶️ Start game", "callback_data": "al:start"}])
        return kb + (wk or [])
    player = g["players"][g["current"]]
    sel = g.get("sel")
    kb = []
    if sel:
        if sel == "build":
            for row in [AL.legal_build(g, g["current"])[i:i + 5]
                        for i in range(0, len(AL.legal_build(g, g["current"])), 5)]:
                kb.append([{"text": f"🏠 {region}", "callback_data": f"al:rb:{region}"}
                           for region in row])
        elif sel == "attack":
            for option in AL.attack_options(g, g["current"]):
                label = "⚔️" if option["kind"] == "neutral" else "🛡️"
                kb.append([{"text": f"{label} {option['region']} ({option['value']})",
                            "callback_data": f"al:ra:{option['region']}"}])
        elif sel == "develop":
            for achievement_id in ["irrigation", "mining", "writing", "agriculture",
                                   "metallurgy", "amphitheatre", "pyramids", "astronomy", "epic"]:
                if achievement_id not in player["achievements"]:
                    kb.append([{"text": AL.ACHIEVEMENTS[achievement_id]["name"],
                                "callback_data": f"al:rd:{achievement_id}"}])
        elif sel == "buy":
            for card_id in AL.MARKET:
                if card_id not in player["bought"]:
                    kb.append([{"text": AL.CARDS[card_id]["name"],
                                "callback_data": f"al:rs:{card_id}"}])
        kb.append([{"text": "↩️ Back", "callback_data": "al:back"}])
    else:
        row = []
        for index, card_id in enumerate(player["hand"]):
            row.append({"text": f"🃏 {index + 1} {AL.CARDS[card_id]['name']}",
                        "callback_data": f"al:p:{index}"})
            if len(row) == 2:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        kb.append([
            {"text": "💰 Buy", "callback_data": "al:s"},
            {"text": "🏠 Build", "callback_data": "al:b"},
            {"text": "⚔️ Attack", "callback_data": "al:a"},
        ])
        kb.append([
            {"text": "📜 Develop", "callback_data": "al:d"},
            {"text": "✅ End turn", "callback_data": "al:e"},
        ])
    if wk:
        kb.extend(wk)
    return kb or None


def altay_render(g, events=None):
    lines = [html.escape(event) for event in (events or [])]
    if g["phase"] == "playing":
        p = g["players"][g["current"]]
        if _is_npc(p):
            lines.append("👉 🤖 NPC's turn - anyone can play for it!")
        else:
            lines.append(f"👉 {altay_mention(g, p['user_id'])} - your move.")
    r = send_board(g, "altay", "\n".join(lines + [altay_board_text(g)]), altay_keyboard(g))
    if r.get("ok"):
        old = g.get("board_message_id")
        g["board_message_id"] = r["result"]["message_id"]
        if old:
            api("deleteMessage", chat_id=g["chat_id"], message_id=old)


def handle_altay(state, msg, cmd, text, uid, name):
    chat_id = msg["chat"]["id"]
    g = altay_get(state, chat_id)
    if cmd == "/altay_rules":
        send(chat_id, ALTAY_RULES)
        return True
    if cmd == "/altay":
        if not g:
            creator_name = msg.get("from", {}).get("first_name") or "Player"
            g = AL.new_game(chat_id, uid, creator_name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("altay", {})[str(chat_id)] = g
            altay_render(g, [f"🏜️ Altay game created by {html.escape(creator_name)}!"])
        else:
            altay_render(g)
        return True
    if not g:
        send(chat_id, "No Altay game here yet - send /altay to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/altay_join_npc":
        err = add_npc("altay", g)
        send(chat_id, err or "🤖 NPC joined - anyone can play for it!")
        if not err:
            altay_render(g)
        return True
    if cmd == "/altay_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        else:
            err = AL.join_game(g, uid, msg.get("from", {}).get("first_name") or "Player")
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                send(chat_id, f"🙋 <b>{name}</b> joined Altay.")
                altay_render(g)
        return True
    if cmd == "/altay_faction":
        parts = text.split()[1:]
        mine = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
        if g["phase"] != "lobby" or mine is None:
            send(chat_id, "⛔ Choose a faction in the lobby.")
        elif not parts:
            send(chat_id, "Usage: /altay_faction &lt;earthfolk|elvenfolk|firefolk|smallfolk&gt;")
        else:
            err = AL.set_faction(g, mine, parts[0])
            send(chat_id, f"⛔ {err}" if err else f"🎌 {html.escape(parts[0].title())} chosen.")
            if not err:
                altay_render(g)
        return True
    if cmd == "/altay_start":
        ev = []
        err = AL.start_game(g, ev)
        send(chat_id, f"⛔ {err}" if err else "🏜️ Altay started!")
        if not err:
            altay_render(g, ev)
        return True
    if cmd == "/altay_cancel":
        if uid != g["players"][0]["user_id"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["altay"][str(chat_id)]
            send(chat_id, "🗑 Altay game cancelled.")
        return True
    if cmd == "/altay_rematch":
        ev, err = rematch_game(state, "altay", chat_id, uid)
        send(chat_id, f"⛔ {err}" if err else "🔄 Rematch!")
        return True
    if cmd == "/altay_score":
        lines = [f"{html.escape(p['name'])}: {AL.score_breakdown(g, i)}" for i, p in enumerate(g["players"])]
        send(chat_id, "<b>Altay scores</b>\n" + "\n".join(lines))
        return True
    idx = altay_actor_idx(g, uid)
    if idx is None:
        send(chat_id, "⛔ You're not in this game (or it isn't your turn).")
        return True
    parts = text.split()[1:]
    ev = []
    if cmd == "/altay_play":
        if not parts or not parts[0].isdigit():
            err = "Usage: /altay_play &lt;card number&gt;"
        else:
            err = AL.play_card(g, idx, int(parts[0]) - 1, ev)
    elif cmd == "/altay_buy":
        err = AL.buy_card(g, idx, parts[0], ev) if parts else "Usage: /altay_buy &lt;card&gt;"
    elif cmd == "/altay_build":
        if not parts or not parts[0].isdigit():
            err = "Usage: /altay_build &lt;territory&gt;"
        else:
            err = AL.build_settlement(g, idx, int(parts[0]), ev)
    elif cmd == "/altay_attack":
        if not parts or not parts[0].isdigit():
            err = "Usage: /altay_attack &lt;territory&gt;"
        else:
            err = AL.attack(g, idx, None, int(parts[0]), ev)
    elif cmd == "/altay_develop":
        err = AL.develop(g, idx, parts[0], ev) if parts else "Usage: /altay_develop &lt;id&gt;"
    elif cmd == "/altay_end":
        err = AL.end_turn(g, idx, ev)
    else:
        return False
    if err:
        send(chat_id, f"⛔ {err}")
    else:
        g["sel"] = None
        altay_render(g, ev)
    return True


def altay_board_json(g, viewer_id=None):
    board = AL.board_json(g, viewer_id)
    me = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
    actor = g["current"] if g["phase"] == "playing" else None
    can_act = bool(me is not None and actor is not None and
                   (me == actor or _is_npc(g["players"][actor])))
    board.update({
        "chat_id": g["chat_id"], "actor": actor, "can_act": can_act,
        "is_player": me is not None, "me": me,
        "log": board["logs"], "rules": ALTAY_RULES,
    })
    if can_act:
        board["legal"] = {
            "build": board["build_options"],
            "attack": board["attack_options"],
            "buy": [card["id"] for card in board["market"]
                    if card["id"] not in board["players"][actor]["bought"]],
        }
    else:
        board["legal"] = {"build": [], "attack": [], "buy": []}
    return board


def altay_api_move(state, chat_id, user_id, body):
    g = altay_get(state, chat_id)
    if not g:
        return [], "no Altay game in that chat"
    action = body.get("action")
    ev = []
    mine = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if mine is not None:
            return ev, None
        err = AL.join_game(g, user_id, (init_user(body.get("init_data", "")) or (None, "Player"))[1])
        if err:
            return [], err
        ev.append("🙋 joined Altay.")
    elif action == "faction":
        if g["phase"] != "lobby" or mine is None:
            return [], "choose a faction in the lobby"
        err = AL.set_faction(g, mine, str(body.get("faction", "")))
        if err:
            return [], err
    elif action == "npc":
        if g["phase"] != "lobby":
            return [], "game already started"
        err = add_npc("altay", g)
        if not err:
            ev.append("🤖 NPC joined - anyone can play for it.")
        return ev, err
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = AL.start_game(g, ev)
        if err:
            return [], err
    elif action == "rematch":
        return rematch_game(state, "altay", chat_id, user_id)
    else:
        actor = altay_actor_idx(g, user_id)
        if actor is None:
            return [], "not in this game"
        try:
            if action == "play":
                err = AL.play_card(g, actor, int(body.get("index", -1)), ev)
            elif action == "buy":
                err = AL.buy_card(g, actor, str(body.get("card", "")), ev)
            elif action == "build":
                err = AL.build_settlement(g, actor, int(body.get("region", -1)), ev)
            elif action == "attack":
                err = AL.attack(g, actor, body.get("from"), int(body.get("region", -1)), ev)
            elif action == "develop":
                err = AL.develop(g, actor, str(body.get("achievement", "")), ev)
            elif action == "end":
                err = AL.end_turn(g, actor, ev)
            else:
                return [], "unknown action"
        except (TypeError, ValueError):
            return [], "bad move"
        if err:
            return [], err
    g["sel"] = None
    altay_render(g, ev)
    return ev, None


REMATCH_END_PHASES = dict(GR.REMATCH_END_PHASES)

RENDERERS = {"games": render, "regicide": rg_render, "odin": odin_render,
             "leaves": leaves_render, "lsd": lsd_render, "spots": spots_render, "yahtzee": yahtzee_render,
             "fliptoons": fliptoons_render, "tornado": tornado_render,
              "castlecombo": castlecombo_render, "artichokes": artichokes_render,
               "fellowship": fotr_render, "azul": azul_render,
               "toybattle": toybattle_render,
               "tokaidoduo": tokaidoduo_render,
                "altay": altay_render}

RULES_BY_KEY = {"games": RULES, "regicide": REGICIDE_RULES, "odin": ODIN_RULES,
                "leaves": LEAVES_MODULE.rules(), "lsd": LSD_RULES, "spots": SPOTS_RULES,
                "yahtzee": YAHTZEE_RULES, "fliptoons": FLIPTOONS_RULES,
                "tornado": TORNADO_RULES, "castlecombo": CASTLECOMBO_RULES,
                "artichokes": ARTICHOKES_RULES, "fellowship": FTR_RULES,
                 "azul": AZUL_RULES, "toybattle": TOYBATTLE_RULES,
                 "tokaidoduo": TOKAIDODUO_RULES,
                 "altay": ALTAY_RULES}


def guide_payload(key):
    """Mini App guide for one game, reusing the canonical Telegram rules."""
    spec = GR.GAMES_BY_KEY.get(key)
    guide = RULES_BY_KEY.get(key)
    if not spec or not guide:
        return None
    return {"ok": True, "key": key, "name": spec.name, "guide": guide}

PLAYER_MAKERS = {
    "games": lambda u, n: G.new_player(u, n),
    "regicide": lambda u, n: {"user_id": u, "name": n, "hand": []},
    "odin": lambda u, n: {"user_id": u, "name": n, "hand": [], "score": O.START_SCORE},
    "leaves": LEAVES_MODULE.new_player,
    "lsd": lambda u, n: {"user_id": u, "name": n, "souls": 5, "candle": None,
                         "in_play": [], "demons": [], "demon_hand": []},
    "spots": lambda u, n: {"user_id": u, "name": n, "dogs": [], "scored": [],
                           "yard": [], "treats": 1},
    "yahtzee": lambda u, n: Y.new_player(u, n),
    "fliptoons": lambda u, n: _ft_player(u, n),
    "castlecombo": lambda u, n: CC.new_player(u, n),
    "tornado": lambda u, n: TS.new_player(u, n),
    "artichokes": lambda u, n: AT.new_player(u, n),
    "fellowship": lambda u, n: FTR.new_player(u, n),
    "azul": lambda u, n: AZ.new_player(u, n),
    "toybattle": lambda u, n: TB.new_player(u, n),
    "tokaidoduo": lambda u, n: TD.new_player(u, n),
    "altay": lambda u, n: AL.new_player(u, n),
}

GAME_MAKERS = {"games": G.new_game, "regicide": R.new_game, "odin": O.new_game,
               "leaves": LEAVES_MODULE.new_game, "lsd": D.new_game, "spots": SP.new_game,
               "yahtzee": Y.new_game, "fliptoons": FT.new_game, "tornado": TS.new_game,
               "castlecombo": CC.new_game, "artichokes": AT.new_game,
                "fellowship": FTR.new_game, "azul": AZ.new_game,
                "toybattle": TB.new_game,
               "tokaidoduo": TD.new_game,
                "altay": AL.new_game}


def rematch_game(state, key, chat_id, uid):
    """Reset a finished game to the lobby with the same players.
    Any player of the finished game may trigger it."""
    g = state.get(key, {}).get(str(chat_id))
    if not g:
        return [], "no game in that chat"
    if g["phase"] not in REMATCH_END_PHASES[key]:
        return [], "game is not over yet"
    if not any(p["user_id"] == uid for p in g["players"]):
        return [], "only players of this game can rematch"
    keep = [(p["user_id"], p["name"], _is_npc(p)) for p in g["players"]]
    creator = next((k for k in keep if k[0] != NPC_ID), keep[0])
    makers = PLAYER_MAKERS
    news = GAME_MAKERS
    chat_type = g.get("chat_type", "private")
    board_id = g.get("board_message_id")
    g.clear()
    g.update(news[key](chat_id, creator[0], creator[1]))
    g["chat_type"] = chat_type
    g["board_message_id"] = board_id
    g["players"] = []
    for u, n, npc_ in keep:
        pm = makers[key](u, n)
        pm["npc"] = npc_
        g["players"].append(pm)
    ev = [f"🔄 Rematch! {len(keep)} player(s) - anyone taps Start."]
    RENDERERS[key](g, ev)
    return ev, None


# ---------- Handlers ----------
def get_game(state, chat_id):
    return state["games"].get(str(chat_id))


def handle_command(state, msg):
    # Mini App (web_app) result: HTML game calls Telegram.WebApp.sendData on win.
    if msg.get("web_app_data"):
        try:
            d = json.loads(msg["web_app_data"].get("data", "{}"))
            send(msg["chat"]["id"],
                 f"🎮 HTML game finished: <b>{html.escape(str(d.get('winner', '?')))}</b> "
                 f"won with {html.escape(str(d.get('score', '?')))} pts in round {html.escape(str(d.get('round', '?')))}!")
        except Exception:
            pass
        return
    chat_id = msg["chat"]["id"]
    user = msg.get("from", {})
    uid, name = user.get("id"), html.escape(user.get("first_name") or "Player")
    text = (msg.get("text") or "").strip()
    # Ignore regular chat messages (and commands addressed to other bots):
    # as a group admin the bot sees all messages, but must stay silent on chat.
    if not text.startswith("/"):
        return
    raw_cmd = text.split()[0]
    if "@" in raw_cmd and raw_cmd.split("@", 1)[1].lower() != "flip7groupbot":
        return
    cmd = raw_cmd.split("@")[0].lower().replace("-", "_")  # Telegram links only [a-z0-9_]
    g = get_game(state, chat_id)
    if g:
        g["chat_type"] = msg.get("chat", {}).get("type", g.get("chat_type", "private"))

    if cmd == "/games":
        chat_type = msg.get("chat", {}).get("type", "private")
        kb = games_spectate_keyboard(state, chat_id, chat_type)
        rich = send_rich(chat_id, games_rich_message(state, chat_id), kb)
        if not rich.get("ok"):
            send(chat_id, games_text_message(state, chat_id), kb)
        return
    if cmd == "/cancel" and msg.get("reply_to_message"):
        # Reply-targeted cancel: cancels the one game whose board message
        # was replied to (searches every game type in this chat).
        _mid = msg["reply_to_message"].get("message_id")
        for _key in GR.GAME_KEYS:
            _gg = state.get(_key, {}).get(str(chat_id))
            if _gg is not None and _gg.get("board_message_id") == _mid:
                del state[_key][str(chat_id)]
                save_state(state)
                send(chat_id, f"🗑 Game cancelled ({_key}).")
                return
        # No matching board message: fall through to the normal /cancel.
    if cmd.startswith("/regicide"):
        handle_regicide(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/odin"):
        handle_odin(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/leaves"):
        handle_leaves(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/lsd"):
        handle_lsd(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/spots"):
        handle_spots(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/yahtzee"):
        handle_yahtzee(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/fliptoons"):
        handle_fliptoons(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/castlecombo"):
        handle_castlecombo(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/tornado"):
        handle_tornado(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/artichokes"):
        handle_artichokes(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/fotr") or cmd.startswith("/fellowship"):
        handle_fellowship(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/azul"):
        handle_azul(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/toybattle"):
        handle_toybattle(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/tokaidoduo"):
        handle_tokaidoduo(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/altay"):
        handle_altay(state, msg, cmd, text, uid, name)
        return
    if cmd in ("/start", "/help", "/commands"):
        send(chat_id, HELP)
        return
    if cmd == "/myid":
        send(chat_id, f"Your Telegram user_id is <code>{uid}</code> (for debugging; the HTML Mini App logs you in automatically).")
        return
    if cmd == "/rules":
        # Context-aware rules: a reply to a board message shows that game's
        # rules; otherwise show the rules of every game present in this chat
        # (Flip 7 rules as the default when there are none).
        _mid = (msg.get("reply_to_message") or {}).get("message_id") if msg.get("reply_to_message") else None
        _by_key = tuple(RULES_BY_KEY.items())
        if _mid:
            for _key, _rules in _by_key:
                _gg = state.get(_key, {}).get(str(chat_id))
                if _gg is not None and _gg.get("board_message_id") == _mid:
                    send(chat_id, _rules)
                    return
        _present = [_rules for _key, _rules in _by_key if state.get(_key, {}).get(str(chat_id))]
        send(chat_id, "\n\n".join(_present) if _present else RULES)
        return
    if cmd == "/flip7_rules":
        send(chat_id, RULES)
        return
    if cmd == "/flip7":
        if not g:
            _name = user.get("first_name") or "Player"
            g = G.new_game(chat_id, uid, _name)
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state["games"][str(chat_id)] = g
            render(g, [f"🎴 Flip 7 game created by {_name}!"])
        else:
            render(g)
        return
    if not g:
        send(chat_id, "No Flip 7 game here yet - send /flip7 to create one, or open the Mini App via /games. /rules for how to play.")
        return
    if cmd == "/flip7_join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        elif len(g["players"]) >= 6:
            send(chat_id, "⛔ Game is full.")
        else:
            g["players"].append(G.new_player(uid, user.get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined Flip 7 ({len(g['players'])} players).")
            render(g)
        return
    if cmd == "/flip7_start":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players.")
        else:
            _ev = [f"🎮 Flip 7 started with {len(g['players'])} players! First to {G.WIN_SCORE}."]
            _order = [(g["dealer_index"] + k) % len(g["players"])
                      for k in range(len(g["players"]))]
            g["deal_queue"] = list(_order)
            g["phase"] = "dealing"
            advance(g, _ev)
            render(g, _ev)
        return
    if cmd in ("/join_npc", "/npc_join"):
        err = add_npc("games", g)
        if err:
            send(chat_id, err)
        else:
            send(chat_id, "🤖 NPC joined - anyone can play for it!")
            render(g)
        return
    send(chat_id, "Commands: /games /rules /cancel (reply to a board) - or use the in-game buttons.")


def handle_callback(state, cb):
    # Telegram HTML5 Game "Play" button: callback has game_short_name, no data.
    # Answer with the game's URL so Telegram opens it (Bot API answerCallbackQuery url).
    if cb.get("game_short_name"):
        if GAME_URL:
            api("answerCallbackQuery", callback_query_id=cb["id"], url=GAME_URL)
        else:
            answer_cb(cb["id"], "HTML game URL not configured (FLIP7_GAME_URL).")
        return
    data = cb.get("data", "")
    uid = cb.get("from", {}).get("id")
    chat_id = cb.get("message", {}).get("chat", {}).get("id")
    if data.endswith(":npc"):
        key = GR.CALLBACK_CODES.get(data.split(":")[0])
        g = state.get(key, {}).get(str(chat_id)) if key else None
        if not g:
            return answer_cb(cb["id"], "No game here.")
        err = add_npc(key, g)
        if err:
            return answer_cb(cb["id"], err)
        answer_cb(cb["id"], "🤖 NPC joined")
        RENDERERS[key](g, ["🤖 NPC joined - anyone can play for it!"])
        return
    if data.startswith("az:"):
        az = azul_get(state, chat_id)
        if not az:
            return answer_cb(cb["id"], "No Azul game here.")
        parts = data.split(":")
        mine = next((i for i, p in enumerate(az["players"]) if p["user_id"] == uid), None)
        ev = []
        if parts == ["az", "join"]:
            if az["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if mine is not None:
                return answer_cb(cb["id"], "Already in!")
            if len(az["players"]) >= AZ.MAX_PLAYERS:
                return answer_cb(cb["id"], "Game is full.")
            az["players"].append(AZ.new_player(uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            azul_render(az, [f"🙋 {cb['from'].get('first_name')} joined Azul."])
        elif parts == ["az", "start"]:
            if az["phase"] != "lobby":
                return answer_cb(cb["id"], "Already started.")
            err = AZ.start_game(az, ev)
            answer_cb(cb["id"], err or "Started")
            if not err:
                azul_render(az, ev)
        elif parts == ["az", "rematch"]:
            ev, err = rematch_game(state, "azul", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            idx = azul_actor_idx(az, uid)
            if idx is None:
                return answer_cb(cb["id"], "Not your turn.")
            if len(parts) == 5 and parts[1] == "t":
                source = "factory" if parts[2] == "f" else "center"
                try:
                    index = int(parts[3])
                except ValueError:
                    return answer_cb(cb["id"], "Bad factory.")
                err = AZ.take_tiles(az, idx, source, index, parts[4], ev)
            elif len(parts) == 3 and parts[1] == "r":
                try:
                    row = int(parts[2])
                except ValueError:
                    return answer_cb(cb["id"], "Bad line.")
                err = AZ.place_tiles(az, idx, row, ev)
            else:
                return answer_cb(cb["id"], "Unknown button.")
            answer_cb(cb["id"], err or "Done")
            if not err:
                azul_render(az, ev)
        return
    if data.startswith("al:"):
        g = altay_get(state, chat_id)
        if not g:
            return answer_cb(cb["id"], "No Altay game here.")
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        ev = []
        mine = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
        if action == "join":
            if g["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            err = AL.join_game(g, uid, cb["from"].get("first_name") or "Player")
            answer_cb(cb["id"], err or "Joined!")
            if not err:
                altay_render(g, [f"🙋 {cb['from'].get('first_name')} joined Altay."])
            return
        if action == "npc":
            if g["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            err = add_npc("altay", g)
            answer_cb(cb["id"], err or "🤖 NPC joined")
            if not err:
                altay_render(g)
            return
        if action == "f":
            if g["phase"] != "lobby" or mine is None:
                return answer_cb(cb["id"], "Choose a faction in the lobby.")
            err = AL.set_faction(g, mine, parts[2] if len(parts) > 2 else "")
            answer_cb(cb["id"], err or "Faction chosen")
            if not err:
                altay_render(g)
            return
        if action == "start":
            if g["phase"] != "lobby":
                return answer_cb(cb["id"], "Already started.")
            err = AL.start_game(g, ev)
            answer_cb(cb["id"], err or "Started")
            if not err:
                altay_render(g, ev)
            return
        if action == "rematch":
            ev, err = rematch_game(state, "altay", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
            return
        actor = altay_actor_idx(g, uid)
        if actor is None:
            return answer_cb(cb["id"], "Not your turn.")
        if action in ("p", "b", "a", "d", "s"):
            if action == "p":
                try:
                    err = AL.play_card(g, actor, int(parts[2]), ev)
                except (IndexError, ValueError):
                    return answer_cb(cb["id"], "Bad card.")
            else:
                g["sel"] = {"p": "play", "b": "build", "a": "attack",
                            "d": "develop", "s": "buy"}[action]
                err = None
        elif action == "back":
            g["sel"] = None
            err = None
        else:
            try:
                if action == "rb":
                    err = AL.build_settlement(g, actor, int(parts[2]), ev)
                elif action == "ra":
                    err = AL.attack(g, actor, None, int(parts[2]), ev)
                elif action == "rd":
                    err = AL.develop(g, actor, parts[2], ev)
                elif action == "rs":
                    err = AL.buy_card(g, actor, parts[2], ev)
                elif action == "e":
                    err = AL.end_turn(g, actor, ev)
                else:
                    return answer_cb(cb["id"], "Unknown button.")
            except (IndexError, ValueError):
                return answer_cb(cb["id"], "Bad move.")
        answer_cb(cb["id"], err or "Done")
        if not err:
            g["sel"] = None
            altay_render(g, ev)
        return
    if data.startswith("tb:"):
        g = toybattle_get(state, chat_id)
        if not g:
            return answer_cb(cb["id"], "No Toy Battle game here.")
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        ev = []
        if action == "join":
            if g["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if any(p["user_id"] == uid for p in g["players"]):
                return answer_cb(cb["id"], "Already in!")
            if len(g["players"]) >= TB_LEN:
                return answer_cb(cb["id"], "Game is full.")
            g["players"].append(TB.new_player(uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            toybattle_render(g, [f"🙋 {cb['from'].get('first_name')} joined Toy Battle."])
            return
        if action == "npc":
            err = add_npc("toybattle", g)
            answer_cb(cb["id"], err or "🤖 NPC joined")
            if not err:
                toybattle_render(g)
            return
        if action == "start":
            if g["phase"] != "lobby":
                return answer_cb(cb["id"], "Already started.")
            err = TB.start_game(g, ev)
            answer_cb(cb["id"], err or "Started")
            if not err:
                toybattle_render(g, ev)
            return
        if action == "rematch":
            ev, err = rematch_game(state, "toybattle", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
            return
        idx = toybattle_actor_idx(g, uid)
        if idx is None:
            return answer_cb(cb["id"], "Not your turn.")
        if action == "draw":
            err = TB.draw(g, idx, ev)
        elif action == "s":
            try:
                g["selected"] = {"index": int(parts[2]), "by": idx}
            except (IndexError, ValueError):
                return answer_cb(cb["id"], "Bad troop.")
            err = None
            g["selected"] = g["selected"] if TB.legal_placements(g, idx).get(g["selected"]["index"]) else None
        elif action == "back":
            g["selected"] = None
            err = None
        elif action == "p":
            try:
                err = TB.place(g, idx, int(parts[2]), int(parts[3]), ev)
            except (IndexError, ValueError):
                return answer_cb(cb["id"], "Bad placement.")
        elif action == "c":
            err = TB.choose(g, idx, ":".join(parts[2:]), ev)
        else:
            return answer_cb(cb["id"], "Unknown button.")
        answer_cb(cb["id"], err or "Done")
        if not err:
            g["selected"] = None
            toybattle_render(g, ev)
        return
    if data.startswith("td:"):
        g = tokaidoduo_get(state, chat_id)
        if not g:
            return answer_cb(cb["id"], "No Tokaido Duo game here.")
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        ev = []
        if action == "join":
            if g["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if any(p["user_id"] == uid for p in g["players"]):
                return answer_cb(cb["id"], "Already in!")
            if len(g["players"]) >= TD_LEN:
                return answer_cb(cb["id"], "Game is full.")
            g["players"].append(TD.new_player(uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            tokaidoduo_render(g, [f"🙋 {cb['from'].get('first_name')} joined Tokaido Duo."])
            return
        if action == "npc":
            err = add_npc("tokaidoduo", g)
            answer_cb(cb["id"], err or "🤖 NPC joined")
            if not err:
                tokaidoduo_render(g)
            return
        if action == "start":
            if g["phase"] != "lobby":
                return answer_cb(cb["id"], "Already started.")
            err = TD.start_game(g, ev)
            answer_cb(cb["id"], err or "Started")
            if not err:
                tokaidoduo_render(g, ev)
            return
        if action == "rematch":
            ev, err = rematch_game(state, "tokaidoduo", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
            return
        idx = tokaidoduo_actor_idx(g, uid)
        if idx is None:
            return answer_cb(cb["id"], "Not your turn.")
        if action == "pick":
            err = TD.pick_die(g, idx, parts[2] if len(parts) > 2 else "", ev)
        elif action == "c":
            err = TD.choose(g, idx, ":".join(parts[2:]), ev)
        else:
            return answer_cb(cb["id"], "Unknown button.")
        answer_cb(cb["id"], err or "Done")
        if not err:
            tokaidoduo_render(g, ev)
        return
    if data.startswith("lv:"):
        return handle_leaves_callback(state, cb, chat_id, uid)
    if data.startswith("fotr:"):
        g = fotr_get(state, chat_id)
        if not g:
            return answer_cb(cb["id"], "No Fellowship game here.")
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        params = {}
        if action == "choose" and len(parts) > 2:
            params = {"character": parts[2]}
        elif action == "out" and len(parts) > 3:
            params = {"card": parts[2], "target": parts[3]}
        elif action == "back" and len(parts) > 2:
            params = {"card": parts[2]}
        elif action == "play" and len(parts) > 2:
            params = {"card": parts[2]}
        elif action == "ring" and len(parts) > 2:
            params = {"use": parts[2] == "1"}
        elif action == "start" and len(parts) > 2:
            params = {"chapter": parts[2]}
        ev, err = fotr_api_move(state, chat_id, uid, {"action": action, **params})
        answer_cb(cb["id"], err or "OK")
        if not err:
            save_state(state)
        return
    if data.startswith("spots:"):
        sp = spots_get(state, chat_id)
        if not sp:
            return answer_cb(cb["id"], "No Spots game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(sp["players"]) if p["user_id"] == uid), None)
        if idx is None and sp.get("pending"):
            idx = _actor_idx(sp, uid, sp["pending"]["player"])
        elif idx is None:
            idx = _actor_idx(sp, uid, sp["current_index"])
        ev = []
        if parts == ["spots", "join"]:
            if sp["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            sp["players"].append({"user_id": uid, "name": cb["from"].get("first_name") or "Player",
                                  "dogs": [], "scored": [], "yard": [], "treats": 1})
            answer_cb(cb["id"], "Joined!")
            spots_render(sp, [f"🙋 {cb['from'].get('first_name')} joined Spots."])
        elif len(parts) == 3 and parts[1] == "trick":
            err = SP.choose_trick(sp, idx, parts[2], ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Trick chosen")
            if not err:
                spots_render(sp, ev)
        elif parts == ["spots", "score"]:
            err = SP.score_action(sp, idx, ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Scored")
            if not err:
                spots_render(sp, ev)
        elif len(parts) >= 4 and parts[1] == "c":
            pend = sp.get("pending")
            if not pend or pend["player"] != idx:
                return answer_cb(cb["id"], "No choice pending for you.")
            kind = parts[2]
            if kind in ("choose_number", "bolt_count"):
                choice = int(parts[3])
            elif kind in ("optional_roll", "repeat"):
                choice = parts[3]
            elif kind == "dig":
                if parts[3] == "done":
                    choice = "done"
                else:
                    choice = {"player": int(parts[3]), "yard": int(parts[4]), "delta": int(parts[5])}
            elif kind == "trot":
                choice = {"from_dog": int(parts[3]), "from_spot": int(parts[4]),
                          "to_dog": int(parts[5]), "to_spot": int(parts[6])}
            elif kind == "dogpile_take":
                if parts[3] == "yard":
                    choice = {"src": "yard", "yard": int(parts[4])}
                else:
                    choice = {"src": "dog", "dog": int(parts[4]), "spot": int(parts[5])}
            else:
                choice = parts[3]
            err = SP.apply_choice(sp, idx, choice, ev)
            answer_cb(cb["id"], err or "Done")
            if not err:
                spots_render(sp, ev)
        elif parts == ["od", "rematch"]:
            ev, err = rematch_game(state, "odin", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        elif parts == ["lsd", "rematch"]:
            ev, err = rematch_game(state, "lsd", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        elif parts == ["spots", "rematch"]:
            ev, err = rematch_game(state, "spots", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            answer_cb(cb["id"], "Unknown button.")
        return
    if data.startswith("spots:"):
        sp = spots_get(state, chat_id)
        if not sp:
            return answer_cb(cb["id"], "No Spots game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(sp["players"]) if p["user_id"] == uid), None)
        if idx is None and sp.get("pending"):
            idx = _actor_idx(sp, uid, sp["pending"]["player"])
        elif idx is None:
            idx = _actor_idx(sp, uid, sp["current_index"])
        ev = []
        if parts == ["spots", "join"]:
            if sp["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            sp["players"].append({"user_id": uid, "name": cb["from"].get("first_name") or "Player",
                                  "dogs": [], "scored": [], "yard": [], "treats": 1})
            answer_cb(cb["id"], "Joined!")
            spots_render(sp, [f"🙋 {cb['from'].get('first_name')} joined Spots."])
        elif len(parts) == 3 and parts[1] == "trick":
            err = SP.choose_trick(sp, idx, parts[2], ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Trick chosen")
            if not err:
                spots_render(sp, ev)
        elif parts == ["spots", "score"]:
            err = SP.score_action(sp, idx, ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Scored")
            if not err:
                spots_render(sp, ev)
        elif len(parts) >= 4 and parts[1] == "c":
            pend = sp.get("pending")
            if not pend or pend["player"] != idx:
                return answer_cb(cb["id"], "No choice pending for you.")
            kind = parts[2]
            if kind in ("choose_number", "bolt_count"):
                choice = int(parts[3])
            elif kind in ("optional_roll", "repeat"):
                choice = parts[3]
            elif kind == "dig":
                choice = "done" if parts[3] == "done" else {"player": int(parts[3]), "yard": int(parts[4]), "delta": int(parts[5])}
            elif kind == "trot":
                choice = {"from_dog": int(parts[3]), "from_spot": int(parts[4]), "to_dog": int(parts[5]), "to_spot": int(parts[6])}
            elif kind == "dogpile_take":
                choice = {"src": "yard", "yard": int(parts[4])} if parts[3] == "yard" else {"src": "dog", "dog": int(parts[4]), "spot": int(parts[5])}
            elif kind == "scavenge":
                choice = "done" if parts[3] == "done" else int(parts[3])
            else:
                choice = parts[3]
            err = SP.apply_choice(sp, idx, choice, ev)
            answer_cb(cb["id"], err or "Done")
            if not err:
                spots_render(sp, ev)
        else:
            answer_cb(cb["id"], "Unknown button.")
        return
    if data.startswith("lsd:"):
        ls = lsd_get(state, chat_id)
        if not ls:
            return answer_cb(cb["id"], "No Summon Demons game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(ls["players"]) if p["user_id"] == uid), None)
        if idx is None:
            _ref = ls["pending"]["player"] if ls.get("pending") else ls["current_index"]
            idx = _actor_idx(ls, uid, _ref)
        ev = []
        if parts == ["lsd", "join"]:
            if ls["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            ls["players"].append({"user_id": uid, "name": cb["from"].get("first_name") or "Player",
                                  "souls": 5, "candle": None, "in_play": [], "demons": [], "demon_hand": []})
            answer_cb(cb["id"], "Joined!")
            lsd_render(ls, [f"🙋 {cb['from'].get('first_name')} joined Let's Summon Demons."])
        elif parts == ["lsd", "roll"]:
            err = D.roll_dice(ls, idx, ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Rolled")
            if not err:
                lsd_render(ls, ev)
        elif parts == ["lsd", "end"]:
            if ls["pending"]:
                return answer_cb(cb["id"], "Resolve the pending choice first.")
            if idx is None or idx != ls["current_index"]:
                return answer_cb(cb["id"], "Not your turn.")
            if not ls["turn"]["rolled"]:
                return answer_cb(cb["id"], "Roll the dice first.")
            D.end_turn(ls, ev)
            answer_cb(cb["id"], "Turn ended")
            lsd_render(ls, ev)
        elif len(parts) == 3 and parts[1] == "buy":
            err = D.buy_card(ls, idx, ls["market"][int(parts[2])]["iid"], ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Bought")
            if not err:
                lsd_render(ls, ev)
        elif len(parts) >= 3 and parts[1] == "c":
            pend = ls.get("pending")
            if not pend or pend["player"] != idx:
                return answer_cb(cb["id"], "No choice pending for you.")
            kind = parts[2]
            if kind in ("steal_card", "alligator") and len(parts) == 5:
                choice = {"player": int(parts[3]), "iid": int(parts[4])}
            elif kind in ("steal_souls", "glen_player", "steal_player") and parts[3] != "supply":
                choice = int(parts[3])
            elif kind in ("gain_block", "activate_choice", "goat_boy", "goat_girl", "sam_animal", "rosemary", "gross_book") and parts[3].isdigit():
                choice = int(parts[3])
            else:
                choice = parts[3] if len(parts) > 3 else ""
                if kind == "replace_block" and choice != "done":
                    choice = int(choice) if choice.isdigit() else choice
            err = D.apply_choice(ls, idx, choice, ev)
            answer_cb(cb["id"], err or "Done")
            if not err:
                lsd_render(ls, ev)
        else:
            answer_cb(cb["id"], "Unknown button.")
        return
    if data.startswith("yz:"):
        yz = yahtzee_get(state, chat_id)
        if not yz:
            return answer_cb(cb["id"], "No Yahtzee game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(yz["players"]) if p["user_id"] == uid), None)
        if idx is None:
            idx = _actor_idx(yz, uid, yz["current_index"])
        ev = []
        if parts == ["yz", "join"]:
            if yz["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            yz["players"].append(Y.new_player(uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            yahtzee_render(yz, [f"🙋 {cb['from'].get('first_name')} joined Yahtzee."])
        elif parts == ["yz", "start"]:
            err = Y.start_game(yz, ev) if yz["phase"] == "lobby" else "already started"
            answer_cb(cb["id"], err or "Started")
            if not err:
                yahtzee_render(yz, ev)
        elif parts == ["yz", "roll"]:
            if idx is None:
                return answer_cb(cb["id"], "not in game")
            keep = yz["turn"]["keep"] if yz.get("turn") else None
            err = Y.roll_dice(yz, idx, keep, ev)
            answer_cb(cb["id"], err or "Rolled")
            if not err:
                yahtzee_render(yz, ev)
        elif len(parts) == 3 and parts[1] == "keep":
            if idx is None or idx != yz["current_index"]:
                return answer_cb(cb["id"], "Not your turn.")
            t = yz.get("turn")
            if not t or t["rolls"] == 0 or t["rolls"] >= Y.MAX_ROLLS:
                return answer_cb(cb["id"], "Can't keep dice now.")
            i = int(parts[2])
            t["keep"][i] = not t["keep"][i]
            answer_cb(cb["id"], "Kept" if t["keep"][i] else "Released")
            yahtzee_render(yz)
        elif len(parts) == 3 and parts[1] == "score":
            if idx is None:
                return answer_cb(cb["id"], "not in game")
            err = Y.score_category(yz, idx, parts[2], ev)
            answer_cb(cb["id"], err or "Scored")
            if not err:
                yahtzee_render(yz, ev)
        elif parts == ["yz", "rematch"]:
            ev, err = rematch_game(state, "yahtzee", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            answer_cb(cb["id"], "Unknown button.")
        return
    if data.startswith("ts:"):
        ts = tornado_get(state, chat_id)
        if not ts:
            return answer_cb(cb["id"], "No Tornado Splash game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(ts["players"]) if p["user_id"] == uid), None)
        picker = (ts["picking_order"][ts["picking_index"]]
                  if ts["phase"] == "picking" and ts["picking_order"] else None)
        if idx is None and picker is not None:
            idx = _actor_idx(ts, uid, picker)
        if idx is None and ts["turn_order"]:
            idx = _actor_idx(ts, uid, ts["turn_order"][ts["current_index"]])
        ev = []
        if parts == ["ts", "join"]:
            if ts["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            if len(ts["players"]) >= TS.MAX_PLAYERS:
                return answer_cb(cb["id"], "Game is full.")
            ts["players"].append(TS.new_player(uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            tornado_render(ts, [f"🙋 {cb['from'].get('first_name')} joined Tornado Splash."])
        elif parts in (["ts", "start"], ["ts", "gp"]):
            err = (TS.start_picking(ts, ev, gp=(parts[1] == "gp"))
                   if ts["phase"] == "lobby" else "already started")
            answer_cb(cb["id"], err or "Started")
            if not err:
                tornado_render(ts, ev)
        elif len(parts) == 3 and parts[1] == "pick":
            if idx is None:
                return answer_cb(cb["id"], "not in game")
            err = TS.pick_boat(ts, idx, int(parts[2]), ev)
            answer_cb(cb["id"], err or "Boat locked in")
            if not err:
                tornado_render(ts, ev)
        elif parts == ["ts", "auto"]:
            if idx is None:
                return answer_cb(cb["id"], "not in game")
            err = TS.auto_assign_boats(ts, ev)
            answer_cb(cb["id"], err or "Boats assigned")
            if not err:
                tornado_render(ts, ev)
        elif parts == ["ts", "hand"]:
            mine = next((i for i, p in enumerate(ts["players"])
                         if p["user_id"] == uid), None)
            if mine is None:
                return answer_cb(cb["id"], "You're not in this game.")
            p = ts["players"][mine]
            if p["boat"] is None:
                return answer_cb(cb["id"], "Pick a boat first.")
            cap = TS.max_move(ts, mine)
            capb = TS.max_move(ts, mine, boost=True)
            cards = " ".join(f"{h+1}{TS.card_str(cd)}"
                             for h, cd in enumerate(p["hand"])) or "(empty)"
            answer_cb(cb["id"],
                      f"🃏 {TS.BOATS[p['boat']]['name']} @{p['pos']}: {cards} · max {cap}"
                      + (f"/{capb}⚡" if not p["boost_used"] else "")
                      + " · /tornado_hand for details")
        elif parts == ["ts", "wait"]:
            if idx is None:
                return answer_cb(cb["id"], "not in game")
            err = TS.do_wait(ts, idx, events=ev)
            answer_cb(cb["id"], err or "Waited")
            if not err:
                tornado_render(ts, ev)
        elif parts == ["ts", "next"]:
            err = TS.next_race(ts, uid, ev)
            answer_cb(cb["id"], err or "Next race!")
            if not err:
                tornado_render(ts, ev)
        elif parts == ["ts", "rematch"]:
            ev, err = rematch_game(state, "tornado", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            answer_cb(cb["id"], "Unknown button.")
        return
    if data.startswith("ft:"):
        ft = fliptoons_get(state, chat_id)
        if not ft:
            return answer_cb(cb["id"], "No Fliptoons game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(ft["players"]) if p["user_id"] == uid), None)
        ev = []
        if parts == ["ft", "join"]:
            if ft["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            if len(ft["players"]) >= 4:
                return answer_cb(cb["id"], "Game is full.")
            ft["players"].append(_ft_player(uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            fliptoons_render(ft, [f"🙋 {cb['from'].get('first_name')} joined Fliptoons."])
        elif parts == ["ft", "start"]:
            if ft["phase"] != "lobby":
                return answer_cb(cb["id"], "Already started.")
            err = FT.start_game(ft, ev)
            answer_cb(cb["id"], err or "Started")
            if not err:
                fliptoons_render(ft, ev)
        elif parts == ["ft", "rematch"]:
            ev, err = rematch_game(state, "fliptoons", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            ref = fliptoons_actor(ft)
            if ref is None:
                return answer_cb(cb["id"], "Nothing to do right now.")
            idx = _actor_idx(ft, uid, ref)
            if idx is None:
                return answer_cb(cb["id"], "Not in this game.")
            if len(parts) == 3 and parts[1] == "hire":
                err = FT.do_market(ft, idx, "hire", int(parts[2]), ev)
            elif len(parts) == 3 and parts[1] == "dismiss":
                err = FT.do_market(ft, idx, "dismiss", int(parts[2]), ev)
            elif parts == ["ft", "skip"]:
                err = FT.do_market(ft, idx, "skip", None, ev)
            elif len(parts) >= 3 and parts[1] == "ch":
                err = FT.apply_choice(ft, idx, ":".join(parts[2:]), ev)
            else:
                return answer_cb(cb["id"], "Unknown button.")
            answer_cb(cb["id"], err or "Done")
            if not err:
                fliptoons_render(ft, ev)
        return
    if data.startswith("cc:"):
        cc = castlecombo_get(state, chat_id)
        if not cc:
            return answer_cb(cb["id"], "No Castle Combo game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(cc["players"]) if p["user_id"] == uid), None)
        ev = []
        if parts == ["cc", "join"]:
            if cc["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            if len(cc["players"]) >= CC.MAX_PLAYERS:
                return answer_cb(cb["id"], "Game is full.")
            cc["players"].append(CC.new_player(
                uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            castlecombo_render(cc, [f"🙋 {cb['from'].get('first_name')} joined Castle Combo."])
        elif parts == ["cc", "start"]:
            if cc["phase"] != "lobby":
                return answer_cb(cb["id"], "Already started.")
            err = CC.start_game(cc, ev)
            answer_cb(cb["id"], err or "Started")
            if not err:
                castlecombo_render(cc, ev)
        elif parts == ["cc", "rematch"]:
            ev, err = rematch_game(state, "castlecombo", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            ref = castlecombo_actor(cc)
            if ref is None:
                return answer_cb(cb["id"], "Nothing to do right now.")
            idx = _actor_idx(cc, uid, ref)
            if idx is None:
                return answer_cb(cb["id"], "Not in this game.")
            if len(parts) == 3 and parts[1] == "buy":
                err = CC.do_take(cc, idx, int(parts[2]), False, ev)
            elif len(parts) == 3 and parts[1] == "flip":
                err = CC.do_take(cc, idx, int(parts[2]), True, ev)
            elif parts == ["cc", "move"]:
                err = CC.do_key(cc, idx, "move", ev)
            elif parts == ["cc", "renew"]:
                err = CC.do_key(cc, idx, "renew", ev)
            elif len(parts) >= 3 and parts[1] == "ch":
                if (cc.get("pending") or {}).get("kind") == "place":
                    return answer_cb(cb["id"], "Use the Mini App to place a card.")
                err = CC.apply_choice(cc, idx, ":".join(parts[2:]), ev)
            else:
                return answer_cb(cb["id"], "Unknown button.")
            answer_cb(cb["id"], err or "Done")
            if not err:
                castlecombo_render(cc, ev)
        return
    if data.startswith("at:"):
        at = artichokes_get(state, chat_id)
        if not at:
            return answer_cb(cb["id"], "No Abandon All Artichokes game here.")
        parts = data.split(":")
        mine = next((i for i, p in enumerate(at["players"]) if p["user_id"] == uid), None)
        ev = []
        if parts == ["at", "join"]:
            if at["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if mine is not None:
                return answer_cb(cb["id"], "Already in!")
            if len(at["players"]) >= AT.MAX_PLAYERS:
                return answer_cb(cb["id"], "Game is full.")
            at["players"].append(AT.new_player(uid, cb["from"].get("first_name") or "Player"))
            answer_cb(cb["id"], "Joined!")
            artichokes_render(at, [f"🙋 {cb['from'].get('first_name')} joined Abandon All Artichokes."])
        elif parts == ["at", "start"]:
            if at["phase"] != "lobby":
                return answer_cb(cb["id"], "Already started.")
            err = AT.start_game(at, ev)
            answer_cb(cb["id"], err or "Started")
            if not err:
                artichokes_render(at, ev)
        elif parts == ["at", "rematch"]:
            ev, err = rematch_game(state, "artichokes", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            idx = artichokes_actor_idx(at, uid)
            if idx is None:
                return answer_cb(cb["id"], "Not your turn.")
            if len(parts) == 3 and parts[1] == "h":
                try:
                    err = AT.harvest(at, idx, int(parts[2]), ev)
                except ValueError:
                    err = "bad row position"
            elif parts == ["at", "skip"]:
                err = AT.skip_harvest(at, idx, ev)
            elif len(parts) == 3 and parts[1] == "p":
                try:
                    err = AT.do_play(at, idx, int(parts[2]), ev)
                except ValueError:
                    err = "bad card"
            elif parts == ["at", "end"]:
                err = AT.end_turn(at, idx, ev)
            elif len(parts) >= 3 and parts[1] == "ch":
                raw = ":".join(parts[2:])
                choice = int(raw) if re.fullmatch(r"-?\d+", raw) else raw
                err = AT.apply_choice(at, idx, choice, ev)
            else:
                return answer_cb(cb["id"], "Unknown button.")
            answer_cb(cb["id"], err or "Done")
            if not err:
                artichokes_render(at, ev)
        return
    if data.startswith("od:"):
        od = odin_get(state, chat_id)
        if not od:
            return answer_cb(cb["id"], "No Odin game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(od["players"]) if p["user_id"] == uid), None)
        if idx is None:
            _ref = od["pickup_player"] if od.get("pickup_player") is not None else od["current_index"]
            idx = _actor_idx(od, uid, _ref)
        ev = []
        if parts == ["od", "join"]:
            if od["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            od["players"].append({"user_id": uid, "name": cb["from"].get("first_name") or "Player", "hand": [], "score": O.START_SCORE})
            answer_cb(cb["id"], "Joined!")
            odin_render(od, [f"🙋 {cb['from'].get('first_name')} joined Odin."])
        elif parts == ["od", "pass"]:
            err = O.pass_turn(od, idx, ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Passed")
            if not err:
                odin_render(od, ev)
        elif len(parts) == 4 and parts[1] == "pickup":
            err = (O.choose_pickup(od, idx, {"suit": parts[2], "rank": int(parts[3])}, ev)
                   if idx is not None else "not in game")
            answer_cb(cb["id"], err or "Taken")
            if not err:
                odin_render(od, ev)
        else:
            answer_cb(cb["id"], "Unknown button.")
        return
    if data.startswith("rg:"):
        rg = rg_get(state, chat_id)
        if not rg:
            return answer_cb(cb["id"], "No Regicide game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(rg["players"]) if p["user_id"] == uid), None)
        if idx is None:
            _ref = rg.get("jester_player") if rg.get("jester_player") is not None else rg["current_index"]
            idx = _actor_idx(rg, uid, _ref)
        ev = []
        if parts == ["rg", "yield"]:
            err = R.yield_turn(rg, idx, ev) if idx is not None else "not in game"
            answer_cb(cb["id"], err or "Yielded")
            if not err:
                rg_render(rg, ev)
        elif len(parts) == 3 and parts[1] == "next":
            if rg["phase"] != "jester_next":
                return answer_cb(cb["id"], "Not after a Jester.")
            if rg.get("jester_player") != idx:
                if idx is None or not rg["players"][rg["jester_player"]].get("npc"):
                    return answer_cb(cb["id"], "Only the Jester player picks next.")
                idx = rg["jester_player"]
            err = R.jester_next(rg, int(parts[2]), ev)
            answer_cb(cb["id"], err or "Next player set")
            if not err:
                rg_render(rg, ev)
        elif parts == ["rg", "join"]:
            if rg["phase"] != "lobby":
                return answer_cb(cb["id"], "Game already started.")
            if idx is not None:
                return answer_cb(cb["id"], "Already in!")
            rg["players"].append({"user_id": uid, "name": cb["from"].get("first_name") or "Player", "hand": []})
            answer_cb(cb["id"], "Joined!")
            rg_render(rg, [f"🙋 {cb['from'].get('first_name')} joined Regicide."])
        elif parts == ["rg", "rematch"]:
            ev, err = rematch_game(state, "regicide", chat_id, uid)
            answer_cb(cb["id"], err or "Rematch!")
            if not err:
                save_state(state)
        else:
            answer_cb(cb["id"], "Unknown button.")
        return
    g = get_game(state, chat_id)
    if g:
        g["chat_type"] = cb.get("message", {}).get("chat", {}).get("type", g.get("chat_type", "private"))
    if not g:
        answer_cb(cb["id"], "No game here.")
        return
    events = []
    parts = data.split(":")

    def deny(t):
        answer_cb(cb["id"], t)

    if parts == ["f7", "join"]:
        if g["phase"] != "lobby":
            return deny("Game already started.")
        if any(p["user_id"] == uid for p in g["players"]):
            return deny("Already in!")
        g["players"].append(G.new_player(uid, cb["from"].get("first_name") or "Player"))
        events.append(f"🙋 {cb['from'].get('first_name')} joined.")
        answer_cb(cb["id"], "Joined!")
    elif parts == ["f7", "hit"] or parts == ["f7", "stay"]:
        if g["phase"] != "playing" or g["pending_action"]:
            return deny("⛔ Not your turn.")
        if g["players"][g["current_index"]]["user_id"] != uid and not g["players"][g["current_index"]].get("npc"):
            return deny(f"⛔ It's {g['players'][g['current_index']]['name']}'s turn.")
        answer_cb(cb["id"], "")
        if parts[1] == "hit":
            do_hit(g, g["current_index"], events)
            advance(g, events)
        else:
            if not do_stay(g, g["current_index"], events):
                return deny(events[0] if events else "Must Hit.")
    elif len(parts) == 3 and parts[0] == "f7" and parts[1] == "act":
        if not g["pending_action"]:
            return deny("No action pending.")
        _ch = next((p for p in g["players"] if p["user_id"] == g["pending_action"]["chooser_id"]), None)
        if g["pending_action"]["chooser_id"] != uid and not (_ch and _ch.get("npc")):
            return deny(f"⛔ {G.name_of(g, g['pending_action']['chooser_id'])} chooses.")
        target = int(parts[2])
        if target not in G.eligible_targets(g, g["pending_action"]["action"]):
            return deny("Invalid target.")
        answer_cb(cb["id"], "")
        do_action_choice(g, target, events)
    elif parts == ["f7", "next"]:
        if g["phase"] != "round_end":
            return deny("Round not over.")
        answer_cb(cb["id"], "")
        G.start_next_round(g, events)
        advance(g, events)
    elif parts == ["f7", "new"]:
        if g["phase"] != "game_end":
            return deny("Game not over.")
        answer_cb(cb["id"], "")
        keep = g["players"]
        g.clear()
        g.update(G.new_game(chat_id, keep[0]["user_id"], keep[0]["name"]))
        events.append("🔄 New game - same players! Anyone taps Start in the Mini App.")
    else:
        return deny("Unknown button.")
    render(g, events)


# ---------- HTTP API: HTML game synced to these live games ----------
# Single process serves token-authenticated Mini App API + static game on
# WEB_PORT (tunnel forwards flip7.xamin.it -> :8080). The API shares the
# exact in-memory `state` with the polling loop (STATE_LOCK), so HTML
# moves and Telegram moves can never diverge. Deck order is never exposed.
def board_json(g, viewer_id=None):
    return {
        "chat_id": g["chat_id"], "phase": g["phase"], "round": g["round"],
        "created_by": g["created_by"],
        "is_player": viewer_id is not None and any(p["user_id"] == viewer_id for p in g["players"]),
        "dealer": g["players"][g["dealer_index"]]["name"],
        "deck_count": len(g["deck"]), "current_index": g["current_index"],
        "winner_id": g["winner_id"],
        "players": [{"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")),
                     "total": p["total"], "numbers": p["numbers"],
                     "modifiers": p["modifiers"],
                     "second_chance": p["second_chance"],
                     "status": p["status"],
                     "last_round": p["last_round"],
                     "flip3_cards": p.get("flip3_cards", [])} for p in g["players"]],
        "flip3": ({"target_index": g["flip3"]["target_index"],
                   "remaining": g["flip3"]["remaining"]}
                  if g.get("flip3") else None),
        "pending_action": ({"action": g["pending_action"]["action"],
                            "chooser_id": g["pending_action"]["chooser_id"],
                            "targets": G.eligible_targets(g, g["pending_action"]["action"])}
                           if g["pending_action"] else None),
    }


def verify_init_data(init_data):
    """Telegram Mini App initData -> user_id, or None if invalid/absent.
    HMAC-SHA256(key='WebAppData'+bot_token, msg=sorted auth_date+user...)."""
    if not init_data or not TOKEN:
        return None
    try:
        pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        hash_recv = pairs.pop("hash", "")
        msg = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, hash_recv):
            return None
        return int(json.loads(pairs["user"])["id"])
    except Exception:
        return None


def init_user(init_data):
    """Verified (user_id, first_name, start_param, chat_instance) or None."""
    if not init_data or not TOKEN:
        return None
    try:
        pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if verify_init_data(init_data) is None:
            return None
        u = json.loads(pairs.get("user", "{}"))
        return (int(u["id"]), u.get("first_name") or "Player",
                pairs.get("start_param", ""), pairs.get("chat_instance", ""))
    except Exception:
        return None


def api_move(state, chat_id, user_id, action, target_index=None, name=""):
    """Same rules as text callbacks. Returns (events, error_or_None)."""
    g = state["games"].get(str(chat_id))
    if not g:
        return [], "no game in that chat"
    events = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if not any(p["user_id"] == user_id for p in g["players"]):
            g["players"].append(G.new_player(user_id, name or "Player"))
            events.append(f"🙋 {name or 'Player'} joined via HTML.")
        return events, None
    if action == "hit":
        if g["phase"] != "playing" or g["pending_action"]:
            return [], "not your turn"
        _cur = g["players"][g["current_index"]]
        if _cur["user_id"] != user_id and not _cur.get("npc"):
            return [], f"it's {_cur['name']}'s turn"
        do_hit(g, g["current_index"], events)
        advance(g, events)
    elif action == "stay":
        if g["phase"] != "playing" or g["pending_action"]:
            return [], "not your turn"
        _cur = g["players"][g["current_index"]]
        if _cur["user_id"] != user_id and not _cur.get("npc"):
            return [], f"it's {_cur['name']}'s turn"
        if not do_stay(g, g["current_index"], events):
            return [], events[0] if events else "must Hit"
    elif action == "action":
        if not g["pending_action"]:
            return [], "no action pending"
        _ch = next((p for p in g["players"] if p["user_id"] == g["pending_action"]["chooser_id"]), None)
        if g["pending_action"]["chooser_id"] != user_id and not (_ch and _ch.get("npc")):
            return [], "only the chooser picks the target"
        if target_index not in G.eligible_targets(g, g["pending_action"]["action"]):
            return [], "invalid target"
        do_action_choice(g, int(target_index), events)
    elif action == "rematch":
        ev, err = rematch_game(state, "games", chat_id, user_id)
        return ev, err
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        if len(g["players"]) < 2:
            return [], "need at least 2 players"
        events.append(f"🎮 Game started with {len(g['players'])} players! First to {G.WIN_SCORE}.")
        order = [(g["dealer_index"] + k) % len(g["players"]) for k in range(len(g["players"]))]
        g["deal_queue"] = list(order)
        g["phase"] = "dealing"
        advance(g, events)
    elif action == "next":
        if g["phase"] != "round_end":
            return [], "round not over"
        G.start_next_round(g, events)
        advance(g, events)
    else:
        return [], "unknown action"
    render(g, events)  # keep the Telegram group board in sync too
    return events, None


def rg_board_json(g, viewer_id=None):
    """Regicide board; only the viewer's own hand is included (private hands)."""
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    is_player = me is not None
    next_rank = g["castle"][-1]["rank"] if g["castle"] else None
    next_suits = sorted({c["suit"] for c in g["castle"] if c["rank"] == next_rank},
                        key="♠♥♦♣".find) if next_rank else []
    return {
        "chat_id": g["chat_id"], "phase": g["phase"], "kills": g["kills"],
        "current_index": g["current_index"], "created_by": g["created_by"],
        "is_player": is_player,
        "tavern_count": len(g["tavern"]), "castle_count": len(g["castle"]),
        "discard_count": len(g["discard"]),
        "enemy": g["enemy"], "enemy_damage": g["enemy_damage"],
        "spade_shield": g["spade_shield"], "effective_attack": R.effective_attack(g) if g["enemy"] else 0,
        "immune_off": g["immune_off"], "discard_needed": g.get("discard_needed"),
        "discard_total": g.get("discard_total"),
        "castle": [c["rank"] for c in reversed(g["castle"])],  # ranks only, next first - suits hidden
        "next_suits": next_suits,
        "played": g["played"],
        "players": [{"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")), "hand_count": len(p["hand"])}
                    for p in g["players"]],
        "my_hand": me["hand"] if me else [],
        "hand_limit": R.hand_limit(g),
    }


def rg_api_move(state, chat_id, user_id, body):
    g = rg_get(state, chat_id)
    if not g:
        return [], "no regicide game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    if action not in ("join", "start"):
        _ref = g.get("jester_player") if action == "jester_next" and g.get("jester_player") is not None else g["current_index"]
        idx = _actor_idx(g, user_id, _ref)
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= 4:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append({"user_id": user_id, "name": iu_name, "hand": []})
        ev.append("🙋 joined Regicide.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = R.start_game(g, ev)
        if err:
            return [], err
    elif idx is None:
        return [], "not in this game"
    elif action == "play":
        cards = [{"suit": c["suit"], "rank": c["rank"]} for c in body.get("cards", [])]
        removed, err = rg_take_cards(g, idx, cards)
        if err:
            return [], err
        err = R.play_cards(g, idx, removed, ev)
        if err:
            for r in removed:
                g["players"][idx]["hand"].append(r)
            return [], err
    elif action == "discard":
        cards = [{"suit": c["suit"], "rank": c["rank"]} for c in body.get("cards", [])]
        if not cards and g["players"][idx]["hand"]:
            return [], "select at least one card to discard"
        removed, err = rg_take_cards(g, idx, cards)
        if err:
            return [], err
        err = R.discard_cards(g, idx, removed, ev)
        if err:
            g["players"][idx]["hand"].extend(removed)
            return [], err
    elif action == "yield":
        err = R.yield_turn(g, idx, ev)
        if err:
            return [], err
    elif action == "jester_next":
        if g.get("jester_player") != idx:
            return [], "only the Jester player picks next"
        err = R.jester_next(g, int(body.get("target_index")), ev)
        if err:
            return [], err
    elif action == "rematch":
        ev, err = rematch_game(state, "regicide", chat_id, user_id)
        return ev, err
    else:
        return [], "unknown action"
    rg_render(g, ev)
    return ev, None


def odin_board_json(g, viewer_id=None):
    """Odin board; only the viewer's own hand is included (private hands)."""
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    return {
        "chat_id": g["chat_id"], "phase": g["phase"], "hand_no": g.get("hand_no", 0),
        "current_index": g["current_index"], "pickup_player": g.get("pickup_player"),
        "created_by": g["created_by"], "hand_starter": g.get("hand_starter", 0),
        "is_player": me is not None,
        "table": g["table"], "table_value": g.get("table_value"),
        "pending_play": g.get("pending_play", []),
        "passes": g.get("passes", 0),
        "deck_count": len(g["deck"]), "discard_count": len(g["discard"]),
        "winners": g.get("winners", []),
        "players": [{"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")),
                     "hand_count": len(p["hand"]), "score": p["score"]}
                    for p in g["players"]],
        "my_hand": me["hand"] if me else [],
    }


def odin_api_move(state, chat_id, user_id, body):
    g = odin_get(state, chat_id)
    if not g:
        return [], "no odin game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    if action not in ("join", "start"):
        _ref = g["pickup_player"] if action == "pickup" and g.get("pickup_player") is not None else g["current_index"]
        idx = _actor_idx(g, user_id, _ref)
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= 6:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append({"user_id": user_id, "name": iu_name, "hand": [], "score": O.START_SCORE})
        ev.append("🙋 joined Odin.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = O.start_game(g, ev)
        if err:
            return [], err
    elif idx is None:
        return [], "not in this game"
    elif action == "play":
        raw = body.get("cards", [])
        if not isinstance(raw, list) or any(
                not isinstance(c, dict) or c.get("suit") not in O.SUITS
                or not str(c.get("rank", "")).isdigit() for c in raw):
            return [], "bad cards"
        cards = [{"suit": c["suit"], "rank": int(c["rank"])} for c in raw]
        removed, err = odin_take_cards(g, idx, cards)
        if err:
            return [], err
        err = O.play_cards(g, idx, removed, ev)
        if err:
            g["players"][idx]["hand"].extend(removed)
            return [], err
    elif action == "pass":
        err = O.pass_turn(g, idx, ev)
        if err:
            return [], err
    elif action == "pickup":
        c = body.get("card") or {}
        if c.get("suit") not in O.SUITS or not str(c.get("rank", "")).isdigit():
            return [], "bad card"
        err = O.choose_pickup(g, idx, {"suit": c["suit"], "rank": int(c["rank"])}, ev)
        if err:
            return [], err
    elif action == "rematch":
        ev, err = rematch_game(state, "odin", chat_id, user_id)
        return ev, err
    else:
        return [], "unknown action"
    odin_render(g, ev)
    return ev, None


def leaves_board_json(g, viewer_id=None):
    return LEAVES_MODULE.board_json(g, viewer_id)


def leaves_api_move(state, chat_id, user_id, body):
    g = leaves_get(state, chat_id)
    if not g:
        return [], "no 13 leaves game in that chat"
    action = body.get("action")
    if action == "rematch":
        return rematch_game(state, "leaves", chat_id, user_id)
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if any(p["user_id"] == user_id for p in g["players"]):
            return [], None
        if len(g["players"]) >= GR.GAMES_BY_KEY["leaves"].max_players:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(LEAVES_MODULE.new_player(user_id, iu_name))
        leaves_render(g, ["🙋 joined."])
        return ["🙋 joined."], None
    if action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        ev = []
        err = LEAVES_MODULE.start_game(g, ev)
        if err:
            return [], err
        leaves_render(g, ev)
        return ev, None
    idx = _actor_idx(g, user_id, g.get("current_index", 0))
    if idx is None:
        return [], "not in this game"
    ev = []
    err = LEAVES_MODULE.apply_action(g, idx, action, body, ev)
    if err:
        return [], err
    leaves_render(g, ev)
    return ev, None

def lsd_board_json(g, viewer_id=None):
    """LSD board; Demon hands are private (only counts are public)."""
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    pend = g.get("pending")
    pend_out = None
    if pend:
        pend_out = dict(pend)
        pend_out["options_detail"] = lsd_pending_options(g)
    return {
        "chat_id": g["chat_id"], "phase": g["phase"],
        "current_index": g["current_index"], "created_by": g["created_by"],
        "is_player": me is not None,
        "market": g["market"], "supply": g["supply"],
        "dice": g.get("dice"), "last_total": g.get("last_total"),
        "turn": g.get("turn"), "pending": pend_out,
        "winner": g.get("winner"),
        "players": [{"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")), "souls": p["souls"],
                     "candle": p["candle"], "in_play": p["in_play"], "demons": p["demons"],
                     "demon_hand_count": len(p["demon_hand"])} for p in g["players"]],
        "my_demon_hand": me["demon_hand"] if me else [],
    }


def lsd_api_move(state, chat_id, user_id, body):
    g = lsd_get(state, chat_id)
    if not g:
        return [], "no summon demons game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    if action not in ("join", "start"):
        _ref = g["pending"]["player"] if g.get("pending") else g["current_index"]
        idx = _actor_idx(g, user_id, _ref)
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= 5:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append({"user_id": user_id, "name": iu_name, "souls": 5,
                             "candle": None, "in_play": [], "demons": [], "demon_hand": []})
        ev.append("🙋 joined Let's Summon Demons.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = D.start_game(g, ev)
        if err:
            return [], err
    elif idx is None:
        return [], "not in this game"
    elif action == "roll":
        err = D.roll_dice(g, idx, ev)
        if err:
            return [], err
    elif action == "buy":
        err = D.buy_card(g, idx, int(body.get("market_iid", 0)), ev)
        if err:
            return [], err
    elif action == "summon":
        sac = body.get("sacrifice") or []
        err = D.summon(g, idx, [int(x) for x in sac], int(body.get("demon_iid", 0)), ev)
        if err:
            return [], err
    elif action == "end":
        if g["pending"]:
            return [], "resolve the pending choice first"
        if idx != g["current_index"]:
            return [], "not your turn"
        if not g["turn"]["rolled"]:
            return [], "you must roll the dice first"
        D.end_turn(g, ev)
    elif action == "choice":
        err = D.apply_choice(g, idx, body.get("choice"), ev)
        if err:
            return [], err
    elif action == "rematch":
        ev, err = rematch_game(state, "lsd", chat_id, user_id)
        return ev, err
    else:
        return [], "unknown action"
    lsd_render(g, ev)
    return ev, None


def spots_board_json(g, viewer_id=None):
    """Spots board. Dogs/yards are public; is_player gates actions."""
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    pend = g.get("pending")
    pend_out = None
    if pend:
        pend_out = {"kind": pend["kind"], "player": pend["player"],
                    "options_detail": spots_pending_options(g)}
    trick = None
    if g.get("trick"):
        t = g["trick"]
        trick = {"tile": t["tile"], "dice": t.get("dice", [])}
    return {
        "chat_id": g["chat_id"], "phase": g["phase"],
        "current_index": g["current_index"], "created_by": g["created_by"],
        "is_player": me is not None,
        "tiles": g["tiles"], "dice_supply": g["dice_supply"],
        "treat_supply": g["treat_supply"], "trick": trick,
        "last_roll": g.get("last_roll"),
        "pending": pend_out, "winner": g.get("winner"),
        "players": [{"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")), "treats": p["treats"],
                     "yard": p["yard"], "dogs": p["dogs"], "scored": p["scored"]}
                    for p in g["players"]],
    }


def spots_api_move(state, chat_id, user_id, body):
    g = spots_get(state, chat_id)
    if not g:
        return [], "no spots game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    if action not in ("join", "start"):
        _ref = g["pending"]["player"] if g.get("pending") else g["current_index"]
        idx = _actor_idx(g, user_id, _ref)
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= 4:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append({"user_id": user_id, "name": iu_name, "dogs": [],
                             "scored": [], "yard": [], "treats": 1})
        ev.append("🙋 joined Spots.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = SP.start_game(g, ev)
        if err:
            return [], err
    elif action == "score":
        if idx is None:
            return [], "not in this game"
        err = SP.score_action(g, idx, ev)
        if err:
            return [], err
    elif action == "trick":
        if idx is None:
            return [], "not in this game"
        err = SP.choose_trick(g, idx, str(body.get("tile", "")), ev)
        if err:
            return [], err
    elif action == "place":
        if idx is None:
            return [], "not in this game"
        tgt = body.get("target") or []
        if not tgt:
            return [], "bad target"
        if tgt[0] == "yard":
            target = ("yard",)
        else:
            target = ("dog", int(tgt[1]), int(tgt[2]))
        err = SP.do_place(g, idx, int(body.get("die_pos", 0)), target, ev)
        if err:
            return [], err
    elif action == "reroll":
        if idx is None:
            return [], "not in this game"
        err = SP.do_reroll(g, idx, body.get("indices"), ev)
        if err:
            return [], err
    elif action == "choice":
        err = SP.apply_choice(g, idx, body.get("choice"), ev)
        if err:
            return [], err
    elif action == "rematch":
        ev, err = rematch_game(state, "spots", chat_id, user_id)
        return ev, err
    else:
        return [], "unknown action"
    spots_render(g, ev)
    return ev, None


def yahtzee_board_json(g, viewer_id=None):
    """Yahtzee board; all scorecards are public."""
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    t = g.get("turn")
    turn_out = None
    dice_scores = None
    if t:
        turn_out = {"rolls": t["rolls"], "dice": list(t["dice"]),
                    "keep": list(t["keep"]), "current_index": g["current_index"]}
        if t["dice"]:
            dice_scores = {key: Y.score_for(key, t["dice"]) for key, _ in Y.CATEGORIES}
    return {
        "chat_id": g["chat_id"], "phase": g["phase"],
        "current_index": g["current_index"], "created_by": g["created_by"],
        "is_player": me is not None,
        "turn": turn_out, "dice_scores": dice_scores,
        "winner_id": g.get("winner_id"), "winners": g.get("winners", []),
        "categories": [{"key": k, "label": lbl} for k, lbl in Y.CATEGORIES],
        "players": [{"user_id": p["user_id"], "name": p["name"], "npc": bool(p.get("npc")),
                     "scores": p["scores"], "yahtzee_bonus": p.get("yahtzee_bonus", 0),
                     "total": Y.total_score(p), "filled": Y.filled_count(p)}
                    for p in g["players"]],
    }


def _yahtzee_keep(body):
    keep = body.get("keep")
    if keep is None:
        return [False] * Y.DICE_COUNT
    if isinstance(keep, list) and all(isinstance(x, bool) for x in keep):
        return list(keep) if len(keep) == Y.DICE_COUNT else None
    if isinstance(keep, list):
        out = [False] * Y.DICE_COUNT
        for x in keep:
            try:
                i = int(x)
            except (TypeError, ValueError):
                return None
            if 0 <= i < Y.DICE_COUNT:
                out[i] = True
        return out
    return None


def yahtzee_api_move(state, chat_id, user_id, body):
    g = yahtzee_get(state, chat_id)
    if not g:
        return [], "no yahtzee game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    if action not in ("join", "start"):
        idx = _actor_idx(g, user_id, g["current_index"])
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= Y.MAX_PLAYERS:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(Y.new_player(user_id, iu_name))
        ev.append("🙋 joined Yahtzee.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = Y.start_game(g, ev)
        if err:
            return [], err
    elif action == "roll":
        if idx is None:
            return [], "not in this game"
        keep = _yahtzee_keep(body)
        if keep is None:
            return [], "bad keep selection"
        err = Y.roll_dice(g, idx, keep, ev)
        if err:
            return [], err
    elif action == "score":
        if idx is None:
            return [], "not in this game"
        err = Y.score_category(g, idx, str(body.get("category", "")), ev)
        if err:
            return [], err
    elif action == "rematch":
        ev, err = rematch_game(state, "yahtzee", chat_id, user_id)
        return ev, err
    else:
        return [], "unknown action"
    yahtzee_render(g, ev)
    return ev, None


def tornado_board_json(g, viewer_id=None):
    """Tornado Splash board; only the viewer's own hand is included."""
    me = next((p for p in g["players"] if p["user_id"] == viewer_id), None)
    my_idx = g["players"].index(me) if me else None
    c = TS.course(g)
    cur = g["turn_order"][g["current_index"]] if g["turn_order"] else None
    picker = (g["picking_order"][g["picking_index"]]
              if g["phase"] == "picking" and g["picking_order"] else None)
    return {
        "chat_id": g["chat_id"], "phase": g["phase"], "gp": g["gp"],
        "race_number": g["race_number"], "total_races": TS.total_races(g),
        "round": g["round"], "created_by": g["created_by"],
        "is_player": me is not None, "my_index": my_idx,
        "current_index": cur, "picker_index": picker,
        "picking_order": list(g["picking_order"]),
        "course": {"name": c["name"], "length": c["length"],
                   "checkpoints": [{"space": cp, "dir": d}
                                   for cp, d in c["checkpoints"]]},
        "winner_id": g.get("winner_id"), "winners": g.get("winners", []),
        "finish_order": list(g["finish_order"]),
        "rank_order": TS.compute_ranks(g),
        "boats": [{"index": i, "name": b["name"], "type": b["type"],
                   "speed": b["speed"], "handling": b["handling"],
                   "weight": b["weight"]} for i, b in enumerate(TS.BOATS)],
        "players": [{"user_id": p["user_id"], "name": p["name"],
                     "npc": bool(p.get("npc")),
                     "boat": p["boat"],
                     "boat_name": (TS.BOATS[p["boat"]]["name"]
                                   if p["boat"] is not None else None),
                     "pos": p["pos"], "finished": p["finished"],
                     "finish_rank": p["finish_rank"], "points": p["points"],
                     "boost_used": p["boost_used"],
                     "hand_count": len(p["hand"])} for p in g["players"]],
        "my_hand": [dict(card) for card in me["hand"]] if me else [],
        "my_max_move": TS.max_move(g, my_idx) if my_idx is not None else None,
        "my_boost_available": bool(my_idx is not None
                                   and not g["players"][my_idx]["boost_used"]),
        "max_players": TS.MAX_PLAYERS,
    }


def _tornado_ints(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("not a list")
    return [int(x) for x in raw]


def tornado_api_move(state, chat_id, user_id, body):
    g = tornado_get(state, chat_id)
    if not g:
        return [], "no tornado game in that chat"
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == user_id), None)
    action = body.get("action")
    if action in ("play", "wait") and idx is None and g["turn_order"]:
        idx = _actor_idx(g, user_id, g["turn_order"][g["current_index"]])
    ev = []
    if action == "join":
        if g["phase"] != "lobby":
            return [], "game already started"
        if idx is not None:
            return ev, None
        if len(g["players"]) >= TS.MAX_PLAYERS:
            return [], "full"
        iu_name = (init_user(body.get("init_data", "")) or (None, "Player"))[1]
        g["players"].append(TS.new_player(user_id, iu_name))
        ev.append("🙋 joined Tornado Splash.")
    elif action == "start":
        if g["phase"] != "lobby":
            return [], "already started"
        err = TS.start_picking(g, ev, gp=bool(body.get("gp")))
        if err:
            return [], err
    elif action == "pick":
        if idx is None:
            return [], "not in this game"
        try:
            boat = int(body.get("boat"))
        except (TypeError, ValueError):
            return [], "no such boat"
        err = TS.pick_boat(g, idx, boat, ev)
        if err:
            return [], err
    elif action == "auto":
        err = TS.auto_assign_boats(g, ev)
        if err:
            return [], err
    elif action == "play":
        if idx is None:
            return [], "not in this game"
        try:
            cards = _tornado_ints(body.get("cards"))
        except (TypeError, ValueError):
            return [], "bad card selection"
        err = TS.do_play(g, idx, cards, boost=bool(body.get("boost")), events=ev)
        if err:
            return [], err
    elif action == "wait":
        if idx is None:
            return [], "not in this game"
        try:
            disc = _tornado_ints(body.get("discard"))
        except (TypeError, ValueError):
            return [], "bad card selection"
        err = TS.do_wait(g, idx, discard=disc, events=ev)
        if err:
            return [], err
    elif action == "next":
        err = TS.next_race(g, user_id, ev)
        if err:
            return [], err
    elif action == "rematch":
        ev, err = rematch_game(state, "tornado", chat_id, user_id)
        return ev, err
    else:
        return [], "unknown action"
    tornado_render(g, ev)
    return ev, None


def start_web_server(state):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", cache="no-store"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            # Telegram WebView / browsers cache Mini App resources - force
            # revalidation so HTML/JS updates show without a hard refresh.
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_OPTIONS(self):
            self._send(204, b"")

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path in HEALTH_PATHS:
                return self._send(200, {"ok": True, "version": WEB_VER,
                                        "games": len(GR.GAME_KEYS)})
            if u.path == "/api/guide":
                key = urllib.parse.parse_qs(u.query).get("key", [""])[0]
                payload = guide_payload(key)
                return self._send(200 if payload else 404,
                                  payload or {"ok": False, "error": "unknown game"})
            if u.path in ("/", "/flip7.html"):
                return self._send(200, open(HTML_PATH, "rb").read(), "text/html")
            if u.path in GAME_JS_FILES:
                return self._send(200, open(GAME_JS_FILES[u.path], "rb").read(),
                                  "text/javascript")
            if u.path == "/castlecombo-faces.js":
                p = os.path.join(os.path.dirname(JS_PATH), "castlecombo-faces.js")
                return self._send(200, open(p, "rb").read(), "text/javascript")
            if u.path == "/castlecombo-messenger.png":
                p = os.path.join(os.path.dirname(JS_PATH), "castlecombo-messenger.png")
                return self._send(200, open(p, "rb").read(), "image/png", cache="public, max-age=86400")
            if u.path.startswith("/cc-icons/") and u.path.endswith((".png", ".woff", ".jpg")):
                p = os.path.join(os.path.dirname(JS_PATH), "cc-icons",
                                 os.path.basename(u.path))
                if os.path.exists(p):
                    ctype = ("font/woff" if u.path.endswith(".woff")
                             else "image/jpeg" if u.path.endswith(".jpg")
                             else "image/png")
                    return self._send(200, open(p, "rb").read(), ctype, cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path in ("/spots-dogs.webp", "/spots-dogs-scored.webp"):
                p = os.path.join(os.path.dirname(JS_PATH), u.path.lstrip("/"))
                return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
            if u.path == "/treat.png":
                p = os.path.join(os.path.dirname(JS_PATH), "treat.png")
                return self._send(200, open(p, "rb").read(), "image/png", cache="public, max-age=86400")
            if u.path == "/spots-dice.png":
                p = os.path.join(os.path.dirname(JS_PATH), "spots-dice.png")
                return self._send(200, open(p, "rb").read(), "image/png", cache="public, max-age=86400")
            if u.path.startswith("/spots-dice/") and u.path.endswith(".png"):
                p = os.path.join(os.path.dirname(JS_PATH), "spots_dice", os.path.basename(u.path))
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), "image/png", cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path == "/spots-yards.webp":
                p = os.path.join(os.path.dirname(JS_PATH), "spots-yards.webp")
                return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
            if u.path.startswith("/spots-tiles/") and u.path.endswith(".jpg"):
                p = os.path.join(os.path.dirname(JS_PATH), "spots_tiles", os.path.basename(u.path))
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), "image/jpeg", cache="no-store")
                return self._send(404, {"ok": False})
            if u.path.startswith("/lsd-cards/") and u.path.endswith(".jpg"):
                p = os.path.join(os.path.dirname(JS_PATH), "lsd_cards", os.path.basename(u.path))
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), "image/jpeg", cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path == "/flip7-cards.webp":
                p = os.path.join(os.path.dirname(JS_PATH), "flip7-cards.webp")
                return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
            if u.path == "/regicide-cards.webp":
                p = os.path.join(os.path.dirname(JS_PATH), "regicide-cards.webp")
                return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
            if u.path == "/odin-cards.webp":
                p = os.path.join(os.path.dirname(JS_PATH), "odin-cards.webp")
                return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
            if u.path == "/13leaves.png":
                p = os.path.join(os.path.dirname(JS_PATH), "13leaves.png")
                return self._send(200, open(p, "rb").read(), "image/png", cache="public, max-age=86400")
            if u.path.startswith("/fliptoons/") and u.path.endswith(".webp"):
                p = os.path.join(os.path.dirname(JS_PATH), "fliptoons", os.path.basename(u.path))
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path == "/castlecombo-cards.webp":
                p = os.path.join(os.path.dirname(JS_PATH), "castlecombo-cards.webp")
                return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
            if u.path in ("/toybattle-board.webp", "/toybattle-tiles.webp", "/toybattle-medals.webp",
                  "/tokaidoduo-board.webp",
                  "/altay-board.webp", "/altay-actions.webp",
                  "/altay-achievements.webp", "/altay-markers.webp",
                  "/altay-tokens.webp"):
                p = os.path.join(os.path.dirname(JS_PATH), u.path.lstrip("/"))
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), "image/webp",
                                      cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path.startswith("/tornado_cards/") and u.path.endswith((".png", ".jpg", ".jpeg")):
                _name = os.path.basename(u.path)
                _ext = os.path.splitext(_name)[1].lower()
                _ctype = "image/jpeg" if _ext in (".jpg", ".jpeg") else "image/png"
                p = os.path.join(os.path.dirname(JS_PATH), "tornado_cards", _name)
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), _ctype, cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path.startswith("/artichokes_cards/") and u.path.endswith((".jpg", ".jpeg")):
                _name = os.path.basename(u.path)
                _num = os.path.splitext(_name)[0]
                if _num.isdigit() and 0 <= int(_num) <= 16:
                    p = os.path.join(os.path.dirname(JS_PATH), "artichokes_cards", _name)
                    if os.path.exists(p):
                        return self._send(200, open(p, "rb").read(), "image/jpeg",
                                          cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path.startswith("/cards/") and u.path.endswith(".svg"):
                p = os.path.join(os.path.dirname(JS_PATH), u.path.lstrip("/"))
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), "image/svg+xml",
                                      cache="public, max-age=86400")
                return self._send(404, {"ok": False})
            if u.path == "/api/mygames":
                # No user_id entry: identity comes only from verified
                # Mini App initData; return only games you're a player in.
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [board_json(g, uid) for g in state["games"].values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/spots/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [spots_board_json(g, uid) for g in state.get("spots", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/spots/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = spots_get(state, chat_id)
                    if g and g.get("trick") and not g.get("pending"):
                        SP.advance(g, [])  # self-heal a stranded trick
                        save_state(state)
                    board = spots_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/yahtzee/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [yahtzee_board_json(g, uid) for g in state.get("yahtzee", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/yahtzee/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = yahtzee_get(state, chat_id)
                    board = yahtzee_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/tornado/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [tornado_board_json(g, uid) for g in state.get("tornado", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/tornado/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = tornado_get(state, chat_id)
                    board = tornado_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/fliptoons/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [fliptoons_board_json(g, uid) for g in state.get("fliptoons", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/fliptoons/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = fliptoons_get(state, chat_id)
                    board = fliptoons_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/castlecombo/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [castlecombo_board_json(g, uid) for g in state.get("castlecombo", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/castlecombo/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = castlecombo_get(state, chat_id)
                    board = castlecombo_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/artichokes/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [artichokes_board_json(g, uid) for g in state.get("artichokes", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/artichokes/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = artichokes_get(state, chat_id)
                    board = artichokes_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/azul/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [azul_board_json(g, uid) for g in state.get("azul", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/azul/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = azul_get(state, chat_id)
                    board = azul_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/toybattle/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [toybattle_board_json(g, uid) for g in state.get("toybattle", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/toybattle/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = toybattle_get(state, chat_id)
                    board = toybattle_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/altay/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [altay_board_json(g, uid) for g in state.get("altay", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/altay/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = altay_get(state, chat_id)
                    board = altay_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/tokaidoduo/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [tokaidoduo_board_json(g, uid) for g in state.get("tokaidoduo", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/tokaidoduo/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = tokaidoduo_get(state, chat_id)
                    board = tokaidoduo_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/lsd/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [lsd_board_json(g, uid) for g in state.get("lsd", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/lsd/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = lsd_get(state, chat_id)
                    board = lsd_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/odin/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [odin_board_json(g, uid) for g in state.get("odin", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/odin/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = odin_get(state, chat_id)
                    board = odin_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})

            if u.path == "/api/leaves/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [leaves_board_json(g, uid) for g in state.get("leaves", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/leaves/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = leaves_get(state, chat_id)
                    board = leaves_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/fellowship/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [fotr_board_json(g, uid) for g in state.get("fellowship", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/fellowship/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = fotr_get(state, chat_id)
                    board = fotr_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/regicide/mygames":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                with STATE_LOCK:
                    games = [rg_board_json(g, uid) for g in state.get("regicide", {}).values()
                             if any(p["user_id"] == uid for p in g["players"])]
                return self._send(200, {"ok": True, "games": games})
            if u.path == "/api/regicide/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = rg_get(state, chat_id)
                    board = rg_board_json(g, uid) if g else None
                return self._send(200 if board else 404, {"ok": bool(board), "game": board})
            if u.path == "/api/games":
                return self._send(410, {"ok": False, "error": "use /api/mygames with init_data"})
            if u.path == "/api/game":
                q = urllib.parse.parse_qs(u.query)
                uid = verify_init_data(q.get("init_data", [""])[0])
                if uid is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                chat_id = q.get("chat_id", [""])[0]
                with STATE_LOCK:
                    g = state["games"].get(str(chat_id))
                    board = board_json(g, uid) if g else None
                return self._send(200 if board else 404,
                                  {"ok": bool(board), "game": board})
            asset = web_assets.resolve(u.path)
            if asset:
                return self._send(200, open(asset, "rb").read(),
                                  web_assets.content_type(asset))
            return self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            if path in ("/api/spots/create", "/api/spots/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/spots/create":
                    chat_id = None
                    for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                        cand = str(cand)
                        if cand.startswith("spots"):
                            cand = cand[len("spots"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = spots_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": spots_board_json(g, uid), "created": False})
                        g = SP.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("spots", {})[str(chat_id)] = g
                        spots_render(g, [f"🐶 Spots game created by {name} via Mini App!"])
                        save_state(state)
                        board = spots_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and start_param.startswith("spots"):
                    try:
                        chat_id = int(start_param[len("spots"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = spots_api_move(state, chat_id, uid, body)
                    g = spots_get(state, chat_id)
                    board = spots_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/yahtzee/create", "/api/yahtzee/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/yahtzee/create":
                    chat_id = None
                    for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                        cand = str(cand)
                        if cand.startswith("yahtzee"):
                            cand = cand[len("yahtzee"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = yahtzee_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": yahtzee_board_json(g, uid), "created": False})
                        g = Y.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("yahtzee", {})[str(chat_id)] = g
                        yahtzee_render(g, [f"🎲 Yahtzee game created by {name} via Mini App!"])
                        save_state(state)
                        board = yahtzee_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and start_param.startswith("yahtzee"):
                    try:
                        chat_id = int(start_param[len("yahtzee"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = yahtzee_api_move(state, chat_id, uid, body)
                    g = yahtzee_get(state, chat_id)
                    board = yahtzee_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/tornado/create", "/api/tornado/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/tornado/create":
                    chat_id = None
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("tornado"):
                            cand = cand[len("tornado"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = tornado_get(state, chat_id)
                        if g and g["phase"] not in ("game_end", "race_end"):
                            return self._send(200, {"ok": True, "game": tornado_board_json(g, uid), "created": False})
                        g = TS.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("tornado", {})[str(chat_id)] = g
                        tornado_render(g, [f"🛥️ Tornado Splash game created by {name} via Mini App!"])
                        save_state(state)
                        board = tornado_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and start_param.startswith("tornado"):
                    try:
                        chat_id = int(start_param[len("tornado"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = tornado_api_move(state, chat_id, uid, body)
                    g = tornado_get(state, chat_id)
                    board = tornado_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/fliptoons/create", "/api/fliptoons/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/fliptoons/create":
                    chat_id = None
                    # Prefer the explicit chat id (startapp param / Mini App URL);
                    # chat_instance is NOT a chat id and only a last resort.
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("fliptoons"):
                            cand = cand[len("fliptoons"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = fliptoons_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": fliptoons_board_json(g, uid), "created": False})
                        g = FT.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("fliptoons", {})[str(chat_id)] = g
                        fliptoons_render(g, [f"🦋 Fliptoons game created by {name} via Mini App!"])
                        save_state(state)
                        board = fliptoons_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and start_param.startswith("fliptoons"):
                    try:
                        chat_id = int(start_param[len("fliptoons"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = fliptoons_api_move(state, chat_id, uid, body)
                    g = fliptoons_get(state, chat_id)
                    board = fliptoons_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/castlecombo/create", "/api/castlecombo/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/castlecombo/create":
                    chat_id = None
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("castlecombo"):
                            cand = cand[len("castlecombo"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = castlecombo_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": castlecombo_board_json(g, uid), "created": False})
                        g = CC.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("castlecombo", {})[str(chat_id)] = g
                        castlecombo_render(g, [f"🏰 Castle Combo game created by {name} via Mini App!"])
                        save_state(state)
                        board = castlecombo_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and start_param.startswith("castlecombo"):
                    try:
                        chat_id = int(start_param[len("castlecombo"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = castlecombo_api_move(state, chat_id, uid, body)
                    g = castlecombo_get(state, chat_id)
                    board = castlecombo_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/artichokes/create", "/api/artichokes/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/artichokes/create":
                    chat_id = None
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("artichokes"):
                            cand = cand[len("artichokes"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = artichokes_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": artichokes_board_json(g, uid), "created": False})
                        g = AT.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("artichokes", {})[str(chat_id)] = g
                        artichokes_render(g, [f"🥬 Abandon All Artichokes game created by {name} via Mini App!"])
                        save_state(state)
                        board = artichokes_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and str(start_param).startswith("artichokes"):
                    try:
                        chat_id = int(str(start_param)[len("artichokes"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = artichokes_api_move(state, chat_id, uid, body)
                    g = artichokes_get(state, chat_id)
                    board = artichokes_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/azul/create", "/api/azul/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/azul/create":
                    chat_id = None
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("azul"):
                            cand = cand[len("azul"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = azul_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": azul_board_json(g, uid), "created": False})
                        g = AZ.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("azul", {})[str(chat_id)] = g
                        azul_render(g, [f"🔷 Azul game created by {name} via Mini App!"])
                        save_state(state)
                        board = azul_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and str(start_param).startswith("azul"):
                    try:
                        chat_id = int(str(start_param)[len("azul"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = azul_api_move(state, chat_id, uid, body)
                    g = azul_get(state, chat_id)
                    board = azul_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/toybattle/create", "/api/toybattle/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/toybattle/create":
                    chat_id = None
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("toybattle"):
                            cand = cand[len("toybattle"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = toybattle_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": toybattle_board_json(g, uid), "created": False})
                        g = TB.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("toybattle", {})[str(chat_id)] = g
                        toybattle_render(g, [f"🎯 Toy Battle game created by {html.escape(name)} via Mini App!"])
                        save_state(state)
                        board = toybattle_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and str(start_param).startswith("toybattle"):
                    try:
                        chat_id = int(str(start_param)[len("toybattle"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = toybattle_api_move(state, chat_id, uid, body)
                    g = toybattle_get(state, chat_id)
                    board = toybattle_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/altay/create", "/api/altay/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/altay/create":
                    chat_id = None
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("altay"):
                            cand = cand[len("altay"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = altay_get(state, chat_id)
                        if g and g["phase"] != "over":
                            return self._send(200, {"ok": True, "game": altay_board_json(g, uid), "created": False})
                        g = AL.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("altay", {})[str(chat_id)] = g
                        altay_render(g, [f"🏜️ Altay game created by {html.escape(name)} via Mini App!"])
                        save_state(state)
                        board = altay_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and str(start_param).startswith("altay"):
                    try:
                        chat_id = int(str(start_param)[len("altay"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = altay_api_move(state, chat_id, uid, body)
                    g = altay_get(state, chat_id)
                    board = altay_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/tokaidoduo/create", "/api/tokaidoduo/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/tokaidoduo/create":
                    chat_id = None
                    for cand in (start_param, str(body.get("chat_id") or ""), chat_instance):
                        cand = str(cand)
                        if cand.startswith("tokaidoduo"):
                            cand = cand[len("tokaidoduo"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = tokaidoduo_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": tokaidoduo_board_json(g, uid), "created": False})
                        g = TD.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("tokaidoduo", {})[str(chat_id)] = g
                        tokaidoduo_render(g, [f"🗾 Tokaido Duo game created by {html.escape(name)} via Mini App!"])
                        save_state(state)
                        board = tokaidoduo_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and str(start_param).startswith("tokaidoduo"):
                    try:
                        chat_id = int(str(start_param)[len("tokaidoduo"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = tokaidoduo_api_move(state, chat_id, uid, body)
                    g = tokaidoduo_get(state, chat_id)
                    board = tokaidoduo_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/lsd/create", "/api/lsd/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/lsd/create":
                    chat_id = None
                    for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                        cand = str(cand)
                        if cand.startswith("lsd"):
                            cand = cand[len("lsd"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = lsd_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": lsd_board_json(g, uid), "created": False})
                        g = D.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("lsd", {})[str(chat_id)] = g
                        lsd_render(g, [f"😈 Let's Summon Demons created by {name} via Mini App!"])
                        save_state(state)
                        board = lsd_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and start_param.startswith("lsd"):
                    try:
                        chat_id = int(start_param[len("lsd"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = lsd_api_move(state, chat_id, uid, body)
                    g = lsd_get(state, chat_id)
                    board = lsd_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/leaves/create", "/api/leaves/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/leaves/create":
                    chat_id = None
                    for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                        cand = str(cand)
                        if cand.startswith("leaves"):
                            cand = cand[len("leaves"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = leaves_get(state, chat_id)
                        if g and g.get("phase") != "game_end":
                            return self._send(200, {"ok": True, "game": leaves_board_json(g, uid), "created": False})
                        g = LEAVES_MODULE.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("leaves", {})[str(chat_id)] = g
                        leaves_render(g, [f"🍃 13 Leaves created by {name} via Mini App!"])
                        save_state(state)
                        board = leaves_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                with STATE_LOCK:
                    events, err = leaves_api_move(state, chat_id, uid, body)
                    g = leaves_get(state, chat_id)
                    board = leaves_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/fellowship/create", "/api/fellowship/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/fellowship/create":
                    chat_id = None
                    for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                        cand = str(cand)
                        if cand.startswith("fellowship"):
                            cand = cand[len("fellowship"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = fotr_get(state, chat_id)
                        if g and g.get("phase") != "game_end":
                            return self._send(200, {"ok": True, "game": fotr_board_json(g, uid), "created": False})
                        g = FTR.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("fellowship", {})[str(chat_id)] = g
                        fotr_render(g, [f"💍 Fellowship created by {name} via Mini App!"])
                        save_state(state)
                        board = fotr_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and str(start_param).startswith("fellowship"):
                    try:
                        chat_id = int(str(start_param)[len("fellowship"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = fotr_api_move(state, chat_id, uid, body)
                    g = fotr_get(state, chat_id)
                    board = fotr_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/odin/create", "/api/odin/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/odin/create":
                    chat_id = None
                    for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                        cand = str(cand)
                        if cand.startswith("odin"):
                            cand = cand[len("odin"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = odin_get(state, chat_id)
                        if g and g["phase"] != "game_end":
                            return self._send(200, {"ok": True, "game": odin_board_json(g, uid), "created": False})
                        g = O.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("odin", {})[str(chat_id)] = g
                        odin_render(g, [f"🛡️ Odin game created by {name} via Mini App!"])
                        save_state(state)
                        board = odin_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                chat_id = body.get("chat_id")
                if not chat_id and start_param.startswith("odin"):
                    try:
                        chat_id = int(start_param[len("odin"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = odin_api_move(state, chat_id, uid, body)
                    g = odin_get(state, chat_id)
                    board = odin_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path in ("/api/regicide/create", "/api/regicide/move"):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                if path == "/api/regicide/create":
                    chat_id = None
                    for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                        cand = str(cand)
                        if cand.startswith("regicide"):
                            cand = cand[len("regicide"):]
                        try:
                            chat_id = int(cand)
                            break
                        except (TypeError, ValueError):
                            continue
                    if not chat_id:
                        return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                    with STATE_LOCK:
                        g = rg_get(state, chat_id)
                        if g and g["phase"] not in ("won", "lost"):
                            return self._send(200, {"ok": True, "game": rg_board_json(g, uid), "created": False})
                        g = R.new_game(chat_id, uid, name)
                        g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                        state.setdefault("regicide", {})[str(chat_id)] = g
                        rg_render(g, [f"⚔️ Regicide game created by {name} via Mini App!"])
                        save_state(state)
                        board = rg_board_json(g, uid)
                    return self._send(200, {"ok": True, "game": board, "created": True})
                # /api/regicide/move
                chat_id = body.get("chat_id")
                # start_param regicide<chat> also acceptable as chat reference
                if not chat_id and start_param.startswith("regicide"):
                    try:
                        chat_id = int(start_param[len("regicide"):])
                    except ValueError:
                        pass
                with STATE_LOCK:
                    events, err = rg_api_move(state, chat_id, uid, body)
                    g = rg_get(state, chat_id)
                    board = rg_board_json(g, uid) if g else None
                    save_state(state)
                return self._send(200 if not err else 400,
                                  {"ok": not err, "error": err, "events": events, "game": board})
            if path == "/api/create":
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except Exception:
                    return self._send(400, {"ok": False, "error": "bad json"})
                iu = init_user(body.get("init_data", ""))
                if iu is None:
                    return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
                uid, name, start_param, chat_instance = iu
                # Trustworthy chat: signed start_param / chat_instance first.
                chat_id = None
                for cand in (chat_instance, start_param, str(body.get("chat_id") or "")):
                    try:
                        chat_id = int(cand)
                        break
                    except (TypeError, ValueError):
                        continue
                if not chat_id:
                    return self._send(400, {"ok": False, "error": "open the Mini App from a chat (startapp link)"})
                with STATE_LOCK:
                    g = state["games"].get(str(chat_id))
                    if g and g["phase"] != "game_end":
                        return self._send(200, {"ok": True, "game": board_json(g, uid), "created": False})
                    g = G.new_game(chat_id, uid, name)
                    g["chat_type"] = "supergroup" if chat_id < 0 else "private"
                    state["games"][str(chat_id)] = g
                    events = [f"🎴 Flip 7 game created by {name} via Mini App! Friends tap Join, anyone taps Start."]
                    render(g, events)
                    save_state(state)
                    board = board_json(g, uid)
                return self._send(200, {"ok": True, "game": board, "created": True})
            if path != "/api/move":
                return self._send(404, {"ok": False, "error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except Exception:
                return self._send(400, {"ok": False, "error": "bad json"})
            verified = verify_init_data(body.get("init_data", ""))
            if verified is None:
                return self._send(403, {"ok": False, "error": "open as Telegram Mini App (init_data required)"})
            user_id = verified
            iu = init_user(body.get("init_data", ""))
            with STATE_LOCK:
                events, err = api_move(state, body.get("chat_id"), user_id,
                                       body.get("action"), body.get("target_index"),
                                       body.get("name") or (iu[1] if iu else ""))
                g = state["games"].get(str(body.get("chat_id")))
                board = board_json(g, user_id) if g else None
                save_state(state)
            return self._send(200 if not err else 400,
                              {"ok": not err, "error": err, "events": events, "game": board})

    srv = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Flip7 web/API listening on :{WEB_PORT} (synced HTML mode)", flush=True)
    return srv


def main():
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN. Create a bot: @BotFather /newbot, "
                         "or run: python3 create_bot.py  (see README.md)")
    api("deleteWebhook", drop_pending_updates=True)
    state = load_state()
    _STATE["state"] = state
    print(f"Flip7 bot polling… state={STATE_FILE} games={len(state['games'])}", flush=True)
    for g in state.get("regicide", {}).values():
        if g.get("phase") != "discard":
            continue
        idx = g.get("current_index")
        if not isinstance(idx, int) or not (0 <= idx < len(g.get("players", []))):
            continue
        if not g["players"][idx].get("hand"):
            ev = []
            R.discard_cards(g, idx, [], ev)
            rg_render(g, ev)
    for g in state.get("artichokes", {}).values():
        pend = g.get("pending")
        if not pend or pend.get("kind") != "eggplant":
            continue
        players = g.get("players", [])
        answers = {}
        for k, v in pend.get("answers", {}).items():
            if isinstance(k, int) and 0 <= k < len(players):
                need = min(2, len(players[k].get("hand", [])))
                if need and len(v) >= need:
                    answers[k] = v
        pend["answers"] = answers
        ev = []
        AT._eggplant_next(g, ev)
        artichokes_render(g, ev)
    start_web_server(state)
    # Unstick games persisted at round_end by older versions: auto-next now.
    for g in state["games"].values():
        if g["phase"] == "round_end":
            ev = []
            G.start_next_round(g, ev)
            advance(g, ev)
            render(g, ev)
    save_state(state)
    offset = None
    while True:
        try:
            r = api("getUpdates", offset=offset, timeout=30,
                    allowed_updates=json.dumps(["message", "callback_query"]))
        except Exception as e:
            print(f"poll error: {e}", file=sys.stderr)
            time.sleep(3)
            continue
        if not r.get("ok"):
            time.sleep(3)
            continue
        for u in r.get("result", []):
            offset = u["update_id"] + 1
            with STATE_LOCK:
                try:
                    if "message" in u:
                        handle_command(state, u["message"])
                    elif "callback_query" in u:
                        handle_callback(state, u["callback_query"])
                except Exception as e:
                    print(f"handler error: {e}", file=sys.stderr)
                save_state(state)


if __name__ == "__main__":
    main()
