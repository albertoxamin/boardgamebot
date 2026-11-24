"""Tokaido Duo engine: pure rules/logic, no Telegram, no I/O.

2 players, each controlling a Pilgrim, a Merchant and an Artist on
Shikoku. Each round the first picker rolls 3 dice (one per character),
draft is 1-2-1, each chosen character must move the exact die value.
First to trigger an end condition (Temple 9, Garden 6, 6th gold slab,
10th Painting gifted) finishes the round, then scores:
Faith = Temple x Garden, Commerce = gold-slab points, Culture = points
for Paintings gifted.

Sources: official Funforge rulebook
(sources/tokaidoduo/rulebook.pdf) and BGA help
(en.doc.boardgamearena.com/Gamehelptokaidoduo). Board layout, dice,
Culture table and Boutique set verified from a live BGA table
(spectated, no login) and the BGA sprite sheets, release
261120-2009, game ID 2337:
- DICE_FACES from spriteDes.jpg (240x120) + live game log.
- CULTURE_POINTS from spritePlateauxJoueurs.png + live player
  panels (1 gift = 2 pts ... 10 gifts = 40).
- BOUTIQUE_TOKENS read face-up on a live table: Pottery-3/4,
  Fan-3/2, Doll-3 x2, Kimono-4 x2.
- STATIONS: ring order read from the board image, clockwise from
  the SE Coastal town; counts 8 coastal / 13 temple / 7 garden /
  5 hot spring / 4 seashore = 37. The large scenic circle at the
  top-left counts as a Hot Spring station (the Pilgrim start
  marker is on it); the small white circles are start markers,
  not stations, and the three blue circles on the right edge are
  Wave-tile slots, not stations.
"""
import random

# --- verified from BGA, release 261120-2009 (see module docstring) ---
DICE_FACES = {"pilgrim": [1, 2, 3, 4, 2, 3],
              "merchant": [1, 2, 3, 1, 2, 3],
              "artist": [1, 2, 3, 1, 1, 2]}
CULTURE_POINTS = [0, 2, 4, 7, 10, 14, 18, 23, 28, 34, 40]  # by Paintings gifted
BOUTIQUE_TOKENS = [("pottery", 3), ("pottery", 4), ("fan", 3), ("fan", 2),
                   ("doll", 3), ("doll", 3), ("kimono", 4), ("kimono", 4)]

GOLD_POINTS = [0, 5, 11, 18, 26, 35, 45]  # by gold slabs, 0..6
WARE_TYPES = ("kimono", "pottery", "doll", "fan")
WARE_BAG = (["kimono"] * 5 + ["pottery"] * 6 + ["doll"] * 7 + ["fan"] * 8)
WARE_EMOJI = {"kimono": "👘", "pottery": "🏺", "doll": "🎎", "fan": "🪭"}
CHARACTERS = ("pilgrim", "merchant", "artist")
CHAR_EMOJI = {"pilgrim": "⛩️", "merchant": "💰", "artist": "🎨"}

# Pilgrim ring, clockwise from the SE Coastal town (near the compass).
# kind: coastal | temple | garden | hotspring | seashore
STATIONS = [
    "coastal", "temple", "garden", "hotspring", "coastal", "temple",
    "seashore", "temple", "garden", "coastal", "temple", "hotspring",
    "seashore", "coastal", "temple", "garden", "temple", "garden",
    "coastal", "temple", "hotspring", "hotspring", "temple", "coastal",
    "seashore", "temple", "temple", "coastal", "garden", "hotspring",
    "temple", "coastal", "seashore", "garden", "garden", "temple",
    "temple",
]
assert len(STATIONS) == 37
# Coastal towns are also Pilgrim stations; town id is "c_<station>".
COASTAL_STATIONS = [i for i, k in enumerate(STATIONS) if k == "coastal"]
assert COASTAL_STATIONS == [0, 4, 9, 13, 18, 23, 27, 31]

# Merchant towns: 4 Mountain towns (draw value) + 8 Coastal towns.
MOUNTAIN_DRAW = {"m_w": 4, "m_cl": 3, "m_c": 3, "m_e": 2}
MOUNTAIN_NAMES = {"m_w": "West Mountain", "m_cl": "Centre-Left Mountain",
                  "m_c": "Centre Mountain", "m_e": "East Mountain"}
TOWN_EDGES = [
    ("m_w", "m_cl"), ("m_cl", "m_c"), ("m_c", "m_e"),
    ("m_w", "c_18"), ("m_w", "c_13"),
    ("m_cl", "c_23"), ("m_cl", "c_9"),
    ("m_c", "c_27"), ("m_c", "c_4"),
    ("m_e", "c_31"), ("m_e", "c_0"),
]
TOWN_ADJ = {}
for _a, _b in TOWN_EDGES:
    TOWN_ADJ.setdefault(_a, []).append(_b)
    TOWN_ADJ.setdefault(_b, []).append(_a)
for _t in list(MOUNTAIN_DRAW) + [f"c_{s}" for s in COASTAL_STATIONS]:
    TOWN_ADJ.setdefault(_t, [])

def town_name(t):
    if t in MOUNTAIN_NAMES:
        return MOUNTAIN_NAMES[t]
    if t.startswith("c_"):
        return f"Coastal town {int(t[2:])}"
    return t

# Artist zones, clockwise from NW. Icon per zone, adjacency derived
# from the board geometry: zones are the 8 interior faces of the
# trade-route graph + outer ring (see module docstring / faces in
# research notes). ZONE_SPACES lists, per zone, the towns and the
# Pilgrim-ring stations surrounding it (for Paint counting).
ZONES = [
    {"icon": "moon", "name": "Moon (NW)"},
    {"icon": "mountain", "name": "Mountain (N)"},
    {"icon": "waterfall", "name": "Waterfall (NE)"},
    {"icon": "bamboo", "name": "Bamboo (E)"},
    {"icon": "mountain", "name": "Mountain (SE)"},
    {"icon": "moon", "name": "Moon (S)"},
    {"icon": "bamboo", "name": "Bamboo (SW)"},
    {"icon": "waterfall", "name": "Waterfall (W)"},
]
ZONE_ICON_EMOJI = {"moon": "🌙", "mountain": "⛰️", "waterfall": "🌊", "bamboo": "🎋"}
ZONE_ADJ = {
    0: [7, 6, 1], 1: [0, 2, 5], 2: [1, 4, 3], 3: [2, 4],
    4: [2, 3, 5], 5: [4, 6, 1], 6: [5, 7, 0], 7: [6, 0],
}
ZONE_SPACES = [
    {"towns": ["c_18", "c_23", "m_cl", "m_w"], "stations": [19, 20, 21, 22]},
    {"towns": ["c_23", "c_27", "m_c", "m_cl"], "stations": [24, 25, 26]},
    {"towns": ["c_27", "c_31", "m_e", "m_c"], "stations": [28, 29, 30]},
    {"towns": ["c_31", "c_0", "m_e"], "stations": [32, 33, 34, 35, 36]},
    {"towns": ["c_0", "c_4", "m_c", "m_e"], "stations": [1, 2, 3]},
    {"towns": ["c_4", "c_9", "m_cl", "m_c"], "stations": [5, 6, 7, 8]},
    {"towns": ["c_9", "c_13", "m_w", "m_cl"], "stations": [10, 11, 12]},
    {"towns": ["c_13", "c_18", "m_w"], "stations": [14, 15, 16, 17]},
]
# Zone centres / town positions (% of board image) for the Mini App.
# The board art is displayed rotated -90deg (portrait), exactly as
# BGA does (#tdn-board:before rotate(-90deg)), so these are in the
# rotated frame: new_x = old_y, new_y = 100 - old_x.
ZONE_POS = [(37, 73), (38, 52), (37, 34), (45, 24),
            (62, 34), (70, 52), (70, 73), (55, 83)]
TOWN_POS = {"m_w": (50, 68), "m_cl": (50, 53), "m_c": (55, 40), "m_e": (48, 27),
            "c_0": (73, 18), "c_4": (85, 40), "c_9": (78, 65), "c_13": (73, 87),
            "c_18": (32, 82), "c_23": (22, 65), "c_27": (22, 40), "c_31": (28, 18)}
# Centres of the wrapped-package symbols in the dashed boxes at the
# board edge, one per coastal town (measured off tokaidoduo-board.webp).
# The boutique pill sits exactly over its town's package (FB-0014),
# not offset towards the board centre.
PACKAGE_POS = {"c_0": (88, 15), "c_4": (91, 33), "c_9": (90, 63), "c_13": (81, 95),
               "c_18": (19, 91), "c_23": (9, 60), "c_27": (9, 47), "c_31": (9, 11)}

# Starting positions: opposite sides. Pilgrim starts are the two
# Temple stations marked with a parasol, Merchant starts the two
# Coastal towns marked with a grid, Artist starts the two zones
# marked with a paintbrush.
STARTS = [
    {"pilgrim": 1, "merchant": "c_0", "artist": 3},
    {"pilgrim": 22, "merchant": "c_18", "artist": 0},
]
PAINTING_TILES = {"purple": (["moon"] * 3 + ["waterfall"] * 3 +
                             ["mountain"] * 2 + ["bamboo"] * 2),
                  "green": (["moon"] * 2 + ["waterfall"] * 2 +
                            ["mountain"] * 3 + ["bamboo"] * 3)}
WAVES = {
    "pilgrim": [("hasty", "Hasty: move +1"), ("tranquil", "Tranquil: move -1")],
    "merchant": [("crafty", "Crafty: +1 coin per Ware sold"),
                 ("robust", "Robust: draw +1 Ware, store 6")],
    "artist": [("proficient", "Proficient: reveal +1 tile when Painting"),
               ("inspired", "Inspired: Gift any icon on your path")],
}


def new_player(user_id, name, color=""):
    return {
        "user_id": int(user_id), "name": name, "color": color,
        "pilgrim_pos": 0, "temple": 1, "garden": 1,
        "merchant_pos": "c_0", "artist_zone": 0,
        "wares": [], "coins": 0, "gold": 0,
        "paintings": [], "gifted": 0,
        "waves": {"pilgrim": None, "merchant": None, "artist": None},
    }


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby", "round": 0, "first_picker": 0,
        "pick_index": 0, "dice": {}, "dice_taken": [],
        "pick_char": None, "pick_value": 0, "pick_path": [],
        "pending": None, "hot_spring": None, "hot_spring_gained": None,
        "waves_board": [], "boutiques": {}, "ware_bag": [],
        "end_triggered": False, "end_reason": "",
        "winner": None, "scores": None,
        "log": [], "board_message_id": None,
    }


def name_of(g, pid):
    return g["players"][pid]["name"] if 0 <= pid < len(g["players"]) else "?"


def start_game(g, events, rng=None):
    if len(g["players"]) != 2:
        return "Tokaido Duo needs exactly 2 players."
    r = rng or random
    for i, p in enumerate(g["players"]):
        p["color"] = "purple" if i == 0 else "green"
        p["pilgrim_pos"] = STARTS[i]["pilgrim"]
        p["merchant_pos"] = STARTS[i]["merchant"]
        p["artist_zone"] = STARTS[i]["artist"]
        p["temple"] = 1
        p["garden"] = 1
        p["wares"] = []
        p["coins"] = 0
        p["gold"] = 0
        p["gifted"] = 0
        p["waves"] = {"pilgrim": None, "merchant": None, "artist": None}
        tiles = list(PAINTING_TILES[p["color"]])
        r.shuffle(tiles)
        p["paintings"] = [{"icon": t, "revealed": False, "gifted": False}
                          for t in tiles]
    boutiques = list(BOUTIQUE_TOKENS)
    r.shuffle(boutiques)
    g["boutiques"] = {f"c_{s}": {"ware": w, "price": pr}
                      for s, (w, pr) in zip(COASTAL_STATIONS, boutiques)}
    g["ware_bag"] = list(WARE_BAG)
    r.shuffle(g["ware_bag"])
    g["waves_board"] = []
    for ch in CHARACTERS:
        side = r.choice(WAVES[ch])[0]
        g["waves_board"].append({"char": ch, "side": side})
    g["hot_spring"] = None
    g["hot_spring_gained"] = None
    g["end_triggered"] = False
    g["end_reason"] = ""
    g["winner"] = None
    g["scores"] = None
    g["phase"] = "play"
    g["round"] = 1
    g["first_picker"] = 0
    g["log"] = []
    events.append("🗾 Tokaido Duo! Each player has a Pilgrim, a Merchant and an Artist.")
    events.append(f"🎲 {name_of(g, 0)} rolls first - pick a die, move that character.")
    _start_round(g, events, rng)
    return None


def _start_round(g, events, rng=None):
    r = rng or random
    g["dice"] = {ch: r.choice(DICE_FACES[ch]) for ch in CHARACTERS}
    g["dice_taken"] = []
    g["pick_index"] = 0
    g["pick_char"] = None
    g["pending"] = None
    events.append("🎲 Dice: " + ", ".join(
        f"{CHAR_EMOJI[ch]} {g['dice'][ch]}" for ch in CHARACTERS) + ".")


def pick_order(g):
    fp = g["first_picker"]
    return [fp, 1 - fp, fp]


def current_picker(g):
    if g["phase"] != "play" or g.get("pending"):
        # pending choices belong to the player who made the pick
        if g.get("pending"):
            return g["pending"]["by"]
        return None
    if g["pick_index"] >= 3:
        return None
    return pick_order(g)[g["pick_index"]]


def available_dice(g):
    return [ch for ch in CHARACTERS if ch not in g["dice_taken"]]


# --- scoring ---

def faith_score(p):
    return p["temple"] * p["garden"]


def commerce_score(p):
    return GOLD_POINTS[min(p["gold"], 6)]


def culture_score(p):
    return CULTURE_POINTS[min(p["gifted"], 10)]


def scores(g):
    out = []
    for p in g["players"]:
        out.append({"faith": faith_score(p), "commerce": commerce_score(p),
                    "culture": culture_score(p),
                    "total": faith_score(p) + commerce_score(p) + culture_score(p),
                    "coins": p["coins"]})
    return out


def _check_end(g, events):
    if g["end_triggered"]:
        return
    for i, p in enumerate(g["players"]):
        if p["temple"] >= 9:
            g["end_triggered"] = True
            g["end_reason"] = f"{name_of(g, i)} completed the Temple track"
        elif p["garden"] >= 6:
            g["end_triggered"] = True
            g["end_reason"] = f"{name_of(g, i)} completed the Garden track"
        elif p["gold"] >= 6:
            g["end_triggered"] = True
            g["end_reason"] = f"{name_of(g, i)} gained a 6th gold slab"
        elif p["gifted"] >= 10:
            g["end_triggered"] = True
            g["end_reason"] = f"{name_of(g, i)} gifted their last Painting"
        if g["end_triggered"]:
            events.append(f"🏁 End of game triggered: {g['end_reason']} - finish this round!")
            return


def _finish_game(g, events):
    g["phase"] = "game_end"
    sc = scores(g)
    g["scores"] = sc
    best = max(s["total"] for s in sc)
    winners = [i for i, s in enumerate(sc) if s["total"] == best]
    if len(winners) == 1:
        g["winner"] = winners[0]
    else:
        most_coins = max(sc[i]["coins"] for i in winners)
        winners = [i for i in winners if sc[i]["coins"] == most_coins]
        g["winner"] = winners[0] if len(winners) == 1 else None
    for i, p in enumerate(g["players"]):
        s = sc[i]
        events.append(f"📊 {name_of(g, i)}: Faith {s['faith']} + Commerce {s['commerce']} "
                      f"+ Culture {s['culture']} = {s['total']} pts")
    if g["winner"] is None:
        events.append("🤝 Shared victory - tied on points and coins!")
    else:
        events.append(f"🏆 {name_of(g, g['winner'])} wins Tokaido Duo!")


def _advance_pick(g, events, rng=None):
    """Move to the next pick in the round, or the next round / game end."""
    if g["phase"] != "play":
        return
    g["pick_char"] = None
    g["pick_value"] = 0
    g["pick_path"] = []
    g["pending"] = None
    g["pick_index"] += 1
    if g["pick_index"] < 3:
        nxt = pick_order(g)[g["pick_index"]]
        events.append(f"👉 {name_of(g, nxt)} picks a die.")
        return
    if g["end_triggered"]:
        _finish_game(g, events)
        return
    g["round"] += 1
    g["first_picker"] = 1 - g["first_picker"]
    events.append(f"🎲 Round {g['round']} - {name_of(g, g['first_picker'])} rolls first.")
    _start_round(g, events, rng)


# --- helpers: coins / wares ---

def _convert_coins(g, pid, events):
    p = g["players"][pid]
    while p["coins"] >= 10 and p["gold"] < 6:
        p["coins"] -= 10
        p["gold"] += 1
        events.append(f"🪙 {name_of(g, pid)} trades 10 coins for a gold slab "
                      f"({p['gold']}/6, {commerce_score(p)} pts).")
        _check_end(g, events)


def ware_cap(p):
    return 6 if p["waves"].get("merchant") == "robust" else 5


def _draw_wares(g, pid, n, events, rng=None):
    r = rng or random
    p = g["players"][pid]
    drawn = []
    for _ in range(n):
        if not g["ware_bag"]:
            break
        drawn.append(g["ware_bag"].pop(r.randrange(len(g["ware_bag"]))))
    if drawn:
        p["wares"].extend(drawn)
        events.append(f"🎒 {name_of(g, pid)} draws {len(drawn)} Ware(s): " +
                      ", ".join(WARE_EMOJI[w] for w in drawn) + ".")
    return drawn


# --- movement: exact-length simple paths ---

def _simple_paths(adj, start, length):
    """All nodes reachable from start in exactly `length` steps,
    never revisiting a node. Returns {node: [path, ...]}."""
    results = {}

    def walk(node, path):
        if len(path) - 1 == length:
            results.setdefault(node, []).append(list(path))
            return
        for nb in adj.get(node, []):
            if nb in path:
                continue
            walk(nb, path + [nb])

    walk(start, [start])
    return results


def pilgrim_destinations(g, pid, value):
    """Pilgrim moves clockwise `value` stations, jumping over an
    occupied landing station to the next empty one. Returns the
    (single) landing station, or None if the ring were full."""
    p = g["players"][pid]
    occupied = set()
    for q in g["players"]:
        occupied.add(q["pilgrim_pos"])
        if q["merchant_pos"].startswith("c_"):
            occupied.add(int(q["merchant_pos"][2:]))
    landing = (p["pilgrim_pos"] + value) % len(STATIONS)
    for _ in range(len(STATIONS)):
        if landing not in occupied:
            return landing
        landing = (landing + 1) % len(STATIONS)
    return None


def merchant_destinations(g, pid, value):
    p = g["players"][pid]
    paths = _simple_paths(TOWN_ADJ, p["merchant_pos"], value)
    out = {}
    for dest, plist in paths.items():
        # Coastal towns hold one meeple at a time (Merchant or Pilgrim).
        if dest.startswith("c_"):
            st = int(dest[2:])
            blocked = False
            for q in g["players"]:
                if q["pilgrim_pos"] == st:
                    blocked = True
                if q is not p and q["merchant_pos"] == dest:
                    blocked = True
            if blocked:
                continue
        out[dest] = plist[0]
    return out


def artist_destinations(g, pid, value):
    p = g["players"][pid]
    paths = _simple_paths(ZONE_ADJ, p["artist_zone"], value)
    return {z: plist[0] for z, plist in paths.items()}


def zone_meeple_count(g, pid, zone):
    """Other meeples (any player, any character except this player's
    Artist) in the arrival zone: towns + ring stations around it."""
    spec = ZONE_SPACES[zone]
    towns = set(spec["towns"])
    stations = set(spec["stations"])
    count = 0
    for i, q in enumerate(g["players"]):
        if q["merchant_pos"] in towns:
            count += 1
        if q["pilgrim_pos"] in stations:
            count += 1
        if i != pid and q["artist_zone"] == zone:
            count += 1
        if i == pid and False:
            pass
    # The moving Artist itself is already in the zone; it does not count.
    return count


# --- picking a die and moving ---

def pick_die(g, pid, char, events, rng=None):
    if g["phase"] != "play":
        return "Game is not in progress."
    if g.get("pending"):
        return "Resolve the pending choice first."
    if current_picker(g) != pid:
        return "Not your pick."
    if char not in CHARACTERS:
        return "Unknown character."
    if char in g["dice_taken"]:
        return "That die is already taken."
    g["dice_taken"].append(char)
    g["pick_char"] = char
    g["pick_value"] = g["dice"][char]
    g["pick_path"] = []
    g["repeating"] = False
    events.append(f"🎲 {name_of(g, pid)} takes the {CHAR_EMOJI[char]} die "
                  f"({g['dice'][char]}) - move the {char}.")
    return _begin_move(g, pid, events, rng)


def _begin_move(g, pid, events, rng=None):
    char = g["pick_char"]
    value = g["pick_value"]
    p = g["players"][pid]
    if char == "pilgrim":
        wave = p["waves"].get("pilgrim")
        opts = [value]
        if wave == "hasty":
            opts.append(value + 1)
        elif wave == "tranquil" and value > 1:
            opts.append(value - 1)
        opts = sorted(set(d for d in opts if d >= 1))
        if len(opts) > 1:
            g["pending"] = {"kind": "pilgrim_wave", "by": pid,
                            "options": opts}
            return None
        return _move_pilgrim(g, pid, opts[0], events, rng)
    if char == "merchant":
        dests = merchant_destinations(g, pid, value)
        if not dests:
            events.append(f"💰 {name_of(g, pid)} has no Merchant path of "
                          f"exactly {value} - no move, no action.")
            return _after_arrival(g, pid, events, rng)
        if len(dests) == 1:
            return _move_merchant(g, pid, next(iter(dests)), events, rng)
        g["pending"] = {"kind": "merchant_dest", "by": pid,
                        "options": sorted(dests)}
        return None
    # artist
    dests = artist_destinations(g, pid, value)
    if not dests:
        events.append(f"🎨 {name_of(g, pid)} has no Artist path of "
                      f"exactly {value} - no move, no action.")
        return _after_arrival(g, pid, events, rng)
    if len(dests) == 1:
        return _move_artist(g, pid, next(iter(dests)), events, rng)
    g["pending"] = {"kind": "artist_dest", "by": pid,
                    "options": sorted(dests)}
    return None


def _after_arrival(g, pid, events, rng=None):
    """Offer the Hot Spring repeat if held and eligible, else next pick."""
    if g["phase"] != "play":
        return None
    if g.get("pending"):
        return None
    if not g.get("repeating") and g.get("hot_spring") == pid:
        gained = g.get("hot_spring_gained")
        now = (g["round"], g["pick_index"])
        if gained != now:
            g["pending"] = {"kind": "hotspring", "by": pid}
            return None
    return _advance_pick(g, events, rng)


def _move_pilgrim(g, pid, distance, events, rng=None):
    p = g["players"][pid]
    g["pick_distance"] = distance
    landing = pilgrim_destinations(g, pid, distance)
    if landing is None:
        events.append("⛩️ No empty Pilgrim station - no move.")
        return _after_arrival(g, pid, events, rng)
    p["pilgrim_pos"] = landing
    kind = STATIONS[landing]
    events.append(f"⛩️ {name_of(g, pid)}'s Pilgrim moves {distance} to "
                  f"station {landing} ({kind}).")
    if kind == "coastal":
        b = g["boutiques"].get(f"c_{landing}", {})
        coins = b.get("price", 2)
        p["coins"] += coins
        events.append(f"🏘️ Coastal town: +{coins} coins "
                      f"({WARE_EMOJI.get(b.get('ware'), '')}{b.get('ware', '')} boutique).")
        _convert_coins(g, pid, events)
        return _after_arrival(g, pid, events, rng)
    if kind == "temple":
        p["temple"] = min(9, p["temple"] + 1)
        events.append(f"⛩️ Temple: {name_of(g, pid)} advances to {p['temple']}/9.")
        _check_end(g, events)
        return _after_arrival(g, pid, events, rng)
    if kind == "garden":
        p["garden"] = min(6, p["garden"] + 1)
        events.append(f"🌳 Garden: {name_of(g, pid)} advances to {p['garden']}/6.")
        _check_end(g, events)
        return _after_arrival(g, pid, events, rng)
    if kind == "hotspring":
        if g.get("hot_spring") == pid:
            events.append("♨️ Hot Spring: you already hold the token - nothing happens.")
        else:
            prev = g.get("hot_spring")
            g["hot_spring"] = pid
            g["hot_spring_gained"] = (g["round"], g["pick_index"])
            events.append("♨️ Hot Spring: " + (f"{name_of(g, pid)} steals the token!"
                          if prev is not None else f"{name_of(g, pid)} takes the token!") +
                          " Use it on a future pick to repeat a move.")
        return _after_arrival(g, pid, events, rng)
    # seashore
    return _seashore(g, pid, events, rng)


def _seashore(g, pid, events, rng=None):
    p = g["players"][pid]
    if all(v is not None for v in p["waves"].values()):
        events.append("🌊 Seashore: you already hold all 3 Wave tiles - no effect.")
        return _after_arrival(g, pid, events, rng)
    board_chars = [w["char"] for w in g["waves_board"]]
    opp = g["players"][1 - pid]
    steal_chars = [ch for ch in CHARACTERS
                   if opp["waves"].get(ch) is not None and ch not in board_chars]
    if not board_chars and not steal_chars:
        events.append("🌊 Seashore: no Wave tiles left to take.")
        return _after_arrival(g, pid, events, rng)
    g["pending"] = {"kind": "wave_take", "by": pid,
                    "board": board_chars, "steal": steal_chars}
    return None


def _take_wave(g, pid, value, events):
    p = g["players"][pid]
    opp = g["players"][1 - pid]
    if value.startswith("board:"):
        ch = value[6:]
        tile = next((w for w in g["waves_board"] if w["char"] == ch), None)
        if not tile:
            return "That Wave tile is not on the board."
        g["waves_board"].remove(tile)
        p["waves"][ch] = tile["side"]
        events.append(f"🌊 {name_of(g, pid)} takes the {ch} Wave tile "
                      f"({tile['side']}).")
    elif value.startswith("steal:"):
        ch = value[6:]
        side = opp["waves"].get(ch)
        if not side:
            return "Your opponent does not hold that Wave tile."
        opp["waves"][ch] = None
        p["waves"][ch] = side
        if ch == "merchant" and side == "robust" and len(opp["wares"]) > 5:
            # Robust loss while holding 6: return 1 Ware to the bag.
            w = opp["wares"].pop()
            g["ware_bag"].append(w)
            events.append(f"🎒 {name_of(g, 1 - pid)} loses Robust with 6 Wares - "
                          f"returns a {WARE_EMOJI[w]}{w} to the bag.")
        events.append(f"🌊 {name_of(g, pid)} steals the {ch} Wave tile ({side})!")
    else:
        return "Unknown Wave tile."
    return None


def _move_merchant(g, pid, dest, events, rng=None):
    p = g["players"][pid]
    paths = merchant_destinations(g, pid, g["pick_value"])
    g["pick_path"] = paths.get(dest, [p["merchant_pos"], dest])
    p["merchant_pos"] = dest
    events.append(f"💰 {name_of(g, pid)}'s Merchant moves to {town_name(dest)}.")
    if dest in MOUNTAIN_DRAW:
        n = MOUNTAIN_DRAW[dest]
        if p["waves"].get("merchant") == "robust":
            n += 1
        _draw_wares(g, pid, n, events, rng)
        if len(p["wares"]) > ware_cap(p):
            g["pending"] = {"kind": "keep_wares", "by": pid}
            return None
        return _after_arrival(g, pid, events, rng)
    # coastal town: sell matching Wares (optional)
    b = g["boutiques"].get(dest, {})
    matching = [w for w in p["wares"] if w == b.get("ware")]
    if not matching:
        events.append(f"🏘️ Coastal town: no {b.get('ware', '')} to sell "
                      f"(boutique: {WARE_EMOJI.get(b.get('ware'), '')}{b.get('ware', '')} "
                      f"for {b.get('price', 2)} coins).")
        return _after_arrival(g, pid, events, rng)
    g["pending"] = {"kind": "sell", "by": pid, "town": dest}
    return None


def _move_artist(g, pid, dest, events, rng=None):
    p = g["players"][pid]
    paths = artist_destinations(g, pid, g["pick_value"])
    g["pick_path"] = paths.get(dest, [p["artist_zone"], dest])
    p["artist_zone"] = dest
    z = ZONES[dest]
    events.append(f"🎨 {name_of(g, pid)}'s Artist moves to the "
                  f"{z['name']} zone {ZONE_ICON_EMOJI[z['icon']]}.")
    g["pending"] = {"kind": "artist_action", "by": pid}
    return None


def _gift_eligible(g, pid):
    p = g["players"][pid]
    top = next((t for t in p["paintings"] if t["revealed"] and not t["gifted"]), None)
    if not top:
        return False
    if p["waves"].get("artist") == "inspired":
        icons = {ZONES[z]["icon"] for z in g.get("pick_path", [])}
        return top["icon"] in icons
    return top["icon"] == ZONES[p["artist_zone"]]["icon"]


def _do_paint(g, pid, events):
    p = g["players"][pid]
    n = zone_meeple_count(g, pid, p["artist_zone"])
    if p["waves"].get("artist") == "proficient":
        n += 1
    remaining = [t for t in p["paintings"] if not t["revealed"]]
    n = min(n, len(remaining))
    for t in remaining[:n]:
        t["revealed"] = True
    events.append(f"🎨 {name_of(g, pid)} Paints: reveals {n} Painting tile(s) "
                  f"({zone_meeple_count(g, pid, p['artist_zone'])} other meeple(s) "
                  f"in the zone).")
    return None


def _do_gift(g, pid, events):
    p = g["players"][pid]
    top = next((t for t in p["paintings"] if t["revealed"] and not t["gifted"]), None)
    if not top:
        return "No revealed Painting to gift."
    top["gifted"] = True
    p["gifted"] += 1
    events.append(f"🎁 {name_of(g, pid)} gifts a {ZONE_ICON_EMOJI[top['icon']]} "
                  f"Painting ({p['gifted']}/10, {culture_score(p)} Culture pts).")
    _check_end(g, events)
    return None


# --- pending choices ---

def pending_options(g, pid):
    pend = g.get("pending")
    if not pend or pend["by"] != pid:
        return []
    kind = pend["kind"]
    if kind == "pilgrim_wave":
        v = g["pick_value"]
        opts = [{"value": f"dist:{d}", "label": f"Move {d} station(s)"}
                for d in pend["options"]]
        return opts
    if kind == "merchant_dest":
        return [{"value": f"dest:{t}", "label": town_name(t)}
                for t in pend["options"]]
    if kind == "artist_dest":
        return [{"value": f"dest:{z}",
                 "label": f"{ZONES[z]['name']} {ZONE_ICON_EMOJI[ZONES[z]['icon']]}"}
                for z in pend["options"]]
    if kind == "wave_take":
        opts = []
        for ch in pend.get("board", []):
            tile = next(w for w in g["waves_board"] if w["char"] == ch)
            opts.append({"value": f"board:{ch}",
                         "label": f"Take {ch} Wave ({tile['side']})"})
        for ch in pend.get("steal", []):
            side = g["players"][1 - pid]["waves"].get(ch)
            opts.append({"value": f"steal:{ch}",
                         "label": f"Steal {ch} Wave ({side}) from opponent"})
        return opts
    if kind == "sell":
        p = g["players"][pid]
        b = g["boutiques"].get(pend["town"], {})
        per = b.get("price", 2)
        if p["waves"].get("merchant") == "crafty":
            per += 1
        opts = []
        for i, w in enumerate(p["wares"]):
            if w == b.get("ware"):
                opts.append({"value": f"sell:{i}",
                             "label": f"Sell {WARE_EMOJI[w]}{w} for {per} coins"})
        opts.append({"value": "done", "label": "Done selling"})
        return opts
    if kind == "keep_wares":
        p = g["players"][pid]
        return [{"value": f"discard:{i}",
                 "label": f"Return {WARE_EMOJI[w]}{w} to the bag"}
                for i, w in enumerate(p["wares"])]
    if kind == "artist_action":
        opts = [{"value": "paint", "label": "🎨 Paint (reveal tiles)"}]
        if _gift_eligible(g, pid):
            opts.append({"value": "gift", "label": "🎁 Gift the top revealed Painting"})
        return opts
    if kind == "hotspring":
        return [{"value": "use",
                 "label": f"♨️ Use Hot Spring: repeat the {g['pick_char']} move "
                          f"({g['pick_value']})"},
                {"value": "skip", "label": "Skip the Hot Spring"}]
    return []


def choose(g, pid, value, events, rng=None):
    pend = g.get("pending")
    if not pend or pend["by"] != pid:
        return "No pending choice."
    valid = {o["value"] for o in pending_options(g, pid)}
    if str(value) not in valid:
        return "Invalid choice."
    kind = pend["kind"]
    if kind == "pilgrim_wave":
        g["pending"] = None
        return _move_pilgrim(g, pid, int(str(value)[5:]), events, rng)
    if kind == "merchant_dest":
        g["pending"] = None
        return _move_merchant(g, pid, str(value)[5:], events, rng)
    if kind == "artist_dest":
        g["pending"] = None
        return _move_artist(g, pid, int(str(value)[5:]), events, rng)
    if kind == "wave_take":
        g["pending"] = None
        err = _take_wave(g, pid, str(value), events)
        if err:
            return err
        return _after_arrival(g, pid, events, rng)
    if kind == "sell":
        if str(value) == "done":
            g["pending"] = None
            return _after_arrival(g, pid, events, rng)
        p = g["players"][pid]
        i = int(str(value)[5:])
        b = g["boutiques"].get(pend["town"], {})
        per = b.get("price", 2)
        if p["waves"].get("merchant") == "crafty":
            per += 1
        w = p["wares"].pop(i)
        p["coins"] += per
        events.append(f"💰 {name_of(g, pid)} sells {WARE_EMOJI[w]}{w} for {per} coins.")
        g["ware_bag"].append(w)
        _convert_coins(g, pid, events)
        if g["phase"] != "play":
            g["pending"] = None
            return None
        if not any(x == b.get("ware") for x in p["wares"]):
            g["pending"] = None
            return _after_arrival(g, pid, events, rng)
        return None  # still pending: sell more or done
    if kind == "keep_wares":
        p = g["players"][pid]
        i = int(str(value)[8:])
        w = p["wares"].pop(i)
        g["ware_bag"].append(w)
        events.append(f"🎒 {name_of(g, pid)} returns a {WARE_EMOJI[w]}{w} to the bag.")
        if len(p["wares"]) > ware_cap(p):
            return None  # still pending
        g["pending"] = None
        return _after_arrival(g, pid, events, rng)
    if kind == "artist_action":
        g["pending"] = None
        if str(value) == "paint":
            _do_paint(g, pid, events)
        else:
            err = _do_gift(g, pid, events)
            if err:
                return err
        return _after_arrival(g, pid, events, rng)
    if kind == "hotspring":
        g["pending"] = None
        if str(value) == "skip":
            return _advance_pick(g, events, rng)
        # repeat the same character move with the same die value
        g["hot_spring"] = None
        g["repeating"] = True
        events.append(f"♨️ {name_of(g, pid)} uses the Hot Spring token to repeat "
                      f"the {g['pick_char']} move ({g['pick_value']})!")
        err = _begin_move(g, pid, events, rng)
        g["repeating"] = False
        return err
    return "Unknown pending choice."


def board_lines(g):
    if g["phase"] == "lobby":
        return [f"🗾 <b>Tokaido Duo lobby</b> - {len(g['players'])}/2 players. "
                "Friends: /tokaidoduo_join, anyone: /tokaidoduo_start"]
    sc = scores(g) if g["phase"] in ("play", "game_end") else None
    lines = [f"🗾 <b>Tokaido Duo</b> - Round {g['round']} | "
             f"Faith ⛩️🌳 · Commerce 💰 · Culture 🎨"]
    for i, p in enumerate(g["players"]):
        mark = "▶️ " if current_picker(g) == i and g["phase"] == "play" else ""
        s = sc[i] if sc else {"faith": 0, "commerce": 0, "culture": 0, "total": 0}
        lines.append(
            f"{mark}{'🟣' if p['color'] == 'purple' else '🟢'} <b>{p['name']}</b> "
            f"⛩️{p['temple']}×🌳{p['garden']}={s['faith']} · 💰{p['gold']} slabs={s['commerce']} "
            f"· 🎨{p['gifted']}/10={s['culture']} · <b>{s['total']} pts</b> · "
            f"🪙{p['coins']} · 🎒{len(p['wares'])}/{ware_cap(p)}")
        lines.append(
            f"   ⛩️ Pilgrim @{p['pilgrim_pos']} ({STATIONS[p['pilgrim_pos']]}) · "
            f"💰 Merchant @{town_name(p['merchant_pos'])} · "
            f"🎨 Artist @{ZONES[p['artist_zone']]['name']}")
    if g["phase"] == "play":
        dice = ", ".join(f"{CHAR_EMOJI[ch]} {g['dice'][ch]}"
                         + (" (taken)" if ch in g["dice_taken"] else "")
                         for ch in CHARACTERS)
        lines.append(f"🎲 Dice: {dice}")
        bouts = "; ".join(
            f"{WARE_EMOJI[w]}{w}→" + "/".join(
                f"{t}({b['price']}🪙)" for t, b in sorted(
                    g["boutiques"].items(), key=lambda kv: int(kv[0].split("_")[1]))
                if b["ware"] == w)
            for w in ("fan", "doll", "kimono", "pottery")
            if any(b["ware"] == w for b in g["boutiques"].values()))
        lines.append(f"🏘️ Sell: {bouts}")
        wb = "; ".join(f"{w['char']}: {dict(WAVES[w['char']])[w['side']]}"
                       for w in g["waves_board"])
        lines.append(f"🌊 Waves on board: {wb}")
        if g.get("hot_spring") is not None:
            lines.append(f"♨️ Hot Spring held by {name_of(g, g['hot_spring'])}.")
        if g.get("pending"):
            lines.append("⚡ Choose: " + " · ".join(
                o["label"] for o in pending_options(g, g["pending"]["by"])))
    if g["phase"] == "game_end":
        lines.append(f"🏆 Game over - winner: <b>{name_of(g, g['winner'])}</b>"
                     if g["winner"] is not None else "🤝 Game over - shared victory")
    return lines
