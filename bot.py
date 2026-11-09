#!/usr/bin/env python3
"""Flip 7 Telegram bot - group play, stdlib only, state in local JSON.

Run:  TELEGRAM_BOT_TOKEN=<token from @BotFather> python3 bot.py
Add the bot to a group, make it admin (or disable privacy via @BotFather
/setprivacy) so it reads commands, then: /newgame, /join, /startgame.
State file: state.json next to this script (override with FLIP7_STATE).
"""
import hashlib, hmac, html, json, os, sys, threading, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game as G
import regicide as R
import odin as O
import lsd as D

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
/newgame - create a game (you join automatically)
/join - join the lobby   /leave - leave lobby
/startgame - anyone starts (needs 2+; official game is 3+ players)
/hit /stay - same as the buttons, only on your turn
/next - next round (when round is over)
/web - play the HTML5 version (Mini App if FLIP7_WEB_URL set, else file)
/play - play via Telegram HTML5 Game (sendGame) or the HTML file
/score - show board &amp; scores   /rules - how to play   /cancel - creator cancels
/regicide - co-op Regicide (also: -join -start -play <cards> -yield -discard <cards> -rules -cancel)
/odin - card-shedding Odin (also: -join -start -play <cards> -pass -pickup <card> -score -cancel -rules)
/lsd - dice game Let's Summon Demons (also: -join -start -roll -buy <n> -summon <demon> <sacrifices> -end -score -cancel -rules)
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
    label = {"regicide": "🎮 Play Regicide (HTML)", "odin": "🎮 Play Odin (HTML)", "lsd": "🎮 Play Summon Demons (HTML)"}.get(game, "🎮 Play Flip 7 (HTML)")
    if chat_type in ("group", "supergroup", "channel"):
        if chat_id:
            start = f"{game}{chat_id}" if game in ("regicide", "odin", "lsd") else str(chat_id)
            url = f"https://t.me/flip7groupbot?startapp={start}"
        else:
            url = WEB_URL
        btn = {"text": label, "url": url}
    else:
        url = WEB_URL + (f"?app={game}" if game in ("regicide", "odin", "lsd") else "")
        btn = {"text": label, "web_app": {"url": url}}
    return [[btn]]


# ---------- State ----------
def load_state():
    s = {"games": {}, "regicide": {}, "odin": {}, "lsd": {}}
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
    return s


def save_state(state):
    import shutil
    if os.path.exists(STATE_FILE):
        shutil.copy2(STATE_FILE, STATE_FILE + ".bak")  # last-good backup
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


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
        return f"❓ {mention(g, uid)} - choose who gets <b>{g['pending_action']['action']}</b>"
    if g["phase"] == "playing":
        p = g["players"][g["current_index"]]
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
                f"Tap Join, then anyone sends /startgame. "
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
Win: defeat last King. Hands are private - only played cards are public (/regicide-play reveals only the played card)."""


def rg_get(state, chat_id):
    return state.setdefault("regicide", {}).get(str(chat_id))


def rg_board_text(g):
    if g["phase"] == "lobby":
        names = ", ".join(html.escape(p["name"]) for p in g["players"])
        return (f"⚔️ <b>Regicide lobby</b> - {len(g['players'])}/4 players: {names}\n"
                f"Anyone: /regicide-join, /regicide-start (needs 2+)")
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
        ping = f"👉 {mention_rg(g, p['user_id'])} - your turn"
        if g["phase"] == "discard":
            ping += f" (discard ≥{g.get('discard_needed', 0)}, done {g.get('discard_total', 0)})"
    if g["phase"] == "jester_next" and g.get("jester_player") is not None:
        ping = f"🎯 {mention_rg(g, g['players'][g['jester_player']]['user_id'])} - pick who goes next"
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
    if cmd == "/regicide-rules":
        send(chat_id, REGICIDE_RULES)
        return True
    if cmd == "/regicide":
        if not g:
            g = R.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("regicide", {})[str(chat_id)] = g
            send(chat_id, "⚔️ Regicide game created! Friends: /regicide-join, anyone: /regicide-start")
            rg_render(g)
        else:
            rg_render(g)
        return True
    if not g:
        send(chat_id, "No Regicide game here yet - send /regicide to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/regicide-join":
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
    if cmd == "/regicide-start":
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
    if cmd == "/regicide-cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["regicide"][str(chat_id)]
            send(chat_id, "🗑 Regicide game cancelled.")
        return True
    if cmd in ("/regicide-play", "/regicide-discard", "/regicide-yield", "/regicide-score"):
        idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
        if idx is None:
            send(chat_id, "⛔ You're not in this Regicide game - /regicide-join in lobby.")
            return True
        ev = []
        if cmd == "/regicide-score":
            rg_render(g, ["📊 Regicide board:"])
            return True
        if cmd == "/regicide-yield":
            err = R.yield_turn(g, idx, ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                rg_render(g, ev)
            return True
        parts = text.split()[1:]
        if not parts:
            send(chat_id, "Usage: /regicide-play 7h  (or 10s, A♠, joker) - played card becomes public; use Mini App for private selection.")
            return True
        cards = [parse_card(t) for t in parts]
        if any(c is None for c in cards):
            send(chat_id, "⛔ Bad card notation - use e.g. 7h, 10s, A♠, joker.")
            return True
        removed, err = rg_take_cards(g, idx, cards)
        if err:
            send(chat_id, f"⛔ {err}")
            return True
        if cmd == "/regicide-play":
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
                f"Friends: /odin-join, anyone: /odin-start")
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
        ping = f"👉 {odin_mention(g, p['user_id'])} - " + (
            "take 1 card from the previous set" if g["phase"] == "pickup" else "your turn")
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
    if cmd == "/odin-rules":
        send(chat_id, ODIN_RULES)
        return True
    if cmd == "/odin":
        if not g:
            g = O.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("odin", {})[str(chat_id)] = g
            send(chat_id, "🛡️ Odin game created! Friends: /odin-join, anyone: /odin-start")
            odin_render(g)
        else:
            odin_render(g)
        return True
    if not g:
        send(chat_id, "No Odin game here yet - send /odin to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/odin-join":
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
    if cmd == "/odin-start":
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
    if cmd == "/odin-cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["odin"][str(chat_id)]
            send(chat_id, "🗑 Odin game cancelled.")
        return True
    if cmd == "/odin-score":
        odin_render(g)
        return True
    if cmd == "/odin-pass":
        idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
        if idx is None:
            send(chat_id, "⛔ You're not in this Odin game - /odin-join in lobby.")
            return True
        ev = []
        err = O.pass_turn(g, idx, ev)
        if err:
            send(chat_id, f"⛔ {err}")
        else:
            odin_render(g, ev)
        return True
    if cmd in ("/odin-play", "/odin-pickup"):
        idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
        if idx is None:
            send(chat_id, "⛔ You're not in this Odin game - /odin-join in lobby.")
            return True
        parts = text.split()[1:]
        if cmd == "/odin-pickup":
            if len(parts) != 1 or parse_odin_card(parts[0]) is None:
                send(chat_id, "Usage: /odin-pickup 6b  (or tap a Take button)")
                return True
            ev = []
            err = O.choose_pickup(g, idx, parse_odin_card(parts[0]), ev)
            if err:
                send(chat_id, f"⛔ {err}")
            else:
                odin_render(g, ev)
            return True
        if not parts:
            send(chat_id, "Usage: /odin-play 6b 3b  (cards you play; notation: number+colour letter, e.g. 6b = 6 blue)")
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
                f"Friends: /lsd-join, anyone: /lsd-start")
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
            ping = f"👉 {lsd_mention(g, g['players'][who]['user_id'])} - make the choice shown below"
        else:
            who = g["current_index"]
            ping = f"👉 {lsd_mention(g, g['players'][who]['user_id'])} - your turn (roll, buy, summon, end)"
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
    if cmd == "/lsd-rules":
        send(chat_id, LSD_RULES)
        return True
    if cmd == "/lsd":
        if not g:
            g = D.new_game(chat_id, uid, msg.get("from", {}).get("first_name") or "Player")
            g["chat_type"] = msg.get("chat", {}).get("type", "private")
            state.setdefault("lsd", {})[str(chat_id)] = g
            send(chat_id, "😈 Let's Summon Demons game created! Friends: /lsd-join, anyone: /lsd-start")
            lsd_render(g)
        else:
            lsd_render(g)
        return True
    if not g:
        send(chat_id, "No Summon Demons game here yet - send /lsd to create one.")
        return True
    g["chat_type"] = g.get("chat_type") or msg.get("chat", {}).get("type", "private")
    if cmd == "/lsd-join":
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
    if cmd == "/lsd-start":
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
    if cmd == "/lsd-cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["lsd"][str(chat_id)]
            send(chat_id, "🗑 Summon Demons game cancelled.")
        return True
    if cmd == "/lsd-score":
        lsd_render(g)
        return True
    idx = next((i for i, p in enumerate(g["players"]) if p["user_id"] == uid), None)
    if idx is None:
        send(chat_id, "⛔ You're not in this game - /lsd-join in lobby.")
        return True
    ev = []
    if cmd == "/lsd-roll":
        err = D.roll_dice(g, idx, ev)
    elif cmd == "/lsd-end":
        if g["pending"]:
            err = "resolve the pending choice first"
        elif not g["turn"]["rolled"]:
            err = "you must roll the dice first"
        else:
            D.end_turn(g, ev)
            err = None
    elif cmd.startswith("/lsd-buy"):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit() or not (1 <= int(parts[1]) <= len(g["market"])):
            send(chat_id, "Usage: /lsd-buy <1-5> (market position)")
            return True
        err = D.buy_card(g, idx, g["market"][int(parts[1]) - 1]["iid"], ev)
    elif cmd == "/lsd-summon":
        parts = text.split()[1:]
        if len(parts) < 2:
            send(chat_id, "Usage: /lsd-summon <demon-slug> <sacrifice-slugs...> e.g. /lsd-summon porkus adam eve jane")
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
    cmd = raw_cmd.split("@")[0].lower()
    g = get_game(state, chat_id)
    if g:
        g["chat_type"] = msg.get("chat", {}).get("type", g.get("chat_type", "private"))

    if cmd.startswith("/regicide"):
        handle_regicide(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/odin"):
        handle_odin(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/lsd"):
        handle_lsd(state, msg, cmd, text, uid, name)
        return
    if cmd.startswith("/lsd"):
        handle_lsd(state, msg, cmd, text, uid, name)
        return
    if cmd in ("/start", "/help", "/commands"):
        send(chat_id, HELP)
        return
    if cmd == "/myid":
        send(chat_id, f"Your Telegram user_id is <code>{uid}</code> (for debugging; the HTML Mini App logs you in automatically).")
        return
    if cmd == "/rules":
        send(chat_id, RULES)
        return
    if cmd in ("/web", "/html"):
        if WEB_URL:
            send(chat_id, "🎮 Tap below to play Flip 7 (HTML):",
                 web_keyboard(msg.get("chat", {}).get("type", "private"), chat_id))
        elif os.path.exists(HTML_PATH):
            r = send_document(chat_id, HTML_PATH,
                              "🎴 Flip 7 HTML5 game - open in a browser (hot-seat, 2+ players, first to 200).")
            if not r.get("ok"):
                send(chat_id, "Couldn't send the HTML file - ask the host to serve web/flip7.html.")
        else:
            send(chat_id, "HTML game not found on server (web/flip7.html missing).")
        return
    if cmd == "/play":
        if GAME_SHORT_NAME and GAME_URL:
            r = api("sendGame", chat_id=chat_id, game_short_name=GAME_SHORT_NAME)
            if not r.get("ok"):
                send(chat_id, "sendGame failed - is the game registered in @BotFather (/newgame) and FLIP7_GAME_URL set?")
        elif WEB_URL:
            send(chat_id, "🎮 Tap below to play Flip 7 (HTML):",
                 web_keyboard(msg.get("chat", {}).get("type", "private"), chat_id))
        elif os.path.exists(HTML_PATH):
            send_document(chat_id, HTML_PATH,
                          "🎴 Flip 7 HTML5 game - open in a browser to play.")
        else:
            send(chat_id, "No HTML game configured - set FLIP7_WEB_URL or FLIP7_GAME_URL/FLIP7_GAME_SHORT_NAME.")
        return
    if cmd in ("/newgame", "/flip7", "/new"):
        if g and g["phase"] != "game_end":
            send(chat_id, "⚠️ Game already in progress here - /score to see it, /cancel (creator) to abort.")
            return
        g = G.new_game(chat_id, uid, user.get("first_name") or "Player")
        g["chat_type"] = msg.get("chat", {}).get("type", "private")
        state["games"][str(chat_id)] = g
        send(chat_id, f"🎴 Flip 7 game created by <b>{name}</b>! Tap Join or send /join.")
        render(g)
        return
    if not g:
        send(chat_id, "No game here yet - send /newgame to create one. /rules for how to play.")
        return
    if cmd == "/join":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Game already started.")
        elif any(p["user_id"] == uid for p in g["players"]):
            send(chat_id, "You're already in!")
        else:
            g["players"].append(G.new_player(uid, user.get("first_name") or "Player"))
            send(chat_id, f"🙋 <b>{name}</b> joined ({len(g['players'])} players).")
            render(g)
        return
    if cmd == "/leave":
        if g["phase"] != "lobby":
            send(chat_id, "⛔ Can't leave mid-game - Stay/bust out of the round instead.")
        else:
            g["players"] = [p for p in g["players"] if p["user_id"] != uid]
            if not g["players"]:
                del state["games"][str(chat_id)]
                send(chat_id, "Lobby empty - game deleted.")
            else:
                send(chat_id, f"👋 {name} left.")
                render(g)
        return
    if cmd == "/cancel":
        if uid != g["created_by"]:
            send(chat_id, "⛔ Only the creator can cancel.")
        else:
            del state["games"][str(chat_id)]
            send(chat_id, "🗑 Game cancelled.")
        return
    if cmd == "/startgame":
        if g["phase"] != "lobby":
            send(chat_id, "Already started.")
        elif len(g["players"]) < 2:
            send(chat_id, "⛔ Need at least 2 players (official: 3+). Friends tap Join!")
        else:
            events = [f"🎮 Game started with {len(g['players'])} players! First to {G.WIN_SCORE}."]
            order = [(g["dealer_index"] + k) % len(g["players"]) for k in range(len(g["players"]))]
            g["deal_queue"] = list(order)
            g["phase"] = "dealing"
            advance(g, events)
            render(g, events)
        return
    if cmd == "/score":
        render(g)
        return
    if cmd == "/next":
        if g["phase"] != "round_end":
            send(chat_id, "Round not over yet.")
        else:
            events = []
            G.start_next_round(g, events)
            advance(g, events)
            render(g, events)
        return
    if cmd in ("/hit", "/stay"):
        events = []
        if g["phase"] != "playing" or g["pending_action"]:
            send(chat_id, "Not your turn / waiting on an action choice.")
        elif g["players"][g["current_index"]]["user_id"] != uid:
            send(chat_id, f"⛔ It's {g['players'][g['current_index']]['name']}'s turn.")
        elif cmd == "/hit":
            do_hit(g, g["current_index"], events)
            advance(g, events)
            render(g, events)
        else:
            if do_stay(g, g["current_index"], events):
                render(g, events)
            else:
                send(chat_id, events[0] if events else "Must Hit.")
        return
    send(chat_id, "Commands: /newgame /join /startgame /hit /stay /web /play /score /rules /cancel")


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
    if data.startswith("lsd:"):
        ls = lsd_get(state, chat_id)
        if not ls:
            return answer_cb(cb["id"], "No Summon Demons game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(ls["players"]) if p["user_id"] == uid), None)
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
    if data.startswith("od:"):
        od = odin_get(state, chat_id)
        if not od:
            return answer_cb(cb["id"], "No Odin game here.")
        parts = data.split(":")
        idx = next((i for i, p in enumerate(od["players"]) if p["user_id"] == uid), None)
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
                return answer_cb(cb["id"], "Only the Jester player picks next.")
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
        if g["players"][g["current_index"]]["user_id"] != uid:
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
        if g["pending_action"]["chooser_id"] != uid:
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
        events.append("🔄 New game - same players! Anyone sends /startgame.")
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
        "players": [{"user_id": p["user_id"], "name": p["name"],
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
        if g["players"][g["current_index"]]["user_id"] != user_id:
            return [], f"it's {g['players'][g['current_index']]['name']}'s turn"
        do_hit(g, g["current_index"], events)
        advance(g, events)
    elif action == "stay":
        if g["phase"] != "playing" or g["pending_action"]:
            return [], "not your turn"
        if g["players"][g["current_index"]]["user_id"] != user_id:
            return [], f"it's {g['players'][g['current_index']]['name']}'s turn"
        if not do_stay(g, g["current_index"], events):
            return [], events[0] if events else "must Hit"
    elif action == "action":
        if not g["pending_action"]:
            return [], "no action pending"
        if g["pending_action"]["chooser_id"] != user_id:
            return [], "only the chooser picks the target"
        if target_index not in G.eligible_targets(g, g["pending_action"]["action"]):
            return [], "invalid target"
        do_action_choice(g, int(target_index), events)
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
        "players": [{"user_id": p["user_id"], "name": p["name"], "hand_count": len(p["hand"])}
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
        "players": [{"user_id": p["user_id"], "name": p["name"],
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
        "players": [{"user_id": p["user_id"], "name": p["name"], "souls": p["souls"],
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
    else:
        return [], "unknown action"
    lsd_render(g, ev)
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
