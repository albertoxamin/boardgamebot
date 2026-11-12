#!/usr/bin/env python3
"""Flip 7 Telegram bot - group play, stdlib only, state in local JSON.

Run:  TELEGRAM_BOT_TOKEN=<token from @BotFather> python3 bot.py
Add the bot to a group, make it admin (or disable privacy via @BotFather
/setprivacy) so it reads commands, then: /games.
State file: state.json next to this script (override with FLIP7_STATE).
"""
import hashlib, hmac, html, json, os, sys, threading, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game as G
import regicide as R
import odin as O
import lsd as D
import spots as SP
import yahtzee as Y
import fliptoons as FT

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
STATE_FILE = os.environ.get("FLIP7_STATE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "state.json")
# HTML5 options (see web/ and README):
#  FLIP7_WEB_URL      https URL of web/flip7.html -> /web opens it as a Mini App
#  FLIP7_GAME_URL + FLIP7_GAME_SHORT_NAME (registered via @BotFather /newgame)
#                     -> /play sends a Telegram HTML5 Game (sendGame)
WEB_URL = os.environ.get("FLIP7_WEB_URL", "")
GAME_URL = os.environ.get("FLIP7_GAME_URL", "")
GAME_SHORT_NAME = os.environ.get("FLIP7_GAME_SHORT_NAME", "")
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "web", "flip7.html")
JS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "web", "flip7.js")
WEB_PORT = int(os.environ.get("FLIP7_WEB_PORT", "8080"))
STATE_LOCK = threading.Lock()  # polling loop + HTTP API share one state
_STATE = {"state": None}

HELP = """🎴 <b>Boardgame bot</b>
/games - list the games you can start (and what's running here)
/rules - how to play (reply to a board for that game's rules)   /cancel - reply to a board to cancel that game
/regicide - co-op Regicide (also /regicide_join /regicide_start /regicide_play /regicide_yield /regicide_discard /regicide_rules /regicide_cancel)
/odin - card-shedding Odin (also /odin_join /odin_start /odin_play /odin_pass /odin_pickup /odin_score /odin_cancel /odin_rules)
/spots - push-your-luck dog dice (also /spots_join /spots_start /spots_trick /spots_place /spots_reroll /spots_score /spots_cancel /spots_rules)
/yahtzee - dice scorecard classic (also /yahtzee_join /yahtzee_start /yahtzee_roll /yahtzee_score /yahtzee_cancel /yahtzee_rules)
/fliptoons - grid-building card market (also /fliptoons_join /fliptoons_start /fliptoons_hire /fliptoons_dismiss /fliptoons_skip /fliptoons_choose /fliptoons_cancel /fliptoons_rules)
/games - list the games you can start (and what's running here)
🤖 /join_npc (or /<game>_join_npc) - add a mock player anyone can control, in the lobby
/lsd - dice game Let's Summon Demons (also /lsd_join /lsd_start /lsd_roll /lsd_buy /lsd_summon /lsd_end /lsd_score /lsd_cancel /lsd_rules)
Play: on your turn tap <b>Hit</b> to flip a card or <b>Stay</b> to bank.
Duplicate number = bust (0 pts). 7 unique numbers = Flip 7 (+15), round ends.
First to 200 wins. Cards are face-up/public, just like the physical game."""

RULES = """<b>Flip 7 rules</b> (deck 94: numbers 0×1,1×1,2×2…12×12; +2/+4/+6/+8/+10/x2; 3× Freeze, Flip Three, Second Chance)
• Dealer deals 1 face-up to each (actions resolved as dealt). Then in turn order: <b>Hit</b> or <b>Stay</b> (Stay needs ≥1 card, banks and sits out).
• 2nd card with same number = <b>bust</b>, 0 pts. Modifiers/actions can't bust.
• <b>7 unique numbers = Flip 7</b>: round ends at once, +15 bonus.
• Score: sum numbers → x2 doubles numbers only → add +modifiers → +15 Flip 7. Bust = 0.
• <b>Freeze</b>: chosen active player banks &amp; leaves. <b>Flip Three</b>: chosen player flips next 3 (stops on bust/Flip 7; Second Chance usable, Freeze/Flip Three deferred). <b>Second Chance</b>: keep 1; saves you from one duplicate.
• Round ends when all stayed/busted/frozen or someone Flip 7s. Round cards are set aside, dealer rotates; reshuffle discards only when deck empties.
• First to <b>200</b> (unique highest; tie = extra rounds) wins."""


# ---------- Telegram API (stdlib) ----------
def api(method, **params):
    if not API:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN (create a bot with @BotFather or python3 create_bot.py)")
    data = json.dumps(params).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"Telegram {method} HTTP {e.code}: {e.read()[:300]}", file=sys.stderr)
        return {"ok": False}


def send(chat_id, text, kb=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb:
        p["reply_markup"] = {"inline_keyboard": kb}
    return api("sendMessage", **p)


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
    label = {"regicide": "🎮 Play Regicide (HTML)", "odin": "🎮 Play Odin (HTML)", "lsd": "🎮 Play Summon Demons (HTML)", "spots": "🎮 Play Spots (HTML)", "yahtzee": "🎮 Play Yahtzee (HTML)", "fliptoons": "🎮 Play Fliptoons (HTML)"}.get(game, "🎮 Play Flip 7 (HTML)")
    if chat_type in ("group", "supergroup", "channel"):
        if chat_id:
            start = f"{game}{chat_id}" if game in ("regicide", "odin", "lsd", "spots", "yahtzee", "fliptoons") else str(chat_id)
            url = f"https://t.me/flip7groupbot?startapp={start}"
        else:
            url = WEB_URL
        btn = {"text": label, "url": url}
    else:
        url = WEB_URL + (f"?app={game}" if game in ("regicide", "odin", "lsd", "spots", "yahtzee", "fliptoons") else "")
        btn = {"text": label, "web_app": {"url": url}}
    return [[btn]]


# ---------- State ----------
def load_state():
    s = {"games": {}, "regicide": {}, "odin": {}, "lsd": {}, "spots": {}, "yahtzee": {}, "fliptoons": {}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                s.update(json.load(f))
        except Exception:
            pass
    s.setdefault("games", {})
    s.setdefault("regicide", {})  # migrate old state files
    s.setdefault("odin", {})
    s.setdefault("lsd", {})
    s.setdefault("spots", {})
    s.setdefault("yahtzee", {})
    s.setdefault("fliptoons", {})
    return s


def save_state(state):
    import shutil
    if os.path.exists(STATE_FILE):
        shutil.copy2(STATE_FILE, STATE_FILE + ".bak")  # last-good backup
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


NPC_ID = -1  # sentinel Telegram user_id for the mock NPC player


def _npc_player():
    return {"user_id": NPC_ID, "name": "🤖 NPC", "npc": True}


def _actor_idx(g, user_id, ref):
    """Index to act as: your own, or the reference player's if it is the
    NPC (anyone may control the NPC)."""
    if g["players"][ref].get("npc"):
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
                f"Join via the Mini App button, then anyone taps Start there. "
                f"(Official game: 3+ players, first to 200.)")
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
        r = send(chat_id, "\n".join(lines) + "\n\n" + text, kb)
        if r.get("ok"):
            old = g.get("board_message_id")
            g["board_message_id"] = r["result"]["message_id"]
            if old:
                api("deleteMessage", chat_id=chat_id, message_id=old)
        return
    if g.get("board_message_id"):
        r = edit(chat_id, g["board_message_id"], text, kb)
        if r.get("ok"):
            return
    r = send(chat_id, text, kb)
    if r.get("ok"):
        g["board_message_id"] = r["result"]["message_id"]


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
    r = send(chat_id, text, kb)
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
            g = R.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("regicide", {})[str(chat_id)] = g
            send(chat_id, "⚔️ Regicide game created! Friends: /regicide_join, anyone: /regicide_start")
            rg_render(g)
        else:
            rg_render(g)
        return True
    if not g:
        send(chat_id, "No Regicide game here yet - send /regicide to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/regicide_join_npc":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p.get("npc") for p in g["players"]):
            send(chat_id, "🤖 NPC is already in this game.")
        elif len(g["players"]) >= 4:
            send(chat_id, "⛔ Regicide is 2-4 players (full).")
        else:
            g["players"].append({**_npc_player(), "hand": []})
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
ODIN_RULES = """🛡️ <b>Odin rules</b> (Helvetiq, 2-6 players): shed your hand fastest, fewest points wins.
Deck 54 = numbers 1-9 in 6 colours (blue/red/pink/green/black/orange); with 2 players 2 colours are removed. Deal 9 each.
• <b>Lead</b> a round with 1 card — or all your hand if it is a single colour/number (that ends the hand).
• <b>Respond</b> with the same number of cards as the table, or one more, as a same-colour or same-number set. The set's digits sorted high→low form its number (6+3 blue = 63) and must beat the table.
• After playing (unless you go out), <b>take 1 card</b> from the previous set; the rest are discarded.
• <b>Pass</b> any time (you can play again next turn). When everyone else has passed, the table is discarded and the last player leads a new round.
• Going out ends the hand immediately (no pickup). Everyone else scores 1 per card left in hand. First to 15+ points ends the game — lowest score wins.
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
        return f"🏆 <b>Odin game over</b> - fewest points wins: <b>{html.escape(w)}</b>\nScores: {scores}"
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
        return [[{"text": "🙋 Join Odin", "callback_data": "od:join"}]] + (wk or [])
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
    r = send(chat_id, text, kb)
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
            g = O.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("odin", {})[str(chat_id)] = g
            send(chat_id, "🛡️ Odin game created! Friends: /odin_join, anyone: /odin_start")
            odin_render(g)
        else:
            odin_render(g)
        return True
    if not g:
        send(chat_id, "No Odin game here yet - send /odin to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/odin_join_npc":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p.get("npc") for p in g["players"]):
            send(chat_id, "🤖 NPC is already in this game.")
        elif len(g["players"]) >= 6:
            send(chat_id, "⛔ Odin is 2-6 players (full).")
        else:
            g["players"].append({**_npc_player(), "hand": [], "score": 0})
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
            g["players"].append({"user_id": uid, "name": msg.get("from", {}).get("first_name") or "Player", "hand": [], "score": 0})
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
        return [[{"text": "🙋 Join Summon Demons", "callback_data": "lsd:join"}]] + (wk or [])
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
    r = send(chat_id, text, kb)
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
            g = D.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("lsd", {})[str(chat_id)] = g
            send(chat_id, "😈 Let's Summon Demons game created! Friends: /lsd_join, anyone: /lsd_start")
            lsd_render(g)
        else:
            lsd_render(g)
        return True
    if not g:
        send(chat_id, "No Summon Demons game here yet - send /lsd to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/lsd_join_npc":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p.get("npc") for p in g["players"]):
            send(chat_id, "🤖 NPC is already in this game.")
        elif len(g["players"]) >= 5:
            send(chat_id, "⛔ Let's Summon Demons is 2-5 players (full).")
        else:
            g["players"].append({**_npc_player(), "souls": 5, "candle": None,
                                 "in_play": [], "demons": [], "demon_hand": []})
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
        return [[{"text": "🙋 Join Spots", "callback_data": "spots:join"}]] + (wk or [])
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
    r = send(chat_id, text, kb)
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
            g = SP.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("spots", {})[str(chat_id)] = g
            send(chat_id, "🐶 Spots game created! Friends: /spots_join, anyone: /spots_start")
            spots_render(g)
        else:
            spots_render(g)
        return True
    if not g:
        send(chat_id, "No Spots game here yet - send /spots to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/spots_join_npc":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p.get("npc") for p in g["players"]):
            send(chat_id, "🤖 NPC is already in this game.")
        elif len(g["players"]) >= 4:
            send(chat_id, "⛔ Spots is 1-4 players (full).")
        else:
            g["players"].append({**_npc_player(), "dogs": [], "scored": [], "yard": [], "treats": 1})
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
        return [[{"text": "🙋 Join Yahtzee", "callback_data": "yz:join"}]] + (wk or [])
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
    r = send(chat_id, text, kb)
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
            g = Y.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("yahtzee", {})[str(chat_id)] = g
            send(chat_id, "🎲 Yahtzee game created! Friends: /yahtzee_join, anyone: /yahtzee_start")
            yahtzee_render(g)
        else:
            yahtzee_render(g)
        return True
    if not g:
        send(chat_id, "No Yahtzee game here yet - send /yahtzee to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/yahtzee_join_npc":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p.get("npc") for p in g["players"]):
            send(chat_id, "🤖 NPC is already in this game.")
        elif len(g["players"]) >= Y.MAX_PLAYERS:
            send(chat_id, f"⛔ Yahtzee is 2-{Y.MAX_PLAYERS} players (full).")
        else:
            g["players"].append({**_npc_player(), **Y.new_player(NPC_ID, "🤖 NPC")})
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
        return [[{"text": "🙋 Join Fliptoons", "callback_data": "ft:join"}]] + (wk or [])
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
    r = send(chat_id, text, kb)
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
            g = FT.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("fliptoons", {})[str(chat_id)] = g
            send(chat_id, "🦋 Fliptoons game created! Friends: /fliptoons_join, "
                          "anyone: /fliptoons_start")
            fliptoons_render(g)
        else:
            fliptoons_render(g)
        return True
    if not g:
        send(chat_id, "No Fliptoons game here yet - send /fliptoons to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/fliptoons_join_npc":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p.get("npc") for p in g["players"]):
            send(chat_id, "🤖 NPC is already in this game.")
        elif len(g["players"]) >= 4:
            send(chat_id, "⛔ Fliptoons is 2-4 players (full).")
        else:
            p = _ft_player(NPC_ID, "🤖 NPC")
            p["npc"] = True
            g["players"].append(p)
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


REMATCH_END_PHASES = {"games": ("game_end",), "regicide": ("won", "lost"),
                     "odin": ("game_end",), "lsd": ("game_end",), "spots": ("game_end",),
                     "yahtzee": ("game_end",), "fliptoons": ("game_end",)}


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
    keep = [(p["user_id"], p["name"], bool(p.get("npc"))) for p in g["players"]]
    creator = next((k for k in keep if k[0] != NPC_ID), keep[0])
    makers = {
        "games": lambda u, n: G.new_player(u, n),
        "regicide": lambda u, n: {"user_id": u, "name": n, "hand": []},
        "odin": lambda u, n: {"user_id": u, "name": n, "hand": [], "score": 0},
        "lsd": lambda u, n: {"user_id": u, "name": n, "souls": 5, "candle": None,
                             "in_play": [], "demons": [], "demon_hand": []},
        "spots": lambda u, n: {"user_id": u, "name": n, "dogs": [], "scored": [],
                               "yard": [], "treats": 1},
        "yahtzee": lambda u, n: Y.new_player(u, n),
        "fliptoons": lambda u, n: _ft_player(u, n),
    }
    news = {"games": G.new_game, "regicide": R.new_game, "odin": O.new_game,
            "lsd": D.new_game, "spots": SP.new_game, "yahtzee": Y.new_game,
            "fliptoons": FT.new_game}
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
    {"games": render, "regicide": rg_render, "odin": odin_render,
     "lsd": lsd_render, "spots": spots_render, "yahtzee": yahtzee_render,
     "fliptoons": fliptoons_render}[key](g, ev)
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
        _catalog = (
            ("games", "🎴 Flip 7", "/games (Mini App button)", "join via the Mini App", "press-your-luck dice, first to 200"),
            ("regicide", "⚔️ Regicide", "/regicide", "/regicide_join", "co-op vs 12 royals, private hands"),
            ("odin", "🛡️ Odin", "/odin", "/odin_join", "card shedding, fewest points wins"),
            ("lsd", "😈 Let's Summon Demons", "/lsd", "/lsd_join", "dice activations, 3 demons + 10 souls"),
            ("spots", "🐶 Spots", "/spots", "/spots_join", "dog dice push-your-luck, 6 scored wins"),
            ("yahtzee", "🎲 Yahtzee", "/yahtzee", "/yahtzee_join", "dice scorecard, 13 boxes"),
            ("fliptoons", "🦋 Fliptoons", "/fliptoons", "/fliptoons_join", "grid-building card market, first to 30 fame"),
        )
        lines = ["🎮 <b>Games you can start:</b>"]
        for _key, _name, _new, _join, _desc in _catalog:
            _g = state.get(_key, {}).get(str(chat_id))
            if _g is None:
                _st = "not started here"
            elif _g["phase"] == "lobby":
                _st = f"lobby ({len(_g['players'])} in) - {_join}"
            elif _g["phase"] in ("game_end", "won", "lost"):
                _st = "finished - start a new one"
            else:
                _st = "in progress"
            lines.append(f"• {_name} — {_new} ({_desc}) · {_st}")
        lines.append("🤖 Add a mock player anyone can control: /join_npc (Flip 7) or /regicide_join_npc, /odin_join_npc, /lsd_join_npc, /spots_join_npc, /yahtzee_join_npc, /fliptoons_join_npc")
        send(chat_id, "\n".join(lines))
        return
    if cmd == "/cancel" and msg.get("reply_to_message"):
        # Reply-targeted cancel: cancels the one game whose board message
        # was replied to (searches every game type in this chat).
        _mid = msg["reply_to_message"].get("message_id")
        for _key in ("games", "regicide", "odin", "lsd", "spots", "yahtzee", "fliptoons"):
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
        _by_key = (("games", RULES), ("regicide", REGICIDE_RULES), ("odin", ODIN_RULES),
                   ("lsd", LSD_RULES), ("spots", SPOTS_RULES), ("yahtzee", YAHTZEE_RULES),
                   ("fliptoons", FLIPTOONS_RULES))
        if _mid:
            for _key, _rules in _by_key:
                _gg = state.get(_key, {}).get(str(chat_id))
                if _gg is not None and _gg.get("board_message_id") == _mid:
                    send(chat_id, _rules)
                    return
        _present = [_rules for _key, _rules in _by_key if state.get(_key, {}).get(str(chat_id))]
        send(chat_id, "\n\n".join(_present) if _present else RULES)
        return
    if not g:
        send(chat_id, "No Flip 7 game here yet - open the Mini App via the /games list or a game board button. /rules for how to play.")
        return
    if cmd in ("/join_npc", "/npc_join"):
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p.get("npc") for p in g["players"]):
            send(chat_id, "🤖 NPC is already in this game.")
        elif len(g["players"]) >= 6:
            send(chat_id, "⛔ Game is full.")
        else:
            _npc = G.new_player(NPC_ID, "🤖 NPC")
            _npc["npc"] = True
            g["players"].append(_npc)
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
            od["players"].append({"user_id": uid, "name": cb["from"].get("first_name") or "Player", "hand": [], "score": 0})
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
        if not cards:
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
        g["players"].append({"user_id": user_id, "name": iu_name, "hand": [], "score": 0})
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
            if u.path in ("/", "/flip7.html"):
                return self._send(200, open(HTML_PATH, "rb").read(), "text/html")
            if u.path == "/flip7.js":
                return self._send(200, open(JS_PATH, "rb").read(), "text/javascript")
            if u.path == "/regicide.js":
                p = os.path.join(os.path.dirname(JS_PATH), "regicide.js")
                return self._send(200, open(p, "rb").read(), "text/javascript")
            if u.path == "/odin.js":
                p = os.path.join(os.path.dirname(JS_PATH), "odin.js")
                return self._send(200, open(p, "rb").read(), "text/javascript")
            if u.path == "/lsd.js":
                p = os.path.join(os.path.dirname(JS_PATH), "lsd.js")
                return self._send(200, open(p, "rb").read(), "text/javascript")
            if u.path == "/spots.js":
                p = os.path.join(os.path.dirname(JS_PATH), "spots.js")
                return self._send(200, open(p, "rb").read(), "text/javascript")
            if u.path == "/yahtzee.js":
                p = os.path.join(os.path.dirname(JS_PATH), "yahtzee.js")
                return self._send(200, open(p, "rb").read(), "text/javascript")
            if u.path == "/fliptoons.js":
                p = os.path.join(os.path.dirname(JS_PATH), "fliptoons.js")
                return self._send(200, open(p, "rb").read(), "text/javascript")
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
            if u.path.startswith("/fliptoons/") and u.path.endswith(".webp"):
                p = os.path.join(os.path.dirname(JS_PATH), "fliptoons", os.path.basename(u.path))
                if os.path.exists(p):
                    return self._send(200, open(p, "rb").read(), "image/webp", cache="public, max-age=86400")
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
