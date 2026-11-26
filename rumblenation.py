"""Rumble Nation engine - pure logic, no Telegram, no I/O (stdlib only).

2-4 player game by Shinichi Yogi (2019, Hobby Japan):
11 castle areas numbered 2-12, 18 soldiers each, 3 dice, tactic cards.

Deployment: on your turn roll 3 dice (one free reroll), split them into a
pair (the castle number) and a single die (ceil(value/2) soldiers), or play
one tactic card from the display (player count + 1 cards).  First player to
place all soldiers takes the highest sword chip (4, 3, 2 or 1 swords for
4, 3 or 2 players); the rest take the next chips in finishing order.
Then war resolves in castle order 2..12: most soldiers + white
reinforcements wins; ties go to the higher sword.  Winners claim the castle
value as points and send white reinforcements to each unresolved adjacent
area where they have soldiers (1 per area in 2-player games, 2 in 3-4
player games).  In 3-4 player games the runner-up takes a small castle
token worth half the value, rounded down.  Highest castle total wins;
the sword chip breaks ties.
"""
import html
import math
import random

SOLDIERS = 18
REINFORCEMENTS = 30
KYO = 4


def sword_chips(n):
    """Sword chips in play for n players: highest first (4, 3, 2, 1)."""
    return tuple(range(n, 0, -1))

REGIONS = (
    # x/y are the centres of the white hexagons printed on the board art
    # (measured off rumblenation-board.webp, 2000x1480) - the castle
    # number tokens sit on those hexes.
    {"name": "Tokuyama", "title": "徳山館", "x": 79.7, "y": 15.7, "land": (), "sea": (1,)},
    {"name": "Yonezawa", "title": "米沢城", "x": 79.2, "y": 44.5, "land": (2,), "sea": (0,)},
    {"name": "Kasugayama", "title": "春日山城", "x": 63.9, "y": 39.8, "land": (1, 3), "sea": ()},
    {"name": "Odawara", "title": "小田原城", "x": 67.7, "y": 79.8, "land": (2, 4), "sea": (8,)},
    {"name": "Kyo", "title": "京", "x": 42.4, "y": 44.5, "land": (3, 5, 6), "sea": ()},
    {"name": "Inabayama", "title": "稲葉山城", "x": 62.2, "y": 70.0, "land": (4, 6, 7), "sea": ()},
    {"name": "Kiyosu", "title": "清洲城", "x": 45.8, "y": 71.3, "land": (5, 7), "sea": ()},
    {"name": "Yoshida Koriyama", "title": "吉田郡山城", "x": 33.8, "y": 35.3,
     "land": (5, 6), "sea": (3, 8, 9)},
    {"name": "Okou", "title": "岡豊城", "x": 19.3, "y": 60.3, "land": (), "sea": (7, 9)},
    {"name": "Usuki", "title": "臼杵城", "x": 17.8, "y": 33.3, "land": (), "sea": (7, 8, 10)},
    {"name": "Shuri", "title": "首里城", "x": 12.5, "y": 89.1, "land": (), "sea": (9,)},
)

CASTLE_VALUES = tuple(range(2, 13))

TACTICS = {
    1: ("Scout", "Move 1 of your soldiers to an adjacent area."),
    2: ("Over the Mountain", "Move 2 soldiers from one area to an adjacent area connected by land."),
    3: ("Marine", "Move 2 soldiers from one area to an adjacent area connected by sea."),
    4: ("Sub Squad", "Move half of your soldiers (rounded down) from one area to an adjacent area."),
    5: ("Ninja", "Move 1 soldier to any other area where you already have soldiers."),
    6: ("Entering Kyo", "Move any number of soldiers from an area adjacent to Kyo into Kyo."),
    7: ("Support", "Move 1 soldier from your stock to an area where you have soldiers."),
    8: ("Rebel", "Return 1 enemy soldier from a shared area to their stock; replace it with yours."),
    9: ("Exile", "Move 1 enemy soldier from an area where you have soldiers to an adjacent area."),
    10: ("Prisoner", "Move 1 enemy soldier from any area to an adjacent area where you have soldiers."),
    11: ("Decoy", "Move 1 of your soldiers and 2 enemy soldiers to a single adjacent area."),
    12: ("Retreat", "Return 3 of your soldiers from one area to your stock."),
}

RULES = """⚔️ <b>Rumble Nation rules</b> (2-4 players, 11 castles): roll 3 dice, deploy soldiers, win castles, score the most points.
• <b>Deployment:</b> roll 3 dice (one free reroll of all three). Split them into a pair and a single die: the pair's sum is the castle area (2-12), the single die sends 1 soldier (1-2), 2 soldiers (3-4) or 3 soldiers (5-6). You may also play ONE tactic card instead of rolling (one per game, from a display of players + 1 cards).
• First to place all 18 soldiers takes the highest sword chip; the rest take the next chips in finishing order. Swords break ties.
• Tactic cards are shared and each may be used once; once anyone is out of soldiers nobody can play them.
• <b>War:</b> castles resolve in number order (2 to 12). Most soldiers + white reinforcements wins the castle and its points; ties go to the higher sword. In 3-4 player games the runner-up takes a small castle token worth half the value (rounded down). The winner places white reinforcements in each adjacent unresolved area where they have soldiers (1 per area in 2-player games, 2 in 3-4 player games).
• Highest total of castle points wins; the sword chip breaks a final tie.
• Commands: /rumblenation_roll, /rumblenation_reroll, /rumblenation_deploy &lt;die&gt; &lt;castle&gt;, /rumblenation_tactic &lt;option&gt; (or use buttons/Mini App)."""


def name_of(g, user_id):
    return next((p["name"] for p in g["players"] if p["user_id"] == user_id), "player")


def new_player(user_id, name):
    return {"user_id": int(user_id), "name": name, "stock": SOLDIERS,
            "sword": 0, "score": 0, "castles": [], "small_castles": [],
            "tactic": None}


def new_game(chat_id, creator_id, creator_name, rng=None):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [new_player(creator_id, creator_name)],
        "phase": "lobby", "current": 0, "turn": 1,
        "castle_at": {}, "troops": {}, "reinforce": {},
        "dice": [], "rerolls": 0, "tactics": [], "used": {},
        "finished": [], "war": [], "winner": None, "log": [],
        "board_message_id": None, "chat_type": "private",
        "_rng": None if rng is None else rng,
    }


def _rng(g):
    return g.get("_rng") or random


def start_game(g, events=None, rng=None):
    """Deal castle tokens and tactic cards; begin the deployment phase."""
    if g["phase"] != "lobby":
        return "game already started"
    n = len(g["players"])
    if n < 2 or n > 4:
        return "Rumble Nation needs 2-4 players"
    ev = events if events is not None else []
    rnd = rng or _rng(g)
    values = list(CASTLE_VALUES)
    rnd.shuffle(values)
    g["castle_at"] = {str(value): i for i, value in enumerate(values)}
    deck = list(TACTICS)
    rnd.shuffle(deck)
    g["tactics"] = deck[:n + 1]
    g["used"] = {}
    g["troops"] = {str(i): {str(p): 0 for p in range(n)} for i in range(len(REGIONS))}
    g["reinforce"] = {str(i): {str(p): 0 for p in range(n)} for i in range(len(REGIONS))}
    g["phase"] = "action"
    g["current"] = 0
    g["turn"] = 1
    g["finished"] = []
    g["war"] = []
    g["winner"] = None
    g["log"] = []
    ev.append(f"⚔️ Rumble Nation started! Castles shuffled; {n + 1} tactic cards on display.")
    return None


def current_player(g):
    return g["players"][g["current"]]


def adjacent(region, sea=True, land=True):
    r = REGIONS[region]
    out = set(r["land"] if land else ()) | set(r["sea"] if sea else ())
    return tuple(sorted(out))


def region_of(g, value):
    idx = g["castle_at"].get(str(value))
    return None if idx is None else int(idx)


def _advance(g, events, from_idx):
    """Pass the turn to the next player who still has soldiers."""
    for step in range(1, len(g["players"]) + 1):
        nxt = (from_idx + step) % len(g["players"])
        if nxt not in g["finished"]:
            g["current"] = nxt
            g["turn"] += 1
            g["dice"] = []
            g["rerolls"] = 0
            g["phase"] = "action"
            events.append(f"👉 {g['players'][nxt]['name']}'s turn.")
            return
    resolve_war(g, events)


def roll(g, idx, events=None, rng=None):
    if g["phase"] != "action" or idx != g["current"]:
        return "not your turn to roll"
    ev = events if events is not None else []
    rnd = rng or _rng(g)
    g["dice"] = [rnd.randint(1, 6) for _ in range(3)]
    g["rerolls"] = 1
    g["phase"] = "select"
    ev.append(f"🎲 {g['players'][idx]['name']} rolled {', '.join(map(str, g['dice']))}.")
    return None


def reroll(g, idx, events=None, rng=None):
    if g["phase"] != "select" or idx != g["current"] or not g["rerolls"]:
        return "you cannot reroll now"
    ev = events if events is not None else []
    rnd = rng or _rng(g)
    g["dice"] = [rnd.randint(1, 6) for _ in range(3)]
    g["rerolls"] = 0
    ev.append(f"🎲 {g['players'][idx]['name']} rerolled: {', '.join(map(str, g['dice']))}.")
    return None


def deploy_options(g, idx):
    """(single die value, castle value) pairs currently available."""
    if g["phase"] != "select" or idx != g["current"] or len(g["dice"]) != 3:
        return []
    out = []
    seen = set()
    for i, single in enumerate(g["dice"]):
        pair_sum = sum(g["dice"]) - single
        if region_of(g, pair_sum) is None:
            continue
        key = (single, pair_sum)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def deploy(g, idx, single, castle, events=None):
    """Deploy soldiers using `single` as the count die and `castle` as the area."""
    ev = events if events is not None else []
    if (single, castle) not in deploy_options(g, idx):
        return "that dice split is not available"
    count = min(math.ceil(int(single) / 2), g["players"][idx]["stock"])
    if count <= 0:
        return "no soldiers left"
    region = region_of(g, castle)
    g["troops"][str(region)][str(idx)] += count
    g["players"][idx]["stock"] -= count
    ev.append(f"🪖 {g['players'][idx]['name']} sends {count} to castle {castle} "
              f"({REGIONS[region]['name']}).")
    g["dice"] = []
    g["rerolls"] = 0
    if g["players"][idx]["stock"] == 0:
        sword = sword_chips(len(g["players"]))[len(g["finished"])]
        g["players"][idx]["sword"] = sword
        g["finished"].append(idx)
        ev.append(f"⚔️ {g['players'][idx]['name']} is out of soldiers and takes the "
                  f"{sword}-sword chip!")
    _advance(g, ev, idx)
    return None


def tactic_options(g, idx, card_id=None):
    """Return target option strings for one tactic card (or all available)."""
    card_ids = [card_id] if card_id is not None else [
        c for c in g["tactics"] if c not in g["used"].values()]
    opts = []
    for cid in card_ids:
        if cid not in TACTICS or cid in g["used"].values():
            continue
        mine = lambda r: g["troops"][str(r)][str(idx)]
        foes = [p for p in range(len(g["players"])) if p != idx]
        theirs = lambda r, foe: g["troops"][str(r)][str(foe)]
        foe_name = lambda foe: g["players"][foe]["name"]
        if g["finished"]:
            continue
        if cid == 1:
            for r in range(len(REGIONS)):
                if mine(r):
                    for d in adjacent(r):
                        opts.append({"card": cid, "value": f"{cid}|{r}|{d}",
                                     "label": f"Scout: {REGIONS[r]['name']} → {REGIONS[d]['name']}"})
        elif cid in (2, 3):
            links = [(r, d) for r in range(len(REGIONS))
                     for d in (REGIONS[r]["land"] if cid == 2 else REGIONS[r]["sea"])
                     if mine(r) >= 2]
            for r, d in links:
                opts.append({"card": cid, "value": f"{cid}|{r}|{d}",
                             "label": f"{TACTICS[cid][0]}: {REGIONS[r]['name']} → {REGIONS[d]['name']}"})
        elif cid == 4:
            for r in range(len(REGIONS)):
                if mine(r) >= 2:
                    for d in adjacent(r):
                        opts.append({"card": cid, "value": f"{cid}|{r}|{d}",
                                     "label": f"Sub Squad: {REGIONS[r]['name']} → {REGIONS[d]['name']}"})
        elif cid == 5:
            for r in range(len(REGIONS)):
                if mine(r):
                    for d in range(len(REGIONS)):
                        if d != r and mine(d):
                            opts.append({"card": cid, "value": f"{cid}|{r}|{d}",
                                         "label": f"Ninja: {REGIONS[r]['name']} → {REGIONS[d]['name']}"})
        elif cid == 6:
            for r in REGIONS[KYO]["land"] + REGIONS[KYO]["sea"]:
                if mine(r):
                    opts.append({"card": cid, "value": f"{cid}|{r}|{KYO}",
                                 "label": f"Entering Kyo: from {REGIONS[r]['name']}"})
        elif cid == 7:
            if g["players"][idx]["stock"]:
                for r in range(len(REGIONS)):
                    if mine(r):
                        opts.append({"card": cid, "value": f"{cid}|-|{r}",
                                     "label": f"Support: {REGIONS[r]['name']}"})
        elif cid == 8:
            if g["players"][idx]["stock"]:
                for foe in foes:
                    for r in range(len(REGIONS)):
                        if mine(r) and theirs(r, foe):
                            opts.append({"card": cid, "value": f"{cid}|{r}|-|{foe}",
                                         "label": f"Rebel: at {REGIONS[r]['name']} (vs {foe_name(foe)})"})
        elif cid == 9:
            for foe in foes:
                for r in range(len(REGIONS)):
                    if mine(r) and theirs(r, foe):
                        for d in adjacent(r):
                            opts.append({"card": cid, "value": f"{cid}|{r}|{d}|{foe}",
                                         "label": f"Exile: {REGIONS[r]['name']} → {REGIONS[d]['name']} (vs {foe_name(foe)})"})
        elif cid == 10:
            for foe in foes:
                for r in range(len(REGIONS)):
                    if theirs(r, foe):
                        for d in adjacent(r):
                            if mine(d):
                                opts.append({"card": cid, "value": f"{cid}|{r}|{d}|{foe}",
                                             "label": f"Prisoner: {REGIONS[r]['name']} → {REGIONS[d]['name']} (vs {foe_name(foe)})"})
        elif cid == 11:
            for foe in foes:
                for r in range(len(REGIONS)):
                    if mine(r) and theirs(r, foe) >= 2:
                        for d in adjacent(r):
                            opts.append({"card": cid, "value": f"{cid}|{r}|{d}|{foe}",
                                         "label": f"Decoy: {REGIONS[r]['name']} → {REGIONS[d]['name']} (vs {foe_name(foe)})"})
        elif cid == 12:
            for r in range(len(REGIONS)):
                if mine(r) >= 3:
                    opts.append({"card": cid, "value": f"{cid}|{r}|-",
                                 "label": f"Retreat: from {REGIONS[r]['name']}"})
    return opts


def play_tactic(g, idx, value, events=None):
    """Play one tactic card by option value; returns an error string or None."""
    ev = events if events is not None else []
    if g["phase"] != "action" or idx != g["current"]:
        return "not your turn to play a tactic"
    if any(f in g["finished"] for f in range(len(g["players"]))):
        return "tactic cards are closed once a player is out of soldiers"
    opts = {o["value"]: o for o in tactic_options(g, idx)}
    if value not in opts:
        return "that tactic target is not available"
    parts = value.split("|")
    cid = int(parts[0])
    src = None if parts[1] == "-" else int(parts[1])
    dst = None if parts[2] == "-" else int(parts[2])
    # Enemy-targeting cards carry the chosen foe as a 4th part; a bare
    # 3-part value from a 2-player game means the only opponent.
    foe_idx = int(parts[3]) if len(parts) > 3 else next(
        (p for p in range(len(g["players"])) if p != idx), idx)
    me, foe = str(idx), str(foe_idx)
    t = g["troops"]
    if cid in (1, 2, 3, 4, 5, 6):
        n = 1 if cid in (1, 5, 6) else (
            min(2, t[str(src)][me]) if cid in (2, 3) else t[str(src)][me] // 2)
        if cid == 6:
            n = t[str(src)][me]
        t[str(src)][me] -= n
        t[str(dst)][me] += n
        ev.append(f"🃏 {g['players'][idx]['name']} used {TACTICS[cid][0]}: "
                  f"{n} → {REGIONS[dst]['name']}.")
    elif cid == 7:
        g["players"][idx]["stock"] -= 1
        t[str(dst)][me] += 1
        ev.append(f"🃏 {g['players'][idx]['name']} used Support: +1 at {REGIONS[dst]['name']}.")
    elif cid == 8:
        t[str(src)][foe] -= 1
        g["players"][foe_idx]["stock"] += 1
        g["players"][idx]["stock"] -= 1
        t[str(src)][me] += 1
        ev.append(f"🃏 {g['players'][idx]['name']} used Rebel at {REGIONS[src]['name']}.")
    elif cid == 9 or cid == 10:
        t[str(src)][foe] -= 1
        t[str(dst)][foe] += 1
        ev.append(f"🃏 {g['players'][idx]['name']} used {TACTICS[cid][0]}: "
                  f"enemy → {REGIONS[dst]['name']}.")
    elif cid == 11:
        t[str(src)][me] -= 1
        t[str(dst)][me] += 1
        moved = 0
        for _ in range(2):
            if t[str(src)][foe] > 0:
                t[str(src)][foe] -= 1
                t[str(dst)][foe] += 1
                moved += 1
        ev.append(f"🃏 {g['players'][idx]['name']} used Decoy: "
                  f"1 own + {moved} enemy → {REGIONS[dst]['name']}.")
    elif cid == 12:
        t[str(src)][me] -= 3
        g["players"][idx]["stock"] += 3
        ev.append(f"🃏 {g['players'][idx]['name']} used Retreat: 3 back to stock.")
    g["used"][idx] = cid
    g["players"][idx]["tactic"] = cid
    _advance(g, ev, idx)
    return None


def _take_reinforcement(g, region):
    """Take a white cube from the supply, or recycle one from a resolved area."""
    supply = REINFORCEMENTS - sum(sum(v.values()) for v in g["reinforce"].values())
    if supply > 0:
        return True
    for castle in CASTLE_VALUES:
        r = g["castle_at"].get(str(castle))
        if r is None or int(r) == region:
            continue
        for p in range(len(g["players"])):
            if g["reinforce"][str(r)][str(p)] > 0:
                g["reinforce"][str(r)][str(p)] -= 1
                return True
    return False


def resolve_war(g, events=None):
    """Resolve all 11 castles in ascending order; set the winner."""
    ev = events if events is not None else []
    if g["phase"] == "game_end":
        return
    g["phase"] = "war"
    g["war"] = []
    n = len(g["players"])
    reinf_each = 1 if n == 2 else 2  # 3-4 player games place 2 reinforcements
    for castle in CASTLE_VALUES:
        r = g["castle_at"].get(str(castle))
        if r is None:
            continue
        r = int(r)
        powers = [g["troops"][str(r)][str(p)] + g["reinforce"][str(r)][str(p)]
                  for p in range(n)]
        if not any(powers):
            ev.append(f"🏯 Castle {castle}: nobody deployed - token set aside.")
            g["war"].append({"castle": castle, "winner": None, "power": powers})
            continue
        ranked = sorted(range(n), key=lambda p: (powers[p], g["players"][p]["sword"]),
                        reverse=True)
        winner = ranked[0]
        runner_up = ranked[1] if n > 2 and powers[ranked[1]] > 0 else None
        g["players"][winner]["castles"].append(castle)
        g["players"][winner]["score"] += castle
        scores_line = " vs ".join(
            f"{g['players'][p]['name']} {powers[p]}" for p in range(n))
        ev.append(f"🏯 Castle {castle}: {g['players'][winner]['name']} wins "
                  f"({scores_line}), +{castle} pts.")
        if runner_up is not None:
            small = castle // 2
            g["players"][runner_up]["small_castles"].append(castle)
            g["players"][runner_up]["score"] += small
            ev.append(f"🥈 {g['players'][runner_up]['name']} takes the small "
                      f"token, +{small} pts.")
        sent = []
        for d in adjacent(r):
            if g["troops"][str(d)][str(winner)] > 0:
                placed = 0
                for _ in range(reinf_each):
                    if _take_reinforcement(g, d):
                        g["reinforce"][str(d)][str(winner)] += 1
                        placed += 1
                if placed:
                    sent.append(REGIONS[d]["name"] +
                                (f" ×{placed}" if placed > 1 else ""))
        if sent:
            ev.append(f"🤍 Reinforcements to {', '.join(sent)}.")
        g["war"].append({"castle": castle, "winner": winner,
                         "runner_up": runner_up, "power": powers,
                         "reinforced": sent})
    scores = [p["score"] for p in g["players"]]
    best = max(scores)
    tied = [p for p, s in enumerate(scores) if s == best]
    top_sword = max(g["players"][p]["sword"] for p in tied)
    best_sword = [p for p in tied if g["players"][p]["sword"] == top_sword]
    g["winner"] = best_sword[0] if len(best_sword) == 1 else None
    g["phase"] = "game_end"
    g["dice"] = []
    who = "Draw" if g["winner"] is None else g["players"][g["winner"]]["name"]
    ev.append(f"🏆 Final score {'-'.join(str(s) for s in scores)}. {who} wins!")


def board_lines(g):
    lines = []
    if g["phase"] == "lobby":
        lines.append(f"⚔️ <b>Rumble Nation lobby</b> ({len(g['players'])}/4): " +
                     ", ".join(html.escape(p["name"]) for p in g["players"]))
        lines.append("Join with /rumblenation_join, then /rumblenation_start.")
        return lines
    names = " vs ".join(
        f"{html.escape(p['name'])}: {p['score']} pts · {p['stock']} left · ⚔️{p['sword']}"
        + (f" · small×{len(p['small_castles'])}" if p.get("small_castles") else "")
        for p in g["players"])
    lines.append(f"⚔️ <b>Rumble Nation</b> · turn {g['turn']} · {names}")
    lines.append("🏯 " + " ".join(
        f"{v}={REGIONS[g['castle_at'][str(v)]]['title']}" for v in CASTLE_VALUES
        if str(v) in g["castle_at"]))
    if g["phase"] in ("action", "select"):
        cards = ", ".join(f"{cid} {TACTICS[cid][0]}" + (" ✓" if cid in g["used"].values() else "")
                          for cid in g["tactics"])
        lines.append("🃏 Display: " + cards)
        if g["phase"] == "select":
            lines.append("🎲 " + " ".join(str(d) for d in g["dice"]) +
                         (" (reroll available)" if g["rerolls"] else ""))
            lines.append("Choose: /rumblenation_deploy &lt;single die&gt; &lt;castle&gt;")
        else:
            lines.append(f"👉 {html.escape(current_player(g)['name'])}: "
                         "/rumblenation_roll or /rumblenation_tactic &lt;option&gt;")
    if g["phase"] == "game_end":
        winner = "draw" if g["winner"] is None else html.escape(g["players"][g["winner"]]["name"])
        lines.append(f"🏆 Winner: <b>{winner}</b> · /rumblenation_rematch")
    lines.extend(html.escape(e) for e in g["log"][-6:])
    return lines


def board_json(g, viewer_id=None):
    me = next((i for i, p in enumerate(g["players"]) if p["user_id"] == viewer_id), None)
    actor = g["current"] if g["phase"] in ("action", "select") else None
    can_act = actor is not None and me is not None and me == actor
    regions = {}
    for i, region in enumerate(REGIONS):
        castle = next((v for v in CASTLE_VALUES
                       if g["castle_at"].get(str(v)) == i), None)
        regions[str(i)] = {
            "name": region["name"], "title": region["title"],
            "x": region["x"], "y": region["y"], "castle": castle,
            "land": list(region["land"]), "sea": list(region["sea"]),
            "troops": [g["troops"].get(str(i), {}).get(str(p), 0) for p in range(len(g["players"]))],
            "reinforce": [g["reinforce"].get(str(i), {}).get(str(p), 0) for p in range(len(g["players"]))],
        }
    board = {
        "chat_id": g["chat_id"], "phase": g["phase"], "turn": g["turn"],
        "players": [{"user_id": p["user_id"], "name": p["name"], "stock": p["stock"],
                     "sword": p["sword"], "score": p["score"],
                     "castles": list(p["castles"]),
                     "small_castles": list(p.get("small_castles", [])),
                     "tactic": p["tactic"]}
                    for p in g["players"]],
        "regions": regions, "dice": list(g["dice"]), "rerolls": g["rerolls"],
        "tactics": [{"id": c, "name": TACTICS[c][0], "text": TACTICS[c][1],
                     "used_by": next((p for p, v in g["used"].items() if v == c), None)}
                    for c in g["tactics"]],
        "actor": actor, "can_act": can_act, "is_player": me is not None,
        "winner": g["winner"], "war": g["war"], "log": g["log"][-12:],
        "deploy": [], "options": [], "tactic_id": None,
    }
    if can_act:
        board["deploy"] = [{"die": d, "castle": c,
                            "soldiers": min(math.ceil(d / 2), g["players"][actor]["stock"])}
                           for d, c in deploy_options(g, actor)]
        board["options"] = tactic_options(g, actor)
    return board
