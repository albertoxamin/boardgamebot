"""Tornado Splash (Arclight Games, 2025) engine: jet-ski racing with cards.

2-5 players (rulebook V1.3). Each racer selects one of 6 boats; every boat has
its own 20-card deck of racing cards (speed boats pack long straights, control
boats pack curve cards - the boat card's Speed/Handling stars). The race is
run over a course of straights and checkpoint turns; the first racer to reach
or cross the goal gate wins and the race continues until all but one have
finished.

Each round has three phases:
1. RANK RACERS - order by proximity to the goal gate; ties -> lighter boat.
2. REPLENISH HAND - draw up to your rank's limit: 1st 4, last 6, others 5.
   Deck empty -> retrieve your previously played cards, earliest first.
3. MAKE WAVES - in rank order, play racing cards and move their total spaces
   (max 3/round; 4 with the once-per-race boost). Passing a checkpoint
   requires a curve card played that turn.

Digital adaptations (the physical game lays cards on the table):
- The course is a line of spaces; card-placement geometry, covering other
  players' cards and the table-edge elimination rule are replaced by the
  checkpoint-curve requirement (no placement, no collisions).
- Your lane always equals your position: played cards are spent, not banked.
- Waiting may discard cards (they go to your played pile and return through the
  earliest-first retrieval), so a hand of pure straights at a checkpoint can
  cycle into curve cards instead of deadlocking.
- Deck compositions are reconstructed (the exact physical lists are not
  published); they follow the boat types (speed/balanced/control).
- Grand Prix variant: 3 races over the 4 courses, points 5/3/2/0 by finish.
"""
import random

MAX_PLAYERS = 5
RACES_IN_GP = 3
BASE_MOVE = 3          # max spaces per round
BOOST_MOVE = 4         # max spaces on your once-per-race boost turn
GP_POINTS = {2: [5, 0], 3: [5, 3, 0], 4: [5, 3, 2, 0], 5: [5, 3, 2, 0]}

# Course cards: (name, track length in spaces, [(checkpoint space, turn dir)])
# Checkpoint semantics: moving FROM space cp (or earlier) PAST cp requires a
# curve card that turn. You may stop exactly on cp without turning.
COURSES = [
    {"name": "Tornado Circuit", "length": 24,
     "checkpoints": [(9, "R"), (17, "L")]},
    {"name": "Splashway", "length": 20,
     "checkpoints": [(6, "L"), (12, "R"), (16, "L")]},
    {"name": "Winding River", "length": 30,
     "checkpoints": [(7, "L"), (13, "R"), (20, "L"), (25, "R")]},
    {"name": "Rainy Road", "length": 26,
     "checkpoints": [(8, "R"), (14, "R"), (22, "L")]},
]
assert all(cp < c["length"] for c in COURSES for cp, _ in c["checkpoints"])

# Boat cards: name, type, speed/handling stars, weight (1=lightest..6),
# and the boat's 20-card racing deck as {s1, s2, c1, c2} counts
# (s=straight card, c=curve card, digit = spaces the card gives).
BOATS = [
    {"name": "Waverunner", "type": "speed", "speed": 3, "handling": 1,
     "weight": 6, "deck": {"s2": 9, "s1": 3, "c1": 4, "c2": 4}},
    {"name": "Bolt", "type": "speed", "speed": 3, "handling": 2,
     "weight": 3, "deck": {"s2": 8, "s1": 4, "c1": 3, "c2": 5}},
    {"name": "Tsunami", "type": "balanced", "speed": 2, "handling": 2,
     "weight": 4, "deck": {"s2": 6, "s1": 5, "c1": 5, "c2": 4}},
    {"name": "Riptide", "type": "balanced", "speed": 2, "handling": 2,
     "weight": 1, "deck": {"s2": 5, "s1": 6, "c1": 6, "c2": 3}},
    {"name": "Squall", "type": "control", "speed": 1, "handling": 3,
     "weight": 2, "deck": {"s2": 3, "s1": 6, "c1": 8, "c2": 3}},
    {"name": "Undertow", "type": "control", "speed": 1, "handling": 3,
     "weight": 5, "deck": {"s2": 4, "s1": 5, "c1": 9, "c2": 2}},
]
assert len(BOATS) == 6
for _b in BOATS:
    assert sum(_b["deck"].values()) == 20, _b["name"]


def _card(kind, spaces):
    return {"kind": kind, "spaces": spaces}  # kind: 's' straight | 'c' curve


def card_str(c):
    return ("🌊" if c["kind"] == "c" else "➡️") + str(c["spaces"])


def build_deck(deck_spec):
    deck = []
    for kind in ("s1", "s2", "c1", "c2"):
        for _ in range(deck_spec[kind]):
            deck.append(_card(kind[0], int(kind[1])))
    random.shuffle(deck)
    return deck


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def new_player(user_id, name):
    return {"user_id": int(user_id), "name": name,
            "boat": None,      # index into BOATS
            "deck": [], "hand": [], "played": [],
            "pos": 0, "finished": False, "finish_rank": None,
            "boost_used": False, "points": 0}


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby",  # lobby|picking|playing|race_end|game_end
        "gp": False, "race_number": 0, "course_index": 0,
        "picking_index": 0, "picking_order": [],
        "round": 0, "turn_order": [], "current_index": 0,
        "finish_order": [], "winner_id": None, "winners": [],
        "board_message_id": None,
    }


def course(g):
    return COURSES[g["course_index"] % len(COURSES)]


def total_races(g):
    return RACES_IN_GP if g["gp"] else 1


# ---------- setup ----------

def start_picking(g, events, gp=None):
    if g["phase"] != "lobby":
        return "already started"
    if len(g["players"]) < 2:
        return "need at least 2 players"
    if len(g["players"]) > MAX_PLAYERS:
        return f"too many players (max {MAX_PLAYERS})"
    if gp is not None:
        g["gp"] = bool(gp)
    for p in g["players"]:
        p["points"] = 0
    g["finish_order"] = []
    g["race_number"] = 0
    g["course_index"] = 0
    # Random player picks first, then clockwise (list order).
    first = random.randrange(len(g["players"]))
    g["picking_order"] = [(first + k) % len(g["players"])
                          for k in range(len(g["players"]))]
    g["picking_index"] = 0
    g["phase"] = "picking"
    mode = "Grand Prix (3 races)" if g["gp"] else "single race"
    events.append(f"🏁 Boat selection ({mode}) - "
                  f"{g['players'][first]['name']} picks first!")
    return None


def pick_boat(g, idx, boat_index, events):
    """Current picker takes an available boat; all picked -> race starts."""
    if g["phase"] != "picking":
        return "not in boat selection"
    if idx != g["picking_order"][g["picking_index"]]:
        return "not your pick"
    if not (0 <= boat_index < len(BOATS)):
        return "no such boat"
    if any(p["boat"] == boat_index for p in g["players"]):
        return "that boat is already taken"
    p = g["players"][idx]
    p["boat"] = boat_index
    b = BOATS[boat_index]
    events.append(f"🛥️ {p['name']} takes the {b['name']} "
                  f"({'⭐' * b['speed']}/{('⭐' * b['handling'])}, weight {b['weight']}).")
    g["picking_index"] += 1
    if g["picking_index"] >= len(g["picking_order"]):
        start_race(g, events)
    return None


def auto_assign_boats(g, events):
    """Randomly give every boat-less player a free boat, then start."""
    if g["phase"] != "picking":
        return "not in boat selection"
    free = [i for i in range(len(BOATS))
            if not any(p["boat"] == i for p in g["players"])]
    random.shuffle(free)
    for idx in g["picking_order"][g["picking_index"]:]:
        g["players"][idx]["boat"] = free.pop()
        b = BOATS[g["players"][idx]["boat"]]
        events.append(f"🛥️ {g['players'][idx]['name']} is auto-assigned "
                      f"the {b['name']}.")
    g["picking_index"] = len(g["picking_order"])
    start_race(g, events)
    return None


def start_race(g, events):
    """Begin race `race_number` (+1): fresh decks/hands/positions."""
    g["race_number"] += 1
    g["course_index"] = (g["race_number"] - 1) % len(COURSES)
    c = course(g)
    for p in g["players"]:
        b = BOATS[p["boat"]]
        p["deck"] = build_deck(b["deck"])
        p["hand"] = []
        p["played"] = []
        p["pos"] = 0
        p["finished"] = False
        p["finish_rank"] = None
        p["boost_used"] = False
    g["finish_order"] = []
    g["round"] = 0
    # All jet skis lined up: the lightest boat is ranked first (rulebook).
    g["turn_order"] = sorted(range(len(g["players"])),
                             key=lambda i: (BOATS[g["players"][i]["boat"]]["weight"],
                                            g["players"][i]["user_id"]))
    g["current_index"] = 0
    # Opening hands: lightest 4, heaviest 6, others 5 (same as rank rule).
    order = list(g["turn_order"])
    for k, idx in enumerate(order):
        limit = 4 if k == 0 else (6 if k == len(order) - 1 else 5)
        _replenish(g["players"][idx], limit)
    g["phase"] = "playing"
    label = f"Race {g['race_number']}/{total_races(g)} - " if g["gp"] else ""
    events.append(f"🌊 {label}{c['name']}! {c['length']} spaces, checkpoints at "
                  + ", ".join(f"{cp} ({d})" for cp, d in c["checkpoints"])
                  + f". {g['players'][g['turn_order'][0]]['name']} goes first.")
    g["round"] = 1


# ---------- ranks & replenish ----------

def compute_ranks(g):
    """Rank order: finished racers by finish order, then the rest by
    proximity to the goal (pos desc), ties -> lighter boat first."""
    def key(i):
        p = g["players"][i]
        if p["finished"]:
            return (0, p["finish_rank"])
        weight = BOATS[p["boat"]]["weight"] if p["boat"] is not None else 99
        return (1, -p["pos"], weight, p["user_id"])
    return sorted(range(len(g["players"])), key=key)


def unfinished(g):
    return [i for i, p in enumerate(g["players"]) if not p["finished"]]


def active_ranks(g):
    """Ranks among unfinished racers (who still act and replenish)."""
    return [i for i in compute_ranks(g) if not g["players"][i]["finished"]]


def _replenish(p, limit):
    """Draw up to `limit`; when the deck is empty retrieve played cards
    earliest first (the track you raced becomes your new hand)."""
    while len(p["hand"]) < limit:
        if p["deck"]:
            p["hand"].append(p["deck"].pop())
        elif p["played"]:
            p["hand"].append(p["played"].pop(0))
        else:
            break


def begin_round(g, events):
    ranks = active_ranks(g)
    g["round"] += 1
    g["turn_order"] = list(ranks)
    g["current_index"] = 0
    n = len(ranks)
    events.append(f"— Round {g['round']} —")
    for k, idx in enumerate(ranks):
        limit = 4 if k == 0 else (6 if k == n - 1 else 5)
        p = g["players"][idx]
        before = len(p["hand"])
        _replenish(p, limit)
        got = len(p["hand"]) - before
        if got:
            events.append(f"🃏 {p['name']} draws {got} card(s) (hand {len(p['hand'])}).")
    if not g["turn_order"]:
        _end_race(g, events)


# ---------- movement ----------

def max_move(g, idx, boost=False):
    p = g["players"][idx]
    if boost and not p["boost_used"]:
        return BOOST_MOVE
    return BASE_MOVE


def _crossed_checkpoints(g, old_pos, new_pos):
    return [cp for cp, d in course(g)["checkpoints"]
            if old_pos <= cp < new_pos]


def do_play(g, idx, hand_positions, boost=False, events=None):
    """Play 1+ cards from your hand (by hand position, any order) and move
    their total spaces. Passing a checkpoint needs a curve card this turn."""
    events = events if events is not None else []
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx not in g["turn_order"] or g["turn_order"][g["current_index"]] != idx:
        return "not your turn"
    p = g["players"][idx]
    cap = max_move(g, idx, boost)
    if boost and p["boost_used"]:
        return "you already used your boost this race"
    if not hand_positions:
        return "play at least one card (or wait)"
    if len(hand_positions) > cap:
        return f"you may play at most {cap} card(s) this turn"
    cards = []
    for h in hand_positions:
        if not (0 <= h < len(p["hand"])):
            return "no such card in your hand"
        cards.append(p["hand"][h])
    total = sum(c["spaces"] for c in cards)
    if total > cap:
        return f"that move is {total} spaces - max {cap} per turn"
    old_pos = p["pos"]
    new_pos = min(old_pos + total, course(g)["length"])
    crossed = _crossed_checkpoints(g, old_pos, new_pos)
    if crossed and not any(c["kind"] == "c" for c in cards):
        cps = ", ".join(str(cp) for cp in crossed)
        return f"you are passing checkpoint {cps} - play a curve card to turn"
    # spend the cards (remove by position, highest first keeps indices stable)
    for h in sorted(set(hand_positions), reverse=True):
        p["played"].append(p["hand"].pop(h))
    if boost:
        p["boost_used"] = True
        events.append(f"⚡ {p['name']} uses the BOOST!")
    c = course(g)
    if new_pos >= c["length"]:
        p["pos"] = c["length"]
        p["finished"] = True
        p["finish_rank"] = len(g["finish_order"]) + 1
        g["finish_order"].append(p["user_id"])
        events.append(f"🏁 {p['name']} crosses the finish line "
                      f"({p['finish_rank']}{_ord(p['finish_rank'])})!")
        if len(unfinished(g)) <= 1:
            return _end_race(g, events)
    else:
        p["pos"] = new_pos
        cpn = _crossed_checkpoints(g, old_pos, new_pos)
        curve = any(x["kind"] == "c" for x in cards)
        played = " + ".join(card_str(x) for x in cards)
        events.append(f"🛥️ {p['name']} plays {played} → space {new_pos}/{c['length']}"
                      + (f" (turn at {cpn[0]} ✓)" if cpn and curve else ""))
    _advance_turn(g, events)
    return None


def do_wait(g, idx, discard=None, events=None):
    """Move 0 this turn. Optionally discard cards (they go to your played
    pile, retrieved earliest-first) so a hand full of straights at a
    checkpoint can cycle into curve cards."""
    events = events if events is not None else []
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx not in g["turn_order"] or g["turn_order"][g["current_index"]] != idx:
        return "not your turn"
    if discard:
        p = g["players"][idx]
        for h in discard:
            if not (0 <= h < len(p["hand"])):
                return "no such card in your hand"
        for h in sorted(set(discard), reverse=True):
            p["played"].append(p["hand"].pop(h))
        events.append(f"🗑️ {g['players'][idx]['name']} discards "
                      f"{len(set(discard))} card(s).")
    events.append(f"⏳ {g['players'][idx]['name']} waits (moves 0).")
    _advance_turn(g, events)
    return None


def _ord(n):
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10 if n % 100 < 11 or n % 100 > 13 else 0, "th")


def _advance_turn(g, events):
    g["current_index"] += 1
    if g["phase"] != "playing":
        return
    live = [i for i in g["turn_order"] if not g["players"][i]["finished"]]
    if g["current_index"] >= len(g["turn_order"]) or not live:
        begin_round(g, events)


# ---------- race / game end ----------

def points_for(n_players, place):
    table = GP_POINTS.get(n_players, GP_POINTS[5])
    return table[place - 1] if place - 1 < len(table) else 0


def _end_race(g, events):
    """Award finishing ranks to whoever is left, score GP points, then
    either start the next GP race or finish the game."""
    c = course(g)
    for i in unfinished(g):
        p = g["players"][i]
        p["finished"] = True
        p["finish_rank"] = len(g["finish_order"]) + 1
        p["pos"] = c["length"]
        g["finish_order"].append(p["user_id"])
        events.append(f"🏁 {p['name']} finishes {p['finish_rank']}{_ord(p['finish_rank'])}.")
    n = len(g["players"])
    if g["gp"]:
        for i in range(n):
            p = g["players"][i]
            pts = points_for(n, p["finish_rank"])
            p["points"] += pts
            events.append(f"🏆 {p['name']}: {p['finish_rank']}{_ord(p['finish_rank'])} place → +{pts} pts (total {p['points']})")
    by_rank = compute_ranks(g)
    first = g["players"][by_rank[0]]
    g["winner_id"] = first["user_id"]
    if not g["gp"]:
        g["phase"] = "race_end"
        g["winners"] = [first["user_id"]]
        events.append(f"🏆 {first['name']} wins the race! "
                      f"(podium: " + ", ".join(
                          f"{k+1}. {g['players'][i]['name']}"
                          for k, i in enumerate(by_rank[:3])) + ")")
        return
    if g["race_number"] >= total_races(g):
        g["phase"] = "game_end"
        top = max(p["points"] for p in g["players"])
        g["winners"] = [p["user_id"] for p in g["players"] if p["points"] == top]
        events.append(f"🏆 Grand Prix over! Champion: "
                      + " & ".join(name_of(g, u) for u in g["winners"])
                      + f" with {top} pts.")
    else:
        g["phase"] = "race_end"
        events.append(f"Race {g['race_number']} done. Next: "
                      f"{COURSES[(g['race_number']) % len(COURSES)]['name']} - "
                      f"anyone taps Rematch/Next race.")


def next_race(g, uid, events):
    """Continue a GP after a race (any player of the game)."""
    if g["phase"] != "race_end" or not g["gp"]:
        return "no race to continue"
    if not any(p["user_id"] == uid for p in g["players"]):
        return "only players can continue the Grand Prix"
    g["phase"] = "playing"
    start_race(g, events)
    return None


def rematch_reset(g, events):
    """Back to boat selection with the same racers (fresh Grand Prix)."""
    for p in g["players"]:
        p["boat"] = None
        p["points"] = 0
    g["phase"] = "lobby"
    g["gp"] = False
    g["race_number"] = 0
    g["course_index"] = 0
    events.append("🔄 Rematch - back to boat selection!")


def max_hand(g, idx):
    """Hand limit for player idx by their rank among unfinished racers."""
    ranks = active_ranks(g)
    try:
        k = ranks.index(idx)
    except ValueError:
        return 0
    n = len(ranks)
    return 4 if k == 0 else (6 if k == n - 1 else 5)
