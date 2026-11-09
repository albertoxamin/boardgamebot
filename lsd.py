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


# ---------------- Turn actions ----------------

def roll_dice(g, idx, events):
    """Roll 2d6 (mandatory action). May pause for a Re-Rollucifer choice."""
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["pending"]:
        return "resolve the pending choice first"
    if g["turn"]["rolled"]:
        return "you already rolled this turn"
    g["dice"] = [random.randint(1, 6), random.randint(1, 6)]
    g["rerolled"] = False
    total = sum(g["dice"])
    events.append(f"🎲 {g['players'][idx]['name']} rolls {g['dice'][0]}+{g['dice'][1]}={total}.")
    if has_demon(g, idx, "rerollucifer"):
        g["pending"] = {"kind": "reroll", "player": idx}
        return None
    _finalize_roll(g, idx, events)
    return None


def _finalize_roll(g, idx, events):
    total = sum(g["dice"])
    g["last_total"] = total
    g["turn"]["rolled"] = True
    g["roll_ctx"] = {"roller": idx, "total": total, "dice": list(g["dice"])}
    # Dice-Zuzzu: own doubles gain the face value.
    if has_demon(g, idx, "dice_zuzzu") and g["dice"][0] == g["dice"][1]:
        events.append("🎲 Dice-Zuzzu: doubles!")
        gain_souls(g, idx, g["dice"][0], events)
    # Build the activation queue: roller first, then clockwise.
    g["activated"] = []
    queue = []
    n = len(g["players"])
    for k in range(n):
        j = (idx + k) % n
        if g["turn"]["only_mine"] and j != idx:
            continue
        p = g["players"][j]
        cards = ([p["candle"]] if p["candle"] else []) + p["in_play"] + p["demons"]
        for c in cards:
            if c["kind"] == "candle":
                if total in c["nums"]:
                    queue.append([j, c["iid"]])
            elif c["kind"] == "demon":
                if j == idx and c["num"] is not None and c["num"] == total:
                    queue.append([j, c["iid"]])
            elif c["num"] == total:
                queue.append([j, c["iid"]])
    g["act_queue"] = queue
    drain(g, events)


def buy_card(g, idx, market_iid, events):
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["pending"]:
        return "resolve the pending choice first"
    if g["turn"]["bought"]:
        return "you already bought this turn"
    card = next((c for c in g["market"] if c["iid"] == market_iid), None)
    if card is None:
        return "that card is not on THE BLOCK"
    if g["players"][idx]["souls"] < BUY_COST:
        return "need 3 Souls to buy"
    g["players"][idx]["souls"] -= BUY_COST
    g["supply"] += BUY_COST
    g["market"].remove(card)
    g["turn"]["bought"] = True
    events.append(f"🛒 {g['players'][idx]['name']} buys {card['name']} for 3 Souls.")
    gain_card(g, idx, card, events)
    check_win(g, events)
    return None


def summon(g, idx, sacrifice_iids, demon_iid, events):
    """Discard 3 (or 4 vs Baphometal) Block cards, summon a Demon from hand."""
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["pending"]:
        return "resolve the pending choice first"
    if g["turn"]["summoned"]:
        return "you already summoned this turn"
    p = g["players"][idx]
    cost = summon_cost(g, idx)
    if len(sacrifice_iids) != cost:
        return f"sacrifice exactly {cost} of your Block cards"
    sac = []
    for iid in sacrifice_iids:
        c = next((c for c in p["in_play"] if c["iid"] == iid), None)
        if c is None:
            return "sacrifice cards must be your Block cards in play (not Candles/Demons)"
        sac.append(c)
    demon = next((c for c in p["demon_hand"] if c["iid"] == demon_iid), None)
    if demon is None:
        return "that Demon is not in your hand"
    for c in sac:
        discard_from_play(g, idx, c, events)
    g["turn"]["summoned"] = True
    if demon["eff"] == "rosemarys_egg":
        _rosemary_replace(g, idx, demon, events)
    else:
        summon_demon(g, idx, demon, events)
    check_win(g, events)
    return None


def _rosemary_replace(g, idx, egg, events):
    """Rosemary's Egg: summoned then immediately discarded; look at the top
    3 Demon cards, summon one, discard the other 2 (choice pending)."""
    p = g["players"][idx]
    if egg in p["demon_hand"]:
        p["demon_hand"].remove(egg)
    g["demon_discard"].append(egg)
    events.append(f"🥚 {p['name']} summons Rosemary's Egg, which immediately "
                  f"discards itself and hatches...")
    _reshuffle(g, "demon_deck", "demon_discard", events)
    top = [g["demon_deck"].pop() for _ in range(min(3, len(g["demon_deck"])))]
    if not top:
        return
    g["pending"] = {"kind": "rosemary", "player": idx, "options": [c["iid"] for c in top],
                    "top": top}


def put_demon_in_play(g, idx, demon, events, free=False):
    """Summon a Demon into play, handling Rosemary's Egg replacement."""
    if demon["eff"] == "rosemarys_egg":
        _rosemary_replace(g, idx, demon, events)
    else:
        summon_demon(g, idx, demon, events, free=free)
    check_win(g, events)


# ---------------- Activation resolution ----------------

def _victims(g, idx):
    """Indices that idx's steal/discard effects may target (no Wraithlok)."""
    return [j for j in range(len(g["players"])) if j != idx
            and not has_demon(g, j, "wraithlok")]


def _stealable(g, j, filt=None):
    """Stealable cards of player j (never Candles)."""
    p = g["players"][j]
    cards = list(p["in_play"]) + list(p["demons"])
    if filt == "kid":
        cards = [c for c in cards if c["ctype"] in ("boy", "girl")]
    elif filt == "any":
        pass
    return cards


def _req_met(g, idx, card):
    """Additional (red-text) activation requirement, checked at activation time."""
    eff = card["eff"]
    p = g["players"][idx]
    if eff == "dog":
        return len(_kids(g, idx)) >= 1
    if eff == "rabbit":
        return sum(1 for c in p["in_play"] if c["ctype"] == "animal") >= 3
    if eff in ("rabid_dog", "stray_cat"):
        return len(_kids(g, idx)) == 0
    if eff == "rainbow_parrot":
        return type_count(g, idx, "boy") >= 2 or type_count(g, idx, "girl") >= 2
    if eff == "chuck":
        return align_count(g, idx, "sweet", exclude_iid=card["iid"]) >= 1
    if eff == "calvin":
        return align_count(g, idx, "rotten") >= 3
    return True


def _lose_card(g, idx, card, events):
    """Remove a card from play to the discard pile (no other checks)."""
    p = g["players"][idx]
    if card in p["in_play"]:
        p["in_play"].remove(card)
        g["discard"].append(card)
        events.append(f"🗑 {card['name']} discarded.")
        return True
    if card in p["demons"]:
        p["demons"].remove(card)
        g["demon_discard"].append(card)
        events.append(f"🗑 {card['name']} discarded.")
        return True
    return False


def drain(g, events):
    """Resolve the activation queue until empty or paused on a choice."""
    while g["act_queue"] and not g["pending"] and g["phase"] != "game_end":
        owner, iid = g["act_queue"].pop(0)
        o2, card = find_card(g, iid)
        if card is None or o2 != owner or iid in g["activated"]:
            continue
        g["activated"].append(iid)
        if not _req_met(g, owner, card):
            events.append(f"⛔ {card['name']} does nothing (requirement not met).")
            continue
        _resolve(g, owner, card, events)
        check_win(g, events)


def _enqueue(g, owner, cards):
    """Chain activations right after the current card."""
    fresh = [[owner, c["iid"]] for c in cards if c["iid"] not in g["activated"]]
    g["act_queue"] = fresh + g["act_queue"]


def _steal_souls_choice(g, idx, amount, events):
    opts = [j for j in _victims(g, idx) if g["players"][j]["souls"] > 0]
    if g["supply"] > 0:
        opts = opts + ["supply"]
    if not opts:
        events.append("👻 No Souls to steal.")
        return
    if len(opts) == 1:
        steal_souls(g, idx, amount, opts[0], events)
        return
    g["pending"] = {"kind": "steal_souls", "player": idx, "amount": amount, "options": opts}


def _gain_block_choice(g, idx, filt, events):
    opts = [c["iid"] for c in g["market"]
            if (filt == "any" or (filt == "animal" and c["ctype"] == "animal")
                or (filt == "boy" and c["ctype"] == "boy")
                or (filt == "rotten_kid" and c["ctype"] in ("boy", "girl") and c["align"] == "rotten"))]
    if not opts:
        events.append("🕳 No matching card on THE BLOCK.")
        return
    if len(opts) == 1:
        card = next(c for c in g["market"] if c["iid"] == opts[0])
        g["market"].remove(card)
        events.append(f"🛒 {g['players'][idx]['name']} gains {card['name']} from THE BLOCK.")
        gain_card(g, idx, card, events)
        return
    g["pending"] = {"kind": "gain_block", "player": idx, "options": opts}


def _optional(g, idx, card, after, events):
    """'YOU MAY DISCARD THIS' effects: ask before paying the discard cost."""
    g["pending"] = {"kind": "optional", "player": idx, "card_iid": card["iid"],
                    "after": after, "name": card["name"]}


def _resolve(g, idx, card, events):
    """Resolve one activation. May set g["pending"] (pauses draining)."""
    eff = card["eff"]
    p = g["players"][idx]
    name = card["name"]

    def ev(s):
        events.append(f"⚡ {name} ({p['name']}): {s}")

    # --- Candles and Demons with numeric activations ---
    if eff == "candle":
        gain_souls(g, idx, 1, events, source=card)
        return
    if eff == "serpent":
        g["phase"] = "game_end"
        g["winner"] = p["user_id"]
        ev("wins the game immediately!")
        return
    if eff == "porkus":
        gain_souls(g, idx, 5, events, source=card)
        return
    if eff == "anti_christ":
        _steal_souls_choice(g, idx, 5, events)
        return
    if eff == "baala":
        _steal_souls_choice(g, idx, sum(1 for c in p["in_play"] if c["ctype"] == "animal"), events)
        return
    if eff == "beelzebuddy":
        ev("activates all of your BOYS and GIRLS.")
        _enqueue(g, idx, [c for c in p["in_play"] if c["ctype"] in ("boy", "girl")])
        return
    if eff == "gross_book":
        _reshuffle(g, "demon_deck", "demon_discard", events)
        if not g["demon_deck"]:
            ev("no Demons left in the deck to find.")
            return
        g["pending"] = {"kind": "gross_book", "player": idx,
                        "options": [c["iid"] for c in g["demon_deck"]]}
        return
    if eff == "clockwork":
        gain_souls(g, idx, 1, events, source=card)
        g["extra_turn"] = True
        ev("collects a Soul and takes an additional turn "
           "(only YOUR cards can activate during that turn)!")
        return
    if eff == "krampus":
        for _ in range(2):
            c = draw_block(g, events)
            if c is not None:
                ev(f"gains {c['name']} from the top of the Block Deck.")
                gain_card(g, idx, c, events)
        return
    if eff == "nine_stopheles":
        opts = [{"player": j, "iid": c["iid"]} for j in _victims(g, idx)
                for c in _stealable(g, j, "any")]
        if not opts:
            ev("no cards to steal.")
            return
        g["pending"] = {"kind": "steal_card", "player": idx, "options": opts}
        return
    if eff == "the_devil":
        opts = [j for j in _victims(g, idx) if _stealable(g, j, "any")]
        if not opts:
            ev("no cards to steal.")
            return
        if len(opts) == 1:
            _devil_steal(g, idx, opts[0], events)
            return
        g["pending"] = {"kind": "steal_player", "player": idx, "options": opts}
        return
    if eff == "wee_r_legion":
        n = len(p["in_play"]) + len(p["demons"]) + (1 if p["candle"] else 0)
        ev(f"collects {n} Soul(s), one per card in play.")
        gain_souls(g, idx, n, events, source=card)
        return
    # --- Simple Block souls ---
    if eff == "soul1":
        gain_souls(g, idx, 1, events, source=card)
        return
    if eff == "soul2":
        gain_souls(g, idx, 2, events, source=card)
        return
    if eff == "soul5":
        gain_souls(g, idx, 5, events, source=card)
        return
    if eff == "lola":
        n = type_count(g, idx, "boy")
        ev(f"collects {n} Soul(s), one per BOY.")
        gain_souls(g, idx, n, events, source=card)
        return
    if eff == "romeo":
        n = type_count(g, idx, "girl")
        ev(f"collects {n} Soul(s), one per GIRL.")
        gain_souls(g, idx, n, events, source=card)
        return
    if eff == "pippi":
        n = sum(1 for c in p["in_play"] if c["ctype"] == "animal")
        ev(f"collects {n} Soul(s), one per ANIMAL.")
        gain_souls(g, idx, n, events, source=card)
        return
    if eff == "lisa":
        n = align_count(g, idx, "sweet")
        ev(f"collects {n} Soul(s), one per SWEET BOY/GIRL (including this one).")
        gain_souls(g, idx, n, events, source=card)
        return
    if eff == "chuck":
        gain_souls(g, idx, 2, events, source=card)
        return
    if eff == "dog":
        gain_souls(g, idx, 1, events, source=card)
        return
    if eff == "rabbit":
        gain_souls(g, idx, 2, events, source=card)
        return
    if eff in ("rabid_dog", "rainbow_parrot"):
        gain_souls(g, idx, 2, events, source=card)
        return
    if eff == "calvin":
        _steal_souls_choice(g, idx, 2, events)
        return
    if eff == "dillinger":
        _steal_souls_choice(g, idx, 1, events)
        return
    if eff == "donnie":
        _steal_souls_choice(g, idx, align_count(g, idx, "rotten"), events)
        return
    if eff == "glen":
        gain_souls(g, idx, 2, events, source=card)
        others = [j for j in range(len(g["players"])) if j != idx]
        if len(others) == 1:
            gain_souls(g, others[0], 1, events)
        else:
            g["pending"] = {"kind": "glen_player", "player": idx, "options": others}
        return
    if eff == "irwin":
        ev("activates all of your ANIMALS.")
        _enqueue(g, idx, [c for c in p["in_play"] if c["ctype"] == "animal"])
        return
    if eff == "destiny":
        opts = [c["iid"] for c in p["in_play"]
                if c["ctype"] in ("boy", "girl") and c["align"] == "sweet"
                and c["iid"] != card["iid"] and c["iid"] not in g["activated"]]
        if not opts:
            ev("no other SWEET BOYS or GIRLS to activate.")
            return
        if len(opts) == 1:
            _enqueue(g, idx, [next(c for c in p["in_play"] if c["iid"] == opts[0])])
            return
        g["pending"] = {"kind": "activate_choice", "player": idx, "options": opts}
        return
    if eff == "jane":
        _gain_block_choice(g, idx, "animal", events)
        return
    if eff == "marylin":
        _gain_block_choice(g, idx, "boy", events)
        return
    if eff == "cat":
        c = draw_block(g, events)
        if c is None:
            ev("Block Deck is empty.")
        elif c["ctype"] == "animal":
            ev(f"gains {c['name']}!")
            gain_card(g, idx, c, events)
        else:
            g["discard"].append(c)
            ev(f"discards {c['name']} (not an ANIMAL).")
        return
    if eff == "tommy":
        c = draw_block(g, events)
        if c is None:
            ev("Block Deck is empty.")
        elif c["ctype"] == "girl":
            ev(f"gains {c['name']}!")
            gain_card(g, idx, c, events)
        else:
            g["discard"].append(c)
            ev(f"discards {c['name']} (not a GIRL).")
        return
    if eff == "alice":
        for _ in range(2):
            c = draw_block(g, events)
            if c is None:
                break
            if c["ctype"] in ("boy", "girl") and c["align"] == "sweet":
                ev(f"gains discarded {c['name']}!")
                gain_card(g, idx, c, events)
            else:
                g["discard"].append(c)
        return
    if eff == "stray_cat":
        c = draw_block(g, events)
        if c is not None:
            ev(f"gains {c['name']} from the top of the Block Deck!")
            gain_card(g, idx, c, events)
        return
    if eff == "skunk":
        ev("everyone discards ALL of their Non-Demon cards!")
        for j, pl in enumerate(g["players"]):
            if has_demon(g, j, "wraithlok") and j != idx:
                events.append(f"🛡️ Wraithlok protects {pl['name']}.")
                continue
            for c in list(pl["in_play"]):
                discard_from_play(g, j, c, events)
        return
    if eff == "delores":
        ev("replaces every SWEET KID on THE BLOCK.")
        for slot, c in enumerate(list(g["market"])):
            if c["ctype"] in ("boy", "girl") and c["align"] == "sweet":
                g["discard"].append(c)
                new = draw_block(g, events)
                if new is not None:
                    g["market"][slot] = new
                    events.append(f"🔁 {c['name']} replaced by {new['name']}.")
                else:
                    g["market"].pop(slot)
        _gain_block_choice(g, idx, "rotten_kid", events)
        return
    # --- Optional 'YOU MAY DISCARD...' effects ---
    if eff in ("alligator", "goldfish", "hawk", "owl", "damian"):
        _optional(g, idx, card, eff, events)
        return
    if eff == "goat":
        boys = [c["iid"] for c in p["in_play"] if c["ctype"] == "boy"]
        girls = [c["iid"] for c in p["in_play"] if c["ctype"] == "girl"]
        if not boys or not girls:
            ev("cannot discard 1 BOY and 1 GIRL - nothing happens.")
            return
        _optional(g, idx, card, "goat", events)
        return
    if eff == "sam":
        if not any(c["ctype"] == "animal" for c in p["in_play"]):
            ev("no ANIMALS to discard - nothing happens.")
            return
        _optional(g, idx, card, "sam", events)
        return
    if eff == "annie":
        _optional(g, idx, card, "annie", events)
        return
    ev("does nothing.")


def _devil_steal(g, idx, target, events):
    p = g["players"][idx]
    victim = g["players"][target]
    stolen = _stealable(g, target, "any")
    for c in stolen:
        if c in victim["in_play"]:
            victim["in_play"].remove(c)
            p["in_play"].append(c)
        else:
            victim["demons"].remove(c)
            p["demons"].append(c)
    events.append(f"😈 {p['name']} steals ALL of {victim['name']}'s cards "
                  f"({len(stolen)})!")


def _after_optional(g, idx, card, after, events):
    """Apply the main effect after an optional discard cost was paid."""
    p = g["players"][idx]
    if after == "goldfish":
        gain_souls(g, idx, 5, events, source=card)
    elif after == "damian":
        if p["demon_hand"]:
            demon = random.choice(p["demon_hand"])
            put_demon_in_play(g, idx, demon, events, free=True)
        else:
            events.append("😈 No Demons in hand to summon.")
    elif after == "hawk":
        gained = []
        for _ in range(7):
            c = draw_block(g, events)
            if c is None:
                break
            if c["ctype"] == "animal":
                gained.append(c["name"])
                gain_card(g, idx, c, events)
            else:
                g["discard"].append(c)
        events.append(f"🦅 Hawk: gained {', '.join(gained) or 'no ANIMALs'}.")
    elif after == "owl":
        gain_souls(g, idx, 4, events, source=card)
        g["pending"] = {"kind": "replace_block", "player": idx,
                        "options": [c["iid"] for c in g["market"]]}
    elif after == "alligator":
        opts = [{"player": j, "iid": c["iid"]} for j in _victims(g, idx)
                for c in _stealable(g, j, "kid")]
        if not opts:
            events.append("🐊 No BOYs/GIRLs to discard.")
            return
        g["pending"] = {"kind": "alligator", "player": idx, "remaining": 2, "options": opts}
    elif after == "goat":
        boys = [c["iid"] for c in p["in_play"] if c["ctype"] == "boy"]
        g["pending"] = {"kind": "goat_boy", "player": idx, "options": boys}
    elif after == "sam":
        opts = [c["iid"] for c in p["in_play"] if c["ctype"] == "animal"]
        if len(opts) == 1:
            c = next(c for c in p["in_play"] if c["iid"] == opts[0])
            discard_from_play(g, idx, c, events)
            gain_souls(g, idx, 6, events, source=card)
        else:
            g["pending"] = {"kind": "sam_animal", "player": idx,
                            "options": opts, "source_iid": card["iid"]}
    elif after == "annie":
        g["pending"] = {"kind": "annie_branch", "player": idx}


def apply_choice(g, idx, choice, events):
    """Apply the current pending choice. Returns error or None."""
    pend = g.get("pending")
    if not pend or pend["player"] != idx:
        return "no pending choice for you"
    kind = pend["kind"]
    p = g["players"][idx]
    if kind == "reroll":
        if choice == "reroll":
            g["dice"] = [random.randint(1, 6), random.randint(1, 6)]
            events.append(f"🔁 Re-Rollucifer re-rolls: {g['dice'][0]}+{g['dice'][1]}={sum(g['dice'])}.")
        g["pending"] = None
        _finalize_roll(g, idx, events)
        return None
    if kind == "optional":
        g["pending"] = None
        if choice == "do":
            _, card = find_card(g, pend["card_iid"])
            if card is not None:
                discard_from_play(g, idx, card, events)
                _after_optional(g, idx, card, pend["after"], events)
        drain(g, events)
        return None
    if kind == "steal_souls":
        g["pending"] = None
        steal_souls(g, idx, pend["amount"], choice, events)
    elif kind == "glen_player":
        g["pending"] = None
        gain_souls(g, choice, 1, events)
    elif kind == "steal_player":
        g["pending"] = None
        _devil_steal(g, idx, choice, events)
    elif kind == "steal_card":
        g["pending"] = None
        opt = next((o for o in pend["options"] if o["player"] == choice.get("player")
                    and o["iid"] == choice.get("iid")), None)
        if opt is None:
            return "that card cannot be stolen"
        j, c = opt["player"], None
        victim = g["players"][j]
        c = next((c for c in victim["in_play"] + victim["demons"] if c["iid"] == opt["iid"]), None)
        if c is None:
            return "that card is no longer available"
        if c in victim["in_play"]:
            victim["in_play"].remove(c)
            p["in_play"].append(c)
        else:
            victim["demons"].remove(c)
            p["demons"].append(c)
        events.append(f"😈 {p['name']} steals {c['name']} from {victim['name']}!")
    elif kind == "gain_block":
        g["pending"] = None
        card = next((c for c in g["market"] if c["iid"] == choice), None)
        if card is None:
            return "that card is not on THE BLOCK"
        g["market"].remove(card)
        events.append(f"🛒 {p['name']} gains {card['name']} from THE BLOCK.")
        gain_card(g, idx, card, events)
    elif kind == "activate_choice":
        g["pending"] = None
        _, card = find_card(g, choice)
        if card is None:
            return "that card is not in play"
        _enqueue(g, idx, [card])
    elif kind == "replace_block":
        # Choice is a list (Mini App multi-select), a single iid (one at a
        # time, Telegram), or "done" to finish.
        if choice == "done":
            g["pending"] = None
        else:
            iids = choice if isinstance(choice, list) else [choice]
            for iid in iids:
                slot = next((i for i, c in enumerate(g["market"]) if c["iid"] == iid), None)
                if slot is not None:
                    old = g["market"].pop(slot)
                    g["discard"].append(old)
                    new = draw_block(g, events)
                    if new is not None:
                        g["market"].insert(slot, new)
                        events.append(f"🔁 {old['name']} replaced by {new['name']}.")
            if isinstance(choice, list):
                g["pending"] = None
    elif kind == "alligator":
        if choice == "done":
            g["pending"] = None
        else:
            opt = next((o for o in pend["options"] if o["player"] == choice.get("player")
                        and o["iid"] == choice.get("iid")), None)
            if opt is None:
                return "that card cannot be discarded"
            j = opt["player"]
            victim = g["players"][j]
            c = next((c for c in victim["in_play"] if c["iid"] == opt["iid"]), None)
            if c is None:
                return "that card is no longer available"
            discard_from_play(g, j, c, events)
            pend["remaining"] -= 1
            pend["options"] = [{"player": o["player"], "iid": o["iid"]} for o in pend["options"]
                               if o["iid"] != opt["iid"]]
            if pend["remaining"] <= 0 or not pend["options"]:
                g["pending"] = None
    elif kind == "goat_boy":
        card = next((c for c in p["in_play"] if c["iid"] == choice), None)
        if card is None or card["ctype"] != "boy":
            return "choose one of your BOYs"
        discard_from_play(g, idx, card, events)
        girls = [c["iid"] for c in p["in_play"] if c["ctype"] == "girl"]
        g["pending"] = {"kind": "goat_girl", "player": idx, "options": girls}
    elif kind == "goat_girl":
        card = next((c for c in p["in_play"] if c["iid"] == choice), None)
        if card is None or card["ctype"] != "girl":
            return "choose one of your GIRLs"
        discard_from_play(g, idx, card, events)
        g["pending"] = None
        _reshuffle(g, "demon_deck", "demon_discard", events)
        if g["demon_deck"]:
            demon = g["demon_deck"].pop()
            events.append(f"🐐 Goat summons the top Demon ({demon['name']}) for free!")
            put_demon_in_play(g, idx, demon, events, free=True)
    elif kind == "sam_animal":
        card = next((c for c in p["in_play"] if c["iid"] == choice), None)
        if card is None or card["ctype"] != "animal":
            return "choose one of your ANIMALS"
        g["pending"] = None
        discard_from_play(g, idx, card, events)
        _, src = find_card(g, pend.get("source_iid"))
        gain_souls(g, idx, 6, events, source=src)
    elif kind == "annie_branch":
        if choice == "steal":
            opts = [{"player": j, "iid": c["iid"]} for j in _victims(g, idx)
                    for c in _stealable(g, j, "kid")]
            if not opts:
                g["pending"] = None
                events.append("😈 No BOYs/GIRLs to steal.")
            else:
                g["pending"] = {"kind": "steal_card", "player": idx, "options": opts}
        elif choice == "gain":
            g["pending"] = None
            _gain_block_choice(g, idx, "any", events)
        else:
            return "choose steal or gain"
    elif kind == "rosemary":
        g["pending"] = None
        top = pend["top"]
        chosen = next((c for c in top if c["iid"] == choice), None)
        if chosen is None:
            return "choose one of the top 3 Demons"
        for c in top:
            if c is not chosen:
                g["demon_discard"].append(c)
        events.append(f"🥚 {p['name']} hatches {chosen['name']}!")
        summon_demon(g, idx, chosen, events, free=True)
    elif kind == "gross_book":
        g["pending"] = None
        chosen = next((c for c in g["demon_deck"] if c["iid"] == choice), None)
        if chosen is None:
            return "that Demon is not in the Demon Deck"
        g["demon_deck"].remove(chosen)
        random.shuffle(g["demon_deck"])
        events.append(f"📖 Gross Book summons {chosen['name']} for free!")
        put_demon_in_play(g, idx, chosen, events, free=True)
    else:
        return "unknown choice"
    drain(g, events)
    check_win(g, events)
    return None
