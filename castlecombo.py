"""Castle Combo (Catch Up Games, 2024) engine.

2-5 players. Two 39-card decks (Castle / Village); each turn the active
player may spend 1 key (move the messenger to the other row, or discard and
renew the 3 face-up cards of the messenger's row), then MUST take one of the
messenger's row cards: pay its cost (minus discounts from owned face-up
cards) or flip it face-down for +6 gold +2 keys. Cards are placed in the
player's floating 3x3 tableau (orthogonally adjacent, never a 4th card in a
row/column), then their ability applies. Cards with a messenger pennant move
the messenger to the other row (all 39 messenger cards send it to the
opposite of their own row). Both displays refill to 3. Everyone takes
exactly one card per turn, so after 9 rounds all players have 9 cards and
the game ends: leftover gold is stored on purses (up to capacity), face-up
cards score their scrolls, keys are 1 point each, face-down cards score 0.
Most points wins; ties broken by leftover (unstored) gold, then shared win.

Rules verified against the official rulebook (Catch Up Games) and the card
faces. Card data cross-checked against the BGA client and card images.
Documented approximations:
- "Neighbor" abilities (one of the players to your left/right) ask the player
  to choose the neighbor.
- OR abilities (e.g. "X OR gain 2 keys") ask the player to choose.
- End-of-game purse filling is automatic, largest purse first (the physical
  game lets the player distribute; this maximises Patron-style thresholds).
- Position conditions use the bounding box of the tableau (they are only
  relevant at game end, where every tableau is a full 3x3, so this equals
  the physical result).
- "Empty space" = one of the 9 tableau spaces without a card, "full space" =
  an occupied space (the printed 3x3 icon in the game aid).
"""
import random

MAX_PLAYERS = 5
START_GOLD = 15
START_KEYS = 2
FLIP_GOLD = 6
FLIP_KEYS = 2
ROUNDS = 9

# Shield colours (BGA icon codes)
RED, ORANGE, BLUE, PURPLE, GREEN, YELLOW = 1, 2, 3, 4, 5, 6
SH_EMOJI = {1: "🛡️", 2: "🛡️", 3: "🛡️", 4: "🛡️", 5: "🛡️", 6: "🛡️"}
SH_NAME = {1: "red", 2: "orange", 3: "blue", 4: "purple", 5: "green", 6: "yellow"}
CASTLE, VILLAGE = 1, 2
LOC_EMOJI = {CASTLE: "🏰", VILLAGE: "🏘️"}


def _c(cid, t, name, loc, cost, sh, mm=0, purse=0, disc=0, ab=None, sc=None, txt=""):
    return {"id": cid, "t": t, "name": name, "loc": loc, "cost": cost,
            "sh": sh, "mm": bool(mm), "purse": purse, "disc": disc,
            "ab": ab, "sc": sc, "txt": txt}


# Card table. Card id == BGA sprite position t (1-39 Castle, 41-79 Village),
# so the Mini App can place art directly from the id. Ability (ab) and
# scoring (sc) encodings:
#   conditions: int=shield colour count, "diff"=distinct shield types,
#   "pmiss"=missing shield types, ("b",loc)=Castle/Village banners,
#   ("single",)/(double,)=cards with 1/2 shields, ("cost",v)=cards costing v,
#   ("purse",)=cards with a purse, ("disc",)=cards with a discount,
#   ("empty",)/("full",)=tableau spaces, ("flip",)=face-down cards,
#   ("nb",cond,res,n)=per cond in a chosen neighbour player's tableau
#   "where" for score shields: "row"/"col"/"rc"(row or column)/"all"
#   abilities: ("g",cond,n)/("k",cond,n) gain n gold/keys per cond,
#   ("gsum",[conds],n) gold per summed conds, ("and",[ab..]), ("or",[ab..]),
#   ("purses",n) n gold on each own purse, ("purse2",) Steward,
#   ("gain",res,n), ("opp",res,n) opponents gain, ("allk",n) all players keys,
#   ("drop",loc) discard a display card of loc and gain its cost
#   scoring: ("sh",where,sh,n), ("diff",where,n), ("pos",[slots],n),
#   ("miss",sh,n), ("pmiss",n), ("pair",a,b,n), ("tri",a,b,c,n),
#   ("sets",n) per set of 3 identical shields, ("bset",loc,n),
#   ("cnt",cond,n), ("flany",n), ("keys",n), ("purse",cap,n) own purse gold,
#   ("pall",n) all stored gold, ("prich",n) per purse holding 5+ gold
CARDS = [
    # ------------------------------------------------------------- Castle
    _c(1, 1, "His Majesty", CASTLE, 6, [BLUE, PURPLE], mm=1,
       ab=("opp", "gold", 1), sc=("sh", "col", BLUE, 4),
       txt="Your opponents gain 1 gold."),
    _c(2, 2, "Prince", CASTLE, 6, [BLUE],
       ab=("g", BLUE, 1), sc=("sh", "row", BLUE, 4),
       txt="Gain 1 gold per blue shield in your tableau."),
    _c(3, 3, "Princess", CASTLE, 3, [BLUE], mm=1, disc=CASTLE,
       sc=("sh", "row", BLUE, 3), txt="Discount of 1 on Castle cards."),
    _c(4, 4, "Chancellor", CASTLE, 6, [BLUE, GREEN],
       ab=("k", GREEN, 1), sc=("cnt", ("b", CASTLE), 2),
       txt="Gain 1 key per green shield in your tableau."),
    _c(5, 5, "Jester", CASTLE, 3, [BLUE], mm=1,
       ab=("g", BLUE, 2), sc=("sh", "rc", BLUE, 2),
       txt="Gain 2 gold per blue shield in your tableau."),
    _c(6, 6, "Queen Mother", CASTLE, 3, [BLUE, BLUE], purse=5,
       ab=("purses", 2), sc=("purse", 5, 2),
       txt="Add 2 gold to each purse. Stores up to 5 gold (2 pts each)."),
    _c(7, 7, "Her Majesty the Queen", CASTLE, 7, [BLUE],
       ab=("k", BLUE, 1), sc=("tri", BLUE, GREEN, ORANGE, 10),
       txt="Gain 1 key per blue shield in your tableau."),
    _c(8, 8, "Baron", CASTLE, 3, [BLUE], disc=3,
       sc=("miss", YELLOW, 10), txt="Discount of 1 on all cards."),
    _c(9, 9, "Duchess", CASTLE, 5, [BLUE, BLUE],
       ab=("gain", "keys", 2), sc=("pos", [1, 2, 3], 8),
       txt="Gain 2 keys."),
    _c(10, 10, "Steward", CASTLE, 0, [BLUE], purse=3,
       ab=("purse2",), sc=("purse", 3, 2),
       txt="Place gold on two of your purses until they are full. Stores up to 3 gold."),
    _c(11, 11, "Mother Superior", CASTLE, 5, [PURPLE, PURPLE],
       ab=("gain", "keys", 4), sc=("pos", [1, 2, 3], 8), txt="Gain 4 keys."),
    _c(12, 12, "Scribe", CASTLE, 4, [PURPLE], mm=1,
       ab=("g", PURPLE, 1), sc=("sh", "rc", GREEN, 3),
       txt="Gain 1 gold per purple shield in your tableau."),
    _c(13, 13, "Gravedigger", CASTLE, 4, [PURPLE, GREEN], purse=8,
       ab=("drop", VILLAGE), sc=("purse", 8, 2),
       txt="Discard one Village card from the display and gain its cost in gold. Stores up to 8 gold."),
    _c(14, 14, "Templar", CASTLE, 5, [PURPLE, RED], mm=1,
       ab=("or", [("nb", PURPLE, "gold", 1), ("k", RED, 1)]), sc=("keys", 1),
       txt="Choose: 1 gold per purple shield of one neighbor, OR 1 key per red shield in your tableau."),
    _c(15, 15, "Cardinal", CASTLE, 4, [PURPLE],
       ab=("k", ("b", CASTLE), 1), sc=("sh", "row", PURPLE, 3),
       txt="Gain 1 key per Castle banner in your tableau."),
    _c(16, 16, "Chaplain", CASTLE, 5, [PURPLE], mm=1,
       ab=("g", ("single",), 1), sc=("cnt", ("b", VILLAGE), 2),
       txt="Gain 1 gold per single-shield card in your tableau."),
    _c(17, 17, "His Holiness", CASTLE, 7, [PURPLE],
       ab=("or", [("gain", "keys", 3), ("opp", "keys", 1)]), sc=("pmiss", 6),
       txt="Choose: gain 3 keys, OR your opponents gain 1 key."),
    _c(18, 18, "Nun", CASTLE, 3, [PURPLE], mm=1,
       ab=("g", ("b", CASTLE), 1), sc=("sh", "col", PURPLE, 3),
       txt="Gain 1 gold per Castle banner in your tableau."),
    _c(19, 19, "Devout", CASTLE, 4, [PURPLE],
       ab=("g", ("empty",), 1), sc=("miss", ORANGE, 10),
       txt="Gain 1 gold per empty space in your tableau."),
    _c(20, 20, "Pilgrim", CASTLE, 6, [PURPLE], mm=1, disc=VILLAGE,
       sc=("diff", "row", 4), txt="Discount of 1 on Village cards."),
    _c(21, 21, "Astronomer", CASTLE, 5, [GREEN, GREEN], disc=CASTLE,
       sc=("pos", [1, 4, 7], 8), txt="Discount of 1 on Castle cards."),
    _c(22, 22, "Alchemist", CASTLE, 6, [GREEN], disc=3,
       sc=("cnt", ("disc",), 4), txt="Discount of 1 on all cards."),
    _c(23, 23, "Professor", CASTLE, 4, [GREEN], mm=1,
       ab=("g", "diff", 1), sc=("sh", "row", GREEN, 3),
       txt="Gain 1 gold per different shield type in your tableau."),
    _c(24, 24, "Apothecary", CASTLE, 3, [GREEN], mm=1, disc=CASTLE,
       sc=("sh", "col", GREEN, 3), txt="Discount of 1 on Castle cards."),
    _c(25, 25, "Goldsmith", CASTLE, 4, [GREEN, ORANGE], mm=1,
       ab=("k", ("double",), 1), sc=("pos", [1, 4, 7], 6),
       txt="Gain 1 key per two-shield card in your tableau."),
    _c(26, 26, "Architect", CASTLE, 4, [GREEN], mm=1, disc=VILLAGE,
       sc=("diff", "all", 2), txt="Discount of 1 on Village cards."),
    _c(27, 27, "Patron", CASTLE, 7, [GREEN],
       ab=("opp", "gold", 2), sc=("prich", 5),
       txt="Your opponents gain 2 gold."),
    _c(28, 28, "Judge", CASTLE, 4, [GREEN], mm=1,
       ab=("gain", "keys", 2), sc=("pair_b", 3),
       txt="Gain 2 keys."),
    _c(29, 29, "Captain", CASTLE, 5, [RED, RED], mm=1, disc=VILLAGE,
       sc=("pos", [3, 6, 9], 8), txt="Discount of 1 on Village cards."),
    _c(30, 30, "Knight", CASTLE, 5, [RED],
       ab=("g", RED, 1), sc=("sh", "rc", BLUE, 3),
       txt="Gain 1 gold per red shield in your tableau."),
    _c(31, 31, "Royal Guard", CASTLE, 4, [BLUE, RED], mm=1,
       ab=("allk", 1), sc=("sh", "col", BLUE, 3),
       txt="All players gain 1 key."),
    _c(32, 32, "Lookout", CASTLE, 6, [RED],
       ab=("k", RED, 1), sc=("diff", "col", 4),
       txt="Gain 1 key per red shield in your tableau."),
    _c(33, 33, "Officer", CASTLE, 5, [RED],
       ab=("gsum", [BLUE, RED], 1), sc=("pair", BLUE, RED, 4),
       txt="Gain 1 gold per blue shield and 1 gold per red shield in your tableau."),
    _c(34, 34, "General", CASTLE, 7, [RED],
       ab=("k", "diff", 1), sc=("sets", 6),
       txt="Gain 1 key per different shield type in your tableau."),
    _c(35, 35, "Guildmaster", CASTLE, 5, [ORANGE, ORANGE], mm=1,
       ab=("drop", VILLAGE), sc=("pos", [7, 8, 9], 5),
       txt="Discard one Village card from the display and gain its cost in gold."),
    _c(36, 36, "Glassblower", CASTLE, 5, [ORANGE], mm=1,
       ab=("gsum", [PURPLE, ORANGE], 1), sc=("pair", PURPLE, ORANGE, 4),
       txt="Gain 1 gold per purple shield and 1 gold per orange shield in your tableau."),
    _c(37, 37, "Chatelaine", CASTLE, 2, [BLUE, ORANGE], disc=CASTLE,
       sc=("diff", "row", 2), txt="Discount of 1 on Castle cards."),
    _c(38, 38, "Pawnbroker", CASTLE, 4, [ORANGE], mm=1,
       ab=("g", ("cost", 4), 1), sc=("cnt", ("cost", 4), 3),
       txt="Gain 1 gold per card with a cost of 4 gold in your tableau."),
    _c(39, 39, "Banker", CASTLE, 7, [ORANGE], mm=1,
       ab=("or", [("purses", 2), ("gain", "keys", 3)]), sc=("pall", 1),
       txt="Choose: 2 gold on each purse, OR gain 3 keys. Scores 1 pt per gold stored on purses."),
    # ------------------------------------------------------------ Village
    _c(41, 41, "Miraculously cured!", VILLAGE, 2, [PURPLE, PURPLE], mm=1, purse=4,
       ab=("k", ("purse",), 1), sc=("purse", 4, 2),
       txt="Gain 1 key per card with a purse in your tableau. Stores up to 4 gold."),
    _c(42, 42, "Vicar", VILLAGE, 0, [PURPLE], mm=1, purse=5,
       ab=("g", ("b", VILLAGE), 1), sc=("purse", 5, 2),
       txt="Gain 1 gold per Village banner in your tableau. Stores up to 5 gold."),
    _c(43, 43, "Spy", VILLAGE, 4, [GREEN, RED],
       ab=("and", [("g", GREEN, 1), ("nb", RED, "keys", 1)]), sc=("pos", [2, 5, 8], 6),
       txt="Gain 1 gold per green shield in your tableau AND 1 key per red shield of one neighbor."),
    _c(44, 44, "Philosopher", VILLAGE, 2, [GREEN], disc=CASTLE,
       sc=("miss", RED, 10), txt="Discount of 1 on Castle cards."),
    _c(45, 45, "Doctor", VILLAGE, 5, [GREEN], mm=1,
       ab=("gsum", [GREEN, YELLOW], 1), sc=("pair", GREEN, YELLOW, 4),
       txt="Gain 1 gold per green shield and 1 gold per yellow shield in your tableau."),
    _c(46, 46, "Inventor", VILLAGE, 2, [GREEN, GREEN],
       ab=("g", GREEN, 1), sc=("cnt", ("b", VILLAGE), 1),
       txt="Gain 1 gold per green shield in your tableau."),
    _c(47, 47, "Squire", VILLAGE, 0, [RED], disc=3,
       sc=("sh", "rc", ORANGE, 2), txt="Discount of 1 on all cards."),
    _c(48, 48, "Bombardier", VILLAGE, 2, [RED],
       ab=("or", [("nb", ORANGE, "gold", 1), ("gain", "keys", 2)]), sc=("sh", "col", RED, 3),
       txt="Choose: 1 gold per orange shield of one neighbor, OR gain 2 keys."),
    _c(49, 49, "Militiaman", VILLAGE, 2, [RED], mm=1,
       ab=("or", [("nb", YELLOW, "gold", 1), ("gain", "keys", 2)]), sc=("sh", "row", RED, 3),
       txt="Choose: 1 gold per yellow shield of one neighbor, OR gain 2 keys."),
    _c(50, 50, "Barbarian", VILLAGE, 2, [RED], mm=1,
       ab=("or", [("nb", GREEN, "gold", 1), ("gain", "keys", 2)]), sc=("miss", GREEN, 10),
       txt="Choose: 1 gold per green shield of one neighbor, OR gain 2 keys."),
    _c(51, 51, "Executioner", VILLAGE, 0, [RED], mm=1,
       ab=("drop", CASTLE), sc=("cnt", ("b", CASTLE), 1),
       txt="Discard one Castle card from the display and gain its cost in gold."),
    _c(52, 52, "Mercenary", VILLAGE, 6, [RED, YELLOW],
       ab=("g", "diff", 1), sc=("tri", PURPLE, RED, YELLOW, 7),
       txt="Gain 1 gold per different shield type in your tableau."),
    _c(53, 53, "Master-at-arms", VILLAGE, 2, [RED, RED], purse=4,
       ab=("g", RED, 1), sc=("purse", 4, 2),
       txt="Gain 1 gold per red shield in your tableau. Stores up to 4 gold."),
    _c(54, 54, "Blacksmith", VILLAGE, 5, [RED, ORANGE],
       ab=("or", [("nb", BLUE, "gold", 1), ("gain", "keys", 2)]), sc=("cnt", ("double",), 2),
       txt="Choose: 1 gold per blue shield of one neighbor, OR gain 2 keys."),
    _c(55, 55, "Stonemason", VILLAGE, 3, [ORANGE], mm=1, disc=VILLAGE,
       sc=("sh", "col", ORANGE, 3), txt="Discount of 1 on Village cards."),
    _c(56, 56, "Potter", VILLAGE, 2, [ORANGE, ORANGE], mm=1, purse=4,
       ab=("purses", 2), sc=("purse", 4, 2),
       txt="Add 2 gold to each purse. Stores up to 4 gold."),
    _c(57, 57, "Armorer", VILLAGE, 3, [ORANGE], disc=3,
       sc=("sh", "rc", RED, 3), txt="Discount of 1 on all cards."),
    _c(58, 58, "Spice Merchant", VILLAGE, 0, [ORANGE],
       ab=("g", ORANGE, 2), sc=("pos", [4, 5, 6], 5),
       txt="Gain 2 gold per orange shield in your tableau."),
    _c(59, 59, "Clockmaker", VILLAGE, 3, [ORANGE], mm=1,
       ab=("g", ORANGE, 1), sc=("sh", "row", ORANGE, 3),
       txt="Gain 1 gold per orange shield in your tableau."),
    _c(60, 60, "Sculptor", VILLAGE, 3, [PURPLE, ORANGE], mm=1, purse=7,
       ab=("k", PURPLE, 1), sc=("purse", 7, 2),
       txt="Gain 1 key per purple shield in your tableau. Stores up to 7 gold."),
    _c(61, 61, "Innkeeper", VILLAGE, 0, [ORANGE], purse=6,
       ab=("and", [("purses", 2), ("opp", "gold", 2)]), sc=("purse", 6, 2),
       txt="Add 2 gold to each purse AND your opponents gain 2 gold. Stores up to 6 gold."),
    _c(62, 62, "Carpenter", VILLAGE, 0, [ORANGE], mm=1,
       ab=("g", "pmiss", 1), sc=("flany", 8),
       txt="Gain 1 gold per shield type missing from your tableau."),
    _c(63, 63, "Locksmith", VILLAGE, 4, [ORANGE, YELLOW], mm=1,
       ab=("k", ORANGE, 1), sc=("keys", 1),
       txt="Gain 1 key per orange shield in your tableau."),
    _c(64, 64, "Farmer", VILLAGE, 5, [YELLOW, YELLOW], mm=1,
       ab=("k", YELLOW, 1), sc=("pos", [7, 8, 9], 7),
       txt="Gain 1 key per yellow shield in your tableau."),
    _c(65, 65, "Woodcutter", VILLAGE, 0, [YELLOW],
       ab=("g", ("full",), 1), sc=("pos", [3, 6, 9], 5),
       txt="Gain 1 gold per full space in your tableau."),
    _c(66, 66, "Brigand", VILLAGE, 7, [YELLOW],
       ab=("nb", ("b", CASTLE), "keys", 1), sc=("bset", VILLAGE, 7),
       txt="Gain 1 key per Castle banner of one neighbor."),
    _c(67, 67, "Witch", VILLAGE, 4, [YELLOW], mm=1,
       ab=("or", [("g", YELLOW, 1), ("nb", PURPLE, "keys", 1)]), sc=("miss", PURPLE, 9),
       txt="Choose: 1 gold per yellow shield in your tableau, OR 1 key per purple shield of one neighbor."),
    _c(68, 68, "Beggar", VILLAGE, 0, [YELLOW],
       ab=("g", ("full",), 1), sc=("sh", "rc", PURPLE, 2),
       txt="Gain 1 gold per full space in your tableau."),
    _c(69, 69, "Monk", VILLAGE, 4, [PURPLE, YELLOW], mm=1,
       ab=("k", PURPLE, 1), sc=("sh", "row", YELLOW, 2),
       txt="Gain 1 key per purple shield in your tableau."),
    _c(70, 70, "Shepherd", VILLAGE, 5, [YELLOW], mm=1,
       ab=("g", ("empty",), 1), sc=("sh", "row", YELLOW, 3),
       txt="Gain 1 gold per empty space in your tableau."),
    _c(71, 71, "Winemaker", VILLAGE, 2, [GREEN, YELLOW],
       ab=("g", ("b", VILLAGE), 1), sc=("diff", "col", 2),
       txt="Gain 1 gold per Village banner in your tableau."),
    _c(72, 72, "Stable Boy", VILLAGE, 4, [BLUE, YELLOW],
       ab=("k", BLUE, 1), sc=("sh", "col", YELLOW, 3),
       txt="Gain 1 key per blue shield in your tableau."),
    _c(73, 73, "Farmhand", VILLAGE, 0, [YELLOW], mm=1, purse=5, disc=VILLAGE,
       sc=("purse", 5, 2), txt="Discount of 1 on Village cards. Stores up to 5 gold."),
    _c(74, 74, "Traveler", VILLAGE, 0, [YELLOW],
       ab=("g", ("cost", 0), 3), sc=("cnt", ("cost", 0), 2),
       txt="Gain 3 gold per 0-cost card in your tableau."),
    _c(75, 75, "Usurper", VILLAGE, 5, [YELLOW], mm=1,
       ab=("k", ("single",), 1), sc=("cnt", ("b", CASTLE), 2),
       txt="Gain 1 key per single-shield card in your tableau."),
    _c(76, 76, "Fisherman", VILLAGE, 2, [YELLOW, YELLOW], disc=CASTLE,
       sc=("pos", [1, 3, 7, 9], 4), txt="Discount of 1 on Castle cards."),
    _c(77, 77, "Revolutionary", VILLAGE, 4, [YELLOW], mm=1,
       ab=("k", ("b", VILLAGE), 1), sc=("miss", BLUE, 9),
       txt="Gain 1 key per Village banner in your tableau."),
    _c(78, 78, "Baker", VILLAGE, 0, [YELLOW],
       ab=("and", [("g", YELLOW, 1), ("k", ("b", VILLAGE), 1)]),
       sc=("pos", [2, 4, 6, 8], 3),
       txt="Gain 1 gold per yellow shield in your tableau AND 1 key per Village banner."),
    _c(79, 79, "Beekeeper", VILLAGE, 2, [YELLOW], purse=9,
       ab=("purses", 2), sc=("purse", 9, 2),
       txt="Add 2 gold to each purse. Stores up to 9 gold."),
]

CARD = {c["id"]: c for c in CARDS}
CASTLE_IDS = [c["id"] for c in CARDS if c["loc"] == CASTLE]
VILLAGE_IDS = [c["id"] for c in CARDS if c["loc"] == VILLAGE]
assert len(CARDS) == 78 and len(CASTLE_IDS) == 39 and len(VILLAGE_IDS) == 39


def card_of(inst):
    return CARD[inst["cid"]]


def card_name(inst):
    return "?" if inst.get("fd") else card_of(inst)["name"]


# ------------------------------------------------------------------ setup

def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [], "phase": "lobby",
        "decks": {CASTLE: [], VILLAGE: []},
        "discards": {CASTLE: [], VILLAGE: []},
        "rows": {CASTLE: [], VILLAGE: []},
        "mm_live": {CASTLE: True, VILLAGE: True},
        "messenger": VILLAGE,
        "current": 0, "round": 1, "turns": 0,
        "iid": 0, "pending": None, "pending_q": [],
        "results": None, "winner": None, "board_message_id": None,
    }


def new_player(user_id, name):
    return {"user_id": int(user_id), "name": name, "npc": False,
            "gold": START_GOLD, "keys": START_KEYS,
            "tableau": [], "last": None}


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def _mk(g, cid):
    g["iid"] += 1
    return {"id": g["iid"], "cid": cid, "fd": False, "gold": 0, "x": 0, "y": 0}


def start_game(g, events):
    if len(g["players"]) < 2:
        return "need at least 2 players"
    if len(g["players"]) > MAX_PLAYERS:
        return f"too many players (max {MAX_PLAYERS})"
    for loc, ids in ((CASTLE, CASTLE_IDS), (VILLAGE, VILLAGE_IDS)):
        g["decks"][loc] = [_mk(g, cid) for cid in ids]
        random.shuffle(g["decks"][loc])
        g["discards"][loc] = []
        g["rows"][loc] = [g["decks"][loc].pop() for _ in range(3)]
    g["messenger"] = VILLAGE
    g["mm_live"] = {CASTLE: True, VILLAGE: True}
    g["current"] = random.randrange(len(g["players"]))
    g["round"] = 1
    g["turns"] = 0
    g["phase"] = "playing"
    g["results"] = None
    g["winner"] = None
    for p in g["players"]:
        p["gold"] = START_GOLD
        p["keys"] = START_KEYS
        p["tableau"] = []
        p["last"] = None
    events.append(f"🏰 Castle Combo begins - {g['players'][g['current']]['name']} is first!")
    return None


# ------------------------------------------------------------------ helpers

def occupied(p):
    return [(c["x"], c["y"]) for c in p["tableau"]]


def _at(p, x, y):
    return next((c for c in p["tableau"] if c["x"] == x and c["y"] == y), None)


def _bounds(p):
    xs = [c["x"] for c in p["tableau"]]
    ys = [c["y"] for c in p["tableau"]]
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None


def placement_options(p):
    """Empty spots orthogonally adjacent to an owned card, keeping the
    tableau inside a 3x3 bounding box."""
    b = _bounds(p)
    if b is None:
        return [(0, 0)]
    x0, x1, y0, y1 = b
    out = []
    for c in p["tableau"]:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            x, y = c["x"] + dx, c["y"] + dy
            if _at(p, x, y) is not None:
                continue
            nx0, nx1 = min(x0, x), max(x1, x)
            ny0, ny1 = min(y0, y), max(y1, y)
            if nx1 - nx0 <= 2 and ny1 - ny0 <= 2:
                if (x, y) not in out:
                    out.append((x, y))
    return out


def slot_label(x, y):
    """1-9 reading-order label of a tableau spot (relative to bounding box)."""
    return 3 * y + x + 1


def _slot_of(inst, p):
    """Normalized 1-9 grid slot of a card."""
    x0, x1, y0, y1 = _bounds(p)
    return slot_label(inst["x"] - x0, inst["y"] - y0)


def discount(g, idx, loc):
    p = g["players"][idx]
    d = 0
    for inst in p["tableau"]:
        if inst["fd"]:
            continue
        dv = card_of(inst)["disc"]
        if dv == 3 or dv == loc:
            d += 1
    return d


def cost_for(g, idx, card):
    return max(0, card["cost"] - discount(g, idx, card["loc"]))


def discounts_summary(g, idx):
    return {CASTLE: discount(g, idx, CASTLE), VILLAGE: discount(g, idx, VILLAGE)}


# ------------------------------------------------------------- conditions

def _shields_on(cards):
    out = {}
    for inst in cards:
        if inst["fd"]:
            continue
        for sh in card_of(inst)["sh"]:
            out[sh] = out.get(sh, 0) + 1
    return out


def _face_ups(p):
    return [c for c in p["tableau"] if not c["fd"]]


def count_cond(g, p, cond):
    """Count of a condition over player p's tableau."""
    if isinstance(cond, int):
        return _shields_on(p["tableau"]).get(cond, 0)
    ups = _face_ups(p)
    if cond == "diff":
        return len(_shields_on(p["tableau"]))
    if cond == "pmiss":
        return 6 - len(_shields_on(p["tableau"]))
    if isinstance(cond, tuple):
        kind = cond[0]
        if kind == "b":
            return sum(1 for c in ups if card_of(c)["loc"] == cond[1])
        if kind == "single":
            return sum(1 for c in ups if len(card_of(c)["sh"]) == 1)
        if kind == "double":
            return sum(1 for c in ups if len(card_of(c)["sh"]) == 2)
        if kind == "cost":
            return sum(1 for c in ups if card_of(c)["cost"] == cond[1])
        if kind == "purse":
            return sum(1 for c in ups if card_of(c)["purse"])
        if kind == "disc":
            return sum(1 for c in ups if card_of(c)["disc"])
        if kind == "empty":
            return 9 - len(p["tableau"])
        if kind == "full":
            return len(p["tableau"])
        if kind == "flip":
            return sum(1 for c in p["tableau"] if c["fd"])
    raise ValueError(f"bad condition {cond!r}")


# --------------------------------------------------------------- abilities

def _add_pending(g, pend):
    if g.get("pending") is None and not g.get("pending_q"):
        g["pending"] = pend
    else:
        g.setdefault("pending_q", []).append(pend)


def _next_pending(g):
    q = g.get("pending_q") or []
    if q:
        g["pending"] = q.pop(0)
        return True
    g["pending"] = None
    return False


def _neighbor_options(g, idx):
    return [i for i in range(len(g["players"])) if i != idx]


def _ability_options(g, idx, ab, inst):
    """Flatten an ability into pending options; None if no choice needed."""
    kind = ab[0]
    p = g["players"][idx]
    if kind == "or":
        opts = []
        for sub in ab[1]:
            if sub[0] == "nb":
                for i in _neighbor_options(g, idx):
                    n = count_cond(g, g["players"][i], sub[1])
                    opts.append({"v": f"nb:{i}", "label": _nb_label(g, i, sub, n)})
            else:
                opts.append({"v": f"ab:{_ability_key(sub)}",
                             "label": _plain_label(g, idx, sub)})
        if len(opts) <= 1:
            return None
        return opts
    if kind == "nb":
        opts = []
        for i in _neighbor_options(g, idx):
            n = count_cond(g, g["players"][i], ab[1])
            opts.append({"v": f"nb:{i}", "label": _nb_label(g, i, ab, n)})
        return opts
    if kind == "and":
        # Only ask when a part depends on a neighbor.
        nbparts = [s for s in ab[1] if s[0] == "nb"]
        if not nbparts:
            return None
        opts = []
        for i in _neighbor_options(g, idx):
            parts = []
            for sub in ab[1]:
                if sub[0] == "nb":
                    n = count_cond(g, g["players"][i], sub[1])
                    parts.append(_nb_label(g, i, sub, n))
                else:
                    parts.append(_plain_label(g, idx, sub))
            opts.append({"v": f"nb:{i}", "label": " + ".join(parts)})
        return opts
    return None


def _nb_label(g, i, sub, n):
    name = g["players"][i]["name"]
    res = sub[2]
    unit = "gold" if res == "gold" else "keys"
    return f"{n} {unit} from {name}'s tableau"


def _plain_label(g, idx, sub):
    kind = sub[0]
    if kind in ("g", "k"):
        res = "gold" if kind == "g" else "keys"
        n = count_cond(g, g["players"][idx], sub[1])
        return f"gain {n} {res} ({sub[2]}/shield)"
    if kind == "gain":
        return f"gain {sub[2]} {sub[1]}"
    if kind == "opp":
        return f"opponents gain {sub[2]} {sub[1]}"
    if kind == "purses":
        return f"{sub[1]} gold on each purse"
    return "choose"


def _ability_key(sub):
    kind = sub[0]
    if kind in ("g", "k"):
        return f"{kind}{sub[1]}_{sub[2]}"
    if kind == "gain":
        return f"gain_{sub[1]}_{sub[2]}"
    if kind == "opp":
        return f"opp_{sub[1]}_{sub[2]}"
    if kind == "purses":
        return f"purses_{sub[1]}"
    return kind


def _apply_simple(g, idx, sub, nb_idx, inst, events):
    """Apply one non-choice ability part."""
    p = g["players"][idx]
    card = card_of(inst)
    kind = sub[0]
    if kind in ("g", "k"):
        n = count_cond(g, p, sub[1]) * sub[2]
        res = "gold" if kind == "g" else "keys"
        if n:
            _gain(g, idx, res, n)
            events.append(f"✨ {card['name']}: +{n} {res}.")
        return
    if kind == "gsum":
        n = sum(count_cond(g, p, c) for c in sub[1]) * sub[2]
        if n:
            _gain(g, idx, "gold", n)
            events.append(f"✨ {card['name']}: +{n} gold.")
        return
    if kind == "gain":
        _gain(g, idx, sub[1], sub[2])
        events.append(f"✨ {card['name']}: +{sub[2]} {sub[1]}.")
        return
    if kind == "opp":
        for i, o in enumerate(g["players"]):
            if i != idx:
                o["gold" if sub[1] == "gold" else "keys"] += sub[2]
        events.append(f"✨ {card['name']}: opponents gain {sub[2]} {sub[1]}.")
        return
    if kind == "allk":
        for o in g["players"]:
            o["keys"] += sub[1]
        events.append(f"✨ {card['name']}: all players gain {sub[1]} key(s).")
        return
    if kind == "nb":
        n = count_cond(g, g["players"][nb_idx], sub[1]) * sub[3]
        if n:
            _gain(g, idx, sub[2], n)
            events.append(f"✨ {card['name']}: +{n} {sub[2]}.")
        return
    if kind == "purses":
        total = 0
        for c in _face_ups(p):
            cap = card_of(c)["purse"]
            if cap:
                add = min(sub[1], cap - c["gold"])
                if add > 0:
                    c["gold"] += add
                    total += add
        if total:
            events.append(f"✨ {card['name']}: {total} gold placed on purses.")
        return
    if kind == "purse2":
        return  # handled via pending choices
    events.append(f"✨ {card['name']} ability (no effect).")


def _gain(g, idx, res, n):
    p = g["players"][idx]
    if res == "gold":
        p["gold"] += n
    else:
        p["keys"] += n


def _apply_ability(g, idx, inst, events):
    """Apply a just-placed card's ability. May queue a pending choice."""
    card = card_of(inst)
    ab = card["ab"]
    if inst["fd"] or ab is None:
        return
    kind = ab[0]
    if kind == "purse2":
        _purse2_pending(g, idx, inst, events)
        return
    if kind == "drop":
        row = g["rows"][ab[1]]
        live = g["mm_live"][ab[1]] and row
        if not live:
            events.append(f"✨ {card['name']}: no {LOC_EMOJI[ab[1]]} display to discard from.")
            return
        opts = [{"v": str(c["id"]),
                 "label": f"Discard {card_of(c)['name']} (gain {card_of(c)['cost']} gold)"}
                for c in row]
        _add_pending(g, {"kind": "drop", "player": idx, "card_id": inst["id"],
                         "loc": ab[1], "options": opts,
                         "prompt": f"⚰️ {card['name']}: discard which "
                                   f"{LOC_EMOJI[ab[1]]} display card?"})
        return
    opts = _ability_options(g, idx, ab, inst)
    if opts:
        _add_pending(g, {"kind": "ability", "player": idx, "card_id": inst["id"],
                         "ab": ab, "options": opts,
                         "prompt": f"✨ {card['name']}: choose one"})
        return
    if kind == "and":
        for sub in ab[1]:
            _apply_simple(g, idx, sub, None, inst, events)
        return
    if kind == "or":
        _apply_simple(g, idx, ab[1][0], None, inst, events)
        return
    _apply_simple(g, idx, ab, None, inst, events)


def _purse2_pending(g, idx, inst, events):
    p = g["players"][idx]
    card = card_of(inst)
    elig = [c for c in _face_ups(p)
            if card_of(c)["purse"] and c["gold"] < card_of(c)["purse"]]
    if not elig:
        events.append(f"✨ {card['name']}: no purse with space left.")
        return
    if len(elig) == 1:
        tgt = elig[0]
        add = card_of(tgt)["purse"] - tgt["gold"]
        tgt["gold"] += add
        events.append(f"✨ {card['name']}: {add} gold stored on {card_of(tgt)['name']}.")
        return
    opts = [{"v": str(c["id"]),
             "label": f"Fill {card_of(c)['name']} (+{card_of(c)['purse'] - c['gold']} gold)"}
            for c in elig]
    _add_pending(g, {"kind": "purse2", "player": idx, "card_id": inst["id"],
                     "options": opts,
                     "prompt": f"💰 {card['name']}: which purse to fill? (choose 2)"})


# ------------------------------------------------------------ turn actions

def do_key(g, idx, act, events):
    if g["phase"] != "playing":
        return "game is not running"
    if g.get("pending"):
        return "resolve the pending choice first"
    if idx != g["current"]:
        return "not your turn"
    p = g["players"][idx]
    if p["keys"] <= 0:
        return "no keys left"
    row = g["messenger"]
    if act == "move":
        other = CASTLE if row == VILLAGE else VILLAGE
        if not g["mm_live"][other]:
            return "the other location is out of cards"
        p["keys"] -= 1
        g["messenger"] = other
        events.append(f"🔑 {p['name']} spends a key - messenger moves to "
                      f"{LOC_EMOJI[other]} {('Castle' if other == CASTLE else 'Village')}.")
        return None
    if act == "renew":
        p["keys"] -= 1
        old = g["rows"][row]
        g["discards"][row].extend(old)
        g["rows"][row] = []
        _refill_row(g, row, events)
        events.append(f"🔑 {p['name']} spends a key - {LOC_EMOJI[row]} display renewed.")
        return None
    return "unknown key action"


def _draw(g, loc):
    """Draw from loc's deck, reshuffling the discard when it runs out."""
    if not g["decks"][loc]:
        if g["discards"][loc]:
            g["decks"][loc] = g["discards"][loc]
            g["discards"][loc] = []
            random.shuffle(g["decks"][loc])
        else:
            return None
    return g["decks"][loc].pop() if g["decks"][loc] else None


def _refill_row(g, loc, events):
    row = g["rows"][loc]
    while len(row) < 3:
        c = _draw(g, loc)
        if c is None:
            break
        row.append(c)
    if len(row) < 3:
        # Location dies: its cards leave the game, messenger parks at the rest.
        g["mm_live"][loc] = False
        g["rows"][loc] = []
        g["decks"][loc] = []
        g["discards"][loc] = []
        other = CASTLE if loc == VILLAGE else VILLAGE
        g["messenger"] = other
        events.append(f"📭 The {LOC_EMOJI[loc]} location is out of cards - its display "
                      f"is removed and the messenger stays at "
                      f"{LOC_EMOJI[other]} {('Castle' if other == CASTLE else 'Village')}.")
        return
    # Replace renewed display cards in-place is handled by callers; nothing here.


def do_take(g, idx, card_id, flipped, events):
    """Take a display card: buy it (flipped=False) or flip it face-down."""
    if g["phase"] != "playing":
        return "game is not running"
    if g.get("pending"):
        return "resolve the pending choice first"
    if idx != g["current"]:
        return "not your turn"
    p = g["players"][idx]
    if len(p["tableau"]) >= 9:
        return "your tableau is complete"
    row = g["messenger"]
    inst = next((c for c in g["rows"][row] if c["id"] == card_id), None)
    if inst is None:
        return "that card is not in the messenger's display"
    card = card_of(inst)
    if flipped:
        p["gold"] += FLIP_GOLD
        p["keys"] += FLIP_KEYS
        inst["fd"] = True
        events.append(f"🔄 {p['name']} takes {card['name']} face-down "
                      f"(+{FLIP_GOLD} gold, +{FLIP_KEYS} keys).")
    else:
        cost = cost_for(g, idx, card)
        if p["gold"] < cost:
            return f"not enough gold (costs {cost}, you have {p['gold']})"
        p["gold"] -= cost
        events.append(f"🛒 {p['name']} buys {card['name']} for {cost} gold.")
    g["rows"][row].remove(inst)
    opts = placement_options(p)
    p["last"] = None
    if len(opts) == 1:
        _place(g, idx, inst, opts[0], events)
        return None
    _add_pending(g, {"kind": "place", "player": idx, "card_id": inst["id"],
                     "card_inst": inst,
                     "options": [{"v": f"{x},{y}", "label": _spot_label(p, x, y)}
                                 for x, y in opts],
                     "prompt": f"📍 Place {card['name']} where?"})
    return None


def _spot_label(p, x, y):
    if not p["tableau"]:
        return "center"
    x0, x1, y0, y1 = _bounds(p)
    return f"spot {slot_label(x - x0, y - y0)}"


def _place(g, idx, inst, xy, events):
    """Place a taken card, apply its ability, then finish the turn. The
    messenger move + refill wait until ability choices resolve (rules order:
    the ability resolves fully before the messenger moves)."""
    p = g["players"][idx]
    inst["x"], inst["y"] = xy
    p["tableau"].append(inst)
    p["last"] = inst["id"]
    pos = _spot_label(p, xy[0], xy[1])
    if inst["fd"]:
        events.append(f"📍 {p['name']} places {card_of(inst)['name']} face-down ({pos}).")
    else:
        events.append(f"📍 {p['name']} places {card_of(inst)['name']} ({pos}).")
    g["_turn_card"] = inst
    _apply_ability(g, idx, inst, events)
    if g.get("pending") or g.get("pending_q"):
        return
    g["_turn_card"] = None
    _finish_turn(g, idx, inst, events)


def _finish_turn(g, idx, inst, events):
    """Messenger move, refill, next player or game end."""
    card = card_of(inst)
    if card["mm"] and not inst["fd"]:
        dest = VILLAGE if card["loc"] == CASTLE else CASTLE
        if g["mm_live"][dest]:
            g["messenger"] = dest
            events.append(f"📯 Messenger moves to {LOC_EMOJI[dest]} "
                          f"{'Castle' if dest == CASTLE else 'Village'}.")
    for loc in (CASTLE, VILLAGE):
        if g["mm_live"][loc] and len(g["rows"][loc]) < 3:
            _refill_row(g, loc, events)
    if not any(g["mm_live"].values()):
        _end_game(g, events)   # both displays out of cards
        return
    g["turns"] += 1
    if all(len(p["tableau"]) >= 9 for p in g["players"]):
        _end_game(g, events)
        return
    g["current"] = (g["current"] + 1) % len(g["players"])
    g["round"] = min(ROUNDS, g["turns"] // len(g["players"]) + 1)


# ------------------------------------------------------- pending resolution

def apply_choice(g, idx, choice, events):
    pend = g.get("pending")
    if not pend or pend["player"] != idx:
        return "no pending choice for you"
    if g["phase"] != "playing":
        return "game is over"
    kind = pend["kind"]
    vals = [o["v"] for o in pend["options"]]
    if str(choice) not in vals:
        return "not a valid option"
    choice = str(choice)
    p = g["players"][idx]
    inst = pend.get("card_inst")
    if inst is None:
        inst = next((c for c in p["tableau"] if c["id"] == pend.get("card_id")), None)
    if kind == "place":
        # Clear the place pending first: _place may queue ability pendings,
        # which must become the active pending, not sit behind this one.
        g["pending"] = None
        x, y = (int(v) for v in choice.split(","))
        _place(g, idx, inst, (x, y), events)
        return None
    if kind == "drop":
        row = g["rows"][pend["loc"]]
        dropped = next((c for c in row if c["id"] == int(choice)), None)
        if dropped is None:
            return "that card is no longer in the display"
        row.remove(dropped)
        g["discards"][pend["loc"]].append(dropped)
        gain = card_of(dropped)["cost"]
        p["gold"] += gain
        events.append(f"⚰️ {p['name']} discards {card_of(dropped)['name']} "
                      f"from the display (+{gain} gold).")
        _after_choice(g, events)
        return None
    if kind == "purse2":
        tgt = next((c for c in p["tableau"] if c["id"] == int(choice)), None)
        if tgt is None:
            return "that purse is not in your tableau"
        cap = card_of(tgt)["purse"]
        add = cap - tgt["gold"]
        tgt["gold"] = cap
        pend["fills"] = pend.get("fills", 0) + 1
        events.append(f"💰 {p['name']} fills {card_of(tgt)['name']} (+{add} gold).")
        # second purse? (Steward fills exactly two)
        if pend["fills"] >= 2:
            _after_choice(g, events)
            return None
        elig = [c for c in _face_ups(p)
                if card_of(c)["purse"] and c["gold"] < card_of(c)["purse"]
                and c["id"] != tgt["id"]]
        if elig:
            pend["options"] = [{"v": str(c["id"]),
                                "label": f"Fill {card_of(c)['name']} "
                                         f"(+{card_of(c)['purse'] - c['gold']} gold)"}
                               for c in elig]
            return None
        _after_choice(g, events)
        return None
    if kind == "ability":
        ab = pend["ab"]
        sub = None
        nb_idx = None
        if choice.startswith("nb:"):
            nb_idx = int(choice[3:])
            nbparts = [s for s in (ab[1] if ab[0] in ("or", "and") else [ab])
                       if s[0] == "nb"]
            sub = nbparts[0]
        else:
            key = choice[3:]
            subs = ab[1] if ab[0] in ("or", "and") else [ab]
            sub = next(s for s in subs if _ability_key(s) == key and s[0] != "nb")
        if ab[0] == "and":
            for s in ab[1]:
                if s[0] == "nb":
                    if choice.startswith(f"nb:{nb_idx}"):
                        _apply_simple(g, idx, s, nb_idx, inst, events)
                else:
                    _apply_simple(g, idx, s, None, inst, events)
        else:
            _apply_simple(g, idx, sub, nb_idx, inst, events)
        _after_choice(g, events)
        return None
    return "unknown pending"


def _after_choice(g, events):
    """Move on after the last pending of a turn resolved. _place defers the
    messenger move + refill while ability pendings exist; this finishes the
    turn once the choices resolve."""
    if _next_pending(g):
        return
    inst = g.get("_turn_card")
    if inst is not None:
        g["_turn_card"] = None
        _finish_turn(g, g["current"], inst, events)


# ------------------------------------------------------------------ scoring

def _norm_slots(p):
    b = _bounds(p)
    if b is None:
        return {}
    x0, x1, y0, y1 = b
    out = {}
    for c in p["tableau"]:
        out[c["id"]] = (c["x"] - x0, c["y"] - y0)
    return out


def _line_cards(p, inst, where, slots):
    sx, sy = slots[inst["id"]]
    out = []
    for c in _face_ups(p):
        cx, cy = slots[c["id"]]
        if where == "row" and cy == sy:
            out.append(c)
        elif where == "col" and cx == sx:
            out.append(c)
        elif where == "rc" and (cx == sx or cy == sy):
            out.append(c)
    return out


def score_card(g, p, inst, slots, key_count):
    if inst["fd"]:
        return 0
    sc = card_of(inst)["sc"]
    if sc is None:
        return 0
    kind = sc[0]
    if kind == "sh":
        n = sum(_shields_on(_line_cards(p, inst, sc[1], slots)).get(sc[2], 0)
                for _ in [0])
        return sc[3] * n
    if kind == "diff":
        if sc[1] == "all":
            return sc[2] * len(_shields_on(p["tableau"]))
        cards = _line_cards(p, inst, sc[1], slots)
        return sc[2] * len(_shields_on(cards))
    if kind == "pos":
        slot = 3 * slots[inst["id"]][1] + slots[inst["id"]][0] + 1
        return sc[2] if slot in sc[1] else 0
    if kind == "miss":
        return sc[2] if count_cond(g, p, sc[1]) == 0 else 0
    if kind == "pmiss":
        return sc[1] * count_cond(g, p, "pmiss")
    if kind == "pair":
        sh = _shields_on(p["tableau"])
        return sc[3] * min(sh.get(sc[1], 0), sh.get(sc[2], 0))
    if kind == "tri":
        sh = _shields_on(p["tableau"])
        return sc[4] * min(sh.get(sc[1], 0), sh.get(sc[2], 0), sh.get(sc[3], 0))
    if kind == "sets":
        sh = _shields_on(p["tableau"])
        return sc[1] * sum(v // 3 for v in sh.values())
    if kind == "bset":
        n = count_cond(g, p, ("b", sc[1]))
        return sc[2] * (n // 3)
    if kind == "cnt":
        return sc[2] * count_cond(g, p, sc[1])
    if kind == "pair_b":
        return sc[1] * min(count_cond(g, p, ("b", CASTLE)),
                           count_cond(g, p, ("b", VILLAGE)))
    if kind == "flany":
        return sc[1] if count_cond(g, p, ("flip",)) > 0 else 0
    if kind == "keys":
        return sc[1] * key_count
    if kind == "purse":
        return sc[2] * min(inst["gold"], sc[1])
    if kind == "pall":
        return sc[1] * sum(c["gold"] for c in _face_ups(p) if card_of(c)["purse"])
    if kind == "prich":
        return sc[1] * sum(1 for c in _face_ups(p)
                           if card_of(c)["purse"] and c["gold"] >= 5)
    return 0


def store_leftover_gold(p):
    """End of game: place leftover gold on purses, largest capacity first."""
    purses = sorted((c for c in p["tableau"] if not c["fd"] and card_of(c)["purse"]),
                    key=lambda c: -card_of(c)["purse"])
    for c in purses:
        cap = card_of(c)["purse"]
        take = min(cap - c["gold"], p["gold"])
        if take > 0:
            c["gold"] += take
            p["gold"] -= take
    return p["gold"]


def score_player(g, idx):
    p = g["players"][idx]
    slots = _norm_slots(p)
    keys = p["keys"]
    total = keys * 1
    breakdown = [{"name": "Keys", "pts": keys, "n": keys, "unit": "key"}]
    for inst in p["tableau"]:
        pts = score_card(g, p, inst, slots, keys)
        card = card_of(inst)
        if pts:
            breakdown.append({"name": card["name"], "pts": pts,
                              "fd": inst["fd"]})
        total += pts
    return total, breakdown


def _end_game(g, events):
    g["phase"] = "game_end"
    results = []
    for i, p in enumerate(g["players"]):
        left = store_leftover_gold(p)
        score, breakdown = score_player(g, i)
        slots = _norm_slots(p)
        # Per-round score sheet entries: tableau placement order == round
        # order; every card is re-evaluated in the final tableau (BGA-style).
        entries = [score_card(g, p, p["tableau"][r], slots, p["keys"])
                   if r < len(p["tableau"]) else 0
                   for r in range(ROUNDS)]
        results.append({"idx": i, "name": p["name"], "score": score,
                        "leftover": left, "breakdown": breakdown,
                        "entries": entries, "keys": p["keys"]})
    mx = max(r["score"] for r in results)
    tops = [r for r in results if r["score"] == mx]
    if len(tops) > 1:
        best = max(r["leftover"] for r in tops)
        tops = [r for r in tops if r["leftover"] == best]
    if len(tops) == 1:
        g["winner"] = tops[0]["idx"]
        events.append(f"🏆 {tops[0]['name']} wins with {mx} points!")
    else:
        g["winner"] = None
        events.append(f"🤝 Shared win at {mx} points!")
    g["results"] = sorted(results, key=lambda r: -r["score"])
    events.append("📊 Final scores: " +
                  ", ".join(f"{r['name']} {r['score']}" for r in g["results"]))


def preview_score(g, idx):
    """Current hypothetical score (gold hypothetically stored on purses)."""
    p = g["players"][idx]
    fake = {"tableau": [], "keys": p["keys"]}
    for c in p["tableau"]:
        d = dict(c)
        cap = card_of(c)["purse"]
        if not c["fd"] and cap:
            d["gold"] = min(cap, c["gold"] + max(0, p["gold"]))
        fake["tableau"].append(d)
    slots = _norm_slots(p)
    total = p["keys"]
    for inst in fake["tableau"]:
        total += score_card(g, fake, inst, slots, p["keys"])
    return total
