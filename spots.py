"""Spots (CMYK, 2022) engine: push-your-luck dice placement on dog cards.

2-4 players (solo d0g mode not implemented). Each player has a pack of
dog cards (gray side up), a yard for buried dice, treats, and scored
dogs. On your turn either do a trick (choose a face-up trick tile, flip
it down, follow its steps: roll dice, place them on matching open
spots on your dogs or bury them, reroll with treats, repeat THEN steps)
or score all your completed dogs. Buried total over 7 = bust (all dice
on unscored dogs and in your yard discarded, turn ends). Completing all
your dogs mid-trick auto-scores them instantly. First to 6 scored wins.

Dog data transcribed from the BGA/TTS scans (8x4 sheet, 32 cards; some
cards depict multiple dogs). Paw counts are from the sheet paw icons.
Trick data transcribed from the physical tiles (all 22; the default set
in play is Adoption Event).
"""
import random

# (slug, name, spots, paws) - spot values are the numbers dice must match
DOG_DATA = [
    ("leif-mudge-bucky", "Leif, Mudge & Bucky", [1, 2, 2, 3], 1),
    ("bristles", "Bristles", [2, 1], 0),
    ("sundrop-nori", "Sundrop & Nori", [2, 3], 0),
    ("goliath", "Goliath", [2, 1, 5], 1),
    ("gumbo", "Gumbo", [2, 6, 1], 1),
    ("bongo", "Bongo", [1, 3], 0),
    ("pebble", "Pebble", [1, 3, 4], 1),
    ("wilbur", "Wilbur", [1, 6, 3], 1),
    ("eloise", "Eloise", [5, 1], 0),
    ("cabbage-taters-ham", "Cabbage, Taters & Ham", [4, 4, 1], 1),
    ("honcho", "Honcho", [6, 4, 1], 1),
    ("ursula", "Ursula", [1, 5], 0),
    ("mayor", "Mayor", [6, 1], 0),
    ("burt", "Burt", [1], 0),
    ("wolfgang", "Wolfgang", [5, 4, 2], 1),
    ("raya", "Raya", [2, 5, 3], 1),
    ("doog", "Doog", [5, 2, 5, 2], 1),
    ("tolene", "Tolene", [4, 2], 0),
    ("rogue", "Rogue", [2, 5, 5], 1),
    ("nutmeg", "Nutmeg", [2, 6, 4], 1),
    ("xerxes", "Xerxes", [5, 2], 0),
    ("rupert", "Rupert", [2, 5, 5], 1),
    ("louise", "Louise", [2, 5], 0),
    ("missy-maam", "Missy & Ma'am", [4, 3], 0),
    ("mirabelle", "Mirabelle", [3, 4, 4], 1),
    ("lil-beth", "Lil Beth", [5, 3], 0),
    ("pierogi-gyota-momo", "Pierogi, Gyota & Momo", [6, 5, 3], 1),
    ("handsome", "Handsome", [2, 5], 0),
    ("frankie", "Frankie", [5, 4], 0),
    ("zipper", "Zipper", [6, 5, 5], 1),
    ("bitsy", "Bitsy", [5, 5], 0),
    ("gretchen", "Gretchen", [6, 6], 0),
]
assert len(DOG_DATA) == 32

# Trick tiles in the Adoption Event set (Howl/Roll Over always included).
BEGINNER_TILES = ["howl", "roll-over", "walk", "run", "fetch", "beg"]
ALL_TILES = ["howl", "roll-over", "walk", "run", "fetch", "beg", "stay", "play-dead",
             "gobble", "chew", "guard", "scavenge", "hunt", "search", "retrieve",
             "trot", "dig", "track", "sprint", "bolt", "dogpile", "chase"]
TILE_NAMES = {t: t.replace("-", " ").title().replace("Roll Over", "Roll Over")
              for t in ALL_TILES}
TILE_NAMES.update({"howl": "Howl", "roll-over": "Roll Over", "stay": "Stay",
                   "play-dead": "Play Dead", "gobble": "Gobble", "chew": "Chew",
                   "guard": "Guard", "scavenge": "Scavenge", "fetch": "Fetch",
                   "hunt": "Hunt", "search": "Search", "retrieve": "Retrieve",
                   "trot": "Trot", "dig": "Dig", "track": "Track", "sprint": "Sprint",
                   "run": "Run", "bolt": "Bolt", "dogpile": "Dogpile", "chase": "Chase",
                   "walk": "Walk", "beg": "Beg"})

TOTAL_DICE = 40
TOTAL_TREATS = 20
START_TREATS = 1
BUST_LIMIT = 7       # buried total > 7 busts
WIN_SCORED = 6
MAX_DOGS = 6


def build_dog_deck():
    deck = [{"slug": slug, "name": name, "spots": list(spots), "paws": paws}
            for slug, name, spots, paws in DOG_DATA]
    random.shuffle(deck)
    return deck


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [{"user_id": int(creator_id), "name": creator_name,
                     "dogs": [], "scored": [], "yard": [], "treats": START_TREATS}],
        "phase": "lobby",  # lobby|playing|game_end
        "dog_deck": [], "dice_supply": TOTAL_DICE, "treat_supply": TOTAL_TREATS,
        "tiles": [],  # {slug, faceup, treat_on}
        "current_index": 0, "winner": None,
        "trick": None,   # active trick state (see below)
        "pending": None, "board_message_id": None, "last_roll": None,
    }


def name_of(g, user_id):
    for p in g["players"]:
        if p["user_id"] == user_id:
            return p["name"]
    return "?"


def start_game(g, events):
    if len(g["players"]) < 2:
        return "need at least 2 players"
    if len(g["players"]) > 4:
        return "too many players (max 4)"
    n = len(g["players"])
    g["dog_deck"] = build_dog_deck()
    for i, d in enumerate(g["dog_deck"]):
        d["iid"] = i + 1
    g["dice_supply"] = TOTAL_DICE - n          # 1 die each for the opening roll
    g["treat_supply"] = TOTAL_TREATS - n
    g["tiles"] = [{"slug": s, "faceup": True, "treat_on": False} for s in BEGINNER_TILES]
    g["trick"] = None
    g["pending"] = None
    for p in g["players"]:
        p["dogs"] = []
        for _ in range(2):
            d = g["dog_deck"].pop()
            d["placed"] = {}
            p["dogs"].append(d)
        p["scored"] = []
        p["yard"] = [random.randint(1, 6)]     # opening roll, buried
        p["treats"] = START_TREATS
    hi = max(p["yard"][0] for p in g["players"])
    g["current_index"] = next(i for i, p in enumerate(g["players"]) if p["yard"][0] == hi)
    g["phase"] = "playing"
    events.append(f"🐶 Spots started! {g['players'][g['current_index']]['name']} "
                  f"rolled highest ({hi}) and goes first.")
    return None


def yard_total(p):
    return sum(p["yard"])


def dog_complete(dog):
    return len(dog.get("placed") or {}) == len(dog["spots"])


def _take_dice(g, n):
    take = min(n, g["dice_supply"])
    g["dice_supply"] -= take
    return [random.randint(1, 6) for _ in range(take)]


def _return_dice(g, n):
    g["dice_supply"] += n


def _gain_treats(g, idx, n, events):
    got = min(n, g["treat_supply"])
    g["treat_supply"] -= got
    g["players"][idx]["treats"] += got
    if got:
        events.append(f"🦴 {g['players'][idx]['name']} gains {got} treat(s).")
    return got


def _spend_treats(g, idx, n):
    if g["players"][idx]["treats"] < n:
        return False
    g["players"][idx]["treats"] -= n
    g["treat_supply"] += n
    return True


def _bust(g, idx, events):
    """Wipe dice from unscored dogs and yard; turn ends immediately."""
    p = g["players"][idx]
    n = sum(len(d.get("placed") or {}) for d in p["dogs"]) + len(p["yard"])
    _return_dice(g, n)
    for d in p["dogs"]:
        d["placed"] = {}
    p["yard"] = []
    g["trick"] = None
    g["pending"] = None
    events.append(f"💥 {p['name']} busts! All dice on dogs and in the yard are discarded.")
    _end_turn(g, events)


def _score_dogs(g, idx, events, instant=False):
    """Score ALL completed dogs: flip them, discard their dice, draw
    replacements up to 6 total cards. Returns True if game ended."""
    p = g["players"][idx]
    done = [d for d in p["dogs"] if dog_complete(d)]
    if not done:
        return False
    for d in done:
        _return_dice(g, len(d.get("placed") or {}))
        p["scored"].append(d)
    p["dogs"] = [d for d in p["dogs"] if d not in done]
    events.append(f"🏅 {p['name']} scores {len(done)} dog(s) "
                  f"({', '.join(d['name'] for d in done)})"
                  + (" - instantly!" if instant else "."))
    for _ in range(len(done)):
        if len(p["dogs"]) + len(p["scored"]) >= MAX_DOGS or not g["dog_deck"]:
            break
        d = g["dog_deck"].pop()
        d["placed"] = {}
        p["dogs"].append(d)
        events.append(f"🃏 Draws {d['name']}.")
    if len(p["scored"]) >= WIN_SCORED:
        g["phase"] = "game_end"
        g["winner"] = p["user_id"]
        g["trick"] = None
        events.append(f"🏆 {p['name']} scored 6 dogs and wins!")
        return True
    return False


def _maybe_auto_score(g, idx, events):
    """Fast-and-risky: all unscored dogs complete -> score instantly."""
    p = g["players"][idx]
    if p["dogs"] and all(dog_complete(d) for d in p["dogs"]):
        return _score_dogs(g, idx, events, instant=True)
    return False


def _place_or_bury(g, idx, die, target, events):
    """target: ('dog', dog_iid, spot_idx) or ('yard',). Validates and places.
    Returns error or None. Bust is checked by the caller after burying."""
    p = g["players"][idx]
    if target[0] == "yard":
        p["yard"].append(die)
        events.append(f"⛏ {p['name']} buries a {die}. (yard total {yard_total(p)})")
        return None
    _, iid, spot_idx = target
    dog = next((d for d in p["dogs"] if d["iid"] == iid), None)
    if dog is None:
        return "that dog is not yours"
    dog.setdefault("placed", {})
    if not (0 <= spot_idx < len(dog["spots"])):
        return "no such spot"
    if spot_idx in dog["placed"]:
        return "spot already filled"
    if dog["spots"][spot_idx] != die:
        return f"that spot needs a {dog['spots'][spot_idx]}, not a {die}"
    dog["placed"][spot_idx] = die
    events.append(f"🐾 {p['name']} places {die} on {dog['name']} "
                  f"({len(dog['placed'])}/{len(dog['spots'])}).")
    return None


def _check_bust(g, idx, events):
    if yard_total(g["players"][idx]) > BUST_LIMIT:
        _bust(g, idx, events)
        return True
    return False


def _end_turn(g, events):
    """Advance to the next player; reset trick tiles if only one is faceup."""
    g["current_index"] = (g["current_index"] + 1) % len(g["players"])
    faceup = [t for t in g["tiles"] if t["faceup"]]
    if len(faceup) == 1:
        t = faceup[0]
        if g["treat_supply"] > 0:
            t["treat_on"] = True
            g["treat_supply"] -= 1
            events.append(f"🦴 A treat is placed on {TILE_NAMES[t['slug']]} and all "
                          f"trick tiles flip faceup.")
        for t2 in g["tiles"]:
            t2["faceup"] = True


def _paws(g, idx):
    return sum(d["paws"] for d in g["players"][idx]["dogs"])


def _incomplete_dogs(g, idx):
    return [d for d in g["players"][idx]["dogs"] if not dog_complete(d)]


# ---------------- Trick engine ----------------

def _fresh_trick(slug, idx=0):
    return {"tile": slug, "idx": idx, "step": 0, "dice": [], "placed_roll": 0,
            "rolled_steps": [], "opt_done": False, "repeat_done": False,
            "fetch_num": None, "guard_num": None, "bolt_left": None,
            "chase_n": 0, "pd_buried": None, "trot_stage": None,
            "dig_left": None, "ret_num": None}


def choose_trick(g, idx, slug, events):
    _heal(g, events)
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["pending"] or g["trick"]:
        return "finish the current trick first"
    tile = next((t for t in g["tiles"] if t["slug"] == slug), None)
    if tile is None:
        return "no such trick tile in this game"
    if not tile["faceup"]:
        return "that trick is face down"
    tile["faceup"] = False
    if tile["treat_on"]:
        tile["treat_on"] = False
        _gain_treats(g, idx, 1, events)
        events.append(f"🦴 {g['players'][idx]['name']} takes the treat on {TILE_NAMES[slug]}!")
    g["trick"] = _fresh_trick(slug, idx)
    events.append(f"🎪 {g['players'][idx]['name']} chooses {TILE_NAMES[slug]}!")
    advance(g, events)
    return None


def advance(g, events):
    """Run trick steps until waiting for input or the trick ends."""
    while g["trick"] and not g["pending"] and g["phase"] == "playing":
        steps = TRICK_STEPS[g["trick"]["tile"]]
        if g["trick"]["step"] >= len(steps):
            g["trick"] = None
            _end_turn(g, events)
            return
        if steps[g["trick"]["step"]](g, events):
            g["trick"]["step"] += 1
        else:
            return


def _heal(g, events):
    """Recover a trick whose pending choice was lost: resume the driver."""
    if g.get("trick") and not g.get("pending"):
        advance(g, events)


def _start_roll(g, events, n):
    if g["dice_supply"] <= 0:
        total = 0
        for p in g["players"]:
            total += sum(len(d["placed"]) for d in p["dogs"]) + len(p["yard"])
            for d in p["dogs"]:
                d["placed"] = {}
            p["yard"] = []
        g["dice_supply"] += total
        events.append("🎲 No dice in supply - all dice in play are reset!")
    g["trick"]["dice"] = _take_dice(g, n)
    g["trick"]["placed_roll"] = 0
    g["last_roll"] = list(g["trick"]["dice"])
    events.append(f"🎲 Rolled {len(g['trick']['dice'])}: "
                  f"{', '.join(map(str, g['trick']['dice']))}.")
    t = g["trick"]
    g["pending"] = {"kind": "place", "player": g["current_index"],
                    "only_num": t.get("only_num"), "hunt_limit": t.get("hunt_limit"),
                    "search": bool(t.get("search")), "placed_sum": 0}
    return False


def _place_done(g, events):
    t = g["trick"]
    left = t["dice"]
    if left:
        _return_dice(g, len(left))
        events.append(f"🗑 {len(left)} leftover die/dice discarded.")
        t["dice"] = []
    g["pending"] = None
    if t["tile"] == "hunt":
        t["hunt_done"] = True
    if t.get("search"):
        t["search_done"] = True
    return True


def _mk_roll(n):
    def fn(g, events):
        t = g["trick"]
        if t["step"] in t["rolled_steps"]:
            return True
        t["rolled_steps"].append(t["step"])
        return _start_roll(g, events, n)
    return fn


def _step_optional_roll(g, events):
    t = g["trick"]
    if t.get("opt_done"):
        return True
    g["pending"] = {"kind": "optional_roll", "player": g["current_index"]}
    return False


def _step_repeat(g, events):
    """Repeatable THEN step: ask repeat/done (Bolt: done only if allowed)."""
    t = g["trick"]
    if t.get("repeat_done"):
        return True
    if t["tile"] == "bolt" and _paws(g, t["idx"]) < t.get("bolt_left", 0):
        t["step"] = 0  # must keep rolling while dice remain in the pool
        return True
    g["pending"] = {"kind": "repeat", "player": g["current_index"]}
    return False


def _step_howl(g, events):
    t = g["trick"]
    if t["step"] == 0:
        t["step"] = 1
        p = g["players"][t["idx"]]
        if len(p["dogs"]) + len(p["scored"]) < MAX_DOGS and g["dog_deck"]:
            d = g["dog_deck"].pop()
            d["placed"] = {}
            p["dogs"].append(d)
            events.append(f"🐶 Draws {d['name']} (Howl).")
    return _step_optional_roll(g, events)


def _step_rollover(g, events):
    t = g["trick"]
    if t.get("ro_done"):
        return True
    t["ro_done"] = True
    p = g["players"][t["idx"]]
    buried = list(p["yard"])
    p["yard"] = []
    t["dice"] = [random.randint(1, 6) for _ in buried]
    t["placed_roll"] = 0
    g["last_roll"] = list(t["dice"])
    events.append(f"🎲 Roll Over: re-rolls {len(buried)} buried dice.")
    g["pending"] = {"kind": "place", "player": t["idx"], "only_num": None,
                    "hunt_limit": None, "search": False, "placed_sum": 0}
    return False


def _step_fetch(g, events):
    t = g["trick"]
    if t.get("fetch_rolled") is None:
        t["fetch_rolled"] = _take_dice(g, 8)
        events.append(f"🎲 Fetch rolls 8: {', '.join(map(str, t['fetch_rolled']))}.")
        g["pending"] = {"kind": "choose_number", "player": t["idx"],
                        "options": sorted(set(t["fetch_rolled"]))}
        return False
    return True


def _step_guard(g, events):
    t = g["trick"]
    if t.get("guard_num") is None:
        g["pending"] = {"kind": "choose_number", "player": t["idx"],
                        "options": list(range(0, 7))}
        return False
    if t.get("guard_rolled") is None:
        t["guard_rolled"] = _take_dice(g, 4)
        num = t["guard_num"]
        kept = [d for d in t["guard_rolled"] if d <= num]
        _return_dice(g, len(t["guard_rolled"]) - len(kept))
        events.append(f"🛡️ Guard: dice over {num} discarded "
                      f"({', '.join(map(str, t['guard_rolled']))} -> keep {kept}).")
        t["dice"] = kept
        t["placed_roll"] = 0
        g["pending"] = {"kind": "place", "player": t["idx"], "only_num": None,
                        "hunt_limit": None, "search": False, "placed_sum": 0}
        return False
    return True


def _step_scavenge(g, events):
    t = g["trick"]
    if t.get("scav_rolled") is None:
        t["scav_rolled"] = _take_dice(g, 4)
        events.append(f"🎲 Scavenge rolls 4: {', '.join(map(str, t['scav_rolled']))}.")
        t["dice"] = list(t["scav_rolled"])
        t["placed_roll"] = 0
        g["pending"] = {"kind": "scavenge", "player": t["idx"],
                        "options": list(range(len(t["dice"])))}
        return False
    return True


def _step_hunt(g, events):
    t = g["trick"]
    if t.get("hunt_done"):
        return True
    t["hunt_limit"] = 2
    return _start_roll(g, events, 2 + _paws(g, t["idx"]))


def _step_search(g, events):
    t = g["trick"]
    if t.get("search_done"):
        return True
    t["search"] = True
    return _start_roll(g, events, 7)


def _step_retrieve(g, events):
    t = g["trick"]
    if t.get("ret_top") is None:
        if not g["dog_deck"]:
            events.append("🃏 Dog deck is empty - Retrieve fizzles.")
            return True
        top = g["dog_deck"][-1]
        t["ret_top"] = top
        g["pending"] = {"kind": "choose_number", "player": t["idx"],
                        "options": sorted(set(top["spots"]))}
        return False
    if t.get("ret_die") is None:
        if g["dice_supply"] <= 0:
            events.append("🎲 No dice in the supply - Retrieve fizzles.")
            return True
        g["dice_supply"] -= 1
        t["ret_die"] = True
        t["dice"] = [t["ret_num"]]
        t["placed_roll"] = 0
        g["pending"] = {"kind": "place", "player": t["idx"], "only_num": None,
                        "hunt_limit": None, "search": False, "placed_sum": 0}
        return False
    return True


def _step_trot(g, events):
    t = g["trick"]
    if t.get("trot_stage") is None:
        idx = t["idx"]
        opts = []
        for d in g["players"][idx]["dogs"]:
            for si in d["placed"]:
                for d2 in g["players"][idx]["dogs"]:
                    for sj in range(len(d2["spots"])):
                        if sj not in d2["placed"]:
                            opts.append({"from_dog": d["iid"], "from_spot": si,
                                         "to_dog": d2["iid"], "to_spot": sj})
        if not opts:
            events.append("🐾 No die to move - Trot fizzles.")
            return True
        t["trot_stage"] = "move"
        g["pending"] = {"kind": "trot", "player": idx, "options": opts}
        return False
    return True


def _step_dig(g, events):
    t = g["trick"]
    if t.get("dig_left") is None:
        t["dig_left"] = _paws(g, t["idx"])
    if t["dig_left"] > 0:
        opts = []
        for j, p in enumerate(g["players"]):
            for yi, v in enumerate(p["yard"]):
                if v < 6:
                    opts.append({"player": j, "yard": yi, "delta": 1})
                opts.append({"player": j, "yard": yi, "delta": -1})
        if not opts:
            t["dig_left"] = 0
            return True
        g["pending"] = {"kind": "dig", "player": t["idx"], "options": opts}
        return False
    return True


def _step_beg(g, events):
    idx = g["trick"]["idx"]
    _gain_treats(g, idx, 1, events)
    _gain_treats(g, idx, _paws(g, idx), events)
    return True


def _step_stay(g, events):
    idx = g["trick"]["idx"]
    n = sum(1 for t in g["tiles"] if not t["faceup"] and t["slug"] != g["trick"]["tile"])
    _gain_treats(g, idx, n, events)
    return True


def _step_play_dead(g, events):
    t = g["trick"]
    if t.get("pd_rolled") is None:
        t["pd_rolled"] = _take_dice(g, 1)
        t["dice"] = list(t["pd_rolled"])
        t["placed_roll"] = 0
        t["pd_buried"] = None
        g["pending"] = {"kind": "place", "player": t["idx"], "only_num": None,
                        "hunt_limit": None, "search": False, "placed_sum": 0}
        return False
    if t.get("pd_buried") is not None:
        _gain_treats(g, t["idx"], t["pd_buried"], events)
    return True


def _step_gobble(g, events):
    idx = g["trick"]["idx"]
    _gain_treats(g, idx, 7, events)
    unfilled = [s for d in g["players"][idx]["dogs"] for i, s in enumerate(d["spots"])
                if i not in d["placed"]]
    if unfilled:
        back = min(g["players"][idx]["treats"], max(unfilled))
        g["players"][idx]["treats"] -= back
        g["treat_supply"] += back
        events.append(f"🦴 Returns {back} treat(s) (highest unfilled spot).")
    return True


def _step_chew(g, events):
    idx = g["trick"]["idx"]
    _gain_treats(g, idx, g["players"][idx]["treats"], events)
    _gain_treats(g, idx, 1, events)
    return True


def _step_bolt_intro(g, events):
    t = g["trick"]
    if t.get("bolt_count") is None:
        cap = min(12, g["dice_supply"])
        if cap < 3:
            events.append("🎲 Not enough dice in supply - Bolt fizzles.")
            return True
        g["pending"] = {"kind": "bolt_count", "player": t["idx"],
                        "options": list(range(3, cap + 1))}
        return False
    g["dice_supply"] -= t["bolt_count"]
    t["bolt_left"] = t["bolt_count"]
    return True


def _step_repeat(g, events):
    """Repeatable THEN step (Run/Chase/Sprint/Dogpile/Bolt): ask again."""
    t = g["trick"]
    if t.get("repeat_done"):
        return True
    if t["tile"] == "bolt" and _paws(g, t["idx"]) < t.get("bolt_left", 0):
        t["step"] = 1  # must keep rolling while the pool has dice left
        return True
    g["pending"] = {"kind": "repeat", "player": g["current_index"]}
    return False


def _end_turn(g, events):
    """Advance to the next player; reset trick tiles if only one is faceup."""
    g["current_index"] = (g["current_index"] + 1) % len(g["players"])
    faceup = [t for t in g["tiles"] if t["faceup"]]
    if len(faceup) == 1:
        t = faceup[0]
        if g["treat_supply"] > 0:
            t["treat_on"] = True
            g["treat_supply"] -= 1
            events.append(f"🦴 A treat is placed on {TILE_NAMES[t['slug']]} and all "
                          f"trick tiles flip faceup.")
        for t2 in g["tiles"]:
            t2["faceup"] = True


def do_place(g, idx, die_pos, target, events):
    """Place/bury one die from the current pool."""
    _heal(g, events)
    pend = g.get("pending")
    if not pend or pend["kind"] != "place" or pend["player"] != idx:
        return "no placement pending for you"
    t = g["trick"]
    if not (0 <= die_pos < len(t["dice"])):
        return "no such die in the pool"
    die = t["dice"][die_pos]
    if pend.get("only_num") is not None and die != pend["only_num"]:
        return f"only {pend['only_num']}s may be placed"
    if pend.get("search") and pend["placed_sum"] + die > 8:
        return "that would put the placed total over 8"
    was_buried = target[0] == "yard"
    err = _place_or_bury(g, idx, die, target, events)
    if err:
        return err
    t["dice"].pop(die_pos)
    t["placed_roll"] += 1
    pend["placed_sum"] = pend.get("placed_sum", 0) + die
    if t["tile"] == "play-dead":
        t["pd_buried"] = die if was_buried else None
    if _check_bust(g, idx, events):
        return None
    _maybe_auto_score(g, idx, events)
    if g["phase"] == "game_end":
        return None
    if pend.get("hunt_limit") is not None and t["placed_roll"] >= pend["hunt_limit"]:
        _place_done(g, events)
        advance(g, events)
        return None
    if not t["dice"]:
        _place_done(g, events)
        advance(g, events)
    return None


def do_reroll(g, idx, indices, events):
    """Spend a treat to reroll dice from the current (unplaced) roll.
    Standard tricks reroll all dice; Track rerolls a chosen subset."""
    _heal(g, events)
    pend = g.get("pending")
    if not pend or pend["kind"] != "place" or pend["player"] != idx:
        return "no roll to reroll"
    t = g["trick"]
    if t["placed_roll"]:
        return "you already placed dice from this roll"
    if g["players"][idx]["treats"] < 1:
        return "no treats to spend"
    if t["tile"] == "track":
        if not indices:
            return "choose at least one die to reroll (Track)"
        idxs = indices
    else:
        idxs = list(range(len(t["dice"])))
    if any(not (0 <= i < len(t["dice"])) for i in idxs):
        return "no such die"
    _spend_treats(g, idx, 1)
    for i in idxs:
        t["dice"][i] = random.randint(1, 6)
    g["last_roll"] = list(t["dice"])
    events.append(f"🔁 {g['players'][idx]['name']} rerolls "
                  f"{'some' if t['tile'] == 'track' else 'all'} dice for a treat: "
                  f"{', '.join(map(str, t['dice']))}.")
    pend["placed_sum"] = 0
    return None


def score_action(g, idx, events):
    """Slow-and-steady scoring instead of a trick."""
    _heal(g, events)
    if g["phase"] != "playing":
        return "not in playing phase"
    if idx != g["current_index"]:
        return "not your turn"
    if g["pending"] or g["trick"]:
        return "finish the current trick first"
    p = g["players"][idx]
    if not any(dog_complete(d) for d in p["dogs"]):
        return "you have no completed dog to score"
    _score_dogs(g, idx, events)
    if g["phase"] != "game_end":
        _end_turn(g, events)
    return None


def apply_choice(g, idx, choice, events):
    """Apply the current pending choice. Returns error or None."""
    _heal(g, events)
    pend = g.get("pending")
    if not pend or pend["player"] != idx:
        return "no pending choice for you"
    kind = pend["kind"]
    t = g["trick"]
    p = g["players"][idx]
    if kind == "optional_roll":
        g["pending"] = None
        t["opt_done"] = True
        if choice == "roll":
            _start_roll(g, events, 1)
        else:
            advance(g, events)
        return None
    if kind == "repeat":
        g["pending"] = None
        if choice == "done":
            t["repeat_done"] = True
            advance(g, events)
            return None
        tile = t["tile"]
        if tile == "run":
            _start_roll(g, events, 1)
        elif tile == "dogpile":
            t["dp_stage"] = None
            _step_dogpile_cycle(g, events)
        elif tile == "sprint":
            _step_sprint_cycle(g, events)
        elif tile == "chase":
            _step_chase_cycle(g, events)
        elif tile == "dogpile":
            _step_dogpile_cycle(g, events)
        elif tile == "bolt":
            _step_bolt_cycle(g, events)
        return None
    if kind == "choose_number":
        g["pending"] = None
        tile = t["tile"]
        if tile == "fetch":
            t["fetch_num"] = choice
            kept = [d for d in t["fetch_rolled"] if d == choice]
            _return_dice(g, len(t["fetch_rolled"]) - len(kept))
            events.append(f"🎯 Fetch: places/buries only {choice}s "
                          f"({', '.join(map(str, kept))}); the rest are discarded.")
            t["dice"] = kept
            t["placed_roll"] = 0
            g["pending"] = {"kind": "place", "player": idx, "only_num": None,
                            "hunt_limit": None, "search": False, "placed_sum": 0}
        elif tile == "guard":
            t["guard_num"] = choice
            advance(g, events)
        else:  # retrieve
            t["ret_num"] = choice
            advance(g, events)
        return None
    if kind == "scavenge":
        if choice == "done":
            g["pending"] = None
            t["scav_done"] = True
            t["placed_roll"] = 0
            g["pending"] = {"kind": "place", "player": idx, "only_num": None,
                            "hunt_limit": None, "search": False, "placed_sum": 0}
            return None
        i = choice
        if not (0 <= i < len(t["dice"])):
            return "no such die"
        if t["dice"][i] >= yard_total(p):
            return "only dice lower than your buried total may be discarded"
        _return_dice(g, 1)
        events.append(f"🗑 Discards a {t['dice'].pop(i)} (Scavenge).")
        pend["options"] = list(range(len(t["dice"])))
        return None
    if kind == "place" and choice == "done" and pend.get("search"):
        _place_done(g, events)
        advance(g, events)
        return None
    if kind == "trot":
        opt = choice
        src = next((d for d in p["dogs"] if d["iid"] == opt["from_dog"]), None)
        dst = next((d for d in p["dogs"] if d["iid"] == opt["to_dog"]), None)
        if src is None or dst is None or opt["from_spot"] not in src["placed"] \
                or opt["to_spot"] in dst["placed"]:
            return "that move is not possible"
        val = src["placed"].pop(opt["from_spot"])
        dst["placed"][opt["to_spot"]] = dst["spots"][opt["to_spot"]]
        g["pending"] = None
        t["trot_stage"] = "done"
        events.append(f"🐾 Moves a die on {src['name']} to {dst['name']} "
                      f"(now a {dst['spots'][opt['to_spot']]}).")
        advance(g, events)
        return None
    if kind == "dig":
        if choice == "done":
            g["pending"] = None
            t["dig_left"] = 0
            advance(g, events)
            return None
        opt = choice
        pl = g["players"][opt["player"]]
        if not (0 <= opt["yard"] < len(pl["yard"])):
            return "that buried die is no longer there"
        v = pl["yard"][opt["yard"]]
        if opt["delta"] == -1 and v == 1:
            pl["yard"].pop(opt["yard"])
            _return_dice(g, 1)
            events.append(f"⛏ {pl['name']}'s buried 1 is discarded (Dig).")
        else:
            nv = v + opt["delta"]
            if not (1 <= nv <= 6):
                return "cannot adjust that die that way"
            pl["yard"][opt["yard"]] = nv
            events.append(f"⛏ {pl['name']}'s buried die {v} -> {nv} (Dig).")
        t["dig_left"] -= 1
        g["pending"] = None
        if _check_bust(g, opt["player"], events):
            return None
        advance(g, events)
        return None
    if kind == "bolt_count":
        g["pending"] = None
        t["bolt_count"] = int(choice)
        advance(g, events)
        return None
    if kind == "dogpile_take":
        opt = choice
        if opt.get("src") == "yard":
            if not (0 <= opt["yard"] < len(p["yard"])):
                return "that buried die is no longer there"
            p["yard"].pop(opt["yard"])
        else:
            d = next((d for d in p["dogs"] if d["iid"] == opt.get("dog")), None)
            if d is None or opt.get("spot") not in d["placed"]:
                return "that placed die is no longer there"
            d["placed"].pop(opt["spot"])
        g["pending"] = None
        t["dp_stage"] = "rolled"
        t["dice"] = [random.randint(1, 6) for _ in range(3)]
        t["placed_roll"] = 0
        g["last_roll"] = list(t["dice"])
        events.append(f"🎲 Dogpile rolls 3 (incl. the taken die): "
                      f"{', '.join(map(str, t['dice']))}.")
        g["pending"] = {"kind": "place", "player": idx, "only_num": None,
                        "hunt_limit": None, "search": False, "placed_sum": 0}
        return None
    return "unknown choice"


def _step_bolt_cycle(g, events):
    t = g["trick"]
    if t.get("cycle_rolled"):
        t["cycle_rolled"] = False
        return True
    if t.get("bolt_left") is None or t["bolt_left"] <= 0:
        return True
    t["bolt_left"] -= 1
    t["cycle_rolled"] = True
    return _start_roll(g, events, 1)


def _step_sprint_cycle(g, events):
    t = g["trick"]
    if t.get("cycle_rolled"):
        t["cycle_rolled"] = False
        return True
    n = len(_incomplete_dogs(g, t["idx"]))
    if n == 0:
        events.append("🐕 No incomplete dogs - Sprint ends.")
        t["repeat_done"] = True
        return True
    t["cycle_rolled"] = True
    return _start_roll(g, events, n)


def _step_dogpile_cycle(g, events):
    t = g["trick"]
    if t.get("dp_stage") is None:
        idx = t["idx"]
        p = g["players"][idx]
        opts = [{"src": "yard", "yard": i} for i in range(len(p["yard"]))]
        for d in p["dogs"]:
            for si in d["placed"]:
                opts.append({"src": "dog", "dog": d["iid"], "spot": si})
        if not opts:
            events.append("🐕 No dice to take - Dogpile ends.")
            return True
        t["dp_stage"] = "take"
        g["pending"] = {"kind": "dogpile_take", "player": idx, "options": opts}
        return False
    return True


def _step_chase_cycle(g, events):
    t = g["trick"]
    if t.get("cycle_rolled"):
        t["cycle_rolled"] = False
        return True
    t["chase_n"] = t.get("chase_n", 0) + 1
    t["cycle_rolled"] = True
    return _start_roll(g, events, t["chase_n"])


TRICK_STEPS = {
    "howl": [_step_howl],
    "roll-over": [_step_rollover, _step_optional_roll],
    "walk": [_mk_roll(2), _step_optional_roll],
    "run": [_mk_roll(3), lambda g, e: _step_repeat(g, e)],
    "fetch": [_step_fetch],
    "beg": [_step_beg],
    "stay": [_step_stay],
    "play-dead": [_step_play_dead],
    "gobble": [_step_gobble],
    "chew": [_step_chew],
    "guard": [_step_guard],
    "scavenge": [_step_scavenge],
    "hunt": [_step_hunt],
    "search": [_step_search],
    "retrieve": [_step_retrieve],
    "trot": [_step_trot, _mk_roll(2)],
    "dig": [_step_dig, _mk_roll(2)],
    "track": [_mk_roll(3)],
    "sprint": [_step_sprint_cycle, lambda g, e: _step_repeat(g, e)],
    "bolt": [lambda g, e: _step_bolt_intro(g, e), _step_bolt_cycle, lambda g, e: _step_repeat(g, e)],
    "dogpile": [_step_dogpile_cycle, lambda g, e: _step_repeat(g, e)],
    "chase": [_step_chase_cycle, lambda g, e: _step_repeat(g, e)],
}


