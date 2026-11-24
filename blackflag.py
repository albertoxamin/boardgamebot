import html
import random
import time

SCHEMA = "blackflag/1"
MIN_PLAYERS = 4
MAX_PLAYERS = 8
WEALTH_TARGET = 4
CALLBACK_PREFIX = "bf"
RELAYOUT = "🔄 Rematch!"

CARD_DECK = {
    918: 4, 919: 2, 920: 3, 921: 2, 922: 1, 923: 1, 924: 1,
    925: 1, 926: 1, 927: 1, 928: 4, 929: 14, 930: 2, 931: 3,
    932: 3, 933: 2, 934: 3, 935: 2, 936: 2, 937: 2, 938: 2,
    939: 4, 940: 2, 941: 6, 942: 6,
}

CARD_INFO = {
    918: ("Parley", "defense", "Ignore the effect of an Attack card.", "shield"),
    919: ("Counterbarrage", "defense", "Cancel a card played against you, then shoot the attacker.", "target"),
    920: ("Cannon", "equipment", "Your Shots hit for +1 Barrel.", "cannon"),
    921: ("Telescope", "equipment", "Your Ship's Range increases by 1.", "telescope"),
    922: ("Sailor", "equipment", "Discard instead of losing 1 Barrel from a Shot.", "sailor"),
    923: ("Sailor", "equipment", "Discard instead of losing 1 Barrel from a Shot.", "sailor"),
    924: ("Sailor", "equipment", "Discard instead of losing 1 Barrel from a Shot.", "sailor"),
    925: ("Sailor", "equipment", "Discard instead of losing 1 Barrel from a Shot.", "sailor"),
    926: ("Sailor", "equipment", "Discard instead of losing 1 Barrel from a Shot.", "sailor"),
    927: ("Sailor", "equipment", "Discard instead of losing 1 Barrel from a Shot.", "sailor"),
    928: ("Sails", "equipment", "Other players see you at distance +1.", "sail"),
    929: ("Broadside", "attack", "At Range 1: Shot for 2 Barrels.", "cannon"),
    930: ("Tortuga", "action", "Every player draws 1 card, starting with you.", "map"),
    931: ("Storm", "action", "Other ships discard 1 Equipment or lose 1 Barrel.", "storm"),
    932: ("Duel", "action", "Both discard in turn; first unable loses 1 Barrel.", "duel"),
    933: ("Order", "attack", "Target discards, then Shoots at you if in Range.", "shot"),
    934: ("Mutiny", "action", "For each Equipment the target has, discard a card or lose 1 Barrel.", "sailor"),
    935: ("Flying Deutchmann", "action", "Leave a spectral token; its target must answer a symbol next turn.", "skull"),
    936: ("Transfer", "action", "Move 1 Barrel from another ship to a ship of their choice.", "hand"),
    937: ("Anomalous Wave", "action", "Move 1 Equipment from another ship to a ship of their choice.", "wave"),
    938: ("Kraken", "action", "Each other ship discards an Attack or loses 1 Barrel.", "kraken"),
    939: ("Boarding", "attack", "At Range: draw 1 random card from the target's hand.", "boarding"),
    940: ("Map", "equipment", "Your Ship's Range increases by 1.", "map"),
    941: ("Leak", "action", "Discard 1 Equipment card in play.", "leak"),
    942: ("Swivel Gun", "attack", "Shot for 2 Barrels; counts as an Attack.", "cannon"),
}

EQUIPMENT = set(range(920, 929)) | {940}
DEFENSE_ONLY = {918, 919}
ATTACK_CARDS = {929: 2, 933: 1, 939: 1, 942: 2}
SHOT_CARDS = {929, 942}
SAILOR_CARDS = set(range(922, 928))

SHIPS = {
    400: ("Queen's Revenge", 4, 3, 2, 4, "extra_shot"),
    401: ("Victoria", 4, 2, 3, 5, "draw3"),
    402: ("Blue Pearl", 3, 1, 1, 4, "dead_man"),
    403: ("Flamboyante", 4, 3, 2, 3, "ignore_sails"),
    404: ("Royal Hap", 3, 2, 1, 4, "hard_to_hit"),
    405: ("Monarch", 3, 1, 1, 4, "draw3"),
    406: ("Leviathan", 5, 2, 2, 5, "leak_proof"),
    407: ("Retribution", 3, 1, 3, 4, "counter"),
    408: ("Bruja Linda", 5, 2, 2, 4, "hidden_cards"),
    409: ("Chimera", 1, 1, 1, 3, "treasure"),
    410: ("Calypso", 2, 2, 2, 3, "reveal"),
    411: ("Banshee", 5, 3, 2, 3, "ignore_ships"),
    412: ("Golden Deer", 3, 1, 2, 4, "equipment_shot"),
    413: ("Adventurous", 4, 2, 2, 4, "draw3"),
}

CAPTAINS = {
    906: ("Banshee", 411, "Ignore other players' Ship abilities."),
    907: ("Mary Reed", 403, "During the draw phase, look at a random card in another player's hand and draw it instead of the first card."),
    908: ("Monarch", 405, "At the end of your turn, draw 1 card if you have 0 or 1 cards."),
    909: ("Calypso", 410, "Each time your Ship sinks, draw 2 cards."),
    910: ("Jack's Parrot", 402, "Your starting Ship gains +1 Barrel."),
    911: ("Bart Robber", 404, "Once per turn, play a card from your hand as if it were a Shot."),
    912: ("Anne Bonny", 407, "Ignore other players' Equipment when you are Shot."),
    913: ("Eddy Englund", 406, "Once per turn, discard an Equipment card to make an extra Shot."),
    914: ("Francis Brake", 412, "Discard 1 card to ignore the effect of an Attack card."),
    915: ("Blackbeer", 400, "After you lose a Barrel, draw 1 card."),
    916: ("Henry Morgan", 413, "Once per turn, discard 1 Barrel to discard 1 Barrel from another player."),
    917: ("Victoria", 401, "Your starting Ship gains +1 Barrel."),
}

CAPTAIN_SHIP = {cid: data[1] for cid, data in CAPTAINS.items()}

ROLES = {
    900: ("Brittish Privateer", "solo_brittish"),
    901: ("Ibberian Privateer", "solo_iberia"),
    902: ("Pirate", "solo"),
    903: ("Ensign", "brittish"),
    904: ("Commodore", "brittish"),
    905: ("Admiral", "iberia"),
    1000: ("Lieutenant", "iberia"),
}

ROLE_DECKS = {
    4: (905, 904, 901, 900),
    5: (905, 904, 903, 1000, 902),
    6: (905, 904, 903, 1000, 901, 900),
    7: (905, 904, 903, 903, 1000, 1000, 902),
    8: (905, 904, 903, 903, 1000, 1000, 901, 900),
}

FLAG_DIR = {"iberia": 1, "brittish": -1}
TEAMS = {
    "iberia": (905, 1000),
    "brittish": (903, 904),
    "solo": (902,),
    "solo_iberia": (901,),
    "solo_brittish": (900,),
}

RULES = """🏴‍☠️ <b>Black Flag!</b> (4-8 players, simplified): sail, shoot, sink ships and move the Treasure Chest to your nation's flag.
• At setup everyone gets a Captain, its Ship, a hidden Role and 4 cards (6th-8th players get 5). The Admiral is revealed. Privateers and the Pirate play alone; Ibberia is Admiral + Lieutenants, Brittish is Commodore + Ensigns.
• On your turn take a Ship if you have none, draw 2, play any number of cards, then keep at most 5. Attacks are limited by your Ship's cannon value.
• SHOT cards hit at Range; Sails make you look 1 farther away, Telescope and Map increase your Range. Sailor/Parley can be played out of turn to stop a Shot; other effects use the displayed defense rules.
• Sinking a Ship moves the Chest toward the enemy flag (2 steps for Admiral/Commodore), discards its Equipment, and gives the sinker a Doubloon. A sunk player chooses a new Ship from the row on their next turn.
• A Privateer/Pirate with 4 Doubloons wins immediately. When the Chest reaches a flag, that nation wins. When the deck empties, remove 1 Hourglass, move both flags inward and reshuffle. If the Hourglass empties, answer a revealed symbol at the start of your turn or lose.
• Commands: /blackflag_join, /blackflag_join_npc, /blackflag_start, /blackflag_ship, /blackflag_play, /blackflag_defend, /blackflag_pass, /blackflag_end, /blackflag_rules, /blackflag_cancel, /blackflag_rematch (or use buttons/Mini App)."""


def rules():
    return RULES


def _esc(value):
    return html.escape(str(value))


def _is_npc_player(player):
    return bool(player.get("npc") or player.get("user_id") == -1)


def _rng(g):
    g["seed"] = (int(g.get("seed", 1)) + 1) % 2147483647
    return random.Random(g["seed"])


def _shuffle(g, values):
    values = list(values)
    _rng(g).shuffle(values)
    return values


def new_player(user_id, name):
    return {
        "user_id": user_id,
        "name": name,
        "npc": False,
        "captain": None,
        "ship": None,
        "role": None,
        "role_revealed": False,
        "hand": [],
        "equipment": [],
        "barrels": 0,
        "max_barrels": 0,
        "doubloons": 0,
    }


def new_game(chat_id, creator_id, creator_name):
    seed = (int(chat_id) * 1000003 + int(time.time() * 1000)) % 2147483647
    return {
        "schema": SCHEMA,
        "chat_id": chat_id,
        "created_by": creator_id,
        "phase": "lobby",
        "players": [new_player(creator_id, creator_name)],
        "deck": [],
        "discard": [],
        "ship_deck": [],
        "ship_discard": [],
        "ship_row": [],
        "captain_deck": [],
        "chest": 0,
        "flags": 5,
        "hourglass": 0,
        "flying": None,
        "davey": None,
        "pending": None,
        "current": 0,
        "turn": 0,
        "attacks_used": 0,
        "attack_bonus": 0,
        "ability_used": False,
        "winner": None,
        "winners": [],
        "end_reason": "",
        "seed": seed or 1,
        "log": [],
    }


def validate(g):
    return bool(
        isinstance(g, dict)
        and g.get("schema") == SCHEMA
        and g.get("phase") in ("lobby", "playing", "game_end")
        and isinstance(g.get("players"), list)
        and len(g["players"]) <= MAX_PLAYERS
    )


def join_game(g, user_id, name):
    if g["phase"] != "lobby":
        return "game already started"
    if len(g["players"]) >= MAX_PLAYERS:
        return f"Black Flag is {MAX_PLAYERS} players (full)."
    if any(p["user_id"] == user_id for p in g["players"]):
        return "already in"
    player = new_player(user_id, name)
    if _is_npc_player(player):
        player["npc"] = True
    g["players"].append(player)
    return None


def card_info(card, hidden=False):
    if card is None:
        return None
    try:
        name, kind, text, symbol = CARD_INFO[int(card)]
    except (KeyError, TypeError, ValueError):
        return {"id": card, "name": "Unknown", "kind": "action", "text": "", "symbol": "", "sprite": [9, 9]}
    index = int(card) - 906
    return {
        "id": int(card),
        "name": name,
        "kind": kind,
        "text": "" if hidden else text,
        "symbol": symbol,
        "sprite": [index % 5, index // 5],
    }


def ship_info(ship):
    if ship is None:
        return None
    try:
        sid = int(ship)
        name, treasure, ship_range, ammo, barrels, ability = SHIPS[sid]
    except (KeyError, TypeError, ValueError):
        return {"id": ship, "name": "Unknown", "treasure": 0, "range": 0, "ammo": 0, "barrels": 0, "ability": "", "sprite": [9, 9]}
    return {
        "id": sid,
        "name": name,
        "treasure": treasure,
        "range": ship_range,
        "ammo": ammo,
        "barrels": barrels,
        "ability": ability,
        "sprite": [(sid - 400) % 4, (sid - 400) // 4],
    }


def captain_info(captain):
    if captain is None:
        return None
    try:
        cid = int(captain)
        name, ship, text = CAPTAINS[cid]
    except (KeyError, TypeError, ValueError):
        return {"id": captain, "name": "Unknown", "ship": None, "text": "", "sprite": [9, 9]}
    index = cid - 906
    return {
        "id": cid,
        "name": name,
        "ship": ship,
        "text": text,
        "sprite": [index % 5, index // 5],
    }


def role_info(role, visible=True):
    if role is None:
        return None
    try:
        rid = int(role)
        name, team = ROLES[rid]
    except (KeyError, TypeError, ValueError):
        return {"id": role, "name": "Unknown", "team": "solo", "hidden": True}
    return {"id": rid, "name": name if visible else "Hidden Role", "team": team, "hidden": not visible}


def name_of(g, user_id):
    return next((p["name"] for p in g["players"] if p["user_id"] == user_id), "player")


def actor(g):
    if g.get("pending"):
        return int(g["pending"]["target"])
    return int(g["current"])


def _begin_turn(g, events, initial=False):
    if g["phase"] != "playing":
        return
    g["turn"] += 1
    g["attacks_used"] = 0
    g["attack_bonus"] = 0
    g["ability_used"] = False
    g["pending"] = None
    index = g["current"]
    player = g["players"][index]
    events.append(f"🎲 Turn {g['turn']}: {player['name']}.")
    _resolve_tokens(g, events)
    if g["phase"] != "playing":
        return
    if not player["ship"]:
        events.append(f"🚢 {player['name']} has no Ship - choose one from the row.")
        return
    amount = 3 if _ship_ability(player, "draw3") else 2
    _give_cards(g, player, amount, events)
    if player["captain"] == 909 and not initial:
        events.append("🃏 Calypso draws 2 extra cards.")
        _give_cards(g, player, 2, events)


def start_game(g, events=None):
    events = events if events is not None else []
    if g["phase"] != "lobby":
        return "already started"
    count = len(g["players"])
    if count < MIN_PLAYERS or count > MAX_PLAYERS:
        return f"Black Flag needs {MIN_PLAYERS}-{MAX_PLAYERS} players."
    g["deck"] = _shuffle(g, [card for card, copies in CARD_DECK.items() for _ in range(copies)])
    captains = _shuffle(g, list(CAPTAINS))
    for index, player in enumerate(g["players"]):
        player["captain"] = captains[index]
        ship_id = CAPTAIN_SHIP[captains[index]]
        ship = ship_info(ship_id)
        player["ship"] = ship_id
        player["max_barrels"] = ship["barrels"] + (1 if captains[index] in (910, 917) else 0)
        player["barrels"] = player["max_barrels"]
        player["equipment"] = []
        player["hand"] = []
    g["ship_deck"] = _shuffle(g, [CAPTAIN_SHIP[cid] for cid in captains[count:]])
    g["ship_discard"] = []
    g["ship_row"] = [g["ship_deck"].pop() for _ in range(min(3, len(g["ship_deck"])))]
    roles = _shuffle(g, list(ROLE_DECKS[count]))
    for index, role in enumerate(roles):
        player = g["players"][index]
        player["role"] = role
        player["role_revealed"] = role == 905
        player["doubloons"] = 0 if role == 905 else 1
    admiral = roles.index(905)
    order = [(admiral + step) % count for step in range(count)]
    for step, index in enumerate(order):
        amount = 5 if step >= 5 else 4
        _give_cards(g, g["players"][index], amount, events)
    g["chest"] = 0
    g["flags"] = 5 if count <= 5 else 6
    g["hourglass"] = {4: 7, 5: 7, 6: 8, 7: 9, 8: 10}[count]
    g["flying"] = None
    g["davey"] = None
    g["pending"] = None
    g["current"] = admiral
    g["turn"] = 0
    g["winner"] = None
    g["winners"] = []
    g["end_reason"] = ""
    g["phase"] = "playing"
    events.append(f"🏴‍☠️ Black Flag started with {count} players!")
    events.append(f"🚩 Flags at {g['flags']}; Hourglass {g['hourglass']}.")
    _begin_turn(g, events, initial=True)
    return None


def _give_cards(g, player, count, events):
    for _ in range(count):
        if not g["deck"]:
            _deck_depleted(g, events)
            if g["phase"] != "playing":
                break
        if g["deck"]:
            player["hand"].append(g["deck"].pop())
    events.append(f"🃏 {player['name']} drew {count} card(s).")


def _deck_depleted(g, events):
    g["hourglass"] -= 1
    g["flags"] = max(3, g["flags"] - 1)
    events.append(f"⌛ Deck empty: Hourglass {g['hourglass']}, Flags at ±{g['flags']}.")
    if g["discard"]:
        g["deck"] = _shuffle(g, g["discard"])
        g["discard"] = []
    else:
        g["deck"] = _shuffle(g, [card for card, copies in CARD_DECK.items() for _ in range(copies)])
    if g["hourglass"] == 0 and not g["davey"]:
        g["davey"] = {"owner": (g["current"] + 1) % len(g["players"])}
        events.append("☠️ Davey Jones' hourglass has run out! The next player must answer a symbol.")
    elif g["hourglass"] < 0:
        _edge_end(g, events)


def _resolve_tokens(g, events):
    index = g["current"]
    player = g["players"][index]
    for key, label in (("davey", "Davey Jones"), ("flying", "Flying Deutchmann")):
        token = g.get(key)
        if not token or token.get("owner") != index:
            continue
        symbol = token.get("symbol") or _rng(g).choice(["cannon", "sail", "sailor", "map", "skull"])
        token["symbol"] = None
        match = next((i for i, card in enumerate(player["hand"])
                      if CARD_INFO[card][3] == symbol), None)
        if match is None:
            events.append(f"👻 {label}: {player['name']} had no {symbol} and suffered!")
            if key == "davey":
                winner = (index - 1) % len(g["players"])
                _finish(g, [winner], f"{player['name']} failed Davey Jones' challenge.", events)
                return
            _damage(g, index, 2, None, events, label)
            g[key] = None
            continue
        card = player["hand"].pop(match)
        g["discard"].append(card)
        events.append(f"👻 {label}: {player['name']} answered {symbol} with {CARD_INFO[card][0]}.")
        if key == "davey":
            token["owner"] = (index + 1) % len(g["players"])
        else:
            g[key] = None


def _finish(g, winners, reason, events=None):
    g["phase"] = "game_end"
    g["winners"] = list(winners)
    g["winner"] = winners[0] if winners else None
    g["end_reason"] = reason
    g["pending"] = None
    for player in g["players"]:
        if player["role"] not in (905,):
            player["role_revealed"] = True
    if events is not None:
        names = ", ".join(g["players"][i]["name"] for i in winners) or "nobody"
        events.append(f"🏁 {reason} Winner: {names}.")


def _edge_end(g, events):
    if g["chest"] >= g["flags"]:
        _finish(g, [i for i, p in enumerate(g["players"]) if p["role"] in TEAMS["iberia"]],
                "The Chest reached the Ibberian flag.", events)
        return
    if g["chest"] <= -g["flags"]:
        _finish(g, [i for i, p in enumerate(g["players"]) if p["role"] in TEAMS["brittish"]],
                "The Chest reached the Brittish flag.", events)
        return
    scores = [(p["doubloons"] + (0 if p["role_revealed"] else 1), i)
              for i, p in enumerate(g["players"])]
    best = max(score for score, _ in scores)
    winners = [i for score, i in scores if score == best]
    if best < WEALTH_TARGET:
        if g["chest"] > 0:
            winners = [i for i, p in enumerate(g["players"]) if p["role"] in TEAMS["iberia"]]
        elif g["chest"] < 0:
            winners = [i for i, p in enumerate(g["players"]) if p["role"] in TEAMS["brittish"]]
        else:
            winners = []
    _finish(g, winners, "The final edge of the world ends the game.", events)


def _check_wealth(g, events):
    for index, player in enumerate(g["players"]):
        if player["role"] in (900, 901, 902) and player["doubloons"] >= WEALTH_TARGET:
            _finish(g, [index], f"{player['name']} reached {WEALTH_TARGET} Doubloons.", events)
            return True
    return False


def _ship_ability(player, ability):
    return player["ship"] is not None and SHIPS[player["ship"]][5] == ability


def _range(g, index):
    player = g["players"][index]
    value = SHIPS[player["ship"]][2] if player["ship"] else 0
    value += sum(1 for card in player["equipment"] if card in (921, 940))
    if player["captain"] == 911:
        value += 1
    return value


def _distance(g, source, target):
    count = len(g["players"])
    distance = min((target - source) % count, (source - target) % count)
    attacker = g["players"][source]
    defender = g["players"][target]
    ignore_sails = _ship_ability(attacker, "ignore_sails") or attacker["captain"] == 906
    if not ignore_sails:
        if 928 in defender["equipment"] or _ship_ability(defender, "hard_to_hit"):
            distance += 1
    return distance


def _target_options(g, index, attack=False):
    options = []
    for other, player in enumerate(g["players"]):
        if other == index or not player["ship"]:
            continue
        if attack and _distance(g, index, other) > _range(g, index):
            continue
        options.append(other)
    return options


def _parse_index(value, count, default=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 0 or number >= count:
        return default
    return number


def _discard_random(g, player, count, events):
    while count > 0 and player["hand"]:
        card = _rng(g).choice(player["hand"])
        player["hand"].remove(card)
        g["discard"].append(card)
        events.append(f"🃏 {player['name']} discarded {CARD_INFO[card][0]}.")
        count -= 1


def _damage(g, target, amount, attacker, events, source=""):
    player = g["players"][target]
    if source == "Leak" and player["captain"] == 913:
        events.append(f"🌊 {player['name']} is immune to Leak.")
        return
    if player["captain"] in (912,) and attacker is not None:
        pass
    player["barrels"] = max(0, player["barrels"] - amount)
    events.append(f"💥 {player['name']} lost {amount} Barrel(s) ({source or 'Shot'}).")
    if player["captain"] == 915 and attacker is not None:
        _give_cards(g, player, 1, events)
    if player["barrels"] <= 0:
        _sink(g, target, attacker, events)


def _sink(g, target, attacker, events):
    player = g["players"][target]
    if not player["ship"]:
        return
    ship = player["ship"]
    g["ship_discard"].append(ship)
    player["ship"] = None
    player["barrels"] = 0
    while player["equipment"]:
        g["discard"].append(player["equipment"].pop())
    if not player["role_revealed"]:
        player["role_revealed"] = True
        player["doubloons"] = max(0, player["doubloons"] - 1)
    team = ROLES[player["role"]][1]
    direction = FLAG_DIR.get(team, 0)
    if direction == 0 and attacker is not None:
        direction = FLAG_DIR.get(ROLES[g["players"][attacker]["role"]][1], 1)
    if direction == 0:
        direction = 1 if target < (attacker if attacker is not None else 0) else -1
    steps = 2 if player["role"] in (905, 904) else 1
    g["chest"] += direction * steps
    events.append(f"🏴 {player['name']} was sunk! Chest moved {abs(steps)} toward {'Ibberia' if direction > 0 else 'Brittish'}.")
    if player["captain"] == 909:
        _give_cards(g, player, 2, events)
    if attacker is not None and attacker != target:
        g["players"][attacker]["doubloons"] += 1
        events.append(f"💰 {g['players'][attacker]['name']} took a Doubloon.")
    if g["chest"] >= g["flags"]:
        _finish(g, [i for i, p in enumerate(g["players"]) if p["role"] in TEAMS["iberia"]],
                "The Chest reached the Ibberian flag.", events)
    elif g["chest"] <= -g["flags"]:
        _finish(g, [i for i, p in enumerate(g["players"]) if p["role"] in TEAMS["brittish"]],
                "The Chest reached the Brittish flag.", events)
    else:
        _check_wealth(g, events)


def _start_pending(g, kind, attacker, target, damage, source, events, **extra):
    g["pending"] = {
        "kind": kind,
        "attacker": attacker,
        "target": target,
        "damage": damage,
        "source": source,
        **extra,
    }
    events.append(f"⚔️ {g['players'][attacker]['name']} targeted {g['players'][target]['name']} with {CARD_INFO[source][0]}.")


def _resolve_pending(g, defended, events):
    pending = g.get("pending")
    if not pending:
        return
    target = pending["target"]
    attacker = pending["attacker"]
    kind = pending["kind"]
    if defended:
        events.append(f"🛡 {g['players'][target]['name']} avoided the effect.")
        g["pending"] = None
        return
    if kind in ("shot", "boarding"):
        damage = pending["damage"] + sum(
            1 for card in g["players"][attacker]["equipment"] if card == 920)
        if kind == "shot":
            _damage(g, target, damage, attacker, events, CARD_INFO[pending["source"]][0])
        else:
            victim = g["players"][target]
            if victim["hand"]:
                card = _rng(g).choice(victim["hand"])
                victim["hand"].remove(card)
                g["players"][attacker]["hand"].append(card)
                events.append(f"🏴 {g['players'][attacker]['name']} boarded and took a card.")
            else:
                events.append("🏴 Boarding found no cards.")
    elif kind == "discard":
        _discard_random(g, g["players"][target], 1, events)
    elif kind == "damage":
        _damage(g, target, pending["damage"], attacker, events, pending.get("label", "effect"))
    g["pending"] = None
    if g["phase"] == "playing":
        _check_wealth(g, events)


def _valid_defense(g, index, card):
    pending = g.get("pending") or {}
    if pending.get("kind") == "discard":
        return True
    if pending.get("kind") not in ("shot", "boarding", "damage"):
        return False
    player = g["players"][index]
    if card == 918 or card in SAILOR_CARDS:
        return True
    if card == 919 and pending.get("kind") == "shot":
        return True
    if player["captain"] == 914:
        return True
    if player["captain"] == 912 and pending.get("kind") == "shot":
        return True
    return False


def take_ship(g, index, choice, events=None):
    events = events if events is not None else []
    if g["phase"] != "playing":
        return "game not in progress"
    player = g["players"][index]
    if player["ship"]:
        return "you already have a Ship"
    if not g["ship_row"]:
        if g["ship_discard"]:
            g["ship_deck"] = _shuffle(g, g["ship_discard"])
            g["ship_discard"] = []
        elif g["ship_deck"]:
            g["ship_deck"] = _shuffle(g, g["ship_deck"])
        else:
            return "no Ships available"
        while len(g["ship_row"]) < 3 and g["ship_deck"]:
            g["ship_row"].append(g["ship_deck"].pop())
    if choice in (None, "", "deck"):
        ship = g["ship_deck"].pop() if g["ship_deck"] else g["ship_row"].pop(0)
        if ship in g["ship_row"]:
            g["ship_row"].remove(ship)
    else:
        row = _parse_index(choice, len(g["ship_row"]))
        if row is None:
            return "bad Ship choice"
        ship = g["ship_row"].pop(row)
    if g["ship_deck"]:
        g["ship_row"].append(g["ship_deck"].pop())
    info = ship_info(ship)
    player["ship"] = ship
    player["max_barrels"] = info["barrels"] + (1 if player["captain"] in (910, 917) else 0)
    player["barrels"] = player["max_barrels"]
    events.append(f"🚢 {player['name']} took the {info['name']}.")
    return None


def play_card(g, index, hand_index, target=None, choice=None, events=None):
    events = events if events is not None else []
    if g["phase"] != "playing":
        return "game not in progress"
    if g.get("pending"):
        return "resolve the pending effect first"
    player = g["players"][index]
    hand_index = _parse_index(hand_index, len(player["hand"]))
    if hand_index is None:
        return "bad card"
    if not player["ship"]:
        return "take a Ship first"
    card = player["hand"][hand_index]
    info = CARD_INFO[card]
    if card in ATTACK_CARDS:
        limit = SHIPS[player["ship"]][2] + g.get("attack_bonus", 0)
        if player["captain"] == 911:
            limit += 1
        if g["attacks_used"] >= limit:
            return "no attacks left this turn"
        options = _target_options(g, index, attack=True)
        target_index = _parse_index(target, len(g["players"]))
        if target_index is None or target_index not in options:
            return "target out of Range"
    elif card in (930, 931, 932, 934, 935, 936, 937, 938, 941):
        options = _target_options(g, index)
        target_index = _parse_index(target, len(g["players"]))
        if target_index is not None and target_index not in options:
            return "invalid target"
        if not options and card not in (930, 938, 941):
            return "no valid target"
        if target_index is None:
            target_index = options[0] if options else None
    else:
        target_index = None
    player["hand"].pop(hand_index)
    g["discard"].append(card)
    events.append(f"🃏 {player['name']} played {info[0]}.")
    if card in EQUIPMENT:
        player["equipment"].append(card)
        g["discard"].pop()
        events.append(f"⚙️ {info[0]} is now in play.")
        return None
    if card in DEFENSE_ONLY:
        events.append(f"🛡 {info[0]} had no effect during the turn.")
        return None
    if card in ATTACK_CARDS:
        g["attacks_used"] += 1
        if card == 939:
            _start_pending(g, "boarding", index, target_index, 1, card, events)
        elif card == 933:
            victim = g["players"][target_index]
            _discard_random(g, victim, 1, events)
            if _distance(g, target_index, index) <= _range(g, target_index):
                _start_pending(g, "shot", target_index, index, 1, 942, events, counter=True)
            else:
                events.append("🎯 Order failed: target is out of Range.")
        else:
            _start_pending(g, "shot", index, target_index, ATTACK_CARDS[card], card, events)
        return None
    if card == 930:
        for other in [index] + [i for i in range(len(g["players"])) if i != index]:
            if g["phase"] != "playing":
                break
            _give_cards(g, g["players"][other], 1, events)
        return None
    if card == 931:
        for other in [i for i in range(len(g["players"])) if i != index and g["players"][i]["ship"]]:
            victim = g["players"][other]
            if victim["equipment"]:
                eq = victim["equipment"].pop()
                g["discard"].append(eq)
                events.append(f"🌪 {victim['name']} lost {CARD_INFO[eq][0]}.")
            elif victim["barrels"]:
                _damage(g, other, 1, index, events, "Storm")
        return None
    if card == 932:
        victim = g["players"][target_index]
        for first, second in ((target_index, index), (index, target_index)):
            actor_player = g["players"][first]
            defender_player = g["players"][second]
            if actor_player["hand"]:
                _discard_random(g, actor_player, 1, events)
            else:
                _damage(g, first, 1, second, events, "Duel")
                break
        if g["phase"] == "playing" and victim["hand"]:
            events.append("🤺 Duel ended.")
        return None
    if card == 934:
        victim = g["players"][target_index]
        for _ in range(len(victim["equipment"])):
            if victim["hand"]:
                _discard_random(g, victim, 1, events)
            elif victim["barrels"]:
                _damage(g, target_index, 1, index, events, "Mutiny")
        return None
    if card == 935:
        g["flying"] = {"owner": target_index}
        symbol = _rng(g).choice(["cannon", "sail", "sailor", "map", "skull"])
        g["pending"] = None
        g["flying"]["symbol"] = symbol
        events.append(f"👻 Flying Deutchmann haunts {g['players'][target_index]['name']}.")
        return None
    if card == 936:
        victim = g["players"][target_index]
        receivers = [i for i in range(len(g["players"])) if i != target_index and g["players"][i]["ship"]]
        if not receivers:
            events.append("🔁 Transfer had no receiver.")
            return None
        receiver = g["players"][receivers[0]]
        amount = min(1, max(0, victim["barrels"] - 1))
        victim["barrels"] -= amount
        receiver["barrels"] += amount
        events.append(f"🔁 {victim['name']} transferred {amount} Barrel to {receiver['name']}.")
        return None
    if card == 937:
        victim = g["players"][target_index]
        receivers = [i for i in range(len(g["players"])) if i != target_index and g["players"][i]["ship"]]
        if not receivers or not victim["equipment"]:
            events.append("🌊 Anomalous Wave had no effect.")
            return None
        receiver = g["players"][receivers[0]]
        eq = victim["equipment"].pop()
        receiver["equipment"].append(eq)
        events.append(f"🌊 {victim['name']} gave {CARD_INFO[eq][0]} to {receiver['name']}.")
        return None
    if card == 938:
        for other, victim in enumerate(g["players"]):
            if other == index or not victim["ship"]:
                continue
            attack = next((i for i, card_id in enumerate(victim["hand"]) if card_id in ATTACK_CARDS), None)
            if attack is not None:
                removed = victim["hand"].pop(attack)
                g["discard"].append(removed)
                events.append(f"🐙 {victim['name']} discarded {CARD_INFO[removed][0]}.")
            elif victim["barrels"]:
                _damage(g, other, 1, index, events, "Kraken")
        return None
    if card == 941:
        if player["captain"] == 913:
            events.append("🌊 Leviathan ignored Leak.")
            return None
        eq_index = _parse_index(choice, len(player["equipment"]), 0)
        if player["equipment"]:
            eq = player["equipment"].pop(eq_index)
            g["discard"].append(eq)
            events.append(f"💧 {player['name']} discarded {CARD_INFO[eq][0]}.")
        else:
            events.append("💧 Leak had no Equipment to remove.")
        return None
    return None


def defend(g, index, hand_index, events=None):
    events = events if events is not None else []
    pending = g.get("pending")
    if not pending or pending["target"] != index:
        return "no effect to defend"
    player = g["players"][index]
    hand_index = _parse_index(hand_index, len(player["hand"]))
    if hand_index is None:
        return "bad card"
    card = player["hand"][hand_index]
    if not _valid_defense(g, index, card):
        return "that card cannot defend"
    player["hand"].pop(hand_index)
    g["discard"].append(card)
    events.append(f"🛡 {player['name']} played {CARD_INFO[card][0]}.")
    if card == 919:
        attacker = pending["attacker"]
        _start_pending(g, "shot", index, attacker, 1, 919, events, counter=True)
        return None
    _resolve_pending(g, True, events)
    return None


def pass_defense(g, index, events=None):
    events = events if events is not None else []
    pending = g.get("pending")
    if not pending or pending["target"] != index:
        return "no effect to pass"
    events.append(f"⏭ {g['players'][index]['name']} passed the defense.")
    _resolve_pending(g, False, events)
    return None


def use_ability(g, index, choice=None, events=None):
    events = events if events is not None else []
    if g["phase"] != "playing" or g.get("pending"):
        return "ability unavailable"
    player = g["players"][index]
    if g.get("ability_used"):
        return "ability already used"
    if not _ship_ability(player, "extra_shot"):
        return "no ship ability"
    if len(player["hand"]) < 2:
        return "need 2 cards"
    indices = choice if isinstance(choice, (list, tuple)) else [choice, choice]
    picked = []
    for value in indices:
        pos = _parse_index(value, len(player["hand"]))
        if pos is None or pos in picked:
            return "bad cards"
        picked.append(pos)
    for pos in sorted(picked, reverse=True):
        card = player["hand"].pop(pos)
        g["discard"].append(card)
        events.append(f"🔥 {player['name']} discarded {CARD_INFO[card][0]}.")
    g["attack_bonus"] += 1
    g["ability_used"] = True
    events.append(f"🔥 {player['name']} gained an extra Shot.")
    return None


def end_turn(g, index, events=None):
    events = events if events is not None else []
    if g["phase"] != "playing":
        return "game not in progress"
    if g.get("pending"):
        return "resolve the pending effect first"
    if g["current"] != index:
        return "not your turn"
    player = g["players"][index]
    if not player["ship"]:
        return "take a Ship first"
    if len(player["hand"]) > 5:
        _discard_random(g, player, len(player["hand"]) - 5, events)
        events.append(f"🃏 {player['name']} discarded down to 5.")
    if player["captain"] == 908 and player["hand"] and len(player["hand"]) <= 1:
        _give_cards(g, player, 1, events)
    g["current"] = (index + 1) % len(g["players"])
    _begin_turn(g, events)
    return None


def apply_action(g, index, action, params=None, events=None):
    params = params or {}
    events = events if events is not None else []
    if g["phase"] != "playing":
        return "game not in progress"
    who = actor(g)
    if index != who:
        return "not your turn"
    if action == "defend":
        return defend(g, index, params.get("index", params.get("card", -1)), events)
    if action == "pass":
        return pass_defense(g, index, events)
    if g.get("pending"):
        return "resolve the pending effect first"
    if action == "play":
        return play_card(g, index, params.get("index", -1), params.get("target"),
                         params.get("choice"), events)
    if action == "ship":
        return take_ship(g, index, params.get("choice", params.get("ship", "deck")), events)
    if action == "ability":
        return use_ability(g, index, params.get("indices", params.get("index")), events)
    if action == "end":
        return end_turn(g, index, events)
    if action == "discard":
        hand_index = _parse_index(params.get("index", -1), len(g["players"][index]["hand"]))
        if hand_index is None:
            return "bad card"
        card = g["players"][index]["hand"].pop(hand_index)
        g["discard"].append(card)
        events.append(f"🃏 {g['players'][index]['name']} discarded {CARD_INFO[card][0]}.")
        return None
    return "unknown action"


def legal_actions(g, viewer_id=None, allow_npc=True):
    who = actor(g)
    result = {
        "actor": who, "hand": [], "targets": [], "ships": [], "defend": [],
        "pass": False, "end": False, "ability": False, "pending": None,
    }
    if g["phase"] != "playing":
        return result
    actor_player = g["players"][who]
    controllable = allow_npc and _is_npc_player(actor_player)
    if viewer_id is not None and not controllable and actor_player["user_id"] != viewer_id:
        return result
    pending = g.get("pending")
    if pending:
        result["pending"] = dict(pending)
        result["defend"] = [i for i, card in enumerate(g["players"][who]["hand"])
                            if _valid_defense(g, who, card)]
        result["pass"] = bool(result["defend"] or not g["players"][who]["hand"])
        return result
    player = g["players"][who]
    result["ships"] = list(range(len(g["ship_row"]))) + ["deck"] if not player["ship"] else []
    result["hand"] = list(range(len(player["hand"]))) if player["ship"] else []
    targets = _target_options(g, who) + _target_options(g, who, attack=True)
    result["targets"] = list(dict.fromkeys(targets))
    result["end"] = bool(player["ship"])
    result["ability"] = bool(player["ship"] and not g.get("ability_used")
                             and _ship_ability(player, "extra_shot") and len(player["hand"]) >= 2)
    return result


def board_lines(g):
    if g["phase"] == "lobby":
        lines = ["🏴‍☠️ <b>Black Flag!</b> lobby:"]
        for index, player in enumerate(g["players"]):
            lines.append(f"• {index + 1}. {_esc(player['name'])}")
        lines.append(f"Need {MIN_PLAYERS}-{MAX_PLAYERS} players. /blackflag_join, /blackflag_join_npc, /blackflag_start.")
        return lines
    if g["phase"] == "game_end":
        names = ", ".join(_esc(g["players"][i]["name"]) for i in g["winners"]) or "nobody"
        return [f"🏁 <b>Black Flag finished</b>: {_esc(g['end_reason'])} Winner: <b>{names}</b>.",
                f"🚩 Chest {g['chest']} · Flags ±{g['flags']} · {RELAYOUT}"]
    lines = [f"🏴‍☠️ <b>Black Flag!</b> Turn {g['turn'] + 1} · Chest {g['chest']} · Flags ±{g['flags']} · Hourglass {g['hourglass']}"]
    row = ", ".join(f"{i + 1}:{ship_info(s)['name']}" for i, s in enumerate(g["ship_row"])) or "empty"
    lines.append(f"🚢 Ship row: {row}")
    pending = g.get("pending")
    if pending:
        lines.append(f"⚔️ Pending: {CARD_INFO[pending['source']][0]} → {_esc(g['players'][pending['target']]['name'])} (/blackflag_defend or /blackflag_pass)")
    for index, player in enumerate(g["players"]):
        cap = captain_info(player["captain"])
        ship = ship_info(player["ship"])
        role = role_info(player["role"], player["role_revealed"] or player["npc"])
        equip = ", ".join(CARD_INFO[c][0] for c in player["equipment"]) or "none"
        hand = "hidden"
        name = _esc(player["name"]) + (" 🤖" if _is_npc_player(player) else "")
        lines.append(
            f"{'▶️' if index == actor(g) else '•'} {name} — {_esc(role['name'])} · "
            f"{_esc(cap['name'] if cap else '?')} / {_esc(ship['name'] if ship else 'adrift')} · "
            f"🛡 {player['barrels']}/{player['max_barrels']} · 💰 {player['doubloons']} · 🃏 {len(player['hand'])}"
        )
        lines.append(f"   ⚙️ {equip}")
    current = g["players"][actor(g)]
    if not current["ship"]:
        lines.append("🚢 /blackflag_ship &lt;row|deck&gt; to choose a Ship.")
    elif pending:
        lines.append("🛡 /blackflag_defend &lt;card&gt; or /blackflag_pass.")
    else:
        lines.append("🎮 /blackflag_play &lt;card&gt; [target], /blackflag_end (or buttons/Mini App).")
    return lines


def board_json(g, viewer_id=None):
    me = next((i for i, player in enumerate(g["players"]) if player["user_id"] == viewer_id), None)
    who = actor(g)
    players = []
    for index, player in enumerate(g["players"]):
        visible = bool(player["role_revealed"] or _is_npc_player(player) or index == me or g["phase"] == "game_end")
        hand_visible = index == me or _is_npc_player(player)
        players.append({
            "user_id": player["user_id"],
            "name": player["name"],
            "npc": player["npc"],
            "captain": captain_info(player["captain"]),
            "ship": ship_info(player["ship"]),
            "role": role_info(player["role"], visible),
            "barrels": player["barrels"],
            "max_barrels": player["max_barrels"],
            "doubloons": player["doubloons"],
            "hand_count": len(player["hand"]),
            "hand": [card_info(card) for card in player["hand"]] if hand_visible else [],
            "equipment": [card_info(card) for card in player["equipment"]],
            "is_current": index == who,
        })
    legal = legal_actions(g, viewer_id)
    return {
        "schema": SCHEMA,
        "chat_id": g["chat_id"],
        "phase": g["phase"],
        "turn": g["turn"],
        "chest": g["chest"],
        "flags": g["flags"],
        "hourglass": g["hourglass"],
        "deck_count": len(g["deck"]),
        "discard_count": len(g["discard"]),
        "ship_row": [ship_info(ship) for ship in g["ship_row"]],
        "ship_deck_count": len(g["ship_deck"]) + len(g["ship_discard"]),
        "flying": g.get("flying"),
        "davey": g.get("davey"),
        "pending": g.get("pending"),
        "players": players,
        "actor": who,
        "me": me,
        "can_act": bool(me is not None and (legal["hand"] or legal["pass"] or legal["end"] or legal["ships"])),
        "legal": legal,
        "target_cards": sorted(set(ATTACK_CARDS) | {932, 934, 935, 936, 937}),
        "winner": g["winner"],
        "winners": g["winners"],
        "winner_names": [g["players"][i]["name"] for i in g["winners"]],
        "end_reason": g["end_reason"],
        "log": g["log"][-12:],
        "rules": RULES,
    }
