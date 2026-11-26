"""Toy Battle engine: pure rules/logic, no Telegram, no I/O."""
import random

BOARD_NAME = "Castle Field"
MEDAL_TARGET = 7
RACK_LIMIT = 8
HQ = (1, 41)
TROOP_NAMES = {
    1: "Skully", 2: "Cap'N", 3: "Jumbo", 4: "Hook",
    5: "XB-42", 6: "Star", 7: "Roxy", 8: "Kwak",
}
# Special ability of each troop, worded from the Toy Battle rules
# (bot.py TOYBATTLE_RULES): the single source of truth for the Mini App
# captions. Kwak's "joker" rule is its ability: it covers any enemy troop
# and can be covered by any troop.
TROOP_ABILITIES = {
    1: "Draw 2 troops",
    2: "Place 1 extra troop",
    3: "Discard an adjacent enemy troop",
    4: "Ignores connection",
    5: "Discard a random enemy rack troop",
    6: "Draw 1 troop",
    7: "No special ability",
    8: "Joker: covers any enemy troop, can be covered by any troop",
}

# Base positions as (top %, left %) of the portrait board art
# (web/toybattle-board.webp, 600x1000), measured off the art itself:
# stone squares and tower platforms, verified with an overlay render.
# The old values were measured on a landscape frame and landed up to a
# full tile off the printed spaces (FB-0090 follow-up / msg 2411).
BASES = {
    1: (94.0, 50.2, [11, 12], False),
    11: (91.5, 83.5, [1, 13], False),
    12: (92.0, 17.5, [1, 14], False),
    13: (77.2, 62.7, [11, 15, 17, 18], False),
    14: (77.1, 37.2, [12, 16, 18, 19], False),
    15: (69.7, 84.9, [13, 17], True),
    16: (69.7, 14.7, [14, 19], True),
    17: (50.6, 79.3, [13, 15, 20, 22], False),
    18: (50.6, 49.7, [13, 14, 22, 23], False),
    19: (50.8, 19.5, [14, 16, 21, 23], False),
    20: (31.1, 85.2, [17, 22], True),
    21: (31.1, 15.0, [19, 23], True),
    22: (22.2, 62.5, [17, 18, 20, 24], False),
    23: (22.5, 37.2, [18, 19, 21, 25], False),
    24: (8.3, 83.3, [22, 41], False),
    25: (8.9, 17.7, [23, 41], False),
    41: (8.1, 50.2, [24, 25], False),
}

REGIONS = {
    1: ([11, 12, 13, 14, 18], 3),
    2: ([13, 15, 17], 1),
    3: ([14, 16, 19], 1),
    4: ([13, 17, 18, 22], 2),
    5: ([14, 18, 19, 23], 2),
    6: ([17, 20, 22], 1),
    7: ([19, 21, 23], 1),
    8: ([18, 22, 23, 24, 25], 3),
}

# Medal spots as (top %, left %, region) of the portrait board art
# (web/toybattle-board.webp, 600x1000). Same landscape-frame error as
# BASES before this fix: the old values put e.g. region-2/6 medals on top
# of the towers. Spots sit on open grass inside their region's gap.
MEDAL_SPOTS = {
    1: (72.5, 45.6, 1), 2: (75.4, 45.6, 1), 3: (78.4, 45.6, 1),
    4: (75.4, 69.8, 2), 5: (75.4, 21.4, 3),
    6: (54.2, 60.8, 4), 7: (57.2, 60.8, 4),
    8: (54.2, 30.9, 5), 9: (57.2, 30.9, 5),
    10: (35.1, 69.8, 6), 11: (35.1, 21.4, 7),
    12: (32.1, 45.6, 8), 13: (35.1, 45.6, 8), 14: (38.1, 45.6, 8),
}


def new_player(user_id, name, color=""):
    return {
        "user_id": int(user_id), "name": name, "color": color,
        "hq": 0, "rack": [], "reserve": [], "discard": [], "medals": 0,
    }


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby", "current": None, "turn": 0,
        "stacks": {str(b): [] for b in BASES},
        "claimed": {str(r): None for r in REGIONS},
        "medals": {str(m): None for m in MEDAL_SPOTS},
        "pending": None, "fx": None,
        "winner": None, "end_reason": "", "log": [],
        "board_message_id": None,
    }


def start_game(g, events, rng=None):
    if len(g["players"]) != 2:
        return "Toy Battle needs exactly 2 players."
    r = rng or random
    for i, p in enumerate(g["players"]):
        p["color"] = "blue" if i == 0 else "red"
        p["hq"] = HQ[i]
        p["reserve"] = [t for t in range(1, 9) for _ in range(3)]
        r.shuffle(p["reserve"])
        del p["reserve"][:4]
        p["rack"] = []
        p["discard"] = []
        p["medals"] = 0
    for i, n in enumerate((3, 4)):
        p = g["players"][i]
        p["rack"] = [p["reserve"].pop() for _ in range(n)]
    g["phase"] = "play"
    g["current"] = 0
    g["turn"] = 1
    g["log"] = []
    events.append("🎯 Toy Battle! Castle Field - first to 7 medals or the enemy HQ wins.")
    events.append(f"🎁 {g['players'][0]['name']} draws 3 troops, {g['players'][1]['name']} draws 4.")
    events.append(f"👉 {g['players'][0]['name']}'s turn.")
    return None


def name_of(g, pid):
    return g["players"][pid]["name"] if 0 <= pid < len(g["players"]) else "?"


def top_troop(g, base):
    stack = g["stacks"].get(str(base)) or []
    return stack[-1] if stack else None


def stack_owner(g, base):
    t = top_troop(g, base)
    return t["owner"] if t else None


def adjacents(base):
    return BASES[int(base)][2]


def is_special(base):
    return BASES[int(base)][3]


def connection(g, pid, target):
    me = g["players"][pid]
    seen = {me["hq"]}
    frontier = list(adjacents(me["hq"]))
    while frontier:
        b = frontier.pop()
        if b == target:
            return True
        if b in seen:
            continue
        seen.add(b)
        if stack_owner(g, b) == pid:
            frontier.extend(adjacents(b))
    return False


def legal_placements(g, pid):
    result = {}
    if g["phase"] != "play" or g["current"] != pid:
        return result
    p = g["players"][pid]
    enemy_hq = g["players"][1 - pid]["hq"]
    for idx, t in enumerate(p["rack"]):
        spots = []
        for b in BASES:
            if b == p["hq"]:
                continue
            if b == enemy_hq:
                if connection(g, pid, b):
                    spots.append(b)
                continue
            if t == 4:
                spots.append(b)
                continue
            top = top_troop(g, b)
            if top and top["owner"] != pid and t != 8 and t <= top["type"]:
                continue
            if connection(g, pid, b):
                spots.append(b)
        result[idx] = sorted(spots)
    return result


def can_act(g, pid):
    p = g["players"][pid]
    if p["rack"] and any(v for v in legal_placements(g, pid).values()):
        return True
    return bool(p["reserve"] and len(p["rack"]) < RACK_LIMIT)


def draw_troops(g, pid, n, events, rng=None):
    p = g["players"][pid]
    count = min(n, RACK_LIMIT - len(p["rack"]), len(p["reserve"]))
    for _ in range(count):
        i = len(p["reserve"]) - 1 if rng is None else rng.randrange(len(p["reserve"]))
        p["rack"].append(p["reserve"].pop(i))
    if count:
        events.append(f"🎁 {name_of(g, pid)} draws {count} troop{'s' if count != 1 else ''}.")
    return count


def check_medals(g, events):
    for rid, (bases, worth) in sorted(REGIONS.items()):
        if g["claimed"].get(str(rid)) is not None:
            continue
        owners = [stack_owner(g, b) for b in bases]
        if None in owners or len(set(owners)) != 1:
            continue
        pid = owners[0]
        g["claimed"][str(rid)] = pid
        for m, spot in MEDAL_SPOTS.items():
            if spot[2] == rid:
                g["medals"][str(m)] = pid
        g["players"][pid]["medals"] += worth
        events.append(f"⭐ {name_of(g, pid)} controls region {rid} and takes {worth} medal{'s' if worth != 1 else ''}!")
        if g["players"][pid]["medals"] >= MEDAL_TARGET:
            g["phase"] = "game_end"
            g["winner"] = pid
            g["end_reason"] = "medals"
            events.append(f"🏆 {name_of(g, pid)} wins with {g['players'][pid]['medals']} medals!")
            return True
    return False


def end_turn(g, events):
    if g["phase"] == "game_end":
        return
    nxt = 1 - g["current"]
    if not can_act(g, nxt):
        g["phase"] = "game_end"
        g["winner"] = g["current"]
        g["end_reason"] = "stuck"
        events.append(f"⛔ {name_of(g, nxt)} has no legal move. {name_of(g, g['current'])} wins on medals!")
        return
    g["current"] = nxt
    g["turn"] += 1
    events.append(f"👉 {name_of(g, nxt)}'s turn.")


def advance_fx(g, pid, events, rng=None):
    fx = g.get("fx")
    if not fx:
        end_turn(g, events)
        return
    while True:
        if fx["stage"] == "troop" and fx["troops"]:
            item = fx["troops"].pop(0)
            t = item["type"]
            b = item["base"]
            if t in (1, 6):
                draw_troops(g, pid, 2 if t == 1 else 1, events, rng)
                continue
            if t == 5:
                other = g["players"][1 - pid]
                if other["rack"]:
                    i = (rng or random).randrange(len(other["rack"]))
                    stolen = other["rack"].pop(i)
                    other["discard"].append(stolen)
                    events.append(f"🤖 XB-42 takes a random troop from {name_of(g, 1 - pid)}'s rack and discards it.")
                continue
            if t == 2:
                g["pending"] = {"kind": "captain", "by": pid, "base": b}
                return
            if t == 3:
                targets = [n for n in adjacents(b) if stack_owner(g, n) == 1 - pid]
                if targets:
                    g["pending"] = {"kind": "jumbo", "by": pid, "base": b, "targets": targets}
                    return
                continue
            continue
        if fx["stage"] == "troop":
            fx["stage"] = "base"
        if fx["stage"] == "base" and fx["bases"]:
            b = fx["bases"].pop(0)
            mine = [str(x) for x in BASES if stack_owner(g, x) == pid and x not in fx["placed"]]
            if is_special(b) and mine:
                g["pending"] = {"kind": "recall", "by": pid, "base": b, "targets": [int(x) for x in mine]}
                return
            continue
        g["fx"] = None
        end_turn(g, events)
        return


def do_place(g, pid, rack_idx, base, events, rng=None, extra=False):
    p = g["players"][pid]
    t = p["rack"].pop(rack_idx)
    g["stacks"][str(base)].append({"type": t, "owner": pid})
    events.append(f"🎯 {name_of(g, pid)} places {TROOP_NAMES[t]} on base {base}"
                  + (" (extra)" if extra else "") + ".")
    if not extra:
        g["fx"] = {"stage": "troop", "troops": [{"base": base, "type": t}],
                   "bases": [base], "placed": [base]}
    else:
        g["fx"]["troops"].append({"base": base, "type": t})
        g["fx"]["bases"].append(base)
        g["fx"]["placed"].append(base)
    if base == g["players"][1 - pid]["hq"]:
        g["phase"] = "game_end"
        g["winner"] = pid
        g["end_reason"] = "hq"
        g["fx"] = None
        events.append(f"🏆 {name_of(g, pid)} captures the enemy HQ and wins!")
        return None
    if check_medals(g, events):
        g["fx"] = None
        return None
    if not extra:
        advance_fx(g, pid, events, rng)
    return None


def draw(g, pid, events, rng=None):
    if g["phase"] != "play" or g["current"] != pid or g["pending"]:
        return "Not your turn."
    p = g["players"][pid]
    if len(p["rack"]) >= RACK_LIMIT:
        return "Your rack is full (8)."
    if not p["reserve"]:
        return "Your reserve is empty."
    draw_troops(g, pid, 2, events, rng)
    end_turn(g, events)
    return None


def place(g, pid, rack_idx, base, events, rng=None):
    if g["phase"] != "play" or g["current"] != pid or g["pending"]:
        return "Not your turn."
    legal = legal_placements(g, pid)
    if rack_idx not in legal or int(base) not in legal[rack_idx]:
        return "Illegal placement."
    return do_place(g, pid, rack_idx, int(base), events, rng)


def pending_options(g, pid):
    pend = g.get("pending")
    if not pend or pend["by"] != pid:
        return []
    opts = []
    if pend["kind"] == "captain":
        for idx, bases in legal_placements(g, pid).items():
            for b in bases:
                opts.append({"value": f"{idx}-{b}",
                             "label": f"Place {TROOP_NAMES[g['players'][pid]['rack'][idx]]} → {b}"})
    elif pend["kind"] == "jumbo":
        for b in pend["targets"]:
            top = top_troop(g, b)
            opts.append({"value": str(b),
                         "label": f"Discard enemy {TROOP_NAMES[top['type']]} on {b}"})
    elif pend["kind"] == "recall":
        for b in pend["targets"]:
            top = top_troop(g, b)
            opts.append({"value": str(b),
                         "label": f"Return your {TROOP_NAMES[top['type']]} from {b}"})
    opts.append({"value": "skip", "label": "Skip"})
    return opts


def choose(g, pid, value, events, rng=None):
    pend = g.get("pending")
    if not pend or pend["by"] != pid:
        return "No pending choice."
    valid = {o["value"] for o in pending_options(g, pid)}
    if str(value) not in valid:
        return "Invalid choice."
    g["pending"] = None
    if pend["kind"] != "captain" and str(value) == "skip":
        advance_fx(g, pid, events, rng)
        return None
    if pend["kind"] == "captain":
        if str(value) != "skip":
            idx, b = str(value).split("-")
            do_place(g, pid, int(idx), int(b), events, rng, extra=True)
            if g["pending"]:
                return None
        advance_fx(g, pid, events, rng)
        return None
    b = int(value)
    if pend["kind"] == "jumbo":
        t = g["stacks"][str(b)].pop()["type"]
        g["players"][1 - pid]["discard"].append(t)
        events.append(f"🦣 Jumbo discards enemy {TROOP_NAMES[t]} on base {b}.")
        check_medals(g, events)
    elif pend["kind"] == "recall":
        t = g["stacks"][str(b)].pop()["type"]
        g["players"][pid]["rack"].append(t)
        events.append(f"🏰 Special base: {name_of(g, pid)} returns {TROOP_NAMES[t]} from {b} to the rack.")
        check_medals(g, events)
    advance_fx(g, pid, events, rng)
    return None


def board_lines(g):
    if g["phase"] == "lobby":
        return [f"🎯 <b>Toy Battle lobby</b> - {len(g['players'])}/2 players. "
                "Friends: /toybattle_join, anyone: /toybattle_start"]
    lines = [f"🎯 <b>Toy Battle</b> - {BOARD_NAME} | Turn {g['turn']} | "
             f"First to {MEDAL_TARGET} medals or enemy HQ"]
    for i, p in enumerate(g["players"]):
        mark = "▶️ " if g["current"] == i and g["phase"] == "play" else ""
        lines.append(f"{mark}{'🔵' if p['color'] == 'blue' else '🔴'} <b>{p['name']}</b> "
                     f"⭐ {p['medals']}/{MEDAL_TARGET} · rack {len(p['rack'])}/8 · reserve {len(p['reserve'])}")
    tops = []
    for b in sorted(BASES):
        t = top_troop(g, b)
        if t:
            tops.append(f"{'🔵' if t['owner'] == 0 else '🔴'}{b}:{TROOP_NAMES[t['type']]}")
    lines.append("🗺️ " + (" · ".join(tops) if tops else "no troops deployed"))
    if g["phase"] == "game_end":
        lines.append(f"🏆 Game over - winner: <b>{name_of(g, g['winner'])}</b>" if g["winner"] is not None
                     else "🤝 Game over - draw")
    return lines
