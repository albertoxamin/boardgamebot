"""Yahtzee engine - pure logic, no Telegram, no I/O. Tested by test_yahtzee.py.

Standard Yahtzee: 5 dice, up to 3 rolls a turn, then score one of 13
boxes.  Upper section (Ones..Sixes) totals 63+ for a 35-point bonus;
Yahtzee is 50 (plus 100 for every extra Yahtzee once the box is filled).
The game ends when every player has filled all 13 boxes; highest total
wins (ties are possible).  2-6 players.
"""
import random

UPPER = ["ones", "twos", "threes", "fours", "fives", "sixes"]
LOWER = ["three_kind", "four_kind", "full_house", "small_straight",
         "large_straight", "yahtzee", "chance"]
CATEGORIES = [
    ("ones", "Ones"), ("twos", "Twos"), ("threes", "Threes"),
    ("fours", "Fours"), ("fives", "Fives"), ("sixes", "Sixes"),
    ("three_kind", "Three of a Kind"), ("four_kind", "Four of a Kind"),
    ("full_house", "Full House"), ("small_straight", "Small Straight"),
    ("large_straight", "Large Straight"), ("yahtzee", "Yahtzee"),
    ("chance", "Chance"),
]
CAT_LABEL = dict(CATEGORIES)
CAT_KEY = {label: key for key, label in CATEGORIES}
UPPER_FACE = {"ones": 1, "twos": 2, "threes": 3, "fours": 4, "fives": 5, "sixes": 6}

DICE_COUNT = 5
MAX_ROLLS = 3
UPPER_BONUS_MIN = 63
UPPER_BONUS = 35
YAHTZEE_SCORE = 50
YAHTZEE_BONUS = 100
MAX_PLAYERS = 6


def new_player(user_id, name):
    return {"user_id": int(user_id), "name": name,
            "scores": {key: None for key in UPPER + LOWER},
            "yahtzee_bonus": 0}


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby",  # lobby|playing|game_end
        "current_index": 0,
        "turn": None,  # {rolls, dice:[5], keep:[bool]}
        "winner_id": None, "winners": [],
        "board_message_id": None,
    }


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


# ---------- Dice / scoring helpers ----------
def counts(dice):
    return [dice.count(face) for face in range(1, 7)]


def is_yahtzee(dice):
    return len(dice) == DICE_COUNT and len(set(dice)) == 1


def has_straight(dice, length):
    present = set(dice)
    return any(all(face in present for face in range(start, start + length))
               for start in range(1, 7 - length + 1))


def full_house(dice):
    c = sorted(counts(dice), reverse=True)
    return c[:2] == [3, 2]


def score_for(category, dice):
    """Points a set of dice would score in `category` (0 if it doesn't fit)."""
    c = counts(dice)
    if category in UPPER_FACE:
        return c[UPPER_FACE[category] - 1] * UPPER_FACE[category]
    if category == "three_kind":
        return sum(dice) if max(c) >= 3 else 0
    if category == "four_kind":
        return sum(dice) if max(c) >= 4 else 0
    if category == "full_house":
        return 25 if full_house(dice) else 0
    if category == "small_straight":
        return 30 if has_straight(dice, 4) else 0
    if category == "large_straight":
        return 40 if has_straight(dice, 5) else 0
    if category == "yahtzee":
        return YAHTZEE_SCORE if is_yahtzee(dice) else 0
    if category == "chance":
        return sum(dice)
    return 0


def upper_subtotal(p):
    return sum(p["scores"].get(key) or 0 for key in UPPER)


def has_upper_bonus(p):
    return upper_subtotal(p) >= UPPER_BONUS_MIN


def total_score(p):
    total = upper_subtotal(p)
    if has_upper_bonus(p):
        total += UPPER_BONUS
    total += sum(p["scores"].get(key) or 0 for key in LOWER)
    total += p.get("yahtzee_bonus", 0)
    return total


def filled_count(p):
    return sum(1 for v in p["scores"].values() if v is not None)


# ---------- Turn flow ----------
def start_game(g, events):
    if len(g["players"]) < 2:
        return "need at least 2 players"
    if len(g["players"]) > MAX_PLAYERS:
        return f"too many players (max {MAX_PLAYERS})"
    g["phase"] = "playing"
    g["current_index"] = 0
    g["winner_id"] = None
    g["winners"] = []
    begin_turn(g)
    events.append(f"🎲 Yahtzee started with {len(g['players'])} players - "
                  f"fill all {len(CATEGORIES)} boxes; highest total wins.")
    return None


def begin_turn(g):
    g["turn"] = {"rolls": 0, "dice": [], "keep": [False] * DICE_COUNT}


def roll_dice(g, idx, keep=None, events=None):
    """Roll (or reroll) the non-kept dice. keep is 5 booleans (positions
    the player wants to hold). Returns an error string or None."""
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    t = g["turn"]
    if not t:
        return "no turn in progress"
    if t["rolls"] >= MAX_ROLLS:
        return "no rolls left - score a box"
    if keep is None:
        keep = [False] * DICE_COUNT
    if len(keep) != DICE_COUNT:
        return "bad keep selection"
    if t["rolls"] == 0:
        t["dice"] = [random.randint(1, 6) for _ in range(DICE_COUNT)]
        t["keep"] = [False] * DICE_COUNT
    else:
        t["keep"] = [bool(k) for k in keep]
        for i in range(DICE_COUNT):
            if not t["keep"][i]:
                t["dice"][i] = random.randint(1, 6)
    t["rolls"] += 1
    if events is not None:
        label = "Rolled" if t["rolls"] == 1 else f"Reroll {t['rolls'] - 1}"
        events.append(f"🎲 {name_of(g, g['players'][idx]['user_id'])}: "
                      f"{label} [{' '.join(str(d) for d in t['dice'])}]")
    return None


def score_category(g, idx, category, events):
    """Score the current dice in a still-open box and end the turn."""
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    t = g["turn"]
    if not t or t["rolls"] < 1:
        return "roll the dice first"
    p = g["players"][idx]
    if category not in p["scores"]:
        return f"unknown category: {category}"
    if p["scores"][category] is not None:
        return "that box is already filled"
    dice = list(t["dice"])
    value = score_for(category, dice)
    bonus = 0
    # Extra Yahtzee bonus: 5-of-a-kind after the Yahtzee box is already scored.
    if (category != "yahtzee" and is_yahtzee(dice)
            and p["scores"].get("yahtzee")):
        bonus = YAHTZEE_BONUS
        p["yahtzee_bonus"] = p.get("yahtzee_bonus", 0) + YAHTZEE_BONUS
    p["scores"][category] = value
    events.append(f"📝 {p['name']} scores <b>{value}</b> in {CAT_LABEL[category]}"
                  + (f" (+{YAHTZEE_BONUS} Yahtzee bonus!)" if bonus else ""))
    _end_turn(g, events)
    return None


def _end_turn(g, events):
    g["turn"] = None
    if all(filled_count(p) == len(CATEGORIES) for p in g["players"]):
        _finish_game(g, events)
        return
    g["current_index"] = (g["current_index"] + 1) % len(g["players"])
    begin_turn(g)


def _finish_game(g, events):
    g["phase"] = "game_end"
    totals = [total_score(p) for p in g["players"]]
    best = max(totals)
    g["winners"] = [i for i, t in enumerate(totals) if t == best]
    g["winner_id"] = (g["winners"][0] if len(g["winners"]) == 1 else None)
    events.append("🏁 All boxes filled - final scores: "
                  + " · ".join(f"{p['name']} {total_score(p)}" for p in g["players"]))
    if len(g["winners"]) == 1:
        events.append(f"🏆 {g['players'][g['winners'][0]]['name']} wins with {best}!")
    else:
        events.append("🤝 Tie: " + ", ".join(g["players"][i]["name"]
                                             for i in g["winners"]) + f" with {best}!")