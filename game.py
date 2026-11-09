"""Flip 7 engine - pure logic, no Telegram, no I/O. Tested by test_game.py.

Rules (The Op / Asmodee, 2024):
Deck 94: numbers 0x1,1x1,2x2..12x12 (79); modifiers +2,+4,+6,+8,+10,x2 (6);
actions 3x(Freeze, Flip Three, Second Chance) (9).
Round: dealer deals 1 face-up to each (actions resolved as dealt), then
players in turn order Hit (take a card) or Stay (bank, out for round).
Duplicate number = bust (0 pts). 7 unique numbers = Flip 7: round ends
immediately, +15. Score: sum(numbers); x2 doubles numbers only; then add
+modifiers; then +15 if Flip 7. First to 200 (unique highest) wins; on a
tie at >=200 play continues. Round cards are set aside (not reshuffled
until deck runs out); dealer rotates left.
Action cards: chooser picks any ACTIVE (not stayed/busted/frozen) player.
 Freeze: target banks and leaves round. Flip Three: target takes next 3
 one at a time, stops on bust/Flip7; Second Chance kept/usable during it,
 Freeze/Flip Three deferred until after the 3 (if not busted).
 Second Chance: keep 1 max; on a later duplicate discard dup+SC, stay in.
Modifiers never bust, never count toward 7.
"""
import html
import random
from copy import deepcopy

WIN_SCORE = 200
FLIP7_BONUS = 15
DECK_SIZE = 94


def build_deck():
    deck = []
    deck.append({"kind": "number", "value": 0})
    for n in range(1, 13):
        for _ in range(n):
            deck.append({"kind": "number", "value": n})
    for m in ["+2", "+4", "+6", "+8", "+10", "x2"]:
        deck.append({"kind": "modifier", "value": m})
    for a in ["Freeze", "Flip Three", "Second Chance"]:
        for _ in range(3):
            deck.append({"kind": "action", "value": a})
    assert len(deck) == DECK_SIZE, len(deck)
    return deck


def new_deck(rng=None):
    d = build_deck()
    (rng or random).shuffle(d)
    return d


def card_str(c):
    if c["kind"] == "number":
        return str(c["value"])
    if c["kind"] == "modifier":
        return c["value"]
    return c["value"]


def score_player(p):
    """Round score for a non-busted player; 0 if busted."""
    if p["status"] == "busted":
        return 0
    total = sum(p["numbers"])
    mods = p["modifiers"]
    if "x2" in mods:
        total *= 2
    total += sum(int(m[1:]) for m in mods if m.startswith("+"))
    if len(p["numbers"]) == 7:
        total += FLIP7_BONUS
    return total


def new_player(user_id, name):
    return {
        "user_id": int(user_id), "name": name, "total": 0,
        "numbers": [], "modifiers": [], "second_chance": False,
        "status": "active",  # active | stayed | busted | frozen
        "last_round": None,
        "flip3_cards": [],  # card keys flipped under Flip Three this round (for UI marking)
    }


def reset_round_player(p):
    p["numbers"] = []
    p["modifiers"] = []
    p["second_chance"] = False
    p["status"] = "active"
    p["flip3_cards"] = []
    # last_round kept from the round just scored (shown during next round)


def new_game(chat_id, creator_id, creator_name, deck=None):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "dealer_index": 0, "round": 1,
        "deck": deck if deck is not None else new_deck(),
        "aside": [],  # cards from finished rounds, reshuffled when deck empties
        "phase": "lobby",  # lobby|dealing|playing|action|round_end|game_end
        "current_index": 0, "deal_queue": [],
        "pending_action": None,  # {action, chooser_id, context}
        "action_queue": [],  # deferred actions waiting for a chooser
        "flip3": None,  # {target_index, remaining, deferred:[action,...]}
        "board_message_id": None, "winner_id": None, "log": [],
    }


def active_indices(g):
    return [i for i, p in enumerate(g["players"]) if p["status"] == "active"]


def draw(g):
    """Draw one card, reshuffling `aside` if deck is empty (mid-round rule:
    cards in front of players are left alone - they are not in `aside`)."""
    if not g["deck"]:
        if not g["aside"]:
            return None
        g["deck"] = g["aside"]
        g["aside"] = []
        random.shuffle(g["deck"])
        g["log"].append("🔀 Deck ran out - discard pile reshuffled.")
    return g["deck"].pop()


def has_duplicate(p, value):
    return value in p["numbers"]


def is_flip7(p):
    return len(p["numbers"]) == 7


def apply_card(g, idx, card, events, in_flip3=False):
    """Apply a drawn card to player idx. Returns outcome string.
    Outcomes: 'ok','bust','flip7','action','saved' (Second Chance save).
    For 'action', g['pending_action'] or (in_flip3) g['flip3']['deferred']
    is set and caller must pause for the chooser."""
    p = g["players"][idx]
    if card["kind"] == "number":
        v = card["value"]
        if has_duplicate(p, v):
            if p["second_chance"]:
                p["second_chance"] = False
                g["aside"].append(card)  # dup discarded
                events.append(f"💛 {p['name']}'s Second Chance saved them from a duplicate {v}!")
                return "saved"
            p["status"] = "busted"
            p["numbers"].append(v)  # keep both copies visible in the pile
            if in_flip3:
                p.setdefault("flip3_cards", []).append(str(v))
            events.append(f"💥 {p['name']} BUSTED on a second {v}! Scores 0 this round.")
            return "bust"
        p["numbers"].append(v)
        if in_flip3:
            p.setdefault("flip3_cards", []).append(str(v))
        events.append(f"🎴 {p['name']} flips {v}")
        if is_flip7(p):
            events.append(f"🃏 FLIP 7! {p['name']} got 7 unique numbers (+{FLIP7_BONUS} bonus) - round ends now!")
            return "flip7"
        return "ok"
    if card["kind"] == "modifier":
        p["modifiers"].append(card["value"])
        if in_flip3:
            p.setdefault("flip3_cards", []).append(str(card["value"]))
        events.append(f"🎴 {p['name']} flips modifier {card['value']}")
        return "ok"
    # action card
    action = card["value"]
    if in_flip3:
        if action == "Second Chance":
            if not p["second_chance"]:
                p["second_chance"] = True
                p.setdefault("flip3_cards", []).append("Second Chance")
                events.append(f"🎴 {p['name']} flips Second Chance (kept)")
            else:
                events.append(f"🎴 Second Chance flipped for {p['name']} but they already have one - discarded")
            return "ok"
        g["flip3"]["deferred"].append(action)
        events.append(f"🎴 {p['name']} flips {action} - deferred until Flip Three finishes")
        return "ok"
    # normal: chooser (the player who drew it) picks an active target
    events.append(f"🎴 {p['name']} flips {action} - {p['name']}, choose who gets it:")
    g["last_chooser_id"] = p["user_id"]
    g["pending_action"] = {"action": action, "chooser_id": p["user_id"],
                           "context": "normal"}
    return "action"


def eligible_targets(g, action):
    """Indices the chooser may pick. Second Chance: active players without one."""
    return [i for i in active_indices(g)
            if not (action == "Second Chance" and g["players"][i]["second_chance"])]


def resolve_action(g, target_idx, events):
    """Resolve g['pending_action'] on target. May start Flip Three or set a
    follow-up pending_action (deferred chain). Returns 'ok'|'flip3'."""
    pa = g["pending_action"]
    action, g["pending_action"] = pa["action"], None
    p = g["players"][target_idx]
    if action == "Freeze":
        p["status"] = "frozen"
        events.append(f"❄️ {p['name']} is FROZEN - banks their cards and leaves the round.")
        return "ok"
    if action == "Second Chance":
        p["second_chance"] = True
        events.append(f"💛 {p['name']} keeps a Second Chance.")
        return "ok"
    if action == "Flip Three":
        if p["status"] != "active":
            events.append(f"🎲 Flip Three fizzles - {p['name']} is no longer active.")
            return "ok"
        events.append(f"🎲 {p['name']} must Flip Three!")
        g["flip3"] = {"target_index": target_idx, "remaining": 3, "deferred": []}
        return "flip3"
    return "ok"


def run_flip3_step(g, events):
    """Deal one of the three Flip-Three cards. Returns 'continue'|'done'|'bust'|'flip7'."""
    f = g["flip3"]
    idx = f["target_index"]
    card = draw(g)
    if card is None:
        f["remaining"] = 0
        return "done"
    outcome = apply_card(g, idx, card, events, in_flip3=True)
    if outcome in ("bust", "flip7"):
        f["remaining"] = 0
        return outcome
    f["remaining"] -= 1
    return "continue" if f["remaining"] > 0 else "done"


def pop_next_action(g, events):
    """Pop next deferred action into pending_action. Returns 'action'|'ok'."""
    if not g.get("action_queue"):
        return "ok"
    action = g["action_queue"].pop(0)
    chooser_id = g.get("last_chooser_id")
    events.append(f"⏳ Deferred {action} - {name_of(g, chooser_id)}, choose who gets it:")
    g["pending_action"] = {"action": action, "chooser_id": chooser_id,
                           "context": "deferred"}
    return "action"


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def finish_flip3(g, events):
    """After 3 cards (no bust/flip7): queue deferred actions for chooser.
    Returns 'action' if a deferred action now needs a target, else 'ok'."""
    f = g["flip3"]
    g["last_chooser_id"] = g["players"][f["target_index"]]["user_id"]
    g["action_queue"].extend(f["deferred"])
    g["flip3"] = None
    return pop_next_action(g, events)


def next_active(g, start):
    n = len(g["players"])
    for k in range(n):
        i = (start + k) % n
        if g["players"][i]["status"] == "active":
            return i
    return None


def round_over(g):
    return not active_indices(g)


def end_round(g, events):
    """Score everyone. No winner -> auto-start next round (phase 'dealing';
    caller/bot then deals via advance()). Winner -> phase 'game_end'.
    Score breakdown is in `events` so auto-advance loses no information."""
    for p in g["players"]:
        s = score_player(p)
        p["last_round"] = s
        p["total"] += s
        cards = ", ".join(map(str, p["numbers"])) or "-"
        mods = ", ".join(p["modifiers"]) or "-"
        events.append(f"• {p['name']}: numbers [{cards}] mods [{mods}] → +{s} (total {p['total']})")
    g["phase"] = "round_end"
    g["flip3"] = None
    g["pending_action"] = None
    g["action_queue"] = []
    top = max(p["total"] for p in g["players"])
    if top >= WIN_SCORE:
        leaders = [p for p in g["players"] if p["total"] == top]
        if len(leaders) == 1:
            g["phase"] = "game_end"
            g["winner_id"] = leaders[0]["user_id"]
            events.append(f"🏆 {leaders[0]['name']} wins with {top} points!")
            return leaders[0]
        events.append("🤝 Tie at 200+ - keep playing until there's a unique winner!")
    else:
        events.append(f"Round {g['round']} over. First to {WIN_SCORE} wins.")
    start_next_round(g, events)  # auto-go-next: deal the following round now
    return None


def start_next_round(g, events):
    for p in g["players"]:
        # collect in-front cards into aside (not reshuffled until deck empties)
        for v in p["numbers"]:
            g["aside"].append({"kind": "number", "value": v})
        for m in p["modifiers"]:
            g["aside"].append({"kind": "modifier", "value": m})
        if p["second_chance"]:
            g["aside"].append({"kind": "action", "value": "Second Chance"})
        reset_round_player(p)
    g["round"] += 1
    g["dealer_index"] = (g["dealer_index"] + 1) % len(g["players"])
    order = [(g["dealer_index"] + k) % len(g["players"]) for k in range(len(g["players"]))]
    g["deal_queue"] = list(order)
    g["phase"] = "dealing"
    events.append(f"Dealer rotates to {g['players'][g['dealer_index']]['name']}. Round {g['round']} - dealing 1 card each…")


def board_lines(g):
    lines = [f"🎴 <b>Flip 7</b> - Round {g['round']} | Dealer: {html.escape(g['players'][g['dealer_index']]['name'])} | Deck: {len(g['deck'])} | First to {WIN_SCORE}"]
    for i, p in enumerate(g["players"]):
        st = {"active": "▶️", "stayed": "✅ stayed", "busted": "💥 bust", "frozen": "❄️ frozen"}[p["status"]]
        nums = " ".join(map(str, sorted(p["numbers"]))) or "—"
        mods = " ".join(sorted(p["modifiers"], key=lambda m: 999 if m == "x2" else int(m[1:]))) or ""
        sc = " 💛SC" if p["second_chance"] else ""
        turn = " 👈" if g["phase"] in ("playing",) and i == g["current_index"] else ""
        f3 = f" 🎲 Flip Three ×{len(p['flip3_cards'])}" if p.get("flip3_cards") else ""
        lines.append(f"{st} <b>{html.escape(p['name'])}</b>{f3} [{nums}]{(' (' + mods + ')') if mods else ''}{sc} = <b>{p['total']}</b> pts{turn}")
    return "\n".join(lines)
