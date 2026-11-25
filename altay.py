"""Altay: Dawn of Civilization engine for the Telegram bot and Mini App.

A compact two-player implementation using the public Board Game Arena art.
Action cards, achievements, settlements and conquest markers are simplified
while keeping the core production / build / combat / development loop.
"""

import random

VERSION = "altay/2"
SEAFARERS_REGIONS = [25, 26]
SEAFARERS_MARKERS = [3, 2]
SEA_ZONES = ["A", "B"]
SEA_COASTS = {
    "A": [0, 6, 12, 13, 18, 19, 23, 25],
    "B": [1, 3, 7, 8, 10, 14, 17, 20, 21, 22, 24, 26],
}
SEA_ANCHORS = {"A": [31.7, 18.7], "B": [80.4, 32.7]}
RESOURCE_NAMES = {
    "food": "Food",
    "wood": "Wood",
    "metal": "Metal",
    "stone": "Stone",
    "culture": "Culture",
}
RESOURCE_ICONS = {
    "food": "🌾",
    "wood": "🪵",
    "metal": "⚒️",
    "stone": "🪨",
    "culture": "📜",
}

FACTION_ORDER = ["EARTHFOLK", "ELVENFOLK", "FIREFOLK", "SMALLFOLK"]
FACTIONS = {
    "EARTHFOLK": {
        "name": "Earthfolk",
        "color": "#d8a529",
        "row": 0,
        "deck": ["colonist", "digger", "hunter", "hunter", "hunter",
                 "village", "village", "warrior", "warrior", "warrior"],
    },
    "ELVENFOLK": {
        "name": "Elvenfolk",
        "color": "#3fae7c",
        "row": 1,
        "deck": ["hunter", "hunter", "hunter", "hunter", "hunter",
                 "loremaster", "loremaster", "village", "warrior", "warrior"],
    },
    "FIREFOLK": {
        "name": "Firefolk",
        "color": "#e35a35",
        "row": 2,
        "deck": ["hunter", "hunter", "hunter", "shaman",
                 "village", "village", "warrior", "warrior", "warrior", "warrior"],
    },
    "SMALLFOLK": {
        "name": "Smallfolk",
        "color": "#8d6bd8",
        "row": 3,
        "deck": ["craftsman_wood", "craftsman_stone", "hunter", "hunter",
                 "hunter", "hunter", "spellweaver", "village", "warrior", "warrior"],
    },
}

CARDS = {
    "colonist": {"name": "Colonist", "kind": "produce", "resources": {"food": 1, "wood": 1},
                 "text": "Produce 1 food and 1 wood."},
    "digger": {"name": "Digger", "kind": "produce", "resources": {"stone": 1},
               "text": "Produce 1 stone."},
    "hunter": {"name": "Hunter", "kind": "produce", "resources": {"food": 1},
               "text": "Produce 1 food."},
    "village": {"name": "Village", "kind": "build",
                "text": "Gain one settlement build (costs 2 food)."},
    "warrior": {"name": "Warrior", "kind": "attack", "swords": 1,
                "text": "Add 1 sword this turn."},
    "loremaster": {"name": "Loremaster", "kind": "produce", "resources": {"culture": 1},
                   "text": "Produce 1 culture."},
    "shaman": {"name": "Shaman", "kind": "produce", "resources": {"food": 1, "culture": 1},
               "text": "Produce 1 food and 1 culture."},
    "spellweaver": {"name": "Spellweaver", "kind": "produce", "resources": {"culture": 2},
                    "text": "Produce 2 culture."},
    "craftsman_wood": {"name": "Craftsman (Wood)", "kind": "produce", "resources": {"wood": 1},
                       "text": "Produce 1 wood."},
    "craftsman_stone": {"name": "Craftsman (Stone)", "kind": "produce", "resources": {"stone": 1},
                        "text": "Produce 1 stone."},
    # Market cards: "sprite" is [col, row] into web/altay-actions.webp
    # (10 cols x 15 rows). Rows 4-14 hold the BGA action cards, one type
    # per row, cols 1-8 (cols 0 and 9 are card backs); col 4 is used.
    # Every sprite below was checked against the sheet (FB-0018): the old
    # coords showed the wrong card — e.g. Scholar showed the card back,
    # Chariot showed a Worker, City showed a Chariot. Two cards are named
    # after their real BGA art: "miner" became Stonecutter (its effect is
    # "produce 2 stone", exactly the Stonecutter's) and "herbalist" became
    # Farmer (produce 2 food). Architect and Champion have no real BGA
    # counterpart, so they use the closest art: Town (build) and Cavalry
    # (2 shields). Legacy ids stay as aliases so games saved before the
    # rename still load and play.
    # "sea_sprite" is the same card's [col, row] into the Seafarers sheet
    # web/altay-seafarers-actions.webp (FB-0056): that sheet is 11 cols
    # x 19 rows, NOT 10 x 18 as the Seafarers code assumed — the action
    # rows sit one row lower (rows 5-15 instead of 4-14), the new row 4
    # holds extra starter art, and the sea cards are rows 16-18. The old
    # coords showed slices of several cards at once in Seafarers games.
    "worker": {"name": "Worker", "kind": "produce", "resources": {"food": 1},
               "cost": {"wood": 1}, "sprite": [4, 12], "sea_sprite": [4, 13],
               "text": "Cost 1 wood. Produce 1 food."},
    "stonecutter": {"name": "Stonecutter", "kind": "produce", "resources": {"stone": 2},
                    "cost": {"wood": 1}, "sprite": [4, 7], "sea_sprite": [4, 8],
                    "text": "Cost 1 wood. Produce 2 stone."},
    "farmer": {"name": "Farmer", "kind": "produce", "resources": {"food": 2},
               "cost": {"food": 1}, "sprite": [4, 4], "sea_sprite": [4, 5],
               "text": "Cost 1 food. Produce 2 food."},
    "scholar": {"name": "Scholar", "kind": "produce", "resources": {"culture": 2},
                "cost": {"culture": 1}, "sprite": [4, 8], "sea_sprite": [4, 9],
                "text": "Cost 1 culture. Produce 2 culture."},
    "chariot": {"name": "Chariot", "kind": "attack", "swords": 2, "cost": {"metal": 2},
                "vp": 1, "sprite": [4, 13], "sea_sprite": [4, 14],
                "text": "Cost 2 metal. 2 swords. Worth 1 VP."},
    "cavalry": {"name": "Cavalry", "kind": "attack", "swords": 2,
                "cost": {"food": 1, "metal": 1}, "vp": 1, "sprite": [4, 10],
                "sea_sprite": [4, 11],
                "text": "Cost 1 food, 1 metal. 2 swords. Worth 1 VP."},
    "architect": {"name": "Architect", "kind": "build2", "cost": {"stone": 2, "wood": 1},
                  "vp": 1, "sprite": [4, 11], "sea_sprite": [4, 12],
                  "text": "Cost 2 stone, 1 wood. Two builds. Worth 1 VP."},
    "champion": {"name": "Champion", "kind": "attack_defense", "swords": 1, "shields": 2,
                 "cost": {"culture": 2}, "vp": 1, "sprite": [4, 10],
                 "sea_sprite": [4, 11],
                 "text": "Cost 2 culture. 1 sword, 2 shields. Worth 1 VP."},
    "merchant": {"name": "Merchant", "kind": "produce", "resources": {"wood": 1, "culture": 1},
                 "cost": {"food": 1}, "sprite": [4, 9], "sea_sprite": [4, 10],
                 "text": "Cost 1 food. Produce 1 wood and 1 culture."},
    "city": {"name": "City", "kind": "build2", "cost": {"stone": 2, "culture": 1},
             "vp": 2, "sprite": [4, 14], "sea_sprite": [4, 15],
             "text": "Cost 2 stone, 1 culture. Two builds. Worth 2 VP."},
    "explorer": {"name": "Explorer", "kind": "sea", "cost": {"culture": 1}, "sprite": [4, 16],
                 "text": "Cost 1 culture. Gain 3 coins, or resettle one of your settlements by sea."},
    "sailor": {"name": "Sailor", "kind": "sea", "swords": 1, "cost": {"food": 1}, "sprite": [4, 17],
               "text": "Cost 1 food. 1 sword, or move a ship or place a crew."},
    "shipwright": {"name": "Shipwright", "kind": "sea", "cost": {"wood": 1}, "sprite": [4, 18],
                   "text": "Cost 1 wood. Place a ship in a sea zone by one of your settlements."},
}
# Legacy ids (pre-FB-0018 names) for games saved before the rename.
CARDS["miner"] = CARDS["stonecutter"]
CARDS["herbalist"] = CARDS["farmer"]
MARKET = ["worker", "stonecutter", "farmer", "scholar", "chariot", "cavalry",
          "architect", "champion", "merchant", "city"]
SEA_MARKET = MARKET + ["explorer", "sailor", "shipwright"]

ACHIEVEMENTS = {
    "irrigation": {"name": "Irrigation", "level": 1, "cost": {"food": 2}, "vp": 1,
                   "sprite": [0, 0], "text": "+1 food when producing."},
    "mining": {"name": "Mining", "level": 1, "cost": {"stone": 2}, "vp": 1,
               "sprite": [1, 0], "text": "+1 stone when producing."},
    "writing": {"name": "Writing", "level": 1, "cost": {"culture": 2}, "vp": 1,
                "sprite": [2, 0], "text": "Draw one extra card each turn."},
    "agriculture": {"name": "Agriculture", "level": 2, "cost": {"food": 3}, "vp": 2,
                    "sprite": [3, 1], "text": "+1 food when producing."},
    "metallurgy": {"name": "Metallurgy", "level": 2, "cost": {"metal": 3}, "vp": 2,
                   "sprite": [4, 1], "text": "Metal cards cost 1 less."},
    "amphitheatre": {"name": "Amphitheatre", "level": 2, "cost": {"culture": 3}, "vp": 2,
                     "sprite": [5, 1], "text": "+1 culture when producing."},
    "pyramids": {"name": "Pyramids", "level": 3, "cost": {"stone": 4}, "vp": 4,
                 "sprite": [6, 2], "text": "Worth 4 VP."},
    "astronomy": {"name": "Astronomy", "level": 3, "cost": {"culture": 4}, "vp": 4,
                  "sprite": [7, 2], "text": "Worth 4 VP."},
    "epic": {"name": "Epic Poetry", "level": 3, "cost": {"food": 4}, "vp": 4,
             "sprite": [8, 2], "text": "Worth 4 VP."},
}
SEA_ACHIEVEMENTS = dict(ACHIEVEMENTS)
# FB-0056: the Seafarers achievements sheet is 12 cols x 3 rows (same
# rows as the base sheet, one extra column) — the old coords assumed
# 4 rows, so Astronomy showed a blank cell and Lighthouse showed the
# Triumphal Arch. Verified against web/altay-seafarers-achievements.webp:
# Astronomy (level 1, "Discard 1 card to sail") is at [6, 0] and the
# new Lighthouse is at [11, 2]; the other achievements sit at their
# base-sheet positions in both sheets.
SEA_ACHIEVEMENTS["astronomy"] = {"name": "Astronomy", "level": 1, "cost": {"culture": 2}, "vp": 1,
                                  "sprite": [6, 0],
                                  "text": "Discard a card to pay for one sea crossing."}
SEA_ACHIEVEMENTS["lighthouse"] = {"name": "Lighthouse", "level": 3, "cost": {"stone": 3, "culture": 2},
                                   "vp": 4, "sprite": [11, 2], "text": "+1 strength in naval support."}

REGION_NAMES = [
    "Green Vale", "Sun Fields", "Far Ridge", "South Meadow", "Lower Basin",
    "East Fields", "West Wood", "High Wood", "East Wood", "South Wood",
    "Eastern Hills", "Southeast Hills", "Black Rock", "Northern Crag",
    "Stone Pass", "South Crag", "South Cliff", "Eastern Cliff", "White Peak",
    "Crystal Peak", "Golden Peak", "Eastern Peak", "Silver Peak", "Central Lake",
    "Sacred Plateau", "Waveborn Isle", "Gull Rock",
]
REGION_POS = [
    [10.0, 6.4], [57.3, 17.7], [92.4, 6.7], [9.0, 89.1], [47.5, 81.0],
    [94.0, 84.8], [17.0, 21.7], [67.4, 7.3], [94.6, 31.9], [18.2, 76.3],
    [79.7, 61.2], [80.6, 92.4], [4.4, 26.3], [39.9, 12.4], [86.4, 16.8],
    [30.7, 68.8], [36.0, 94.8], [78.1, 78.3], [10.1, 52.2], [38.3, 54.7],
    [68.9, 30.6], [92.8, 55.5], [61.7, 90.0], [28.7, 34.8], [59.5, 53.7],
    [31.0, 34.0], [66.0, 52.0],
]
REGION_TYPES = {}
for _region in [0, 1, 3, 4, 5, 9, 23, 24, 25]:
    REGION_TYPES[_region] = "farmland"
for _region in [2, 6, 7, 8, 10, 11, 26]:
    REGION_TYPES[_region] = "forest"
for _region in [12, 13, 14, 15, 16, 17]:
    REGION_TYPES[_region] = "hill"
for _region in [18, 19, 20, 21, 22]:
    REGION_TYPES[_region] = "mountain"
TERRAIN_RESOURCE = {"farmland": "food", "forest": "wood", "hill": "metal",
                    "mountain": "culture"}
VICTORY_MARKERS = {19: 4, 20: 7, 22: 10, 25: 4, 26: 7}
MARKER_VALUES = {
    0: 1, 1: 2, 2: 2, 3: 1, 4: 2, 5: 1, 6: 1, 7: 2, 8: 1, 9: 2,
    10: 2, 11: 1, 12: 2, 13: 2, 14: 1, 15: 2, 16: 1, 17: 2,
    18: 3, 19: 2, 20: 1, 21: 3, 22: 2, 23: 2, 24: 1, 25: 3, 26: 2,
}
_ADJACENCY = {
    0: [6], 1: [7, 13, 20], 2: [8, 14], 3: [9, 18], 4: [16, 22],
    5: [11, 17], 6: [0, 12, 18], 7: [1, 13, 20], 8: [2, 14, 21],
    9: [3, 15, 18], 10: [21, 24], 11: [5, 17, 22],
    12: [6, 18, 23], 13: [1, 7, 23], 14: [2, 8], 15: [9, 18, 19, 23],
    16: [4, 22], 17: [5, 11, 22], 18: [3, 6, 9, 12, 15, 23, 24],
    19: [15, 23, 24], 20: [1, 7, 24], 21: [8, 10, 24],
    22: [4, 11, 16, 17, 24], 23: [12, 13, 15, 18, 19, 24],
    24: [10, 18, 19, 20, 21, 22, 23], 25: [], 26: [],
}
ADJACENCY = {region: sorted(neighbors) for region, neighbors in _ADJACENCY.items()}
START_REGIONS = [0, 3]
HAND_SIZE = 5
SETTLEMENT_LIMIT = 4
START_SETTLEMENTS = 15


def validate():
    return (len(REGION_NAMES) == len(REGION_POS) == len(ADJACENCY) == 27
            and all(item in CARDS for deck in FACTIONS.values() for item in deck["deck"])
            and all(item in CARDS for item in SEA_MARKET)
            and all(region in ADJACENCY for region in VICTORY_MARKERS))


def is_seafarers(game):
    return bool(game and game.get("seafarers"))


def region_ids(game=None):
    ids = list(range(25))
    if is_seafarers(game):
        ids.extend(SEAFARERS_REGIONS)
    return ids


def market(game=None):
    return list(SEA_MARKET if is_seafarers(game) else MARKET)


def achievement_defs(game=None):
    return SEA_ACHIEVEMENTS if is_seafarers(game) else ACHIEVEMENTS


def achievement_def(game, achievement_id):
    return achievement_defs(game).get(achievement_id)


def set_seafarers(game, enabled):
    if game.get("phase") != "lobby":
        return "The expansion can only be changed in the lobby."
    game["seafarers"] = bool(enabled)
    return None


def _rng(game, supplied=None):
    if supplied is not None:
        return supplied
    seed = game.get("seed")
    return random.Random(seed if seed is not None else game.get("chat_id", 0))


def new_player(user_id, name):
    return {
        "user_id": int(user_id),
        "name": str(name),
        "npc": False,
        "faction": None,
        "hand": [],
        "deck": [],
        "discard": [],
        "resources": {key: 0 for key in RESOURCE_NAMES},
        "reserve": START_SETTLEMENTS,
        "captured": 0,
        "markers": 0,
        "marks": [],
        "achievements": [],
        "achievement": None,
        "achievement_paid": {},
        "bought": [],
        "swords": 0,
        "sword_cards": 0,
        "builds": 0,
        "shields": 0,
        "coins": 0,
        "ships": {zone: 0 for zone in SEA_ZONES},
        "ship_supply": 0,
        "crews": 0,
        "ship_crews": {zone: 0 for zone in SEA_ZONES},
        "ships_to_place": 0,
        "traded": False,
        "played": [],
    }


def new_game(chat_id, creator_id, creator_name):
    return {
        "schema": VERSION,
        "chat_id": int(chat_id),
        "phase": "lobby",
        "seafarers": False,
        "players": [new_player(creator_id, creator_name)],
        "board": None,
        "current": 0,
        "turn": 0,
        "logs": [],
        "end_at": None,
        "winner": None,
        "scores": None,
        "seed": random.randrange(1 << 30),
    }


def join_game(game, user_id, name):
    if game["phase"] != "lobby":
        return "Game already started."
    if len(game["players"]) >= 2:
        return "Altay supports two players."
    if any(player["user_id"] == int(user_id) for player in game["players"]):
        return "You are already in the game."
    game["players"].append(new_player(user_id, name))
    return None


def set_faction(game, player_index, faction):
    faction = str(faction).upper()
    if faction not in FACTIONS:
        return "Unknown faction."
    if any(player["faction"] == faction for player in game["players"]):
        return "That faction is taken."
    game["players"][player_index]["faction"] = faction
    return None


def _log(game, message):
    game.setdefault("logs", []).append(str(message))
    game["logs"] = game["logs"][-60:]


def _shuffle(cards, rng):
    cards = list(cards)
    rng.shuffle(cards)
    return cards


def _marker(region, resource=None):
    value = MARKER_VALUES.get(region, 1)
    return {"value": value, "resource": resource or TERRAIN_RESOURCE[REGION_TYPES[region]],
            "vp": VICTORY_MARKERS.get(region)}


def _normalize(game):
    if not game.get("board"):
        return
    for region in game["board"].values():
        region.setdefault("settlements", [])
    for player in game["players"]:
        for key in ("hand", "deck", "discard", "marks", "achievements", "bought", "played"):
            player.setdefault(key, [])
        for key in ("reserve", "captured", "markers", "swords", "sword_cards", "builds",
                    "shields", "coins", "ship_supply", "crews", "ships_to_place"):
            player.setdefault(key, 0)
        player.setdefault("resources", {key: 0 for key in RESOURCE_NAMES})
        player.setdefault("ships", {zone: 0 for zone in SEA_ZONES})
        player.setdefault("ship_crews", {zone: 0 for zone in SEA_ZONES})
        player.setdefault("achievement", None)
        player.setdefault("achievement_paid", {})
        player.setdefault("traded", False)
        for zone in SEA_ZONES:
            player["ships"].setdefault(zone, 0)
            player["ship_crews"].setdefault(zone, 0)
        for key in RESOURCE_NAMES:
            player["resources"].setdefault(key, 0)
            player["achievement_paid"].setdefault(key, 0)


def start_game(game, events=None, rng=None):
    events = events if events is not None else []
    if game["phase"] != "lobby":
        return "Game already started."
    if len(game["players"]) != 2:
        return "Altay needs exactly two players."
    rng = _rng(game, rng)
    used = []
    for index, player in enumerate(game["players"]):
        faction = player.get("faction")
        if faction not in FACTIONS or faction in used:
            faction = next(f for f in FACTION_ORDER if f not in used)
            player["faction"] = faction
        used.append(faction)
        deck = list(FACTIONS[faction]["deck"])
        if is_seafarers(game):
            deck.append("shipwright")
        player["deck"] = _shuffle(deck, rng)
        player["hand"] = []
        player["discard"] = []
        player["resources"] = {key: 0 for key in RESOURCE_NAMES}
        player["reserve"] = START_SETTLEMENTS
        player["captured"] = 0
        player["markers"] = 0
        player["marks"] = []
        player["achievements"] = []
        player["achievement"] = None
        player["achievement_paid"] = {}
        player["swords"] = 0
        player["sword_cards"] = 0
        player["builds"] = 0
        player["shields"] = 0
        player["coins"] = 0
        player["ships"] = {zone: 0 for zone in SEA_ZONES}
        player["ship_supply"] = 3 if is_seafarers(game) else 0
        player["crews"] = 3 if is_seafarers(game) else 0
        player["ship_crews"] = {zone: 0 for zone in SEA_ZONES}
        player["ships_to_place"] = 0
        player["traded"] = False
        player["bought"] = []
        player["played"] = []
    game["board"] = {
        str(region): {"marker": _marker(region), "settlements": []}
        for region in region_ids(game)
    }
    if is_seafarers(game):
        island_values = list(SEAFARERS_MARKERS)
        rng.shuffle(island_values)
        for region, value in zip(SEAFARERS_REGIONS, island_values):
            marker = _marker(region)
            marker["value"] = value
            game["board"][str(region)]["marker"] = marker
    for index, player in enumerate(game["players"]):
        region = str(START_REGIONS[index])
        game["board"][region]["marker"] = None
        game["board"][region]["settlements"].append(index)
        _draw(game, index, HAND_SIZE, rng)
    game["phase"] = "playing"
    game["current"] = 0
    game["turn"] = 0
    game["end_at"] = None
    game["winner"] = None
    game["scores"] = None
    game["logs"] = []
    events.append("Altay begins. Each player starts with one settlement in a fertile territory.")
    if is_seafarers(game):
        events.append("Seafarers: two sea zones, two island territories, 3 ships and 3 crews each.")
    return None


def _draw(game, player_index, count, rng):
    player = game["players"][player_index]
    drawn = 0
    for _ in range(count):
        if not player["deck"]:
            if not player["discard"]:
                break
            player["deck"] = _shuffle(player["discard"], rng)
            player["discard"] = []
        player["hand"].append(player["deck"].pop())
        drawn += 1
    return drawn


def _can_pay(resources, cost):
    return all(resources.get(key, 0) >= amount for key, amount in cost.items())


def _pay(resources, cost):
    for key, amount in cost.items():
        resources[key] -= amount


def _active_players(game):
    return [index for index, player in enumerate(game["players"])
            if player.get("user_id") and not player.get("left")]


def _player_name(game, index):
    return game["players"][index].get("name", f"Player {index + 1}")


def _faction_name(game, index):
    faction = game["players"][index].get("faction")
    return FACTIONS.get(faction, {}).get("name", faction or "Unknown")


def _zone_index(zone):
    return SEA_ZONES.index(zone) if zone in SEA_ZONES else len(SEA_ZONES)


def coast_zones(region):
    return sorted((zone for zone, regions in SEA_COASTS.items() if region in regions),
                  key=_zone_index)


def _ship_route(game, player_index, origin, target):
    if not is_seafarers(game) or origin not in ADJACENCY or target not in ADJACENCY:
        return None
    shared = set(coast_zones(origin)) & set(coast_zones(target))
    if shared:
        return [sorted(shared, key=_zone_index)[0]]
    origins = coast_zones(origin)
    targets = coast_zones(target)
    for start in origins:
        for end in targets:
            if _zone_index(end) == _zone_index(start) + 1:
                return [start, end]
    return None


def _can_pay_route(player, route):
    astronomy = "astronomy" in player.get("achievements", [])
    return all(player.get("ships", {}).get(zone, 0) > 0 or (astronomy and player.get("hand"))
               for zone in route)


def _spend_crossing(game, player_index, route, events):
    player = game["players"][player_index]
    astronomy = "astronomy" in player.get("achievements", [])
    for zone in route:
        if player["ships"].get(zone, 0) > 0:
            player["ships"][zone] -= 1
            player["ship_supply"] += 1
            if player["ship_crews"].get(zone, 0) > 0:
                player["ship_crews"][zone] -= 1
                events.append(f"A crew was lost crossing sea zone {zone}.")
            continue
        if astronomy and player["hand"]:
            card = player["hand"].pop()
            player["discard"].append(card)
            events.append(f"{_player_name(game, player_index)} discarded a card to cross sea zone {zone}.")
            continue
        return f"You need a ship in sea zone {zone} to sail there."
    return None


def _routes_to(game, player_index, region_id, from_region=None, via=None):
    if game.get("phase") != "playing" or region_id not in ADJACENCY:
        return []
    board = game["board"]
    player = game["players"][player_index]
    routes = []
    if str(region_id) not in board:
        return []
    for source, neighbors in ADJACENCY.items():
        if str(source) not in board or not board[str(source)]["settlements"].count(player_index):
            continue
        if from_region is not None and source != from_region:
            continue
        if region_id in neighbors:
            route = {"from": source, "via": [], "sea": False}
            if via is None or via == []:
                routes.append(route)
            continue
        sea_route = _ship_route(game, player_index, source, region_id)
        if not sea_route or not _can_pay_route(player, sea_route):
            continue
        if via is not None and list(via) != sea_route:
            continue
        routes.append({"from": source, "via": sea_route, "sea": True})
    return routes


def _choose_route(game, player_index, region_id, from_region=None, via=None):
    routes = _routes_to(game, player_index, region_id, from_region, via)
    if not routes:
        return None
    return min(routes, key=lambda route: (len(route["via"]), route["from"]))


def ship_placements(game, player_index):
    if not is_seafarers(game) or not game.get("board"):
        return []
    return sorted((zone for zone, regions in SEA_COASTS.items()
                   if any(game["board"][str(region)]["settlements"].count(player_index)
                          for region in regions)), key=_zone_index)


def naval_support(game, player_index, region_id):
    if not is_seafarers(game):
        return 0
    player = game["players"][player_index]
    support = sum(player.get("ships", {}).get(zone, 0) for zone in coast_zones(region_id))
    if "lighthouse" in player.get("achievements", []):
        support += 1
    return support


def _check_current(game, player_index):
    if game.get("phase") != "playing":
        return "No game in progress."
    if game["current"] != player_index:
        return "It is not your turn."
    return None


def _card_sprite(game, player_index, card_id):
    card = CARDS[card_id]
    if "sprite" in card:
        # FB-0056: in Seafarers games the market cards live on the
        # Seafarers sheet, where they sit one row lower — use the
        # card's sea_sprite there. Starter cards keep their base
        # coords: rows 0-3 are identical in both sheets.
        if is_seafarers(game) and "sea_sprite" in card:
            return list(card["sea_sprite"])
        return list(card["sprite"])
    # Starter cards have no fixed sprite: each faction row of
    # altay-actions.webp lists that faction's starter deck in order
    # (verified against the BGA sheet), so the picture column is the
    # card's position in its faction's deck. The old fixed
    # "starter_col" per card type was wrong for most factions (FB-0018):
    # e.g. Village showed a Hunter and Warrior showed a Village, while
    # the caption named the right card — so picture and description
    # did not match.
    faction = game["players"][player_index].get("faction")
    deck = FACTIONS.get(faction, {}).get("deck", [])
    row = FACTIONS.get(faction, {}).get("row", 0)
    if card_id in deck:
        return [deck.index(card_id), row]
    return [0, row]


def card_info(game, player_index, card_id):
    card = CARDS.get(card_id)
    if not card:
        return None
    info = {"id": card_id, "name": card["name"], "kind": card["kind"],
            "text": card["text"], "sprite": _card_sprite(game, player_index, card_id),
            "cost": card.get("cost", {}), "vp": card.get("vp", 0),
            "resources": card.get("resources", {}), "swords": card.get("swords", 0),
            "shields": card.get("shields", 0)}
    return info


def legal_build(game, player_index):
    if game.get("phase") != "playing":
        return []
    player = game["players"][player_index]
    if player["reserve"] <= 0 or player["builds"] <= 0 or player["resources"]["food"] < 2:
        return []
    options = []
    for region_id in region_ids(game):
        region = game["board"][str(region_id)]
        own = region["settlements"].count(player_index)
        enemy = any(owner != player_index for owner in region["settlements"])
        if own > 0 and own < SETTLEMENT_LIMIT:
            options.append(region_id)
        elif own == 0 and not enemy and region["marker"] is None:
            if region_id not in SEAFARERS_REGIONS or _choose_route(game, player_index, region_id):
                options.append(region_id)
    return options


def attack_options(game, player_index):
    if game.get("phase") != "playing":
        return []
    board = game["board"]
    options = []
    for region_id in region_ids(game):
        region = board[str(region_id)]
        route = _choose_route(game, player_index, region_id)
        if route is None:
            continue
        if region["marker"] is not None:
            options.append({"from": route["from"], "region": region_id, "via": route["via"],
                            "sea": route["sea"], "kind": "neutral",
                            "value": region["marker"]["value"],
                            "resource": region["marker"]["resource"]})
        enemies = sorted({owner for owner in region["settlements"] if owner != player_index})
        if enemies:
            options.append({"from": route["from"], "region": region_id, "via": route["via"],
                            "sea": route["sea"], "kind": "player",
                            "value": len(region["settlements"]), "defender": enemies[0]})
    return options


def _sea_play(game, player_index, card_id, params, events):
    if not is_seafarers(game):
        return "Seafarers cards require the expansion."
    params = params if isinstance(params, dict) else ({"action": params} if params else {})
    action = params.get("action")
    player = game["players"][player_index]
    if card_id == "explorer":
        if action in (None, "coins"):
            player["coins"] += 3
            events.append(f"{_player_name(game, player_index)} gained 3 coins.")
            return None
        if action != "resettle":
            return "Unknown Explorer action."
        try:
            region_id = int(params.get("region", -1))
        except (TypeError, ValueError):
            return "Choose a territory to resettle."
        if region_id not in ADJACENCY:
            return "Choose a valid territory."
        region = game["board"][str(region_id)]
        if region["marker"] is not None or any(region["settlements"]):
            return "That territory is not empty."
        from_region = params.get("from")
        if from_region is not None:
            try:
                from_region = int(from_region)
            except (TypeError, ValueError):
                return "Choose a valid starting territory."
        routes = [route for route in _routes_to(game, player_index, region_id, from_region)
                  if route["sea"]]
        if not routes:
            return "You cannot resettle there by sea."
        route = min(routes, key=lambda item: (len(item["via"]), item["from"]))
        error = _spend_crossing(game, player_index, route["via"], events)
        if error:
            return error
        game["board"][str(route["from"])]["settlements"].remove(player_index)
        region["settlements"].append(player_index)
        events.append(f"{_player_name(game, player_index)} resettled by sea to "
                      f"{REGION_NAMES[region_id]}.")
        return None
    if card_id == "sailor":
        if action in (None, "sword"):
            player["swords"] += 1
            player["sword_cards"] += 1
            events.append(f"{_player_name(game, player_index)} gained 1 sword from Sailor.")
            return None
        if action == "crew":
            zone = params.get("zone")
            if zone not in SEA_ZONES:
                return "Choose a valid sea zone."
            if player["crews"] <= 0 or player["ships"][zone] <= player["ship_crews"][zone]:
                return "You cannot place a crew there."
            player["crews"] -= 1
            player["ship_crews"][zone] += 1
            events.append(f"{_player_name(game, player_index)} placed a crew in sea zone {zone}.")
            return None
        if action == "move":
            start = params.get("from")
            end = params.get("to")
            if start not in SEA_ZONES or end not in SEA_ZONES:
                return "Choose valid sea zones."
            if player["ships"][start] <= 0:
                return "You have no ship in that sea zone."
            player["ships"][start] -= 1
            player["ships"][end] += 1
            crew = player["ship_crews"][start]
            if crew:
                player["ship_crews"][start] = 0
                player["ship_crews"][end] += crew
            events.append(f"{_player_name(game, player_index)} moved a ship from "
                          f"sea zone {start} to {end}.")
            return None
        return "Unknown Sailor action."
    if card_id == "shipwright":
        zone = params.get("zone")
        available = ship_placements(game, player_index)
        if zone is None:
            if not available:
                return "You need a settlement beside a sea zone."
            zone = available[0]
        if zone not in available:
            return "Place a ship beside one of your settlements."
        if player["ships_to_place"] > 0:
            player["ships_to_place"] -= 1
        elif player["ship_supply"] > 0:
            player["ship_supply"] -= 1
        else:
            return "You have no ships left to place."
        player["ships"][zone] += 1
        events.append(f"{_player_name(game, player_index)} placed a ship in sea zone {zone}.")
        return None
    return "Unknown Seafarers card."


def play_card(game, player_index, hand_index, events=None, rng=None, params=None):
    events = events if events is not None else []
    error = _check_current(game, player_index)
    if error:
        return error
    player = game["players"][player_index]
    if not isinstance(hand_index, int) or not 0 <= hand_index < len(player["hand"]):
        return "Choose a valid card from your hand."
    card_id = player["hand"].pop(hand_index)
    card = CARDS[card_id]
    player["discard"].append(card_id)
    player["played"].append(card_id)
    if card["kind"] == "sea":
        error = _sea_play(game, player_index, card_id, params, events)
        if error:
            player["discard"].remove(card_id)
            player["played"].remove(card_id)
            player["hand"].insert(hand_index, card_id)
            return error
        events.append(f"{_player_name(game, player_index)} played {card['name']} — {card['text']}")
        return None
    if card.get("resources"):
        _normalize(game)
        bonus = 0
        if "irrigation" in player["achievements"] and "food" in card["resources"]:
            bonus += 1
        if "mining" in player["achievements"] and "stone" in card["resources"]:
            bonus += 1
        if "amphitheatre" in player["achievements"] and "culture" in card["resources"]:
            bonus += 1
        for key, amount in card["resources"].items():
            player["resources"][key] += amount + (bonus if key in ("food", "stone", "culture") else 0)
    if card["kind"] == "build":
        player["builds"] += 1
    if card["kind"] == "build2":
        player["builds"] += 2
    if card.get("swords"):
        player["swords"] += card["swords"]
        player["sword_cards"] += 1
    if card.get("shields"):
        player["shields"] += card["shields"]
    events.append(f"{_player_name(game, player_index)} played {card['name']} — {card['text']}")
    return None


def buy_card(game, player_index, card_id, events=None, rng=None):
    events = events if events is not None else []
    error = _check_current(game, player_index)
    if error:
        return error
    if card_id not in market(game):
        return "That card is not in the market."
    player = game["players"][player_index]
    if card_id in player["bought"]:
        return "You already acquired that card this turn."
    cost = dict(CARDS[card_id].get("cost", {}))
    if "metallurgy" in player["achievements"] and "metal" in cost:
        cost["metal"] = max(0, cost["metal"] - 1)
    if not _can_pay(player["resources"], cost):
        return "You cannot afford that card."
    _pay(player["resources"], cost)
    player["discard"].append(card_id)
    player["bought"].append(card_id)
    events.append(f"{_player_name(game, player_index)} acquired {CARDS[card_id]['name']}.")
    return None


def build_settlement(game, player_index, region_id, events=None, rng=None):
    events = events if events is not None else []
    error = _check_current(game, player_index)
    if error:
        return error
    if not isinstance(region_id, int) or region_id not in region_ids(game):
        return "Choose a territory from 0 to 24."
    if region_id not in legal_build(game, player_index):
        return "You cannot build there."
    player = game["players"][player_index]
    if region_id in SEAFARERS_REGIONS:
        route = _choose_route(game, player_index, region_id)
        if route is None or not route["sea"]:
            return "You need a ship to build there."
        error = _spend_crossing(game, player_index, route["via"], events)
        if error:
            return error
    player["resources"]["food"] -= 2
    player["builds"] -= 1
    player["reserve"] -= 1
    game["board"][str(region_id)]["settlements"].append(player_index)
    events.append(f"{_player_name(game, player_index)} built in {REGION_NAMES[region_id]}.")
    if player["reserve"] <= 0:
        game["end_at"] = game["turn"] + (1 if player_index == 1 else 0)
        events.append("The last settlement was built. The game is near its end.")
    return None


def attack(game, player_index, from_region, region_id, events=None, rng=None):
    events = events if events is not None else []
    error = _check_current(game, player_index)
    if error:
        return error
    player = game["players"][player_index]
    if player["swords"] <= 0:
        return "You need a sword to attack."
    if from_region is not None:
        try:
            from_region = int(from_region)
        except (TypeError, ValueError):
            return "Choose a valid starting territory."
    option = next((option for option in attack_options(game, player_index)
                   if option["region"] == region_id
                   and (from_region is None or option["from"] == from_region)), None)
    if option is None:
        return "You cannot attack that territory."
    if option["sea"] and player["reserve"] <= 0:
        return "You need a settlement in reserve for a sea attack."
    route = _choose_route(game, player_index, region_id, option["from"], option["via"])
    if route is None:
        return "You cannot attack that territory."
    error = _spend_crossing(game, player_index, route["via"], events)
    if error:
        return error
    from_region = option["from"]
    rng = _rng(game, rng)
    strength = (game["board"][str(from_region)]["settlements"].count(player_index)
                + player["swords"] + naval_support(game, player_index, region_id))
    used_cards = player["sword_cards"]
    player["swords"] = 0
    player["sword_cards"] = 0
    if option["kind"] == "neutral":
        region = game["board"][str(region_id)]
        if strength > option["value"]:
            marker = region["marker"]
            player["markers"] += 1
            player["marks"].append({"region": region_id, "value": marker["value"]})
            if marker["resource"]:
                player["resources"][marker["resource"]] += 1
            region["marker"] = None
            if option["sea"]:
                region["settlements"].append(player_index)
                player["reserve"] -= 1
            events.append(
                f"{_player_name(game, player_index)} conquered {REGION_NAMES[region_id]} "
                f"with {strength} against {option['value']}."
            )
        else:
            events.append(
                f"{_player_name(game, player_index)} failed to conquer {REGION_NAMES[region_id]} "
                f"({strength} vs {option['value']})."
            )
    else:
        defender = option["defender"]
        other = game["players"][defender]
        region = game["board"][str(region_id)]
        shields = min(other["shields"] + sum(CARDS.get(card, {}).get("shields", 0)
                                             for card in other["hand"]), 4)
        defense = len(region["settlements"]) + shields
        other["shields"] = 0
        for index in range(len(other["hand"]) - 1, -1, -1):
            if CARDS.get(other["hand"][index], {}).get("shields") and shields > 0:
                other["discard"].append(other["hand"].pop(index))
                shields -= 1
        _draw(game, defender, sum(CARDS.get(card, {}).get("shields", 0)
                                  for card in other["discard"][-4:]), rng)
        if strength > defense:
            region["settlements"].remove(defender)
            player["captured"] += 1
            if option["sea"]:
                region["settlements"].append(player_index)
                player["reserve"] -= 1
            events.append(
                f"{_player_name(game, player_index)} captured a settlement in "
                f"{REGION_NAMES[region_id]} ({strength} vs {defense})."
            )
        else:
            events.append(
                f"{_player_name(game, player_index)} failed to take {REGION_NAMES[region_id]} "
                f"({strength} vs {defense})."
            )
    _draw(game, player_index, used_cards, rng)
    return None


def develop(game, player_index, achievement_id, events=None, rng=None):
    events = events if events is not None else []
    error = _check_current(game, player_index)
    if error:
        return error
    achievement = achievement_def(game, achievement_id)
    if not achievement:
        return "Unknown achievement."
    player = game["players"][player_index]
    if achievement_id in player["achievements"]:
        return "You already completed that achievement."
    if player["achievement"] and player["achievement"] != achievement_id:
        return "Finish your current achievement first."
    if player["achievement"] is None:
        player["achievement"] = achievement_id
        player["achievement_paid"] = {key: 0 for key in achievement["cost"]}
    paid = player["achievement_paid"]
    choices = [key for key, amount in achievement["cost"].items()
               if paid.get(key, 0) < amount and player["resources"].get(key, 0) > 0]
    if not choices:
        return "You need a resource to invest in that achievement."
    resource = choices[0]
    paid[resource] = paid.get(resource, 0) + 1
    player["resources"][resource] -= 1
    if all(paid.get(key, 0) >= amount for key, amount in achievement["cost"].items()):
        player["achievements"].append(achievement_id)
        player["achievement"] = None
        player["achievement_paid"] = {}
        events.append(f"{_player_name(game, player_index)} developed {achievement['name']}.")
    else:
        progress = "/".join(f"{paid.get(key, 0)}/{amount}"
                            for key, amount in achievement["cost"].items())
        events.append(f"{_player_name(game, player_index)} invested in {achievement['name']} ({progress}).")
    return None


def trade(game, player_index, give, receive, events=None, rng=None):
    events = events if events is not None else []
    error = _check_current(game, player_index)
    if error:
        return error
    if not is_seafarers(game):
        return "Trading requires the Seafarers expansion."
    player = game["players"][player_index]
    if player.get("traded"):
        return "You already traded this turn."
    if receive not in RESOURCE_NAMES:
        return "Choose a resource to receive."
    if not isinstance(give, dict) or len(give) not in (1, 2):
        return "Give either three of one resource or two different resources."
    if any(key not in RESOURCE_NAMES or amount < 1 for key, amount in give.items()):
        return "Choose valid resources to trade."
    if len(give) == 1 and next(iter(give.values())) != 3:
        return "Give exactly three of one resource."
    if len(give) == 2 and any(amount != 1 for amount in give.values()):
        return "Give exactly one each of two resources."
    if give.get(receive):
        return "Trade for a different resource."
    if not _can_pay(player["resources"], give):
        return "You cannot afford that trade."
    _pay(player["resources"], give)
    player["resources"][receive] += 1
    player["traded"] = True
    events.append(f"{_player_name(game, player_index)} traded resources for 1 {RESOURCE_NAMES[receive]}.")
    return None


def score(game, player_index):
    _normalize(game)
    player = game["players"][player_index]
    definitions = achievement_defs(game)
    points = sum(definitions.get(item, {}).get("vp", 0) for item in player["achievements"])
    all_cards = player["hand"] + player["discard"] + player["deck"]
    points += sum(CARDS.get(item, {}).get("vp", 0) for item in all_cards)
    for region in game["board"].values():
        if player_index in region["settlements"]:
            points += 1
            if region["marker"] and region["marker"].get("vp"):
                points += region["marker"]["vp"]
    points += player["captured"]
    points += player["markers"] // 3
    points += player.get("coins", 0)
    return points


def score_breakdown(game, player_index):
    _normalize(game)
    player = game["players"][player_index]
    definitions = achievement_defs(game)
    achievements = sum(definitions.get(item, {}).get("vp", 0) for item in player["achievements"])
    cards = sum(CARDS.get(item, {}).get("vp", 0)
                for item in player["hand"] + player["discard"] + player["deck"])
    territories = 0
    markers = 0
    for region in game["board"].values():
        if player_index in region["settlements"]:
            territories += 1
            if region["marker"] and region["marker"].get("vp"):
                markers += region["marker"]["vp"]
    captured = player["captured"]
    conquest = player["markers"] // 3
    coins = player.get("coins", 0)
    return {
        "achievements": achievements, "cards": cards, "territories": territories,
        "victory_markers": markers, "captured": captured, "conquest_markers": conquest,
        "coins": coins,
        "total": achievements + cards + territories + markers + captured + conquest + coins,
    }


def _finalize(game, events):
    totals = [score(game, index) for index in range(len(game["players"]))]
    best = max(totals)
    winners = [index for index, value in enumerate(totals) if value == best]
    if len(winners) == 1:
        game["winner"] = winners[0]
    else:
        tie = [(score_breakdown(game, index)["achievements"],
                score_breakdown(game, index)["cards"],
                score_breakdown(game, index)["territories"]) for index in winners]
        game["winner"] = winners[tie.index(max(tie))]
    game["scores"] = totals
    game["phase"] = "over"
    events.append(f"Final scores: {', '.join(f'{_player_name(game, i)} {v}' for i, v in enumerate(totals))}.")
    events.append(f"{_player_name(game, game['winner'])} wins Altay!")


def end_turn(game, player_index, events=None, rng=None):
    events = events if events is not None else []
    error = _check_current(game, player_index)
    if error:
        return error
    player = game["players"][player_index]
    kept = dict(player["resources"])
    player["resources"] = {key: 0 for key in RESOURCE_NAMES}
    player["swords"] = 0
    player["sword_cards"] = 0
    player["builds"] = 0
    player["shields"] = 0
    player["bought"] = []
    player["played"] = []
    player["traded"] = False
    if any(kept.values()):
        items = ", ".join(f"{amount} {RESOURCE_ICONS[key]}"
                          for key, amount in kept.items() if amount)
        events.append(f"{_player_name(game, player_index)} discarded {items}.")
    game["turn"] += 1
    game["current"] = 1 - game["current"]
    if game["end_at"] is not None and game["turn"] >= game["end_at"]:
        _finalize(game, events)
    else:
        draw = HAND_SIZE + (1 if "writing" in player["achievements"] else 0)
        _draw(game, game["current"], max(0, draw - len(game["players"][game["current"]]["hand"])), _rng(game, rng))
        events.append(f"{_player_name(game, game['current'])} begins turn {game['turn'] + 1}.")
    return None


def board_json(game, viewer_id=None):
    _normalize(game)
    players = []
    for index, player in enumerate(game["players"]):
        show_hand = (viewer_id is None or player["user_id"] == viewer_id or player.get("npc"))
        info = {
            "index": index,
            "name": player.get("name", f"Player {index + 1}"),
            "user_id": player.get("user_id"),
            "npc": bool(player.get("npc")),
            "faction": player.get("faction"),
            "faction_name": _faction_name(game, index),
            "color": FACTIONS.get(player.get("faction"), {}).get("color", "#888"),
            "resources": dict(player["resources"]),
            "hand": [card_info(game, index, card) for card in player["hand"]] if show_hand else [],
            "hand_count": len(player["hand"]),
            # Played cards are public: what each player did this turn, with
            # the card's effect text, so the effect is visible (FB-0013).
            "played": [card_info(game, index, card) for card in player["played"]],
            "deck_count": len(player["deck"]),
            "discard_count": len(player["discard"]),
            "reserve": player["reserve"],
            "captured": player["captured"],
            "markers": player["markers"],
            "achievements": list(player["achievements"]),
            "achievement": player["achievement"],
            "achievement_paid": dict(player["achievement_paid"]),
            "swords": player["swords"],
            "builds": player["builds"],
            "coins": player.get("coins", 0),
            "ship_supply": player.get("ship_supply", 0),
            "ships": dict(player.get("ships", {})),
            "crews": player.get("crews", 0),
            "ship_crews": dict(player.get("ship_crews", {})),
            "ships_to_place": player.get("ships_to_place", 0),
            "traded": bool(player.get("traded")),
            "bought": list(player["bought"]),
            "score": score(game, index) if game.get("board") else 0,
        }
        players.append(info)
    regions = []
    for region_id in region_ids(game):
        region = game["board"][str(region_id)] if game.get("board") else {"marker": None, "settlements": []}
        marker = region.get("marker")
        regions.append({
            "id": region_id,
            "name": REGION_NAMES[region_id],
            "type": REGION_TYPES[region_id],
            "pos": list(REGION_POS[region_id]),
            "adj": list(ADJACENCY[region_id]),
            "vp": VICTORY_MARKERS.get(region_id, 0),
            "marker": dict(marker) if marker else None,
            "settlements": [
                {"owner": owner,
                 "color": FACTIONS.get(game["players"][owner].get("faction"), {}).get("color", "#888"),
                 # FB-0023: the faction, so the Mini App can draw the
                 # settlement with that faction's token icon from
                 # altay-tokens.webp instead of a plain coloured square.
                 "faction": game["players"][owner].get("faction")}
                for owner in region.get("settlements", [])
            ],
        })
    current = game.get("current", 0)
    market_info = [card_info(game, current, card_id) for card_id in market(game)]
    achievements = []
    for achievement_id, achievement in achievement_defs(game).items():
        item = {"id": achievement_id, "name": achievement["name"],
                "level": achievement["level"], "cost": dict(achievement["cost"]),
                "vp": achievement["vp"], "text": achievement["text"],
                "sprite": list(achievement["sprite"]),
                "done": [achievement_id in player["achievements"] for player in game["players"]],
                "active": [player["achievement"] == achievement_id for player in game["players"]]}
        achievements.append(item)
    return {
        "schema": VERSION,
        "phase": game.get("phase", "lobby"),
        "seafarers": is_seafarers(game),
        "turn": game.get("turn", 0),
        "current": current,
        "players": players,
        "regions": regions,
        "sea_zones": list(SEA_ZONES),
        "sea_anchors": {zone: list(pos) for zone, pos in SEA_ANCHORS.items()},
        "sea_coasts": {zone: list(regions) for zone, regions in SEA_COASTS.items()},
        "ship_placements": ship_placements(game, current),
        "market": market_info,
        "achievements": achievements,
        "build_options": legal_build(game, current),
        "attack_options": attack_options(game, current),
        "logs": list(game.get("logs", []))[-12:],
        "winner": game.get("winner"),
        "scores": game.get("scores"),
        "resources": RESOURCE_NAMES,
        "resource_icons": RESOURCE_ICONS,
        "factions": {key: {"name": value["name"], "color": value["color"]}
                     for key, value in FACTIONS.items()},
    }


def hand_summary(game, player_index):
    player = game["players"][player_index]
    counts = {}
    for card_id in player["hand"]:
        counts[card_id] = counts.get(card_id, 0) + 1
    return ", ".join(f"{CARDS[card_id]['name']} x{count}" for card_id, count in counts.items()) or "empty"
