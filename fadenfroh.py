"""Fadenfroh engine - pure logic, no Telegram, no I/O (stdlib only).

Five rounds of market drafting, stitching three overlapping rows and scoring
against four rotating goal cards.  Rules and the full scoring-card table were
checked against the official 1 More Time Games rulebook
(sources/fadenfroh/rulebook.pdf) and the Board Game Arena client, release
261119-1515.  Card art is the BGA sprite sheet in sources/fadenfroh/bga/.
"""
import html
import random

MIN_PLAYERS = 2
MAX_PLAYERS = 4
ROUNDS = 5
COLORS = ("white", "yellow", "purple")
COLOR_CODE = {"W": "white", "Y": "yellow", "P": "purple"}
BERRIES = ("blueberry", "strawberry")
ANIMALS = ("bunny", "cat", "squirrel")
FLOWERS = ("daisy", "thistle", "crocus", "dandelion")
REGULAR = BERRIES + ANIMALS + FLOWERS
SYMBOLS = REGULAR + ("feather", "hoop")

SYMBOL_NAMES = {
    "blueberry": "blueberry", "strawberry": "strawberry",
    "bunny": "bunny", "cat": "cat", "squirrel": "squirrel",
    "daisy": "daisy", "thistle": "thistle", "crocus": "crocus",
    "dandelion": "dandelion", "feather": "feather circle", "hoop": "embroidery hoop",
}
SYMBOL_ICONS = {
    "blueberry": "🫐", "strawberry": "🍓", "bunny": "🐰", "cat": "🐈", "squirrel": "🐿️",
    "daisy": "🌼", "thistle": "🌾", "crocus": "🌸", "dandelion": "🌻",
    "feather": "🪶", "hoop": "🪡",
}
COLOR_ICONS = {"white": "⚪", "yellow": "🟡", "purple": "🟣"}

# Background colour of each half of the 81 BGA fabric-card sheet cells,
# row-major order from fabric-cards.jpg (9 columns x 9 rows).
COLOR_GRID = (
    "WP", "PY", "YW", "WW", "WY", "YW", "PW", "PY", "YP",
    "PP", "YP", "PY", "PY", "PP", "PP", "YP", "YP", "PY",
    "PP", "WP", "PW", "PP", "WP", "PP", "PP", "WP", "PW",
    "PP", "YW", "WP", "PY", "YW", "PW", "WY", "YW", "PW",
    "PY", "PP", "PY", "YP", "PY", "YY", "YP", "PY", "PP",
    "PP", "PP", "PP", "WP", "PW", "PP", "PP", "PW", "PP",
    "WY", "YP", "WP", "PW", "WW", "PY", "PY", "PW", "PP",
    "PP", "PP", "WY", "PP", "WY", "WP", "PP", "PW", "YY",
    "WP", "YY", "WP", "YP", "WP", "YP", "YP", "PP", "WW",
)

SCORING_CARDS = {
    1: ("Berries", "2 VP per blueberry, -1 VP per strawberry (never below 0)."),
    2: ("Berries", "4 VP per strawberry + blueberry pair."),
    3: ("Berries", "Odd blueberries: 2 VP each. Even strawberries: 2 VP each."),
    4: ("Berries", "6 VP per group of 3+ strawberries; 9 VP per group of 4+ blueberries."),
    5: ("Animals", "3 VP per animal with no adjacent animal."),
    6: ("Animals", "2 VP per animal, +1 VP per animal if all three animal counts differ."),
    7: ("Animals", "4 VP per animal of the most common type, -1 VP per animal of the other types."),
    8: ("Animals", "1 VP per animal, +6 VP per bunny-cat-squirrel trio."),
    9: ("Flowers", "Per row: 2/3/4 different flowers score 4/9/15 VP."),
    10: ("Flowers", "Per column, one flower type: 1/2/3 alike score 2/7/12 VP."),
    11: ("Flowers", "5/11/18 VP per group of 2/3/4+ equal flowers."),
    12: ("Flowers", "Flowers on the six row ends: 2/3/4/5/6 score 4/8/13/18/24 VP."),
    13: ("Colours", "2 VP per half in your largest same-colour group."),
    14: ("Colours", "5 VP per group of 4+ halves of the same colour."),
    15: ("Colours", "1 VP per half with no adjacent half of the same colour; +3 at 12, +7 more at 16."),
    16: ("Colours", "2 VP per purple half in its largest group, -2 VP per white half in its largest group (min 0)."),
}

ROUND_CARDS = {2: ("A", "B"), 3: ("B", "C"), 4: ("C", "D"), 5: ("D", "A")}
ROUND_PAIRS = (("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"))

RULES = """🪡 <b>Fadenfroh rules</b> (2-4 players, five rounds): draft fabric and materials, stitch three overlapping rows, score the rotating goals.
• <b>Market:</b> each round the market has one offer per player (1-3 cards), threads, needles and the thimble. On your turn take one material (thread / needle / thimble) or pass and take an offer; taking an offer ends your shopping. If everyone else has passed, you get all remaining material and must take the last offer.
• <b>Embroidery:</b> trade 3 threads for a draw of 3 cards and keep 1, repeatedly. Then place every card in one of your three rows: it must cover at least one half of an already placed card. Spend a needle to place a card next to a row without covering anything. Discard what you do not place.
• <b>Scoring:</b> rounds 2-5 score goal pairs A+B, B+C, C+D, D+A; every scored round also gives 2 VP per visible feather circle. Only visible halves and symbols count. Groups use orthogonal adjacency and ignore needles.
• <b>Round 5:</b> also choose goal B or C, score 2 VP per remaining material, and score each embroidery hoop (VP per matching symbol shown on the hoop). Ties are broken by the higher starting-card number.
• Commands: /fadenfroh_material &lt;thread|needle|thimble&gt;, /fadenfroh_pass &lt;offer&gt;, /fadenfroh_keep &lt;n&gt;, /fadenfroh_place &lt;card&gt; &lt;row&gt; &lt;side&gt; &lt;cover&gt; [needle], /fadenfroh_discard &lt;cards&gt;, /fadenfroh_bonus &lt;B|C&gt; (or use buttons/Mini App)."""


def _build_cards():
    """Deterministic 81-card deck matching the BGA sheet's half colours."""
    regular = [s for s in REGULAR for _ in range(22)]
    rng = random.Random(2762)
    rng.shuffle(regular)
    special = {5: (0, "feather"), 23: (1, "feather"),
               41: (0, "hoop"), 62: (1, "hoop")}
    out = []
    pos = 0
    for i, pair in enumerate(COLOR_GRID):
        halves = []
        for h, code in enumerate(pair):
            color = COLOR_CODE[code]
            syms = []
            if i in special and special[i][0] == h:
                kind = special[i][1]
                syms.append(kind)
                if kind == "hoop":
                    syms.append(REGULAR[(i + 3) % len(REGULAR)])
            else:
                count = (i + h * 2) % 3
                for _ in range(count):
                    syms.append(regular[pos % len(regular)])
                    pos += 1
            halves.append({"c": color, "s": syms})
        out.append({"id": i, "h": halves})
    return out


CARDS = _build_cards()


def name_of(g, user_id):
    return next((p["name"] for p in g["players"] if p["user_id"] == user_id), "player")


def new_player(user_id, name):
    return {"user_id": int(user_id), "name": name, "threads": 1, "needles": 1,
            "thimble": False, "supply": [], "rows": [], "score": 0,
            "start_no": 0, "passed": False, "bonus": None}


# Starting-card sheet (starting-cards.jpg): 4 columns (starting numbers
# 1-4) x 3 rows (white, yellow, purple). art = [column, sheet row].
_START_SHEET_ROW = {"white": 0, "yellow": 1, "purple": 2}


def _start_rows(player, start_no):
    player["start_no"] = start_no
    player["rows"] = []
    for row, color in enumerate(("yellow", "white", "purple")):
        a = {"id": f"s{row}", "h": 0, "c": color, "s": [], "start": True,
             "art": [start_no - 1, _START_SHEET_ROW[color]], "start_no": start_no}
        b = dict(a, h=1)
        player["rows"].append({"3": a, "4": b})


def new_game(chat_id, creator_id, creator_name, rng=None):
    g = {"chat_id": int(chat_id), "created_by": int(creator_id),
         "players": [new_player(creator_id, creator_name)],
         "phase": "lobby", "round": 0, "turn": 0, "current": 0,
         "market": {}, "deck": [], "discard": [], "goals": {},
         "active": [], "pass_order": [], "embroidery_order": [], "embroidery_pos": 0,
         "pending": None, "winner": None, "log": [], "board_message_id": None,
         "chat_type": "private"}
    return g


def _rng(g):
    return g.get("_rng") or random


def draw(g):
    if not g["deck"]:
        if not g["discard"]:
            return None
        g["deck"] = list(g["discard"])
        g["discard"] = []
        _rng(g).shuffle(g["deck"])
    return g["deck"].pop()


def discard(g, card_id):
    g["discard"].append(card_id)


def start_game(g, events=None, rng=None, scoring="random"):
    if g["phase"] != "lobby":
        return "game already started"
    n = len(g["players"])
    if not MIN_PLAYERS <= n <= MAX_PLAYERS:
        return f"Fadenfroh needs {MIN_PLAYERS}-{MAX_PLAYERS} players"
    ev = events if events is not None else []
    rnd = rng or _rng(g)
    g["deck"] = list(range(len(CARDS)))
    rnd.shuffle(g["deck"])
    g["discard"] = []
    g["round"] = 1
    g["turn"] = 1
    g["winner"] = None
    g["log"] = []
    if scoring == "beginner":
        g["goals"] = {k: v for k, v in zip("ABCD", (13, 2, 8, 9))}
    else:
        goals = [rnd.choice([n for n in SCORING_CARDS if SCORING_CARDS[n][0] == cat])
                 for cat in ("Berries", "Animals", "Flowers", "Colours")]
        rnd.shuffle(goals)
        g["goals"] = dict(zip("ABCD", goals))
    for i, p in enumerate(g["players"]):
        p["score"] = 0
        p["bonus"] = None
        _start_rows(p, i + 1)
    ev.append(f"🪡 Fadenfroh started! Goals: " + ", ".join(
        f"{k}={v}" for k, v in sorted(g["goals"].items())))
    _market_phase(g, ev, rnd)
    return None


def _market_phase(g, events, rnd=None):
    rnd = rnd or _rng(g)
    n = len(g["players"])
    threads = {2: 4, 3: 7, 4: 10}[n]
    needles = {2: 1, 3: 2, 4: 2}[n]
    offers = []
    sizes = {2: (3, 2), 3: (3, 2, 1), 4: (3, 2, 2, 1)}[n]
    for size in sizes:
        cards = []
        for _ in range(size):
            card = draw(g)
            if card is None:
                break
            cards.append(card)
        if cards:
            offers.append(cards)
    g["market"] = {"threads": threads, "needles": needles, "thimble": True,
                   "offers": offers}
    for p in g["players"]:
        p["passed"] = False
    starter = next((i for i, p in enumerate(g["players"]) if p["thimble"]), 0)
    g["current"] = starter
    g["players"][starter]["thimble"] = False
    g["market"]["thimble"] = True
    g["active"] = [i for i in range(n)]
    g["pass_order"] = []
    g["phase"] = "shopping"
    events.append(f"🛒 Round {g['round']} market: {threads} threads, {needles} needles, "
                  f"thimble, {len(offers)} offers. {g['players'][starter]['name']} starts.")
    _shopping_auto(g, events)


def _shopping_auto(g, events):
    """Last active player gets the leftover material, then must take an offer."""
    m = g["market"]
    if len(g["active"]) == 1 and m["offers"]:
        idx = g["active"][0]
        p = g["players"][idx]
        got = []
        for kind in ("threads", "needles"):
            if m[kind]:
                n = m[kind]
                p[kind] += n
                got.append(f"{n} {kind}")
                m[kind] = 0
        if m.get("thimble"):
            p["thimble"] = True
            m["thimble"] = False
            got.append("thimble")
        if got:
            events.append(f"🎁 {p['name']} takes the remaining material: {', '.join(got)}.")
    g["current"] = g["active"][0] if g["active"] else 0


def _advance_shopping(g, events):
    if not g["active"] or (not g["market"]["offers"] and not _material_left(g["market"])):
        if g["active"]:
            events.append("🛒 The market is empty - embroidery begins.")
        g["phase"] = "embroidery"
        g["embroidery_order"] = list(g["pass_order"])
        g["embroidery_pos"] = 0
        events.append("🧵 Shopping is over - embroidery begins.")
        _embroidery_auto(g, events)
        return
    g["turn"] += 1
    _shopping_auto(g, events)


def _material_left(m):
    return bool(m["threads"] or m["needles"] or m.get("thimble"))


def take_material(g, idx, kind, events=None):
    if g["phase"] != "shopping" or idx != g["current"] or idx not in g["active"]:
        return "not your turn in the market"
    if len(g["active"]) == 1:
        return "you must take the last offer now"
    m = g["market"]
    key = {"thread": "threads", "needle": "needles", "thimble": "thimble"}.get(kind)
    if not key:
        return "take thread, needle or thimble"
    if key == "thimble":
        if not m["thimble"]:
            return "the thimble is not in the market"
        m["thimble"] = False
        g["players"][idx]["thimble"] = True
    else:
        if not m[key]:
            return "none left in the market"
        m[key] -= 1
        g["players"][idx][key] += 1
    ev = events if events is not None else []
    ev.append(f"🧶 {g['players'][idx]['name']} took a {kind}.")
    g["active"].append(g["active"].pop(0))
    _advance_shopping(g, ev)
    return None


def pass_offer(g, idx, offer, events=None):
    if g["phase"] != "shopping" or idx != g["current"] or idx not in g["active"]:
        return "not your turn in the market"
    m = g["market"]
    try:
        offer = int(offer)
    except (TypeError, ValueError):
        return "bad offer"
    if not 0 <= offer < len(m["offers"]):
        return "that offer is not available"
    cards = m["offers"].pop(offer)
    g["players"][idx]["supply"].extend(cards)
    g["players"][idx]["passed"] = True
    g["active"].remove(idx)
    g["pass_order"].append(idx)
    ev = events if events is not None else []
    ev.append(f"🙋 {g['players'][idx]['name']} took an offer of {len(cards)} card(s) and is stitching.")
    _advance_shopping(g, ev)
    return None


def _embroidery_auto(g, events):
    """Advance automatic thread exchanges / finished players."""
    while g["embroidery_pos"] < len(g["embroidery_order"]):
        idx = g["embroidery_order"][g["embroidery_pos"]]
        p = g["players"][idx]
        if p["threads"] >= 3:
            p["threads"] -= 3
            drawn = [c for c in (draw(g) for _ in range(3)) if c is not None]
            g["pending"] = {"kind": "keep", "by": idx, "cards": drawn}
            events.append(f"🧶 {p['name']} traded 3 threads: choose 1 of {len(drawn)} cards.")
            return
        g["pending"] = {"kind": "place", "by": idx, "cards": list(p["supply"])}
        p["supply"] = []
        if not g["pending"]["cards"]:
            events.append(f"🧵 {p['name']} has nothing to stitch.")
            g["pending"] = None
            g["embroidery_pos"] += 1
            continue
        return
    g["phase"] = "scoring"
    g["pending"] = None
    _score_round(g, events)


def pending_options(g, idx):
    pend = g.get("pending")
    if not pend or pend.get("by") != idx:
        return []
    if pend["kind"] == "keep":
        return [{"value": str(i), "label": f"Keep card {i + 1}"}
                for i in range(len(pend["cards"]))]
    if pend["kind"] == "place":
        out = []
        for i, cid in enumerate(pend["cards"]):
            for row in range(3):
                for option in placement_options(g, idx, cid, row):
                    side, cover, needle = option
                    out.append({"value": f"{i}:{row}:{side}:{cover}:{int(needle)}",
                                "label": f"{card_label(cid)} → row {row + 1} "
                                         f"{'L' if side == 'left' else 'R'} "
                                         f"{'2' if cover == 2 else '1'}"
                                         f"{' +needle' if needle else ''}",
                                "card": cid, "row": row})
        return out
    if pend["kind"] == "bonus":
        return [{"value": "B", "label": "Score goal B"},
                {"value": "C", "label": "Score goal C"}]
    return []


def apply_choice(g, idx, value, events=None):
    pend = g.get("pending")
    if not pend or pend.get("by") != idx:
        return "no choice pending for you"
    ev = events if events is not None else []
    if pend["kind"] == "keep":
        try:
            n = int(value)
        except (TypeError, ValueError):
            return "bad card number"
        if not 0 <= n < len(pend["cards"]):
            return "bad card number"
        cid = pend["cards"][n]
        g["players"][idx]["supply"].append(cid)
        for other in pend["cards"]:
            if other != cid:
                discard(g, other)
        ev.append(f"🪡 {g['players'][idx]['name']} kept {card_label(cid)}.")
        g["pending"] = None
        _embroidery_auto(g, ev)
        return None
    if pend["kind"] == "place":
        parts = str(value).split(":")
        if len(parts) != 5:
            return "bad placement"
        try:
            ci, row, side, cover = int(parts[0]), int(parts[1]), parts[2], int(parts[3])
            needle = parts[4] == "1"
        except ValueError:
            return "bad placement"
        if not 0 <= ci < len(pend["cards"]):
            return "bad card"
        cid = pend["cards"][ci]
        err = place_card(g, idx, cid, row, side, cover, needle, ev)
        if err:
            return err
        pend["cards"].pop(ci)
        if not pend["cards"]:
            g["pending"] = None
            g["embroidery_pos"] += 1
            _embroidery_auto(g, ev)
        return None
    if pend["kind"] == "bonus":
        if str(value).upper() not in ("B", "C"):
            return "choose B or C"
        g["players"][idx]["bonus"] = str(value).upper()
        ev.append(f"🎯 {g['players'][idx]['name']} scores goal {g['players'][idx]['bonus']}.")
        g["pending"] = None
        _bonus_auto(g, ev)
        return None
    return "unknown choice"


def _placement_targets(slots, side, cover, needle):
    cols = sorted(int(c) for c in slots)
    lo, hi = cols[0], cols[-1]
    if needle:
        gap = lo - 1 if side == "left" else hi + 1
        start = gap - 2 if side == "left" else gap + 1
    elif cover == 1:
        start = lo - 1 if side == "left" else hi
    else:
        start = lo if side == "left" else hi - 1
    return start, (start, start + 1), (None if not needle else gap)


def placement_options(g, idx, card_id, row, needle_ok=True):
    p = g["players"][idx]
    if not 0 <= row < 3 or g["phase"] != "embroidery":
        return []
    slots = p["rows"][row]
    if not slots:
        return []
    out = []
    for side in ("left", "right"):
        for cover in (1, 2):
            out.append((side, cover, False))
        if needle_ok and p["needles"] > 0:
            out.append((side, 0, True))
    return [o for o in out if _placement_valid(g, idx, card_id, row, *o)[0] is None]


def _placement_valid(g, idx, card_id, row, side, cover, needle):
    p = g["players"][idx]
    slots = p["rows"][row]
    _, targets, gap = _placement_targets(slots, side, cover, needle)
    if needle:
        if p["needles"] <= 0:
            return "no needle available", None
        if gap in slots or any(c in slots for c in targets):
            return "that space is occupied", None
        return None, (gap, targets)
    if any(slots.get(str(c), {}).get("needle") for c in targets):
        return "a needle blocks that space", None
    covered = [c for c in targets if str(c) in slots and not slots[str(c)].get("needle")]
    if not covered:
        return "a card must cover at least one placed half", None
    if cover == 2 and len(covered) < 2:
        return "this does not cover two halves", None
    return None, targets


def place_card(g, idx, card_id, row, side, cover, needle=False, events=None):
    pend = g.get("pending")
    if g["phase"] != "embroidery" or not pend or pend.get("by") != idx or pend["kind"] != "place":
        return "not your embroidery turn"
    if card_id not in pend["cards"] or side not in ("left", "right"):
        return "bad placement"
    if needle:
        cover = 0
    elif cover not in (1, 2):
        return "bad placement"
    err, targets = _placement_valid(g, idx, card_id, row, side, cover, needle)
    if err:
        return err
    p = g["players"][idx]
    slots = p["rows"][row]
    if needle:
        gap, targets = targets
        slots[str(gap)] = {"needle": True, "c": None, "s": []}
        p["needles"] -= 1
    card = CARDS[card_id]
    for h, col in enumerate(targets):
        half = dict(card["h"][h], id=card_id, h=h)
        slots[str(col)] = half
    ev = events if events is not None else []
    ev.append(f"🪡 {p['name']} stitched {card_label(card_id)} into row {row + 1}.")
    return None


def discard_supply(g, idx, card_ids, events=None):
    pend = g.get("pending")
    if not pend or pend.get("by") != idx or pend["kind"] != "place":
        return "not your embroidery turn"
    ev = events if events is not None else []
    for cid in card_ids:
        if cid in pend["cards"]:
            pend["cards"].remove(cid)
            discard(g, cid)
            ev.append(f"🗑 {g['players'][idx]['name']} discarded {card_label(cid)}.")
    if not pend["cards"]:
        g["pending"] = None
        g["embroidery_pos"] += 1
        _embroidery_auto(g, ev)
    return None


def _visible_halves(p):
    """Return rows of (column, half) for visible halves; needles are skipped."""
    rows = []
    for row in p["rows"]:
        out = []
        for col in sorted(row, key=int):
            half = row[col]
            if not half.get("needle"):
                out.append((int(col), half))
        rows.append(out)
    return rows


def _grid(p):
    return {(ri, col): half for ri, row in enumerate(_visible_halves(p))
            for col, half in row}


def _neighbours(grid, ri, col):
    for r, c in ((ri - 1, col), (ri + 1, col), (ri, col - 1), (ri, col + 1)):
        if (r, c) in grid:
            yield (r, c)


def _match_groups(grid, attr, value=None):
    def matches(h):
        return h["c"] == value if attr == "color" else value in h["s"]

    seen = set()
    groups = []
    for key, half in grid.items():
        if key in seen or not matches(half):
            continue
        stack = [key]
        seen.add(key)
        group = []
        while stack:
            k = stack.pop()
            group.append(grid[k])
            for nk in _neighbours(grid, *k):
                if nk not in seen and matches(grid[nk]):
                    seen.add(nk)
                    stack.append(nk)
        groups.append(group)
    return groups


def _counts(halves, symbols):
    c = {s: 0 for s in symbols}
    for half in halves:
        for s in half["s"]:
            if s in c:
                c[s] += 1
    return c


def _score_card(n, p):
    grid = _grid(p)
    halves = list(grid.values())
    berries = _counts(halves, BERRIES)
    animals = _counts(halves, ANIMALS)
    if n == 1:
        return max(0, 2 * berries["blueberry"] - berries["strawberry"])
    if n == 2:
        return 4 * min(berries.values())
    if n == 3:
        b = berries["blueberry"]
        s = berries["strawberry"]
        return (2 * b if b % 2 else 0) + (2 * s if s % 2 == 0 else 0)
    if n == 4:
        return (6 * len([g for g in _match_groups(grid, "symbol", "strawberry") if len(g) >= 3]) +
                9 * len([g for g in _match_groups(grid, "symbol", "blueberry") if len(g) >= 4]))
    if n == 5:
        total = 0
        for key, half in grid.items():
            for s in half["s"]:
                if s in ANIMALS and not any(a in grid[nk]["s"]
                                            for nk in _neighbours(grid, *key)
                                            for a in ANIMALS):
                    total += 3
        return total
    if n == 6:
        total = sum(animals.values())
        return 2 * total + (total if len(set(animals.values())) == 3 else 0)
    if n == 7:
        vals = list(animals.values())
        m = max(vals)
        return 4 * m - (sum(vals) - m)
    if n == 8:
        return sum(animals.values()) + 6 * min(animals.values())
    if n == 9:
        total = 0
        for row in _visible_halves(p):
            kinds = {s for _, h in row for s in h["s"] if s in FLOWERS}
            total += {2: 4, 3: 9, 4: 15}.get(len(kinds), 0)
        return total
    if n == 10:
        cols = sorted({c for _, c in grid})
        total = 0
        for col in cols:
            best = 0
            for flower in FLOWERS:
                cnt = sum(1 for (ri, c), h in grid.items()
                          if c == col and flower in h["s"])
                best = max(best, {1: 2, 2: 7, 3: 12}.get(cnt, 0))
            total += best
        return total
    if n == 11:
        total = 0
        for flower in FLOWERS:
            for group in _match_groups(grid, "symbol", flower):
                size = len(group)
                if size >= 4:
                    total += 18
                elif size == 3:
                    total += 11
                elif size == 2:
                    total += 5
        return total
    if n == 12:
        ends = []
        for row in _visible_halves(p):
            if row:
                ends.append(row[0][1])
                if len(row) > 1:
                    ends.append(row[-1][1])
        n_flowers = sum(1 for h in ends if any(s in FLOWERS for s in h["s"]))
        return {2: 4, 3: 8, 4: 13, 5: 18, 6: 24}.get(n_flowers, 0)
    if n == 13:
        groups = [g for color in COLORS for g in _match_groups(grid, "color", color)]
        return 2 * max((len(g) for g in groups), default=0)
    if n == 14:
        return 5 * sum(1 for color in COLORS for g in _match_groups(grid, "color", color)
                       if len(g) >= 4)
    if n == 15:
        total = 0
        for key, half in grid.items():
            if not any(grid[nk]["c"] == half["c"] for nk in _neighbours(grid, *key)):
                total += 1
        if total >= 12:
            total += 3
        if total >= 16:
            total += 7
        return total
    if n == 16:
        purple = max((len(g) for g in _match_groups(grid, "color", "purple")), default=0)
        white = max((len(g) for g in _match_groups(grid, "color", "white")), default=0)
        return max(0, 2 * purple - 2 * white)
    return 0


def score_details(p, card_no):
    return _score_card(card_no, p)


def _score_round(g, events):
    rnd = g["round"]
    if rnd == 1:
        events.append("📝 Round 1 has no scoring.")
        _next_round(g, events)
        return
    pairs = ROUND_PAIRS[rnd - 2]
    for i, p in enumerate(g["players"]):
        total = sum(_score_card(g["goals"][letter], p) for letter in pairs)
        feathers = sum(1 for h in _grid(p).values() if "feather" in h["s"])
        total += 2 * feathers
        p["score"] += total
        events.append(f"🎯 {p['name']} scored {total} ({pairs[0]}+{pairs[1]}, "
                      f"{feathers} feather{'s' if feathers != 1 else ''}).")
    if rnd == ROUNDS:
        g["phase"] = "bonus"
        g["pending"] = next(({"kind": "bonus", "by": i} for i, p in enumerate(g["players"])
                             if p["bonus"] is None), None)
        if g["pending"] is None:
            _bonus_auto(g, events)
        else:
            events.append("🎯 Final round: choose goal B or C (or tap a button).")
    else:
        _next_round(g, events)


def _bonus_auto(g, events):
    pend = next(({"kind": "bonus", "by": i} for i, p in enumerate(g["players"])
                 if p["bonus"] is None), None)
    if pend:
        g["phase"] = "bonus"
        g["pending"] = pend
        return
    for i, p in enumerate(g["players"]):
        extra = _score_card(g["goals"][p["bonus"]], p)
        material = p["threads"] + p["needles"] + (1 if p["thimble"] else 0)
        extra += 2 * material
        grid = _grid(p)
        hoop_pts = 0
        for half in grid.values():
            if "hoop" in half["s"]:
                for s in half["s"]:
                    if s in REGULAR:
                        hoop_pts += 2 * sum(1 for h in grid.values() if s in h["s"])
        extra += hoop_pts
        p["score"] += extra
        events.append(f"🏁 {p['name']} scored {extra} final bonus (B/C, {material} material, "
                      f"{hoop_pts} hoop points).")
    best = max(p["score"] for p in g["players"])
    tied = [i for i, p in enumerate(g["players"]) if p["score"] == best]
    g["winner"] = max(tied, key=lambda i: g["players"][i]["start_no"]) if len(tied) > 1 else tied[0]
    g["phase"] = "game_end"
    g["pending"] = None
    events.append(f"🏆 {g['players'][g['winner']]['name']} wins with {best} VP!")


def _next_round(g, events):
    g["round"] += 1
    g["turn"] += 1
    _market_phase(g, events)


def current_index(g):
    if g["phase"] in ("shopping", "embroidery"):
        pend = g.get("pending")
        if pend and g["phase"] == "embroidery":
            return pend["by"]
        if g["phase"] == "embroidery" and g["embroidery_pos"] < len(g["embroidery_order"]):
            return g["embroidery_order"][g["embroidery_pos"]]
        return g["current"] if g["phase"] == "shopping" else None
    if g["phase"] == "bonus" and g.get("pending"):
        return g["pending"]["by"]
    return None


def card_name(cid):
    card = CARDS[int(cid)]
    return " / ".join(COLOR_ICONS[h["c"]] + " " +
                      (", ".join(SYMBOL_ICONS[s] for s in h["s"]) or "—")
                      for h in card["h"])


def card_label(cid):
    return f"#{int(cid) + 1} {card_name(cid)}"


def board_lines(g):
    if g["phase"] == "lobby":
        yield f"🪡 Fadenfroh lobby: {len(g['players'])}/{MAX_PLAYERS} players."
        for p in g["players"]:
            yield f"• {p['name']}"
        return
    yield f"🪡 Fadenfroh - round {g['round']}/5 · phase: {g['phase']}"
    yield "🎯 Goals: " + " ".join(f"{k}={g['goals'][k]}" for k in "ABCD")
    m = g["market"]
    yield (f"🛒 Market: 🧵{m['threads']} 🪡{m['needles']} "
           f"{'🟘' if m.get('thimble') else ''} · offers: " +
           (" ".join(f"[{i}] {len(c)} cards" for i, c in enumerate(m["offers"])) or "none"))
    for i, p in enumerate(g["players"]):
        rows = []
        for row in _visible_halves(p):
            rows.append(" ".join(f"{h['c'][0]}{''.join(SYMBOL_ICONS[s] for s in h['s'])}"
                                 for _, h in row))
        yield (f"{'▶' if current_index(g) == i else '·'} <b>{html.escape(p['name'])}</b> "
               f"{p['score']} VP · 🧵{p['threads']} 🪡{p['needles']} "
               f"{'🟘' if p['thimble'] else ''} · cards: {len(p['supply'])}")
        yield "   " + (" | ".join(rows) if rows else "empty")
    if g.get("log"):
        yield "📜 " + " · ".join(html.escape(e) for e in g["log"][-3:])


def board_json(g, viewer_id=None):
    """Public board with private hands filtered to the viewer."""
    out = {"chat_id": g["chat_id"], "phase": g["phase"], "round": g["round"],
           "turn": g["turn"], "actor": current_index(g), "goals": dict(g["goals"]),
           "market": {"threads": g["market"].get("threads", 0),
                      "needles": g["market"].get("needles", 0),
                      "thimble": bool(g["market"].get("thimble")),
                      "offers": [list(c) for c in g["market"].get("offers", [])]},
           "log": list(g["log"][-12:]), "winner": g["winner"],
           "players": [], "options": [], "pending": None}
    pend = g.get("pending")
    if pend:
        out["pending"] = {"kind": pend["kind"], "by": pend["by"]}
        if viewer_id is None or viewer_id == g["players"][pend["by"]]["user_id"]:
            out["pending"]["cards"] = list(pend["cards"])
        out["options"] = pending_options(g, pend["by"])
    for i, p in enumerate(g["players"]):
        show = viewer_id is None or p["user_id"] == viewer_id
        out["players"].append({
            "user_id": p["user_id"], "name": p["name"], "score": p["score"],
            "threads": p["threads"], "needles": p["needles"], "thimble": p["thimble"],
            "start_no": p["start_no"], "supply_count": len(p["supply"]),
            "supply": list(p["supply"]) if show else [],
            "rows": [[{"col": int(c), **h} for c, h in sorted(row.items(), key=lambda kv: int(kv[0]))]
                     for row in p["rows"]],
            "bonus": p["bonus"], "passed": p["passed"],
        })
    out["cards"] = {str(c["id"]): {"name": card_name(c["id"]),
                                   "colors": [h["c"] for h in c["h"]],
                                   "symbols": [list(h["s"]) for h in c["h"]]}
                    for c in CARDS}
    out["scoring"] = {str(k): {"category": SCORING_CARDS[k][0], "text": SCORING_CARDS[k][1]}
                      for k in SCORING_CARDS}
    out["symbols"] = {"icons": SYMBOL_ICONS, "colors": COLOR_ICONS}
    return out
