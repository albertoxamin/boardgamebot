"""13 Leaves (I'm Out) engine - pure logic, no Telegram, no I/O.

Rules (13 Leaves / I'm Out, Masato Uesugi; CMYK):
- Deck 62 cards, values 1..13 with distribution (by value): 1->2,2->3,3->4,4->5,5->6,6->7,7->8,8->7,9->6,10->5,11->4,12->3,13->2.
- 3-6 players. Deal: 3p 12, 4p 11, 5p 10, 6p 9. Cards kept hidden.
- Rounds: players play in turn (clockwise). A central row (line) has stacks at ends.
  * First play of a round (empty row): play any number of cards of the same value.
  * After that, on your turn you may play to either end: you must play >= the count of cards
    in that end stack, and you play cards of the same value that are <= lowest or >= highest
    of the row (extending toward an extreme) OR you may match the end value by adding to that
    end stack? "either matching the rank of the end card, or going more towards the corresponding extreme"
    and you must play >= number of cards at that end. Also "Matching numbers stack." So to play
    on the left end (lowest side), legal values are: == leftmost value (add to that stack) OR < leftmost? No:
    "add cards of any value lower than the lowest card on the table or any value higher than the highest card".
    And "play cards that match the value of one of the last played cards on each end" (stack them). Yes.
    So for an end: you can stack onto it if you play same value AND play >= count of that stack? Or play same count rules.
    "You must play a number of cards equal to or greater than the number of cards at the end of the sequence they are playing on"
    (when playing on that end). Yes.
- If you cannot/won't play: pass. When you pass, take any one card from the row (from any position)
  and add it to your hand. You are out for the rest of this round (cannot play again until next round).
- Round ends when all but one have passed: the last active player discards the row and leads the next round.
- Game ends immediately when any player empties their hand: that player wins (instant win). (Standard I'm Out)
"""
import random
from collections import Counter

MIN_PLAYERS = 3
MAX_PLAYERS = 6


def build_deck():
    deck = []
    counts = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 7, 9: 6, 10: 5, 11: 4, 12: 3, 13: 2}
    for v, c in counts.items():
        for _ in range(c):
            deck.append(v)
    assert len(deck) == 62, len(deck)
    return deck


def deal_counts(nplayers):
    return {3: 12, 4: 11, 5: 10, 6: 9}[nplayers]


def new_player(user_id, name):
    return {"user_id": int(user_id), "name": name, "hand": []}


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby",  # lobby|playing|round_end|game_end
        "deck": [],
        "row": [],          # list of stacks: [{"value": v, "count": n}, ...] in order low->high
        "current_index": 0,
        "passed": [],    # user_ids who passed this round
        "leader_index": 0,
        "winner_id": None,
        "board_message_id": None,
        "log": [],
    }


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def start_game(g, events):
    n = len(g["players"])
    if n < MIN_PLAYERS or n > MAX_PLAYERS:
        return f"need {MIN_PLAYERS}-{MAX_PLAYERS} players"
    g["deck"] = build_deck()
    random.shuffle(g["deck"])
    cnt = deal_counts(n)
    for p in g["players"]:
        p["hand"] = [g["deck"].pop() for _ in range(cnt)]
        p["hand"].sort()
    g["phase"] = "playing"
    g["row"] = []
    g["passed"] = []
    g["leader_index"] = 0
    g["current_index"] = 0
    g["winner_id"] = None
    events.append(f"🍃 13 Leaves started ({n} players). First player leads any set.")
    return None


def _active_indices(g):
    passed_ids = g["passed"]
    return [i for i, p in enumerate(g["players"]) if p["user_id"] not in passed_ids]


def _next_active(g, start):
    n = len(g["players"])
    for k in range(1, n + 1):
        i = (start + k) % n
        if g["players"][i]["user_id"] not in g["passed"]:
            return i
    return None


def row_low(g):
    return g["row"][0]["value"] if g["row"] else None


def row_high(g):
    return g["row"][-1]["value"] if g["row"] else None


def legal_plays(g, idx):
    """Return list of possible play descriptions: ('left'|'right'|'new', value, min_count)"""
    p = g["players"][idx]
    hand_counts = Counter(p["hand"])
    moves = []
    if not g["row"]:
        for v, cnt in hand_counts.items():
            for k in range(1, cnt + 1):
                moves.append(("new", v, k))
        return moves
    lo = row_low(g)
    hi = row_high(g)
    left_c = g["row"][0]["count"]
    right_c = g["row"][-1]["count"]
    # left end: stack same as lo if enough, or play lower values with >= left_c
    if hand_counts[lo] >= left_c:
        moves.append(("left", lo, left_c))
    for v in range(lo - 1, 0, -1):
        if hand_counts[v] >= left_c:
            moves.append(("left", v, left_c))
    # right end
    if hand_counts[hi] >= right_c:
        moves.append(("right", hi, right_c))
    for v in range(hi + 1, 14):
        if hand_counts[v] >= right_c:
            moves.append(("right", v, right_c))
    return moves


def can_play_any(g, idx):
    return len(legal_plays(g, idx)) > 0


def play(g, idx, value, count, events):
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["players"][idx]["user_id"] in g["passed"]:
        return "you are out this round"
    p = g["players"][idx]
    # validate
    have = p["hand"].count(value)
    if have < count:
        return f"you only have {have} of {value}"
    if not g["row"]:
        # first play of round
        pass
    else:
        lo = row_low(g)
        hi = row_high(g)
        left_c = g["row"][0]["count"]
        right_c = g["row"][-1]["count"]
        ok = False
        # try left
        if value == lo and count >= left_c:
            ok = True
            side = "left"
        elif value < lo and count >= left_c:
            ok = True
            side = "left"
        # try right
        if value == hi and count >= right_c:
            ok = True
            side = "right"
        elif value > hi and count >= right_c:
            ok = True
            side = "right"
        if not ok:
            return "illegal play for current row"
    # remove cards
    removed = 0
    new_hand = []
    for c in p["hand"]:
        if c == value and removed < count:
            removed += 1
        else:
            new_hand.append(c)
    p["hand"] = new_hand
    # apply to row
    if not g["row"]:
        g["row"] = [{"value": value, "count": count}]
        events.append(f"🃏 {p['name']} leads with {count}×{value}")
    else:
        lo = row_low(g)
        hi = row_high(g)
        if value == lo:
            g["row"][0]["count"] += count
            events.append(f"🃏 {p['name']} adds {count}×{value} to the left (now {g['row'][0]['count']})")
        elif value < lo:
            g["row"].insert(0, {"value": value, "count": count})
            events.append(f"🃏 {p['name']} plays {count}×{value} on the left")
        elif value == hi:
            g["row"][-1]["count"] += count
            events.append(f"🃏 {p['name']} adds {count}×{value} to the right (now {g['row'][-1]['count']})")
        else:  # value > hi
            g["row"].append({"value": value, "count": count})
            events.append(f"🃏 {p['name']} plays {count}×{value} on the right")
    # win check
    if len(p["hand"]) == 0:
        g["phase"] = "game_end"
        g["winner_id"] = p["user_id"]
        events.append(f"🏆 {p['name']} is out of cards! Wins!")
        return None
    # advance to next active
    nxt = _next_active(g, idx)
    if nxt is None:
        # round ends
        _end_round(g, events, idx)
    else:
        g["current_index"] = nxt
    return None


def pass_turn(g, idx, events, take_index=None):
    """Pass: take one card from row[take_index] (0 = leftmost stack)."""
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["players"][idx]["user_id"] in g["passed"]:
        return "already passed"
    if not g["row"]:
        return "cannot pass on first play of round"
    p = g["players"][idx]
    if take_index is None:
        take_index = 0
    if take_index < 0 or take_index >= len(g["row"]):
        return "bad take index"
    taken_val = g["row"][take_index]["value"]
    g["row"][take_index]["count"] -= 1
    if g["row"][take_index]["count"] <= 0:
        g["row"].pop(take_index)
    p["hand"].append(taken_val)
    p["hand"].sort()
    g["passed"].append(p["user_id"])
    events.append(f"⏭ {p['name']} passes and takes a {taken_val} (from row pos {take_index + 1})")
    active = _active_indices(g)
    if len(active) <= 1:
        _end_round(g, events, active[0] if active else idx)
        return None
    nxt = _next_active(g, idx)
    g["current_index"] = nxt if nxt is not None else idx
    return None


def _end_round(g, events, last_idx):
    # last active leads next round
    g["row"] = []
    g["passed"] = []
    g["leader_index"] = last_idx
    g["current_index"] = last_idx
    events.append(f"🔁 Round over. {g['players'][last_idx]['name']} leads a new round.")
