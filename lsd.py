"""Let's Summon Demons (Cryptozoic / Steven Rhodes Games Vol.1) engine.

2-5 players. Each starts with a Candle in play, 3 hidden Demon cards and
5 Souls. On your turn, once each in any order: roll 2d6 (mandatory),
buy 1 card from THE BLOCK for 3 Souls, summon a Demon by discarding
3 of your Block cards (4 if an opponent has Baphometal). When dice are
rolled, every player's in-play cards matching the total activate
(Demons only on their owner's rolls); Candles collect a Soul on any of
their numbers. First to 3+ summoned Demons AND 10+ Souls wins at once.

Card data below is transcribed from the physical cards (Steven Rhodes
art scans): 38 unique Block cards (100 copies), 20 Demons, 5 Candles.
Effects that need a choice pause resolution in g["pending"] until the
owner responds; choices are rendered as buttons by bot.py / lsd.js.
"""
import random

# ---------------- Card data ----------------
# (slug, name, ctype, align, num, effect, copies)
BLOCK_DATA = [
    # Animals (32 copies: two "strangest" at 1 copy, rest at 3)
    ("alligator", "Alligator", "animal", None, 7, "alligator", 3),
    ("cat", "Cat", "animal", None, 7, "cat", 3),
    ("dog", "Dog", "animal", None, 7, "dog", 3),
    ("goat", "Goat", "animal", None, 7, "goat", 1),
    ("goldfish", "Goldfish", "animal", None, 7, "goldfish", 3),
    ("hawk", "Hawk", "animal", None, 7, "hawk", 3),
    ("owl", "Owl", "animal", None, 7, "owl", 3),
    ("rabbit", "Rabbit", "animal", None, 7, "rabbit", 3),
    ("rabid-dog", "Rabid Dog", "animal", None, 7, "rabid_dog", 3),
    ("rainbow-parrot", "Rainbow Parrot", "animal", None, 7, "rainbow_parrot", 1),
    ("skunk", "Skunk", "animal", None, 7, "skunk", 3),
    ("stray-cat", "Stray Cat", "animal", None, 7, "stray_cat", 3),
    # Neutral kids (10 copies each type: 4+3+3)
    ("adam", "Adam", "boy", None, 8, "soul1", 4),
    ("irwin", "Irwin", "boy", None, 8, "irwin", 3),
    ("romeo", "Romeo", "boy", None, 8, "romeo", 3),
    ("eve", "Eve", "girl", None, 6, "soul1", 4),
    ("jane", "Jane", "girl", None, 6, "jane", 3),
    ("lola", "Lola", "girl", None, 6, "lola", 3),
    # Rotten boys (12 copies: 2 each)
    ("rotten-calvin", "Rotten Calvin", "boy", "rotten", 9, "calvin", 2),
    ("rotten-damian", "Rotten Damian", "boy", "rotten", 11, "damian", 2),
    ("rotten-dillinger", "Rotten Dillinger", "boy", "rotten", 10, "dillinger", 2),
    ("rotten-donnie", "Rotten Donnie", "boy", "rotten", 12, "donnie", 2),
    ("rotten-sam", "Rotten Sam", "boy", "rotten", 10, "sam", 2),
    ("rotten-tommy", "Rotten Tommy", "boy", "rotten", 9, "tommy", 2),
    # Rotten girls (12 copies: 3 each)
    ("rotten-annie", "Rotten Annie", "girl", "rotten", 9, "annie", 3),
    ("rotten-carrie", "Rotten Carrie", "girl", "rotten", 11, "soul2", 3),
    ("rotten-delores", "Rotten Delores", "girl", "rotten", 10, "delores", 3),
    ("rotten-regan", "Rotten Regan", "girl", "rotten", 9, "soul1", 3),
    # Sweet boys (12 copies: 3 each)
    ("sweet-chuck", "Sweet Chuck", "boy", "sweet", 4, "chuck", 3),
    ("sweet-glen", "Sweet Glen", "boy", "sweet", 5, "glen", 3),
    ("sweet-jesus", "Sweet Jesus", "boy", "sweet", 3, "soul2", 3),
    ("sweet-louis", "Sweet Louis", "boy", "sweet", 5, "soul1", 3),
    # Sweet girls (12 copies: 2 each)
    ("sweet-alice", "Sweet Alice", "girl", "sweet", 4, "alice", 2),
    ("sweet-caroline", "Sweet Caroline", "girl", "sweet", 2, "soul5", 2),
    ("sweet-destiny", "Sweet Destiny", "girl", "sweet", 5, "destiny", 2),
    ("sweet-lisa", "Sweet Lisa", "girl", "sweet", 3, "lisa", 2),
    ("sweet-marylin", "Sweet Marylin", "girl", "sweet", 5, "marylin", 2),
    ("sweet-pippi", "Sweet Pippi", "girl", "sweet", 4, "pippi", 2),
]
assert sum(c[6] for c in BLOCK_DATA) == 100

# (slug, name, num or None for ongoing, effect) - Demons activate on the
# owner's rolls only; None means a persistent (infinity) power.
DEMON_DATA = [
    ("anti-christ", "Anti-Christ", 10, "anti_christ"),
    ("asmodeus", "Asmodeus", None, "asmodeus"),
    ("baala-bad-dog", "Baala Bad Dog", 8, "baala"),
    ("baphometal", "Baphometal", None, "baphometal"),
    ("beelzebuddy", "Beelze'Buddy", 7, "beelzebuddy"),
    ("the-gross-book-of-demons", "The Gross Book of Demons", 3, "gross_book"),
    ("clockwork-satan", "Clockwork Satan", 9, "clockwork"),
    ("dice-zuzzu", "Dice-Zuzzu", None, "dice_zuzzu"),
    ("dollagorgon", "Dollagorgon", None, "dollagorgon"),
    ("krampus", "Krampus", 4, "krampus"),
    ("nine-stopheles", "Nine-Stopheles", 11, "nine_stopheles"),
    ("oni-twi", "Oni Twi", None, "oni_twi"),
    ("porkus", "Porkus", 5, "porkus"),
    ("re-rollucifer", "Re-Rollucifer", None, "rerollucifer"),
    ("rosemarys-egg", "Rosemary's Egg", None, "rosemarys_egg"),
    ("the-serpent", "The Serpent", 2, "serpent"),
    ("succubus-twin", "Succubus Twin", None, "succubus_twin"),
    ("the-devil", "The Devil", 12, "the_devil"),
    ("wee-r-legion", "Wee 'R' Legion", 6, "wee_r_legion"),
    ("wraithlok", "Wraithlok", None, "wraithlok"),
]
assert len(DEMON_DATA) == 20

CANDLE_DATA = [  # (slug, name, activation numbers) - always "Collect a Soul."
    ("evil-candle", "Evil Candle", [9, 10, 11]),
    ("good-candle", "Good Candle", [3, 4, 5]),
    ("kind-candle", "Kind Candle", [5, 6]),
    ("naughty-candle", "Naughty Candle", [8, 9]),
    ("beginners-candle", "Beginner's Candle", [6, 8]),
]
assert len(CANDLE_DATA) == 5

START_SOULS = 5
BUY_COST = 3
MARKET_SIZE = 5
WIN_DEMONS = 3
WIN_SOULS = 10
TOTAL_SOUL_TOKENS = 40
MAX_PLAYERS = 5


def _card(slug, name, kind, ctype, align, num, nums, eff):
    return {"slug": slug, "name": name, "kind": kind, "ctype": ctype,
            "align": align, "num": num, "nums": nums, "eff": eff}


def build_block_deck():
    deck = []
    for slug, name, ctype, align, num, eff, copies in BLOCK_DATA:
        for _ in range(copies):
            deck.append(_card(slug, name, "block", ctype, align, num, None, eff))
    random.shuffle(deck)
    return deck


def build_demon_deck():
    deck = [_card(slug, name, "demon", None, None, num, None, eff)
            for slug, name, num, eff in DEMON_DATA]
    random.shuffle(deck)
    return deck


def build_candles():
    return [_card(slug, name, "candle", None, None, None, nums, "candle")
            for slug, name, nums in CANDLE_DATA]


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [{"user_id": int(creator_id), "name": creator_name,
                     "souls": START_SOULS, "candle": None, "in_play": [],
                     "demons": [], "demon_hand": []}],
        "phase": "lobby",  # lobby|playing|game_end
        "block_deck": [], "market": [], "discard": [],
        "demon_deck": [], "demon_discard": [],
        "supply": TOTAL_SOUL_TOKENS, "current_index": 0,
        "turn": {"rolled": False, "bought": False, "summoned": False, "only_mine": False},
        "dice": None, "last_total": None, "winner": None,
        "pending": None, "act_queue": [], "activated": [],
        "extra_turn": False, "roll_ctx": None, "next_iid": 1,
        "board_message_id": None,
    }


def _mk(g, card):
    card = dict(card)
    card["iid"] = g["next_iid"]
    g["next_iid"] += 1
    return card


def start_game(g, events):
    if len(g["players"]) < 2:
        return "need at least 2 players"
    if len(g["players"]) > MAX_PLAYERS:
        return "too many players (max 5)"
    g["block_deck"] = [_mk(g, c) for c in build_block_deck()]
    g["demon_deck"] = [_mk(g, c) for c in build_demon_deck()]
    g["discard"] = []
    g["demon_discard"] = []
    g["supply"] = TOTAL_SOUL_TOKENS - START_SOULS * len(g["players"])
    candles = [_mk(g, c) for c in build_candles()]
    random.shuffle(candles)
    for p in g["players"]:
        p["souls"] = START_SOULS
        p["candle"] = candles.pop()
        p["in_play"] = []
        p["demons"] = []
        p["demon_hand"] = [g["demon_deck"].pop() for _ in range(3)]
    g["market"] = [g["block_deck"].pop() for _ in range(MARKET_SIZE)]
    g["current_index"] = 0
    g["phase"] = "playing"
    g["turn"] = {"rolled": False, "bought": False, "summoned": False, "only_mine": False}
    g["dice"] = None
    g["pending"] = None
    g["act_queue"] = []
    events.append(f"😈 Let's Summon Demons started! {g['players'][0]['name']} "
                  f"takes the first turn. Souls: {g['supply']} in supply.")
    return None


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def find_card(g, iid):
    """(owner_idx, card) for an in-play/demon/candle card, else (None, None)."""
    for i, p in enumerate(g["players"]):
        if p["candle"] and p["candle"]["iid"] == iid:
            return i, p["candle"]
        for c in p["in_play"] + p["demons"]:
            if c["iid"] == iid:
                return i, c
    return None, None


def has_demon(g, idx, eff):
    return any(c["eff"] == eff for c in g["players"][idx]["demons"])


def _kids(g, idx):
    return [c for c in g["players"][idx]["in_play"] if c["ctype"] in ("boy", "girl")]


def type_count(g, idx, ctype):
    """Count of a type, honouring Dollagorgon (boys<->girls)."""
    cards = _kids(g, idx)
    if has_demon(g, idx, "dollagorgon"):
        return len(cards)
    return sum(1 for c in cards if c["ctype"] == ctype)


def align_count(g, idx, align, exclude_iid=None):
    """Sweet/Rotten kid count; Succubus Twin makes all kids count as both."""
    cards = [c for c in _kids(g, idx) if c["iid"] != exclude_iid]
    if has_demon(g, idx, "succubus_twin"):
        return len(cards)
    return sum(1 for c in cards if c["align"] == align)


def gain_souls(g, idx, n, events, source=None):
    """Collect n souls from the supply (capped). Oni Twi doubles boy/girl
    cards' souls on the owner's own turns."""
    if n <= 0:
        return 0
    if (source is not None and source["ctype"] in ("boy", "girl")
            and has_demon(g, idx, "oni_twi")
            and g.get("roll_ctx") and g["roll_ctx"]["roller"] == idx):
        n *= 2
    got = min(n, g["supply"])
    g["supply"] -= got
    g["players"][idx]["souls"] += got
    if got:
        events.append(f"👻 {g['players'][idx]['name']} collects {got} Soul(s).")
    return got


def steal_souls(g, thief, amount, target, events):
    """target: player index or 'supply'. Returns souls actually stolen."""
    if target == "supply":
        got = min(amount, g["supply"])
        g["supply"] -= got
    else:
        got = min(amount, g["players"][target]["souls"])
        g["players"][target]["souls"] -= got
    g["players"][thief]["souls"] += got
    if got:
        src = "the supply" if target == "supply" else g["players"][target]["name"]
        events.append(f"👻 {g['players'][thief]['name']} steals {got} Soul(s) from {src}.")
    return got


def gain_card(g, idx, card, events):
    """Put a Block card into play for a player (Asmodeus hook applies)."""
    g["players"][idx]["in_play"].append(card)
    if card["ctype"] == "animal" and has_demon(g, idx, "asmodeus"):
        events.append(f"🐴 Asmodeus: {g['players'][idx]['name']} gained an Animal.")
        gain_souls(g, idx, 1, events)


def discard_from_play(g, idx, card, events, cause=None):
    p = g["players"][idx]
    if card in p["in_play"]:
        p["in_play"].remove(card)
        g["discard"].append(card)
        events.append(f"🗑 {p['name']} discards {card['name']}.")
        return True
    for lst in ("demons",):
        if card in p[lst]:
            p[lst].remove(card)
            g["demon_discard"].append(card)
            events.append(f"🗑 {p['name']} discards {card['name']}.")
            return True
    return False


def summon_cost(g, idx):
    """3, or 4 for other players while an opponent has Baphometal."""
    for j, p in enumerate(g["players"]):
        if j != idx and has_demon(g, j, "baphometal"):
            return 4
    return 3


def check_win(g, events):
    if g["phase"] == "game_end":
        return True
    for p in g["players"]:
        if len(p["demons"]) >= WIN_DEMONS and p["souls"] >= WIN_SOULS:
            g["phase"] = "game_end"
            g["winner"] = p["user_id"]
            events.append(f"🏆 {p['name']} has {len(p['demons'])} Demons and "
                          f"{p['souls']} Souls - ultimate Demon Summoner wins!")
            return True
    return False


def summon_demon(g, idx, demon, events, free=False):
    """Move a Demon from hand into play. Rosemary's Egg is handled by the
    caller via a pending choice (it is discarded and replaced)."""
    p = g["players"][idx]
    if demon in p["demon_hand"]:
        p["demon_hand"].remove(demon)
    p["demons"].append(demon)
    events.append(f"😈 {p['name']} summons {demon['name']}!"
                  + (" (for free)" if free else ""))
    check_win(g, events)


def _reshuffle(g, deck_key, discard_key, events):
    if not g[deck_key] and g[discard_key]:
        g[deck_key] = g[discard_key]
        g[discard_key] = []
        random.shuffle(g[deck_key])
        events.append("🔀 Discards reshuffled into a new deck.")


def draw_block(g, events):
    _reshuffle(g, "block_deck", "discard", events)
    return g["block_deck"].pop() if g["block_deck"] else None


def refill_market(g, events):
    while len(g["market"]) < MARKET_SIZE:
        c = draw_block(g, events)
        if c is None:
            break
        g["market"].append(c)


def end_turn(g, events):
    """Refill THE BLOCK and pass (or repeat, after Clockwork Satan)."""
    refill_market(g, events)
    if g.get("extra_turn"):
        g["extra_turn"] = False
        g["turn"] = {"rolled": False, "bought": False, "summoned": False, "only_mine": True}
        events.append(f"⏰ {g['players'][g['current_index']]['name']} takes an "
                      f"additional turn - only their cards can activate!")
    else:
        g["current_index"] = (g["current_index"] + 1) % len(g["players"])
        g["turn"] = {"rolled": False, "bought": False, "summoned": False, "only_mine": False}
    g["dice"] = None
    g["last_total"] = None
    g["activated"] = []
