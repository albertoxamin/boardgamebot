"""Fliptoons (Thunderworks Games, Season 1, 2025) engine.

2-4 players. Each round: Flip (shuffle deck, reveal cards one at a time
into a 3x2 grid, left to right / top row then bottom), Check Fame (each
player totals their grid's fame), Market (clockwise from first player,
up to 2 actions: hire a toon from the market or dismiss one of your own
face-up grid cards for 5 fame; caterpillar costs 3), Cleanup (grid back
to deck). First player to reach 30 fame in a Check Fame takes Critic's
Choice (+3 at Final Flip) and triggers the end; after cleanup everyone
does one Final Flip, most fame wins (ties re-flip among tied players).

Deck composition (rulebook): 24 starting cards, all rank 0, gray - per
player 2 Caterpillars (fame 0, dismiss cost 3), 1 Skunk (0), 1 Dragonfly
(0, +1 per unique adjacent name), 1 Bee (1), 1 Snail (2). 53 toon cards
(ranks 1-25) form the toon deck / market. Prices [3,4,7,10,15] by rank
position; when the toon deck runs out, remaining market cards sit under
the highest prices. Toon deck AND market empty also triggers Final Flip.

Rules verified against the Season 1 rulebook text (incl. FAQ rulings),
kuribodo.com's BGA card list and the lehi-innovation rules summary.
Approximations used (documented): Cow copies the highest adjacent
computed fame (players choose any one adjacent card); Alligator picks
the top face-up dismissable card of the target stack; Alligators in
extra rows do not trigger; Lion's "+4 if all adjacent face-up cards are
rank 16 or lower" is vacuously true with no neighbors; rabbit self-stack
scans grid slots in reading order, then extra rows.
"""
import random

STARTER_NAMES = ["Caterpillar", "Skunk", "Dragonfly", "Bee", "Snail"]
STARTER_FAME = [0, 0, 0, 1, 2]          # caterpillar, skunk, dragonfly, bee, snail
CATERPILLAR, SKUNK, DRAGONFLY, BEE, SNAIL = 0, 1, 2, 3, 4

# rank -> (name, count in toon deck, fame)
TOON_DEFS = [
    ("Ostrich", 3, 1), ("Eagle", 2, 4), ("Donkey", 2, 1), ("Butterfly", 3, 2),
    ("Dog", 4, 0), ("Goat", 2, 1), ("Sheep", 2, 1), ("Camel", 5, 2),
    ("Rabbit", 4, 3), ("Horse", 2, 4), ("Snake", 2, 1), ("Elephant", 2, 7),
    ("Rooster", 2, 0), ("Cat", 2, 1), ("Alligator", 2, 6), ("Lion", 2, 3),
    ("Monkey", 2, 3), ("Pig", 1, -1), ("Peacock", 2, 5), ("Turkey", 2, 5),
    ("Bull", 1, 3), ("Tiger", 1, 3), ("Deer", 1, 3), ("Bear", 1, 1), ("Cow", 1, 0),
]
TOON_NAMES = [d[0] for d in TOON_DEFS]
TOON_FAME = {i + 1: d[2] for i, d in enumerate(TOON_DEFS)}
COUNTS = {i + 1: d[1] for i, d in enumerate(TOON_DEFS)}
assert sum(COUNTS.values()) == 53

UNFLIPPABLE = {2, 9, 12, 21}      # eagle, rabbit, elephant, bull
UNDISMISSABLE = {14, 22}          # cat, tiger
PRICES = [3, 4, 7, 10, 15]
FAME_TARGET = 30
CRITIC_BONUS = 3
TIE_CAP = 10
DISMISS_COST = 5


def card_name(inst):
    return STARTER_NAMES[inst["s"]] if inst["s"] is not None else TOON_NAMES[inst["r"] - 1]


def base_fame(inst):
    return STARTER_FAME[inst["s"]] if inst["s"] is not None else TOON_FAME[inst["r"]]


def _label(inst):
    return ("?" if inst["fd"] else card_name(inst))


def _mk(g, r, s=None):
    g["iid"] += 1
    return {"id": g["iid"], "r": r, "s": s, "fd": False}


def new_game(chat_id, creator_id, creator_name):
    return {
        "chat_id": int(chat_id), "created_by": int(creator_id),
        "players": [{"user_id": int(creator_id), "name": creator_name,
                     "deck": [], "grid": [], "extra": [], "discarded": [],
                     "fame": 0, "fame_bonus": 0, "bonus_actions": 0,
                     "actions": 0, "last_placed": None, "ostrich_queue": [],
                     "eagle_pending": False, "after_flip": [], "in_flip": False}],
        "phase": "lobby",  # lobby|playing|game_end
        "stage": "flip",   # flip|market|cleanup|final_flip|tie_flip|game_end
        "toon_deck": [], "toon_discard": [], "market": [None] * 5,
        "first": 0, "round": 0, "flip_list": [], "flip_pos": 0,
        "market_idx": 0, "end_triggered": False, "critic_holder": None,
        "stall": 0, "active": [], "tie_players": None, "tie_count": 0, "winner": None,
        "iid": 0, "pending": None, "pending_q": [], "board_message_id": None,
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
    for p in g["players"]:
        p["deck"] = [_mk(g, 0, CATERPILLAR), _mk(g, 0, CATERPILLAR),
                     _mk(g, 0, SKUNK), _mk(g, 0, DRAGONFLY),
                     _mk(g, 0, BEE), _mk(g, 0, SNAIL)]
        p["discarded"] = []
        p["fame"] = p["fame_bonus"] = p["bonus_actions"] = 0
    for r, (_, count, _) in enumerate(TOON_DEFS, 1):
        for _ in range(count):
            g["toon_deck"].append(_mk(g, r))
    random.shuffle(g["toon_deck"])
    g["first"] = random.randrange(n)
    g["round"] = 1
    g["active"] = list(range(n))
    g["flip_list"] = [(g["first"] + k) % n for k in range(n)]
    g["flip_pos"] = 0
    g["stage"] = "flip"
    g["phase"] = "playing"
    cards = [g["toon_deck"].pop() for _ in range(5)]
    cards.sort(key=lambda i: i["r"])
    g["market"] = cards
    events.append(f"🎬 Fliptoons round 1 - {g['players'][g['first']]['name']} is first player!")
    advance(g, events)
    return None


# ---------------------------------------------------------------- grid helpers

def _all_grid_cards(p):
    out = []
    for st in p["grid"]:
        out.extend(st)
    for e in p["extra"]:
        out.extend(e["cards"])
    return out


def _cell_of(p, iid):
    for i, st in enumerate(p["grid"]):
        if any(c["id"] == iid for c in st):
            return ("slot", i)
    for j, e in enumerate(p["extra"]):
        if any(c["id"] == iid for c in e["cards"]):
            return ("extra", j)
    return None


def _stack_at(p, cell):
    kind, i = cell
    return p["grid"][i] if kind == "slot" else p["extra"][i]["cards"]


def _neighbor_cells(p, cell):
    kind, i = cell
    if kind == "extra":
        return [("slot", p["extra"][i]["below"])]
    out = []
    if i % 3:
        out.append(("slot", i - 1))
    if i % 3 < 2:
        out.append(("slot", i + 1))
    if i >= 3:
        out.append(("slot", i - 3))
    else:
        out.append(("slot", i + 3))
    for j, e in enumerate(p["extra"]):
        if e["below"] == i:
            out.append(("extra", j))
    return out


def _reading_cells(p):
    return [("slot", i) for i in range(6)] + \
           [("extra", j) for j in range(len(p["extra"]))]


def _grid_full(p):
    return all(p["grid"])


def _grid_slots(p):
    return [("slot", i) for i in range(6)]


def _rabbit_target(p, skip=None):
    """First cell (reading order) holding a face-up rabbit or any face-down card."""
    for cell in _reading_cells(p):
        if cell == skip:
            continue
        st = _stack_at(p, cell)
        for c in st:
            if c["fd"] or (c["r"] == 9 and not c["fd"]):
                return cell
    return None


def _remove_from_grid(p, inst):
    cell = _cell_of(p, inst["id"])
    if cell:
        st = _stack_at(p, cell)
        st[:] = [c for c in st if c["id"] != inst["id"]]
    return cell


# ------------------------------------------------------------------- dismissal

def _dismiss(g, idx, inst, events, src=""):
    """Remove a card (grid or deck) for player idx; pigs trigger placement."""
    p = g["players"][idx]
    where = _remove_from_grid(p, inst)
    if where is None:
        if inst in p["deck"]:
            p["deck"].remove(inst)
    if inst["r"] == 18:
        _add_pending(g, _pig_pending(g, idx, inst))
        events.append(f"🐷 Pig dismissed - choose a deck for it.")
        return
    p["discarded"].append(inst)
    src = f" ({src})" if src else ""
    events.append(f"🗑 {_label(inst)} dismissed{src}.")


def _add_pending(g, pend):
    if g.get("pending") is None and not g.get("pending_q"):
        g["pending"] = pend
    else:
        g.setdefault("pending_q", []).append(pend)


def _pig_pending(g, idx, inst):
    opts = [{"v": "own", "label": "my deck"}]
    for i, o in enumerate(g["players"]):
        if i != idx:
            opts.append({"v": f"p{i}", "label": f"{o['name']}'s deck"})
    opts.append({"v": "toon", "label": "toon deck"})
    return {"kind": "pig", "player": idx, "card": inst, "options": opts,
            "prompt": "🐷 Pig: place it in which deck?"}


# ------------------------------------------------------------------ flip phase

def _flip_init(g, idx, events):
    p = g["players"][idx]
    random.shuffle(p["deck"])
    p["grid"] = [[] for _ in range(6)]
    p["extra"] = []
    p["last_placed"] = None
    p["ostrich_queue"] = []
    p["eagle_pending"] = False
    p["after_flip"] = []
    p["in_flip"] = True


def _flip_step(g, idx, events):
    """Reveal the next deck card and place it (or stack it on an ostrich)."""
    p = g["players"][idx]
    inst = p["deck"].pop()
    prev_placed = p["last_placed"]
    cell = None
    if p["ostrich_queue"]:
        oid = p["ostrich_queue"].pop(0)
        cell = _cell_of(p, oid)
        _stack_at(p, cell).append(inst)
        events.append(f"🦩 {_label(inst)} stacks on the Ostrich.")
    self_stacked = False
    if cell is None:
        tgt = None
        if inst["r"] == 9:
            tgt = _rabbit_target(p)
        elif inst["r"] == 20 and prev_placed is not None:
            tgt = _cell_of(p, prev_placed)
        if tgt is not None:
            _stack_at(p, tgt).append(inst)
            cell = tgt
            self_stacked = True
            under = _label(_stack_at(p, tgt)[-2])
            events.append(f"{'🐇 Rabbit' if inst['r'] == 9 else '🦃 Turkey'} stacks on {under}.")
    if cell is None:
        slot = next(i for i in range(6) if not p["grid"][i])
        p["grid"][slot].append(inst)
        cell = ("slot", slot)
    p["last_placed"] = inst["id"]
    _resolve_when_placed(g, idx, inst, cell, prev_placed, events,
                         self_stacked=self_stacked)


def _resolve_when_placed(g, idx, inst, cell, prev_placed, events, self_stacked=False):
    p = g["players"][idx]
    r = inst["r"]
    if p["eagle_pending"]:
        p["eagle_pending"] = False
        if r not in UNFLIPPABLE:
            inst["fd"] = True
            events.append(f"🦅 Eagle flips {_label(inst)} face-down (ability skipped).")
            return
    if r == 2 and not _grid_full(p):
        p["eagle_pending"] = True
        events.append("🦅 Eagle: the next placed card will be flipped.")
    elif r == 1 and not _grid_full(p):
        p["ostrich_queue"].append(inst["id"])
        events.append("🦩 Ostrich: the next revealed card stacks on it.")
    elif r == 9 and not self_stacked:
        tgt = _rabbit_target(p, skip=cell)
        if tgt is not None:
            _remove_from_grid(p, inst)
            _stack_at(p, tgt).append(inst)
            events.append(f"🐇 Rabbit re-stacks on {_label(_stack_at(p, tgt)[-2])}.")
    elif r == 20 and not self_stacked and prev_placed is not None:
        tgt = _cell_of(p, prev_placed)
        if tgt is not None and tgt != cell:
            _remove_from_grid(p, inst)
            _stack_at(p, tgt).append(inst)
            events.append(f"🦃 Turkey re-stacks on {_label(_stack_at(p, tgt)[-2])}.")
    elif r == 12 and prev_placed is not None:
        tgt = _cell_of(p, prev_placed)
        if tgt is not None:
            for c in _stack_at(p, tgt):
                if c["id"] == prev_placed:
                    if c["r"] not in UNFLIPPABLE:
                        c["fd"] = True
                        events.append(f"🐘 Elephant flips {_label(c)} face-down.")
                    break
    elif r == 17 and cell[0] == "slot" and cell[1] < 3 and len(_stack_at(p, cell)) == 1:
        p["grid"][cell[1]].pop()
        p["extra"].append({"below": cell[1], "cards": [inst]})
        events.append(f"🐒 Monkey climbs into a new row above (slot {cell[1] + 1} freed).")
    elif r == 11:
        _snake(g, idx, cell, events)


def _snake(g, idx, cell, events):
    p = g["players"][idx]
    top = p["deck"][-1] if p["deck"] else None
    if top is not None:
        if top["r"] in UNDISMISSABLE:
            events.append("🐍 Deck top cannot be dismissed - it stays in the deck.")
        else:
            p["deck"].pop()
            _dismiss(g, idx, top, events, "snake")
    if g["toon_deck"]:
        t = g["toon_deck"].pop()
        _stack_at(p, cell).append(t)
        p["after_flip"].append(t["id"])
        events.append(f"🐍 Snake stacks {_label(t)} from the toon deck.")
    else:
        events.append("🐍 Toon deck empty - nothing to stack.")


def _resolve_after_flip(g, idx, events):
    """When-hired abilities of snake-stacked cards resolve after the flip."""
    p = g["players"][idx]
    while p["after_flip"]:
        iid = p["after_flip"][0]
        inst = next((c for st in p["grid"] for c in st if c["id"] == iid), None)
        if inst is None:  # pig already moved out via pending
            p["after_flip"].pop(0)
            continue
        r = inst["r"]
        if r == 19:
            p["fame_bonus"] += 2
            p["bonus_actions"] += 1
            p["after_flip"].pop(0)
            events.append("🦚 Snake-stacked Peacock: +2 fame and a bonus action.")
        elif r == 4 and any(c["s"] == CATERPILLAR and not c["fd"]
                            for st in p["grid"] for c in st):
            p["after_flip"].pop(0)
            opts = [{"v": str(c["id"]), "label": f"Dismiss {card_name(c)}"}
                    for st in p["grid"] for c in st
                    if c["s"] == CATERPILLAR and not c["fd"]]
            opts.append({"v": "skip", "label": "Skip"})
            _add_pending(g, {"kind": "butterfly", "player": idx, "options": opts,
                             "prompt": "🦋 Butterfly: dismiss a caterpillar for 0?"})
            return
        elif r == 10:
            p["after_flip"].pop(0)
            _add_pending(g, _horse_pending(g, idx))
            events.append("🐴 Snake-stacked Horse: discard any market cards.")
            return
        elif r == 18:
            p["after_flip"].pop(0)
            _remove_from_grid(p, inst)
            _add_pending(g, _pig_pending(g, idx, inst))
            events.append("🐷 Snake-stacked Pig: choose a deck for it.")
            return
        else:
            p["after_flip"].pop(0)


# -------------------------------------------------------------- fame computing

def _face_ups(p):
    """[(inst, cell)] for every face-up card in the player's grid."""
    out = []
    for cell in _reading_cells(p):
        for inst in _stack_at(p, cell):
            if not inst["fd"]:
                out.append((inst, cell))
    return out


def grid_fame(g, p):
    ups = _face_ups(p)
    comp = {}
    for inst, cell in ups:
        if inst["r"] != 25:
            comp[inst["id"]] = _card_fame(g, p, inst, cell, ups, comp)
    for inst, cell in ups:
        if inst["r"] == 25:
            best = 0
            for o, oc in ups:
                if o["id"] == inst["id"] or o["r"] == 25:
                    continue
                if oc in _neighbor_cells(p, cell):
                    best = max(best, comp[o["id"]])
            comp[inst["id"]] = best
    return sum(comp.values())


def _card_fame(g, p, inst, cell, ups, comp):
    r, s = inst["r"], inst["s"]
    if s is not None:
        f = STARTER_FAME[s]
        if s == DRAGONFLY:
            names = {card_name(o) for o, oc in ups
                     if oc in _neighbor_cells(p, cell)}
            f += len(names)
        return f
    if r == 1:
        return 1
    if r == 2:
        return 4
    if r == 3:
        return 1 + (5 if cell[0] == "slot" and cell[1] >= 3 else 0)
    if r == 4:
        return 2
    if r == 5:
        if any(o and o["r"] == 5 for o in g["market"]):
            return 5
        pi = g["players"].index(p)
        for i in g["active"]:
            if i != pi and any(o["r"] == 5 for o, _ in _face_ups(g["players"][i])):
                return 5
        return 0
    if r == 6:
        return 1 + (3 if cell[0] == "slot" and cell[1] < 3 else 0)
    if r == 7:
        return 1 + (4 if cell[0] == "slot" and cell[1] in (1, 4) else 0)
    if r == 8:
        mine = sum(1 for o, _ in ups if o["r"] == 8)
        pi = g["players"].index(p)
        best = sum(1 for o in g["market"] if o and o["r"] == 8)
        for i in g["active"]:
            if i != pi:
                best = max(best, sum(1 for o, _ in _face_ups(g["players"][i])
                                     if o["r"] == 8))
        return 2 + (2 if mine >= best else 0)
    if r in (9, 10, 12):
        return TOON_FAME[r]
    if r == 11:
        return 1
    if r == 13:
        return sum(1 for o, _ in ups if o["r"] <= 13)
    if r == 14:
        return 1 + sum(1 for d in p["discarded"] if d["s"] is not None)
    if r == 15:
        return 6
    if r == 16:
        adj = [o for o, oc in ups if oc in _neighbor_cells(p, cell)]
        return 3 + (4 if all(o["r"] <= 16 for o in adj) else 0)
    if r == 17:
        return 3
    if r == 18:
        return -1
    if r in (19, 20):
        return TOON_FAME[r]
    if r == 21:
        return 3 + (7 if any(c["fd"] for st in p["grid"] for c in st) or
                    any(c["fd"] for e in p["extra"] for c in e["cards"]) else 0)
    if r == 22:
        return 3 + len(p["discarded"])
    if r == 23:
        names = [card_name(o) for o, _ in ups]
        return 3 + (5 if len(set(names)) == len(names) else 0)
    if r == 24:
        return 1 + len(ups)
    return 0


# ------------------------------------------------------------ check fame phase

def _check_fame(g, events):
    for p in g["players"]:
        p["fame"] = grid_fame(g, p)
    vals = {i: g["players"][i]["fame"] for i in g["active"]}
    mx = max(vals.values())
    tops = [i for i, v in vals.items() if v == mx]
    for i in g["active"]:
        events.append(f"⭐ {g['players'][i]['name']}: {vals[i]} fame")
    if mx >= FAME_TARGET:
        g["end_triggered"] = True
        if len(tops) == 1:
            g["critic_holder"] = tops[0]
            events.append(f"🏆 {g['players'][tops[0]]['name']} takes Critic's Choice "
                          f"(+3 at Final Flip)! Final Flip after this round.")
        else:
            g["critic_holder"] = None
            events.append("🏆 Tie for most fame - Critic's Choice is returned. "
                          "Final Flip after this round.")


# ---------------------------------------------------------------- market phase

def _start_market_player(g, events):
    idx = g["market_idx"]
    p = g["players"][idx]
    p["actions"] = 2 + p["bonus_actions"]
    if _skunk_eligible(g, idx):
        opts = []
        for cell in _reading_cells(p):
            for c in _stack_at(p, cell):
                if not c["fd"] and c["r"] not in UNDISMISSABLE:
                    opts.append({"v": str(c["id"]), "label": f"Dismiss {card_name(c)}"})
        _add_pending(g, {"kind": "skunk", "player": idx, "options": opts,
                         "prompt": "🦨 You have the least fame - the Skunk forces a "
                                   "free dismissal (mandatory, no action spent)."})
        events.append(f"🦨 {p['name']} has the least fame - Skunk ability triggers.")


def _skunk_eligible(g, idx):
    p = g["players"][idx]
    if not any(c["s"] == SKUNK and not c["fd"] for c in _all_grid_cards(p)):
        return False
    fame = p["fame"]
    return all(g["players"][i]["fame"] > fame
               for i in g["active"] if i != idx)


def _available(p):
    return p["fame"] + p["fame_bonus"]


def _spend(p, cost):
    take = min(cost, p["fame_bonus"])
    p["fame_bonus"] -= take
    p["fame"] -= cost - take


def do_market(g, idx, act, arg, events):
    """act: 'hire' (arg=slot 0-4), 'dismiss' (arg=card id) or 'skip'."""
    if g["phase"] != "playing" or g["stage"] != "market":
        return "not in the market phase"
    if g.get("pending"):
        return "resolve the pending choice first"
    if idx != g["market_idx"]:
        return "not your market turn"
    p = g["players"][idx]
    if act == "skip":
        events.append(f"⏭ {p['name']} ends the market phase.")
        p["actions"] = 0
        advance(g, events)
        return None
    if p["actions"] <= 0:
        return "no actions left"
    if act == "hire":
        try:
            slot = int(arg)
        except (TypeError, ValueError):
            return "bad slot"
        if not 0 <= slot < 5:
            return "bad slot"
        card = g["market"][slot]
        if card is None:
            return "that market slot is empty"
        cost = PRICES[slot]
        if cost > _available(p):
            return f"not enough fame (costs {cost})"
        _spend(p, cost)
        g["market"][slot] = None
        if card["r"] != 18:      # pig's deck placement is chosen by its pending
            p["deck"].append(card)
        p["actions"] -= 1
        g["stall"] = 0
        events.append(f"🛒 {p['name']} hires {_label(card)} for {cost} fame.")
        r = card["r"]
        if r == 19:
            p["fame_bonus"] += 2
            p["bonus_actions"] += 1
            events.append("🦚 Peacock: +2 fame and a bonus market action.")
        elif r == 4 and any(c["s"] == CATERPILLAR and not c["fd"]
                            for c in _all_grid_cards(p)):
            opts = [{"v": str(c["id"]), "label": f"Dismiss {card_name(c)}"}
                    for c in _all_grid_cards(p)
                    if c["s"] == CATERPILLAR and not c["fd"]]
            opts.append({"v": "skip", "label": "Skip"})
            _add_pending(g, {"kind": "butterfly", "player": idx, "options": opts,
                             "prompt": "🦋 Butterfly: dismiss a caterpillar for 0?"})
        elif r == 10:
            _add_pending(g, _horse_pending(g, idx))
        elif r == 18:
            _add_pending(g, _pig_pending(g, idx, card))
        if g.get("pending"):
            return None
        if p["actions"] <= 0:
            advance(g, events)
        return None
    if act == "dismiss":
        try:
            iid = int(arg)
        except (TypeError, ValueError):
            return "bad card"
        cell = _cell_of(p, iid)
        if cell is None:
            return "no such card in your grid"
        inst = next(c for c in _stack_at(p, cell) if c["id"] == iid)
        if inst["fd"]:
            return "cannot dismiss a face-down card"
        if inst["r"] in UNDISMISSABLE:
            return "this card cannot be dismissed"
        total = len(p["deck"]) + len(_all_grid_cards(p))
        if total < 4:
            return "cannot dismiss with fewer than 4 cards in deck+grid"
        cost = 3 if inst["s"] == CATERPILLAR else DISMISS_COST
        if cost > _available(p):
            return f"not enough fame (costs {cost})"
        _spend(p, cost)
        p["actions"] -= 1
        _dismiss(g, idx, inst, events, f"{cost} fame")
        if g.get("pending"):
            return None
        if p["actions"] <= 0:
            advance(g, events)
        return None
    return "unknown action"


def _horse_pending(g, idx):
    return {"kind": "horse", "player": idx, "n": 0,
            "options": _horse_options(g), "prompt": "🐴 Horse: discard any number "
            "of market cards (they refill with new reveals)."}
def _horse_options(g):
    opts = [{"v": str(i), "label": f"Discard {_label(c)} ({PRICES[i]} fame)"}
            for i, c in enumerate(g["market"]) if c]
    opts.append({"v": "done", "label": "Done"})
    return opts


def _end_of_market_dismissals(g, idx, events):
    p = g["players"][idx]
    for cell in _grid_slots(p):
        st = _stack_at(p, cell)
        if any(c["r"] == 15 and not c["fd"] for c in st):
            right = ("slot", cell[1] + 1) if cell[1] % 3 < 2 else None
            tgt = None
            if right is not None:
                for c in reversed(_stack_at(p, right)):
                    if not c["fd"] and c["r"] not in UNDISMISSABLE:
                        tgt = c
                        break
            if tgt is not None:
                events.append("🐊 Alligator dismisses the card to its right.")
                _dismiss(g, idx, tgt, events, "alligator")
    for cell in _grid_slots(p):
        st = _stack_at(p, cell)
        for c in list(st):
            if c["r"] == 3 and not c["fd"]:
                events.append("🫏 Donkey dismisses itself (it earned its +5).")
                _dismiss(g, idx, c, events, "donkey")


def _finish_market_player(g, events):
    idx = g["market_idx"]
    p = g["players"][idx]
    _end_of_market_dismissals(g, idx, events)
    p["fame"] = p["fame_bonus"] = p["bonus_actions"] = 0
    p["actions"] = 0
    _refill_market(g, events)
    if len(g["players"]) == 2 and idx == 1:
        cards = [c for c in g["market"] if c]
        if cards:
            gone = [cards[0]] if len(cards) == 1 else [cards[0], cards[-1]]
            for c in gone:
                g["toon_discard"].append(c)
                g["market"][g["market"].index(c)] = None
            events.append("🃏 2-player: leftmost and rightmost market cards discarded.")
            _refill_market(g, events)
    g["market_idx"] += 1


def _refill_market(g, events):
    cards = [c for c in g["market"] if c]
    if g["toon_deck"]:
        need = 5 - len(cards)
        take = min(need, len(g["toon_deck"]))
        cards += [g["toon_deck"].pop() for _ in range(take)]
        cards.sort(key=lambda i: i["r"])
        if len(cards) == 5:
            g["market"] = cards
        else:
            g["market"] = [None] * (5 - len(cards)) + cards
    else:
        cards.sort(key=lambda i: i["r"])
        g["market"] = [None] * (5 - len(cards)) + cards
    if not g["toon_deck"] and not any(g["market"]) and not g["end_triggered"]:
        g["end_triggered"] = True
        events.append("📼 Toon deck and market are empty - Final Flip after this round.")


def _horse_refill(g, n, events):
    cards = [c for c in g["market"] if c]
    take = min(n, len(g["toon_deck"]))
    cards += [g["toon_deck"].pop() for _ in range(take)]
    cards.sort(key=lambda i: i["r"])
    if len(cards) == 5 or not g["toon_deck"]:
        g["market"] = [None] * (5 - len(cards)) + cards
    else:
        slots = [None] * 5
        pos = 0
        for c in cards:
            while pos < 5 and slots[pos] is not None:
                pos += 1
            slots[pos] = c
        g["market"] = slots
    events.append(f"🐴 Horse refill: {take} new card(s) revealed.")


# -------------------------------------------------------------------- cleanup

def _cleanup(g, events):
    for p in g["players"]:
        p["deck"].extend(_all_grid_cards(p))
        p["grid"] = [[] for _ in range(6)]
        p["extra"] = []
        p["last_placed"] = None
        p["ostrich_queue"] = []
        p["eagle_pending"] = False
        p["after_flip"] = []
        p["in_flip"] = False
    n = len(g["players"])
    if g["end_triggered"]:
        g["stage"] = "final_flip"
        g["active"] = list(range(n))
        g["flip_list"] = list(range(n))
        g["flip_pos"] = 0
        events.append("🎬 FINAL FLIP!")
    else:
        if not g["toon_deck"]:
            g["stall"] += 1
            if g["stall"] >= 8:
                g["end_triggered"] = True
                events.append("📼 The toon deck is empty and nobody can buy "
                              "anything - Final Flip triggered.")
        else:
            g["stall"] = 0
        g["first"] = (g["first"] + 1) % n
        g["round"] += 1
        g["stage"] = "flip"
        g["active"] = list(range(n))
        g["flip_list"] = [(g["first"] + k) % n for k in range(n)]
        g["flip_pos"] = 0
        events.append(f"🎬 Round {g['round']} - {g['players'][g['first']]['name']} is first player.")


# ------------------------------------------------------------ phase transitions

def _end_flip_phase(g, events):
    for p in g["players"]:
        p["in_flip"] = False
    if g["stage"] == "flip":
        _check_fame(g, events)
        g["stage"] = "market"
        g["market_idx"] = g["first"]
        _start_market_player(g, events)
    elif g["stage"] == "final_flip":
        _final_check(g, events)
    else:
        _tie_check(g, events)


def _flip_phase_step(g, events):
    if g["flip_pos"] >= len(g["flip_list"]):
        _end_flip_phase(g, events)
        return
    idx = g["flip_list"][g["flip_pos"]]
    p = g["players"][idx]
    if not p["in_flip"]:
        _flip_init(g, idx, events)
    while p["deck"] and not _grid_full(p):
        _flip_step(g, idx, events)
        if g.get("pending"):
            return
    if p["after_flip"]:
        _resolve_after_flip(g, idx, events)
        if g.get("pending"):
            return  # in_flip stays True; resume resolves the rest
    p["in_flip"] = False
    g["flip_pos"] += 1
    name = g["players"][idx]["name"]
    events.append(f"🎭 {name} placed {len(_all_grid_cards(p))} card(s).")


def _final_check(g, events):
    _decide_winner(g, events, final=True)


def _tie_check(g, events):
    _decide_winner(g, events, final=False)


def _decide_winner(g, events, final):
    for i in g["active"]:
        p = g["players"][i]
        p["fame"] = grid_fame(g, p)
    if g["critic_holder"] in g["active"]:
        g["players"][g["critic_holder"]]["fame"] += CRITIC_BONUS
    vals = {i: g["players"][i]["fame"] for i in g["active"]}
    mx = max(vals.values())
    tops = [i for i, v in vals.items() if v == mx]
    for i in g["active"]:
        events.append(f"⭐ {g['players'][i]['name']}: {vals[i]} fame")
    if len(tops) == 1:
        g["winner"] = tops[0]
        g["phase"] = "game_end"
        g["stage"] = "game_end"
        events.append(f"🏆 {g['players'][tops[0]]['name']} wins the Final Flip "
                      f"with {mx} fame!")
        return
    g["tie_players"] = tops
    g["tie_count"] += 1
    if g["tie_count"] >= TIE_CAP:
        g["winner"] = None
        g["phase"] = "game_end"
        g["stage"] = "game_end"
        events.append("🤝 Still tied after 10 flips - it's a draw!")
        return
    for i in tops:
        p = g["players"][i]
        p["deck"].extend(_all_grid_cards(p))
        p["grid"] = [[] for _ in range(6)]
        p["extra"] = []
        p["in_flip"] = False
    g["active"] = tops
    g["stage"] = "tie_flip"
    g["flip_list"] = list(tops)
    g["flip_pos"] = 0
    events.append("🤝 Tie for most fame - tied players flip again!")


# ----------------------------------------------------------------- main driver

def advance(g, events):
    """Auto-resolve until a player input is needed or the game ends."""
    guard = 0
    while guard < 10000:
        guard += 1
        if g["phase"] != "playing":
            return False
        if g.get("pending"):
            return True
        st = g["stage"]
        if st in ("flip", "final_flip", "tie_flip"):
            _flip_phase_step(g, events)
            continue
        if st == "market":
            if g["market_idx"] >= len(g["players"]):
                g["stage"] = "cleanup"
                continue
            p = g["players"][g["market_idx"]]
            if p["actions"] <= 0:
                _finish_market_player(g, events)
                continue
            return True
        if st == "cleanup":
            _cleanup(g, events)
            continue
        return False
    return False


# ------------------------------------------------------------ pending handling

def apply_choice(g, idx, choice, events):
    """Resolve the current pending. Returns an error string or None."""
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
    if kind == "skunk":
        g["pending"] = None
        iid = int(choice)
        cell = _cell_of(g["players"][idx], iid)
        inst = next(c for c in _stack_at(g["players"][idx], cell) if c["id"] == iid)
        _dismiss(g, idx, inst, events, "skunk")
    elif kind == "butterfly":
        g["pending"] = None
        if choice != "skip":
            inst = next(c for c in _all_grid_cards(g["players"][idx])
                        if c["id"] == int(choice))
            _dismiss(g, idx, inst, events, "butterfly")
    elif kind == "pig":
        g["pending"] = None
        inst = pend["card"]
        if choice == "own":
            g["players"][idx]["deck"].append(inst)
            events.append("🐷 Pig placed on top of your deck.")
        elif choice == "toon":
            g["toon_deck"].append(inst)
            random.shuffle(g["toon_deck"])
            events.append("🐷 Pig shuffled back into the toon deck.")
        else:
            i = int(choice[1:])
            g["players"][i]["deck"].append(inst)
            events.append(f"🐷 Pig placed on top of {g['players'][i]['name']}'s deck.")
    elif kind == "horse":
        if choice == "done":
            g["pending"] = None
            _horse_refill(g, pend["n"], events)
        else:
            slot = int(choice)
            card = g["market"][slot]
            if card is None:
                return "that market slot is empty"
            g["market"][slot] = None
            g["toon_discard"].append(card)
            pend["n"] += 1
            pend["options"] = _horse_options(g)
            events.append(f"🐴 {card_name(card)} discarded from the market.")
            return None
    else:
        return "unknown pending"
    q = g.get("pending_q") or []
    if q:
        g["pending"] = q.pop(0)
        return None
    g["pending"] = None
    advance(g, events)
    return None
