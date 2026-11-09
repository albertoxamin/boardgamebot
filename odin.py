"""Odin (Helvetiq, 2024) engine: ladder-climbing card shedding.

2-6 players, 54 cards (numbers 1-9 in 6 colours); with 2 players two
colours are removed (36 cards). Deal 9 each. In turn, lead with 1 card
(or all of your hand if it is a single colour/number), otherwise play
the same number of cards as the table or one more, as a same-colour or
same-number set whose digits, sorted high-to-low, form a higher number
than the table. After playing you take 1 card from the previous set
(rest discarded). Pass freely; when everyone else has passed, the last
player discards the table and leads a new round. Going out ends the
hand at once (no pickup); everyone else scores 1 per card left in
hand. First to 15 points loses the race - lowest score wins.

Hands are private: this module never serialises other players' hands
for display; bot.py filters board JSON per viewer.
"""
import random

# Sheet rows top-to-bottom (BGA odin_cards_minified.jpg, 6 rows x 10 cols).
SUITS = ["blue", "red", "pink", "green", "black", "orange"]
SUIT_HEX = {"blue": "#2563eb", "red": "#dc2626", "pink": "#ec4899",
            "green": "#16a34a", "black": "#111827", "orange": "#f97316"}
RANKS = list(range(1, 10))
HAND_SIZE = 9
WIN_SCORE = 15
MAX_PLAYERS = 6


def card_str(c):
    return f"{c['rank']}{c['suit'][0]}"  # e.g. 6b = 6 blue


def set_value(cards):
    """Digits sorted high-to-low form the number: [2,8] -> 82, [5] -> 5."""
    return int("".join(str(r) for r in sorted((c["rank"] for c in cards), reverse=True)))


def is_mono(cards):
    return (len({c["suit"] for c in cards}) == 1
            or len({c["rank"] for c in cards}) == 1)


def suits_in_play(nplayers):
    return SUITS[:4] if nplayers == 2 else list(SUITS)  # 2P: remove 2 colours


def build_deck(nplayers):
    deck = [{"suit": s, "rank": r} for s in suits_in_play(nplayers) for r in RANKS]
    random.shuffle(deck)
    return deck


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [{"user_id": int(creator_id), "name": creator_name,
                     "hand": [], "score": 0}],
        "phase": "lobby",  # lobby|playing|pickup|game_end
        "deck": [], "discard": [], "table": [], "pending_play": [],
        "table_value": None, "current_index": 0, "last_player": None,
        "passes": 0, "pickup_player": None, "hand_starter": 0, "hand_no": 0,
        "winners": [], "board_message_id": None,
    }


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def start_hand(g, events, starter):
    g["hand_no"] = g.get("hand_no", 0) + 1
    g["deck"] = build_deck(len(g["players"]))
    g["discard"] = []
    g["table"] = []
    g["pending_play"] = []
    g["table_value"] = None
    g["passes"] = 0
    g["pickup_player"] = None
    g["last_player"] = None
    g["hand_starter"] = starter
    g["current_index"] = starter
    for p in g["players"]:
        p["hand"] = [g["deck"].pop() for _ in range(HAND_SIZE)]
    g["phase"] = "playing"
    events.append(f"🃏 New hand dealt (9 each) - {g['players'][starter]['name']} leads with 1 card.")


def start_game(g, events):
    if len(g["players"]) < 2:
        return "need at least 2 players"
    start_hand(g, events, 0)
    return None


def validate_play(g, idx, cards):
    """Returns error string or None. Leadership (empty table) vs response."""
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if not cards:
        return "select at least one card"
    # Caller removes the played cards before calling, so the pre-play
    # hand is hand + cards (ownership itself is checked by the caller).
    hand = g["players"][idx]["hand"] + list(cards)
    if not g["table"]:
        # Leading a round: 1 card, or all of your hand if it is mono.
        if len(cards) == 1 or (len(cards) == len(hand) and is_mono(hand)):
            return None
        return ("lead with 1 card" + (" or all of your hand (single colour/number)"
                                      if is_mono(hand) else ""))
    # Responding to the table set.
    if len(cards) not in (len(g["table"]), len(g["table"]) + 1):
        return f"play {len(g['table'])} or {len(g['table']) + 1} cards"
    if len(cards) >= 2 and not is_mono(cards):
        return "a set of 2+ cards must share a colour or a number"
    if set_value(cards) <= g["table_value"]:
        return f"must beat {g['table_value']} (your set is {set_value(cards)})"
    return None


def end_hand(g, events, winner_idx):
    for p in g["players"]:
        p["score"] += len(p["hand"])
    events.append(f"🏁 {g['players'][winner_idx]['name']} goes out! "
                  + " · ".join(f"{p['name']} +{len(p['hand'])} = {p['score']}"
                               for p in g["players"]))
    if any(p["score"] >= WIN_SCORE for p in g["players"]):
        low = min(p["score"] for p in g["players"])
        g["winners"] = [i for i, p in enumerate(g["players"]) if p["score"] == low]
        g["phase"] = "game_end"
        events.append("🏆 Game over - fewest points wins: "
                      + ", ".join(g["players"][i]["name"] for i in g["winners"]) + "!")
        return
    start_hand(g, events, (g["hand_starter"] + 1) % len(g["players"]))


def play_cards(g, idx, cards, events):
    """Cards are already removed from the player's hand by the caller.
    Returns error or None. Non-lead plays enter the pickup phase."""
    err = validate_play(g, idx, cards)
    if err:
        return err
    name = g["players"][idx]["name"]
    if not g["table"]:
        g["table"] = list(cards)
        g["table_value"] = set_value(cards)
        g["last_player"] = idx
        g["passes"] = 0
        events.append(f"🎴 {name} leads {set_value(cards)} "
                      f"({', '.join(card_str(c) for c in cards)}).")
        if not g["players"][idx]["hand"]:
            end_hand(g, events, idx)
        else:
            g["current_index"] = (idx + 1) % len(g["players"])
        return None
    prev = list(g["table"])
    events.append(f"🎴 {name} plays {set_value(cards)} "
                  f"({', '.join(card_str(c) for c in cards)}) over {g['table_value']}.")
    if not g["players"][idx]["hand"]:
        g["table"] = list(cards)  # hand ends now, no pickup
        end_hand(g, events, idx)
        return None
    g["pending_play"] = list(cards)
    g["pickup_player"] = idx
    g["last_player"] = idx
    g["phase"] = "pickup"
    events.append(f"✋ {name}: take 1 card from the previous set "
                  f"({', '.join(card_str(c) for c in prev)}); the rest are discarded.")
    return None


def choose_pickup(g, idx, card, events):
    if g["phase"] != "pickup":
        return "not in pickup phase"
    if idx != g["pickup_player"]:
        return "only the player who just played picks up"
    match = next((c for c in g["table"]
                  if c["suit"] == card["suit"] and c["rank"] == card["rank"]), None)
    if match is None:
        return "that card is not in the previous set"
    name = g["players"][idx]["name"]
    g["table"] = [c for c in g["table"] if c is not match]
    g["discard"].extend(g["table"])  # the rest of the previous set
    g["players"][idx]["hand"].append(match)
    g["table"] = list(g["pending_play"])
    g["pending_play"] = []
    g["table_value"] = set_value(g["table"])
    g["pickup_player"] = None
    g["passes"] = 0
    g["phase"] = "playing"
    g["current_index"] = (idx + 1) % len(g["players"])
    events.append(f"✋ {name} takes {card_str(match)}; {g['table_value']} to beat.")
    return None


def pass_turn(g, idx, events):
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if not g["table"]:
        return "you must lead a card"
    name = g["players"][idx]["name"]
    events.append(f"⏭ {name} passes.")
    g["passes"] += 1
    if g["passes"] >= len(g["players"]) - 1:
        g["discard"].extend(g["table"])
        g["table"] = []
        g["table_value"] = None
        g["passes"] = 0
        g["current_index"] = g["last_player"]
        events.append(f"🔁 Everyone passed - table discarded, "
                      f"{g['players'][g['last_player']]['name']} leads a new round with 1 card.")
    else:
        g["current_index"] = (idx + 1) % len(g["players"])
    return None
